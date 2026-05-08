#!/usr/bin/env python3
"""
One-off: set data.parallel_iterations on the For Loop in the Check Email workflow.

Run from backend/ after deploy when DATABASE_URL points at the target DB:

  uv run python scripts/enable_parallel_for_loop_check_email.py

Uses workflow id 8aea7c97-f73e-4176-beaa-624fc14725b2 and the Check Email graph's
for_loop node (by control_type). Idempotent.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlmodel import Session, select

from app.persistence.db import engine
from app.persistence.tables import WorkflowDefinition

CHECK_EMAIL_WORKFLOW_ID = uuid.UUID("8aea7c97-f73e-4176-beaa-624fc14725b2")


def main() -> None:
    wid = CHECK_EMAIL_WORKFLOW_ID
    with Session(engine) as session:
        wf = session.exec(select(WorkflowDefinition).where(WorkflowDefinition.id == wid)).first()
        if wf is None:
            raise SystemExit(f"WorkflowDefinition not found: {wid}")
        if wf.name.strip().casefold() != "check email".casefold():
            raise SystemExit(f"Workflow {wid} is named {wf.name!r}; aborting (safety check).")
        graph: dict[str, Any] = dict(wf.graph or {})
        nodes = list(graph.get("nodes") or [])
        changed = False
        for i, raw in enumerate(nodes):
            if not isinstance(raw, dict):
                continue
            if raw.get("kind") != "control" or raw.get("control_type") != "for_loop":
                continue
            data = dict(raw.get("data") or {})
            if data.get("parallel_iterations") is True:
                print("parallel_iterations already true; nothing to do.")
                return
            data["parallel_iterations"] = True
            nodes[i] = {**raw, "data": data}
            changed = True
            break
        if not changed:
            raise SystemExit("No for_loop node found in graph.")
        graph["nodes"] = nodes
        wf.graph = graph
        session.add(wf)
        session.commit()
    print(f"Updated workflow {wid}: parallel_iterations enabled on For Loop.")


if __name__ == "__main__":
    main()
