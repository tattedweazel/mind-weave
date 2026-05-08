#!/usr/bin/env python3
"""
Insert a **temporary** workflow (fetch_url → dictionary value by key ``body`` → html_parse_basic →
stop), run it once against **https://books.toscrape.com/** with a **real HTTP** request, and print
the **html_parse_basic** dictionary (title, `text_blocks` as `{tag, text}` list, links).

This is the same executor path as **POST …/run_stream** / ``scripts/run_workflow_stream.py``, but
does not require you to hand-build the graph in the UI. Use it to inspect **`text_blocks`** (tag + text per block) on
real pages (see **docs/OPERATIONS.md** in the repo: *Offline script (books.toscrape sample)*).

``chdir`` to ``backend/`` before imports so ``DATABASE_URL`` and ``.env`` match **uvicorn**.

Requires network. No LLM calls.

Example::

  cd backend && uv run python scripts/run_books_toscrape_fetch_parse_sample.py

After a run, reuse the printed **workflow id** with::

  uv run python scripts/run_workflow_stream.py --workflow-id <uuid>

The workflow row is left in the database so you can open it in the editor. Pass **--cleanup** to
delete the created **user and workflow** after the run.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
os.chdir(_BACKEND_ROOT)

from sqlmodel import Session

from app.domain.workflow_executor.executor import WorkflowExecutor
from app.persistence.db import engine
from app.persistence.tables import User, WorkflowDefinition


def _books_toscrape_graph() -> dict:
    return {
        "nodes": [
            {"id": "n_start", "kind": "start", "label": "Start", "data": {}, "position": {}},
            {
                "id": "n_fetch",
                "kind": "skill",
                "skill_type": "fetch_url",
                "label": "Fetch",
                "data": {
                    "url": "https://books.toscrape.com/",
                    "method": "GET",
                    "headers": {},
                    "cache_policy": "bypass",
                    "required_inputs": [{"key": "url", "type": "string", "value": None}],
                },
                "position": {"x": 0, "y": 0},
            },
            {
                "id": "n_body",
                "kind": "utility",
                "utility_type": "dictionary_value_by_key",
                "label": "Body",
                "data": {
                    "output_value_type": "string",
                    "required_inputs": [
                        {"key": "key", "type": "string", "value": "body"},
                        {"key": "dictionary", "type": "dictionary", "value": None},
                        {"key": "fallback", "type": "any", "value": None},
                    ],
                },
                "position": {"x": 200, "y": 0},
            },
            {
                "id": "n_parse",
                "kind": "utility",
                "utility_type": "html_parse_basic",
                "label": "HTML Parse Basic",
                "data": {"required_inputs": [{"key": "html", "type": "string", "value": None}]},
                "position": {"x": 400, "y": 0},
            },
            {
                "id": "n_stop",
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                "position": {"x": 600, "y": 0},
            },
        ],
        "edges": [
            {"source": "n_start", "target": "n_fetch"},
            {
                "source": "n_fetch",
                "target": "n_body",
                "source_handle": "output",
                "target_handle": "dictionary",
            },
            {
                "source": "n_fetch",
                "target": "n_body",
                "source_handle": "signal_out",
                "target_handle": "trigger",
            },
            {
                "source": "n_body",
                "target": "n_parse",
                "source_handle": "output",
                "target_handle": "html",
            },
            {
                "source": "n_body",
                "target": "n_parse",
                "source_handle": "signal_out",
                "target_handle": "trigger",
            },
            {
                "source": "n_parse",
                "target": "n_stop",
                "source_handle": "output",
                "target_handle": "output",
            },
        ],
    }


async def _run(*, cleanup: bool) -> int:
    graph = _books_toscrape_graph()
    uid = uuid.uuid4()
    wf_id = uuid.uuid4()
    user = User(
        id=uid,
        username=f"books_sample_{uid.hex[:8]}",
        password_hash="books_sample",
        is_admin=False,
    )
    wf_row = WorkflowDefinition(
        id=wf_id,
        user_id=uid,
        name="Sample: books.toscrape.com fetch + html_parse_basic",
        graph=graph,
    )
    with Session(engine) as session:
        session.add(user)
        session.add(wf_row)
        session.commit()
        wf = session.get(WorkflowDefinition, wf_id)
        assert wf is not None
        ex = WorkflowExecutor(session, uid)
        result = await ex.run(wf)
        if cleanup:
            session.delete(wf)
            session.delete(user)
            session.commit()

    print(f"Run status: {result.status}", file=sys.stderr)
    print(f"Workflow id (for run_workflow_stream.py): {wf_id}", file=sys.stderr)
    for nr in result.node_results:
        if nr.node_id == "n_parse" and nr.status == "ok" and nr.output is not None:
            data = getattr(nr.output, "data", None)
            if isinstance(data, dict):
                blocks = data.get("text_blocks") or []
                block_chars = sum(
                    len(b["text"]) for b in blocks if isinstance(b, dict) and "text" in b
                )
                print(
                    f"text_blocks count: {len(blocks)}; total chars in block text: {block_chars}",
                    file=sys.stderr,
                )
            print(json.dumps(data if isinstance(data, dict) else nr.output, indent=2, ensure_ascii=False, default=str))
            return 0 if result.status == "ok" else 1
    print("html_parse_basic node not found or failed", file=sys.stderr)
    for nr in result.node_results:
        print(f"  {nr.node_id} {nr.status} {nr.error!r}", file=sys.stderr)
    return 1


def main() -> int:
    p = argparse.ArgumentParser(
        description="Run fetch_url + html_parse_basic against books.toscrape.com; print parse output."
    )
    p.add_argument(
        "--cleanup",
        action="store_true",
        help="Delete the created user and workflow after the run.",
    )
    args = p.parse_args()
    return asyncio.run(_run(cleanup=args.cleanup))


if __name__ == "__main__":
    raise SystemExit(main())
