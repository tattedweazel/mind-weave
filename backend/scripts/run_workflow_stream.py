#!/usr/bin/env python3
"""
Stream a workflow run to stdout as NDJSON — the same line-oriented events as
``POST /api/v1/workflow-definitions/{id}/run_stream``.

Runs ``WorkflowExecutor.run_stream`` in-process against ``DATABASE_URL`` (no HTTP,
no JWT). Uses the **same** LM Studio settings and DB file as the API: the script
changes the process cwd to ``backend/`` before importing ``app`` so ``.env`` and
``sqlite:///./mindweave.db`` resolve like ``uvicorn`` started from ``backend/``.

**LLM calls** go through the same ``httpx`` code path as ``POST .../run_stream``.
If LM Studio shows no requests, check the stderr line printed at startup
(``LMSTUDIO_BASE_URL``) matches your running API and that this process can reach
that host (firewall, VPN, or remote agent vs local machine).

Usage::

  cd backend && uv run python scripts/run_workflow_stream.py \\
    --workflow-id d51622c0-8781-4e7e-8f2a-f52f77bdde98 \\
    --input-json '{"input_overrides": {"user_input": "test"}}'

Optional JSON body fields (same as the API): ``input_overrides``, ``output_overrides``,
``execution_time_zone``.

Optional flags:
  --user-id — executor user (defaults to the workflow's ``user_id``, else the first row in ``users``).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

# --- Match API process: cwd must be backend/ before loading Settings + SQLite URL. ---
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
os.chdir(_BACKEND_ROOT)

from sqlmodel import Session, select

from app.core.config import settings
from app.domain.workflow_executor.executor import WorkflowExecutor
from app.persistence.db import engine
from app.persistence.tables import User, WorkflowDefinition


def _normalize_uuid(s: str) -> uuid.UUID:
    t = s.strip()
    if re.fullmatch(r"[0-9a-fA-F]{32}", t):
        t = f"{t[:8]}-{t[8:12]}-{t[12:16]}-{t[16:20]}-{t[20:]}"
    return uuid.UUID(t)


def _resolve_user_id(session: Session, wf: WorkflowDefinition, override: uuid.UUID | None) -> uuid.UUID:
    if override is not None:
        return override
    if wf.user_id is not None:
        return wf.user_id
    u = session.exec(select(User).limit(1)).first()
    if u is None:
        raise SystemExit(
            "Workflow has no user_id and the database has no users; pass --user-id explicitly.",
        )
    return u.id


async def _run_async(
    wf_id: uuid.UUID,
    body: dict[str, Any],
    user_override: uuid.UUID | None,
) -> int:
    from app.domain.workflow_output_overrides import validate_and_build_output_overrides

    with Session(engine) as session:
        wf = session.get(WorkflowDefinition, wf_id)
        if wf is None:
            print(f"WorkflowDefinition not found: {wf_id}", file=sys.stderr)
            return 1

        user_id = _resolve_user_id(session, wf, user_override)

        input_overrides = body.get("input_overrides")
        output_overrides = body.get("output_overrides")
        etz = body.get("execution_time_zone")

        om: dict[str, Any] | None = None
        if isinstance(output_overrides, dict) and output_overrides:
            try:
                om = validate_and_build_output_overrides(session, user_id, wf.graph, output_overrides)
            except ValueError as e:
                print(f"output_overrides: {e}", file=sys.stderr)
                return 2

        executor = WorkflowExecutor(session, user_id)
        async for line in executor.run_stream(
            wf,
            input_overrides=input_overrides if isinstance(input_overrides, dict) else None,
            output_overrides_map=om,
            execution_time_zone=etz if isinstance(etz, str) else None,
        ):
            sys.stdout.write(line if line.endswith("\n") else line + "\n")
            sys.stdout.flush()

    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="Run workflow run_stream (NDJSON to stdout).")
    p.add_argument("--workflow-id", required=True, help="WorkflowDefinition UUID.")
    p.add_argument(
        "--user-id",
        default=None,
        help="User id for executor (default: workflow owner, else first user).",
    )
    p.add_argument(
        "--input-json",
        default="{}",
        help='JSON object with optional input_overrides, output_overrides, execution_time_zone (default "{}").',
    )
    args = p.parse_args()

    print(
        "run_workflow_stream: "
        f"cwd={os.getcwd()!r} "
        f"LMSTUDIO_BASE_URL={settings.LMSTUDIO_BASE_URL!r} "
        f"DATABASE_URL={settings.DATABASE_URL!r}",
        file=sys.stderr,
    )

    wf_uuid = _normalize_uuid(args.workflow_id)
    uid: uuid.UUID | None = _normalize_uuid(args.user_id) if args.user_id else None

    try:
        body = json.loads(args.input_json)
    except json.JSONDecodeError as e:
        print(f"Invalid --input-json: {e}", file=sys.stderr)
        return 2
    if not isinstance(body, dict):
        print("--input-json must be a JSON object.", file=sys.stderr)
        return 2

    return asyncio.run(_run_async(wf_uuid, body, uid))


if __name__ == "__main__":
    raise SystemExit(main())
