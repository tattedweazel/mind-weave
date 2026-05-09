#!/usr/bin/env python3
"""
Live HTTP check: Upsert Document persists **body** correctly (not only **name**).

Exercises the same API as the browser (`POST /workflow-definitions/`, `POST …/run`,
`GET /documents/{id}`). Two graphs:

1. Slim **Save text** rows: String primitive → **Upsert** with **target_handle** ``name``
   (mis-save pattern from older canvas defaults) plus inline Explorer title — executor
   should recover wired text into ``content``.
2. **Explicit** ``target_handle: content`` sanity check.
3. **Alias** ``target_handle: output`` (maps to ``content``, same as ``text`` / ``body`` / ``markdown``).

No LLM / STT / external network.

For **Workflow Editor parity** against **sync POST `/run`** (same **`GET`** definition row as the SPA; **Build** uses **`POST …/runs`** + **`GET …/events`** instead),
use **`run_persisted_workflow_stream_http_e2e.py`** with **`--workflow-id`** owned by your login user.

Example::

  cd backend && uv run python scripts/run_upsert_document_http_e2e.py
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import os
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

from app.core.security import get_password_hash  # noqa: E402
from app.main import app  # noqa: E402
from app.persistence.db import engine  # noqa: E402
from app.persistence.tables import User  # noqa: E402

E2E_USERNAME = "upsert_document_http_e2e"
E2E_PASSWORD = "UpsertDocumentE2E12"
_BODY_MARKER = "upsert-http-e2e-body-" + "x" * 40


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _ensure_user() -> None:
    with Session(engine) as session:
        u = session.exec(select(User).where(User.username == E2E_USERNAME)).first()
        if u is None:
            session.add(User(username=E2E_USERNAME, password_hash=get_password_hash(E2E_PASSWORD), is_admin=False))
            session.commit()


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
    thread = threading.Thread(target=server.run, name="upsert-doc-http-e2e-uvicorn", daemon=True)
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


async def _login(client: httpx.AsyncClient) -> None:
    r = await client.post("/api/v1/auth/login", data={"username": E2E_USERNAME, "password": E2E_PASSWORD})
    r.raise_for_status()


def _upsert_nodes(*, upsert_id: str, doc_title: str, target_handle: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    src = "n_body_src"
    return (
        [
            {
                "id": src,
                "kind": "primitive",
                "primitive_type": "string",
                "label": "Body",
                "data": {"text": _BODY_MARKER},
                "position": {"x": 0, "y": 0},
            },
            {
                "id": upsert_id,
                "kind": "utility",
                "utility_type": "upsert_document",
                "label": "Upsert Document",
                "data": {
                    "required_inputs": [
                        {"key": "name", "type": "string", "value": doc_title},
                        {"key": "content", "type": "string", "value": ""},
                    ],
                },
                "position": {"x": 240, "y": 0},
            },
        ],
        [{"source": src, "target": upsert_id, "target_handle": target_handle}],
    )


async def _run_once(client: httpx.AsyncClient, *, wf_name: str, upsert_id: str, doc_title: str, target_handle: str) -> None:
    nodes, edges = _upsert_nodes(upsert_id=upsert_id, doc_title=doc_title, target_handle=target_handle)
    wf = await client.post(
        "/api/v1/workflow-definitions/",
        json={"name": wf_name, "graph": {"nodes": nodes, "edges": edges}},
    )
    wf.raise_for_status()
    wf_id = str(wf.json()["id"])
    run = await client.post(f"/api/v1/workflow-definitions/{wf_id}/run", json={})
    run.raise_for_status()
    body = run.json()
    if body.get("status") != "ok":
        raise RuntimeError(f"run failed: {body}")
    step = next((r for r in (body.get("node_results") or []) if r.get("node_id") == upsert_id), None)
    if step is None or step.get("status") != "ok":
        raise RuntimeError(f"missing upsert step ok: {body}")
    markdown = ((step.get("output") or {}).get("markdown") or "").strip()
    if markdown != _BODY_MARKER:
        raise RuntimeError(f"step output.markdown mismatch ({target_handle=!r}): {markdown!r}")
    doc_id = (step.get("output") or {}).get("document_id")
    if not doc_id:
        raise RuntimeError(f"no document_id in step: {step}")
    g = await client.get(f"/api/v1/documents/{doc_id}")
    g.raise_for_status()
    row = g.json()
    if row.get("name") != doc_title:
        raise RuntimeError(f"document row name mismatch: {row!r}")
    if (row.get("body") or "").strip() != _BODY_MARKER:
        raise RuntimeError(f"document row body mismatch ({target_handle=!r}): {row!r}")


async def _main(port: int) -> int:
    _ensure_user()
    async with httpx.AsyncClient(base_url=f"http://127.0.0.1:{port}", timeout=30.0) as client:
        await _login(client)
        suffix = uuid.uuid4().hex[:8]
        await _run_once(
            client,
            wf_name=f"upsert_e2e_miswired_name_{suffix}",
            upsert_id="n_up_bad",
            doc_title=f"e2e_title_{suffix}",
            target_handle="name",
        )
        await _run_once(
            client,
            wf_name=f"upsert_e2e_explicit_content_{suffix}",
            upsert_id="n_up_ok",
            doc_title=f"e2e_title_b_{suffix}",
            target_handle="content",
        )
        await _run_once(
            client,
            wf_name=f"upsert_e2e_alias_output_{suffix}",
            upsert_id="n_up_alias",
            doc_title=f"e2e_title_c_{suffix}",
            target_handle="output",
        )
    print(
        f"ok — upsert document HTTP e2e passed (miswired name + explicit content + alias output); "
        f"body_len={len(_BODY_MARKER)}",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="HTTP e2e: Upsert Document name + persisted body.")
    p.add_argument("--port", type=int, default=0, help="Uvicorn port (default: free)")
    args = p.parse_args()
    port = args.port or _free_port()
    with _run_server(port):
        return asyncio.run(_main(port))


if __name__ == "__main__":
    raise SystemExit(main())
