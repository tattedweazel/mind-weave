#!/usr/bin/env python3
"""
Browser-faithful HTTP check: run a **persisted** workflow by id via **run_stream**.

Unlike ``run_upsert_document_http_e2e.py`` (synthetic ``POST /workflow-definitions/`` + ``POST /run``),
this script:

1. Logs in (cookie jar, same as the SPA)
2. **GET** ``/api/v1/workflow-definitions/{id}`` — same JSON the Workflow Editor loaded from the DB
3. **POST** ``/api/v1/workflow-definitions/{id}/run_stream`` — same entry point as
   ``ApiClient.runWorkflowStream`` in the SPA
4. Consumes NDJSON until ``event: end`` (or ``error``)

Optional **``--assert-upsert-body-non-empty``** finds ``upsert_document`` steps (or ``--upsert-node-id``)
and fails if document output ``markdown`` is blank; on failure, prints edges targeting that node from
the GET graph (compare with ``analyze_workflow_definition.py --summarize``).

Use the **owning user's** credentials; otherwise GET/run_stream return 404.

Examples::

  cd backend && uv run python scripts/run_persisted_workflow_stream_http_e2e.py \\
    --workflow-id f2df2602-ba7a-4bad-b1cd-af0d69509766 \\
    --username you --password '...' \\
    --assert-upsert-body-non-empty

  # Against an already-running API (no embedded uvicorn)::
  cd backend && uv run python scripts/run_persisted_workflow_stream_http_e2e.py \\
    --base-url http://127.0.0.1:8000 \\
    --workflow-id <uuid> --username you --password '...'
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import os
import re
import socket
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
os.chdir(_BACKEND_ROOT)

import httpx  # noqa: E402
import uvicorn  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.security import get_password_hash  # noqa: E402
from app.main import app  # noqa: E402
from app.persistence.db import engine  # noqa: E402
from app.persistence.tables import User  # noqa: E402

DEFAULT_E2E_USERNAME = "persisted_workflow_stream_e2e"
DEFAULT_E2E_PASSWORD = "PersistedWfStreamE2E12"


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _normalize_uuid(s: str) -> uuid.UUID:
    t = s.strip()
    if re.fullmatch(r"[0-9a-fA-F]{32}", t):
        t = f"{t[:8]}-{t[8:12]}-{t[12:16]}-{t[16:20]}-{t[20:]}"
    return uuid.UUID(t)


@contextlib.contextmanager
def _run_server(port: int):
    config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
        access_log=False,
        lifespan="on",
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, name="persisted-wf-stream-http-e2e-uvicorn", daemon=True)
    thread.start()
    deadline = time.monotonic() + 10
    while not server.started and thread.is_alive() and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        raise RuntimeError("uvicorn did not start within 10 seconds")
    try:
        yield
    finally:
        server.should_exit = True
        thread.join(timeout=10)


def _ensure_user(*, username: str, password: str) -> None:
    """Create login user when missing (embedded uvicorn only — same pattern as other HTTP e2e scripts)."""
    with Session(engine) as session:
        u = session.exec(select(User).where(User.username == username)).first()
        if u is None:
            session.add(
                User(username=username, password_hash=get_password_hash(password), is_admin=False),
            )
            session.commit()


def _upsert_node_ids(graph: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for n in graph.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        if n.get("kind") == "utility" and n.get("utility_type") == "upsert_document":
            nid = n.get("id")
            if isinstance(nid, str) and nid:
                out.append(nid)
    return out


def _ri_snapshot(data: dict[str, Any] | None) -> tuple[str, str]:
    """Short debug strings for upsert name/content inline values."""
    data = data or {}
    req = data.get("required_inputs") or []
    name_s = ""
    content_s = ""
    if isinstance(req, list):
        for item in req:
            if not isinstance(item, dict):
                continue
            k = item.get("key")
            v = item.get("value")
            if k == "name":
                name_s = "" if v is None else str(v)[:80]
            if k == "content":
                content_s = "" if v is None else str(v)[:80]
    return name_s, content_s


def _print_edges_into_upsert(graph: dict[str, Any], upsert_id: str) -> None:
    print(f"\nEdges targeting upsert node {upsert_id!r} (from GET graph):", file=sys.stderr)
    for i, e in enumerate(graph.get("edges") or []):
        if not isinstance(e, dict):
            continue
        if e.get("target") != upsert_id:
            continue
        print(
            f"  [{i}] source={e.get('source')!r} target={e.get('target')!r} "
            f"source_handle={e.get('source_handle')!r} target_handle={e.get('target_handle')!r}",
            file=sys.stderr,
        )


async def _login(client: httpx.AsyncClient, username: str, password: str) -> None:
    r = await client.post("/api/v1/auth/login", data={"username": username, "password": password})
    r.raise_for_status()


async def _consume_run_stream(
    client: httpx.AsyncClient,
    workflow_id: str,
    body: dict[str, Any],
    *,
    stream_timeout: float,
) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """
    POST run_stream; return (end_event_result_dict, node_id -> raw node_end result payload).
    """
    node_ends: dict[str, dict[str, Any]] = {}
    end_payload: dict[str, Any] = {}
    timeout = httpx.Timeout(connect=15.0, read=stream_timeout, write=60.0, pool=15.0)
    async with client.stream(
        "POST",
        f"/api/v1/workflow-definitions/{workflow_id}/run_stream",
        json=body,
        timeout=timeout,
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line.strip():
                continue
            ev = json.loads(line)
            kind = ev.get("event")
            if kind == "node_end":
                nid = ev.get("node_id")
                if isinstance(nid, str):
                    node_ends[nid] = dict(ev.get("result") or {})
            elif kind == "end":
                end_payload = dict(ev.get("result") or {})
            elif kind == "error":
                raise RuntimeError(f"run_stream error event: {ev}")
            elif kind == "input_required":
                raise RuntimeError(
                    "run_stream stalled on input_required (this workflow expects browser upload "
                    f"or other interactive input): {json.dumps(ev)[:800]}"
                )
    if not end_payload:
        raise RuntimeError("run_stream closed without an 'end' event (timeout or proxy drop?)")
    return end_payload, node_ends


async def _run(
    *,
    base_url: str,
    workflow_id: str,
    username: str,
    password: str,
    stream_timeout: float,
    body: dict[str, Any],
    assert_upsert_body: bool,
    upsert_node_id: str | None,
) -> int:
    client_timeout = httpx.Timeout(connect=15.0, read=min(stream_timeout + 60.0, 3600.0), write=60.0, pool=15.0)
    async with httpx.AsyncClient(base_url=base_url, timeout=client_timeout) as client:
        await _login(client, username, password)
        get_wf = await client.get(f"/api/v1/workflow-definitions/{workflow_id}")
        get_wf.raise_for_status()
        wf_blob = get_wf.json()
        name = wf_blob.get("name", "")
        gid = wf_blob.get("id", workflow_id)
        print(f"Loaded workflow {gid!r} name={name!r} (GET /workflow-definitions)", file=sys.stderr)

        end_result, node_ends = await _consume_run_stream(
            client, workflow_id, body, stream_timeout=stream_timeout
        )
        status = end_result.get("status")
        print(f"run_stream finished: overall status={status!r}", file=sys.stderr)
        if status not in ("ok", "partial"):
            print(json.dumps(end_result, indent=2)[:4000], file=sys.stderr)
            return 1

        if not assert_upsert_body:
            return 0

        graph = wf_blob.get("graph") if isinstance(wf_blob.get("graph"), dict) else {}
        upsert_ids = [upsert_node_id] if upsert_node_id else _upsert_node_ids(graph)
        if not upsert_ids:
            print("No upsert_document nodes in graph (--assert-upsert-body-non-empty ignored).", file=sys.stderr)
            return 0

        failures: list[str] = []
        for uid in upsert_ids:
            res = node_ends.get(uid)
            if not res:
                failures.append(f"{uid}: no node_end in stream")
                _print_edges_into_upsert(graph, uid)
                continue
            if res.get("status") != "ok":
                failures.append(f"{uid}: step status={res.get('status')!r} error={res.get('error')!r}")
                _print_edges_into_upsert(graph, uid)
                continue
            out = res.get("output") or {}
            if out.get("kind") != "document":
                failures.append(f"{uid}: output.kind={out.get('kind')!r} (expected document)")
                _print_edges_into_upsert(graph, uid)
                continue
            md = str(out.get("markdown") or "").strip()
            if not md:
                failures.append(f"{uid}: output.markdown empty")
                raw_node = next(
                    (x for x in (graph.get("nodes") or []) if isinstance(x, dict) and x.get("id") == uid),
                    {},
                )
                ns, cs = _ri_snapshot(raw_node if isinstance(raw_node, dict) else {})
                print(
                    f"  Explorer snapshot: name[:80]={ns!r} content[:80]={cs!r}",
                    file=sys.stderr,
                )
                _print_edges_into_upsert(graph, uid)
                did = out.get("document_id")
                if did:
                    dr = await client.get(f"/api/v1/documents/{did}")
                    if dr.is_success:
                        row = dr.json()
                        print(
                            f"  GET /documents/{did}: body_len={len((row.get('body') or ''))} "
                            f"name={row.get('name')!r}",
                            file=sys.stderr,
                        )
            else:
                did = out.get("document_id")
                if did:
                    dr = await client.get(f"/api/v1/documents/{did}")
                    dr.raise_for_status()
                    api_body = (dr.json().get("body") or "").strip()
                    if api_body != md.strip():
                        failures.append(f"{uid}: stream markdown != GET /documents body")

        if failures:
            for f in failures:
                print(f"ASSERT_FAIL: {f}", file=sys.stderr)
            return 2
        print("ok — upsert document body non-empty (stream + optional GET parity)", file=sys.stderr)
        return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="HTTP e2e: GET persisted workflow, POST run_stream (Workflow Editor parity).",
    )
    p.add_argument("--workflow-id", required=True, help="WorkflowDefinition UUID (owner must match --username).")
    p.add_argument("--username", default=DEFAULT_E2E_USERNAME, help="Login user (must own the workflow).")
    p.add_argument("--password", default=DEFAULT_E2E_PASSWORD, help="Login password.")
    p.add_argument(
        "--base-url",
        default="",
        help="If set (e.g. http://127.0.0.1:8000), skip embedded uvicorn and call this API.",
    )
    p.add_argument("--port", type=int, default=0, help="Embedded uvicorn port (default: free port).")
    p.add_argument(
        "--stream-timeout",
        type=float,
        default=600.0,
        help="Seconds to wait for full run_stream body (default 600).",
    )
    p.add_argument(
        "--input-overrides-json",
        default="",
        help='Optional JSON object for request body input_overrides, e.g. \'{"user_input":"x"}\'',
    )
    p.add_argument(
        "--output-overrides-json",
        default="",
        help="Optional JSON object for request body output_overrides (same as WorkflowRunRequest).",
    )
    p.add_argument("--execution-time-zone", default="", help="Optional IANA zone for body.execution_time_zone.")
    p.add_argument(
        "--assert-upsert-body-non-empty",
        action="store_true",
        help="After stream, require upsert_document steps to have non-empty document markdown / DB body.",
    )
    p.add_argument(
        "--upsert-node-id",
        default="",
        help="When asserting, only this node id (otherwise all upsert_document nodes).",
    )
    args = p.parse_args()

    wf_id = str(_normalize_uuid(args.workflow_id))
    body: dict[str, Any] = {}
    if args.input_overrides_json.strip():
        body["input_overrides"] = json.loads(args.input_overrides_json)
    if args.output_overrides_json.strip():
        body["output_overrides"] = json.loads(args.output_overrides_json)
    if args.execution_time_zone.strip():
        body["execution_time_zone"] = args.execution_time_zone.strip()

    upsert_nid = args.upsert_node_id.strip() or None

    async def _go(url: str) -> int:
        try:
            return await _run(
                base_url=url,
                workflow_id=wf_id,
                username=args.username,
                password=args.password,
                stream_timeout=args.stream_timeout,
                body=body,
                assert_upsert_body=args.assert_upsert_body_non_empty,
                upsert_node_id=upsert_nid,
            )
        except httpx.HTTPStatusError as exc:
            print(f"HTTP {exc.response.status_code}: {exc.request.url!r}", file=sys.stderr)
            try:
                print(exc.response.text[:3000], file=sys.stderr)
            except Exception:
                pass
            return 4
        except Exception as exc:
            print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
            return 5

    if not args.base_url.strip():
        _ensure_user(username=args.username, password=args.password)

    print(
        f"run_persisted_workflow_stream_http_e2e: cwd={os.getcwd()!r} DATABASE_URL={settings.DATABASE_URL!r}",
        file=sys.stderr,
    )

    if args.base_url.strip():
        base = args.base_url.strip().rstrip("/")
        return asyncio.run(_go(base))

    port = args.port or _free_port()
    with _run_server(port):
        return asyncio.run(_go(f"http://127.0.0.1:{port}"))


if __name__ == "__main__":
    raise SystemExit(main())
