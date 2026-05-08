#!/usr/bin/env python3
"""
Offline analysis of a persisted WorkflowDefinition graph.

The graph is loaded from the ``workflow_definitions.graph`` column — the **same**
persisted JSON the API returns for ``GET /api/v1/workflow-definitions/{id}`` (SPA / Workflow Editor).

Runs the same For Loop / For Loop End structural checks as the executor
(validate_for_loop_bodies, validate_for_loop_end_configuration) against that
row. Optional: Upsert-centric **``--summarize``** (targets for upsert regressions),
or **node_run_logs** for a run id.

Usage (from backend/):

  uv run python scripts/analyze_workflow_definition.py \\
    --workflow-id edd3ac00-803c-4696-864b-cae0b979b498

  uv run python scripts/analyze_workflow_definition.py \\
    --workflow-id <uuid> --run-id <uuid>

  uv run python scripts/analyze_workflow_definition.py \\
    --workflow-id <uuid> --edges

  uv run python scripts/analyze_workflow_definition.py \\
    --workflow-id f2df2602-ba7a-4bad-b1cd-af0d69509766 --summarize

DATABASE_URL comes from the environment (see app.core.config / .env). The script
changes cwd to ``backend/`` before importing ``app`` (same as ``run_workflow_stream.py``)
so ``sqlite:///./mindweave.db`` resolves correctly when run from the repo root.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from pathlib import Path
from typing import Any

_BACKEND_ROOT = Path(__file__).resolve().parent.parent
os.chdir(_BACKEND_ROOT)

from sqlmodel import Session, select

from app.domain.schemas import GraphEdge
from app.domain.workflow_executor.graph import validate_for_loop_bodies, validate_for_loop_end_configuration
from app.domain.workflow_executor.parsing import _parse_node
from app.persistence.db import engine
from app.persistence.tables import NodeRunLog, WorkflowDefinition, WorkflowRun


def _normalize_uuid(s: str) -> uuid.UUID:
    t = s.strip()
    if re.fullmatch(r"[0-9a-fA-F]{32}", t):
        t = f"{t[:8]}-{t[8:12]}-{t[12:16]}-{t[16:20]}-{t[20:]}"
    return uuid.UUID(t)


def _parse_nodes(graph: dict[str, Any]) -> dict[str, Any]:
    nodes_by_id: dict[str, Any] = {}
    for raw in graph.get("nodes") or []:
        parsed = _parse_node(raw)
        if parsed is not None:
            nodes_by_id[parsed.id] = parsed
    return nodes_by_id


def _node_id_to_label(graph: dict[str, Any]) -> dict[str, str]:
    """Map graph node id -> label from raw JSON (matches canvas display names)."""
    out: dict[str, str] = {}
    for raw in graph.get("nodes") or []:
        if not isinstance(raw, dict):
            continue
        nid = raw.get("id")
        if isinstance(nid, str) and nid:
            lab = raw.get("label")
            out[nid] = lab if isinstance(lab, str) and lab.strip() else "(no label)"
    return out


def _summarize_upsert_document_view(graph: dict[str, Any], id_to_label: dict[str, str]) -> None:
    """Compact Upsert-centric view for debugging regressions tied to wiring / explorer defaults."""
    upsert_rows: list[tuple[str, str]] = []
    node_by_id: dict[str, dict[str, Any]] = {}
    for raw in graph.get("nodes") or []:
        if not isinstance(raw, dict):
            continue
        nid = raw.get("id")
        if not isinstance(nid, str) or not nid:
            continue
        node_by_id[nid] = raw
        if raw.get("kind") == "utility" and raw.get("utility_type") == "upsert_document":
            upsert_rows.append((nid, id_to_label.get(nid, "(no label)")))
    print("\n--- Upsert-centric summary (--summarize) ---")
    if not upsert_rows:
        print("  (no utility_type=upsert_document nodes)")
        return
    print("Upsert Document nodes:")
    for nid, lab in sorted(upsert_rows, key=lambda x: x[0]):
        print(f"  {nid}  ->  {lab}")
    edges = [e for e in (graph.get("edges") or []) if isinstance(e, dict)]
    for nid, lab in sorted(upsert_rows, key=lambda x: x[0]):
        print(f"\nEdges targeting upsert node {nid!r} ({lab}):")
        found = False
        for i, e in enumerate(edges):
            if e.get("target") != nid:
                continue
            found = True
            print(
                f"  [{i}] source={e.get('source')!r} -> target={e.get('target')!r}   "
                f"source_handle={e.get('source_handle')!r} target_handle={e.get('target_handle')!r}"
            )
        if not found:
            print("  (none)")
        raw_n = node_by_id.get(nid) or {}
        data = raw_n.get("data")
        if not isinstance(data, dict):
            data = {}
        req = data.get("required_inputs") or []
        snippets: list[str] = []
        if isinstance(req, list):
            for item in req:
                if not isinstance(item, dict):
                    continue
                key = item.get("key")
                val = item.get("value")
                if key in ("name", "content"):
                    vs = "(empty)" if val is None else str(val)
                    if len(vs) > 120:
                        vs = vs[:117] + "..."
                    snippets.append(f"{key}={vs!r}")
        if snippets:
            print(f"  required_inputs excerpts: {'; '.join(snippets)}")
        else:
            print("  required_inputs excerpts: (none or non-inline)")


def analyze_graph_dict(graph: dict[str, Any]) -> tuple[list[str], list[str]]:
    """Return (info_lines, error_lines). Empty error_lines means graph passes loop validators."""
    nodes_by_id = _parse_nodes(graph)
    edges = [GraphEdge(**e) for e in graph.get("edges") or []]
    errors: list[str] = []
    info: list[str] = [
        f"Parsed nodes: {len(nodes_by_id)}, edges: {len(edges)}",
        f"Graph schema_version: {graph.get('schema_version')!r}",
    ]
    try:
        validate_for_loop_bodies(nodes_by_id, edges)
        info.append("validate_for_loop_bodies: OK")
    except ValueError as exc:
        errors.append(f"validate_for_loop_bodies: {exc}")
    try:
        validate_for_loop_end_configuration(nodes_by_id, edges)
        info.append("validate_for_loop_end_configuration: OK")
    except ValueError as exc:
        errors.append(f"validate_for_loop_end_configuration: {exc}")
    return info, errors


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Analyze workflow graph loop wiring against the persisted row "
            "(same graph as GET /api/v1/workflow-definitions/{id})."
        ),
    )
    p.add_argument(
        "--workflow-id",
        required=True,
        help="WorkflowDefinition id (UUID, with or without hyphens).",
    )
    p.add_argument("--run-id", default=None, help="Optional WorkflowRun id to list node_run_logs.")
    p.add_argument(
        "--json",
        action="store_true",
        help="Print raw graph JSON (large).",
    )
    p.add_argument(
        "--edges",
        action="store_true",
        help="List edges with source/target handles (React Flow / API field names).",
    )
    p.add_argument(
        "--summarize",
        action="store_true",
        help="Print Upsert Document nodes, edges into them, and trimmed required_inputs name/content excerpts.",
    )
    args = p.parse_args()
    wf_uuid = _normalize_uuid(args.workflow_id)

    with Session(engine) as session:
        wf = session.get(WorkflowDefinition, wf_uuid)
        if wf is None:
            print(f"WorkflowDefinition not found: {wf_uuid}", file=sys.stderr)
            return 1
        print(f"name: {wf.name!r}")
        print(f"id:   {wf.id}")
        graph = wf.graph if isinstance(wf.graph, dict) else {}
        id_to_label = _node_id_to_label(graph)
        if id_to_label:
            print("\nNodes (id -> label, as in the editor):")
            for nid in sorted(id_to_label.keys()):
                print(f"  {nid}  ->  {id_to_label[nid]}")
        if args.json:
            print(json.dumps(graph, indent=2))
        if args.edges:
            print("\nEdges (source -> target, handles):")
            for i, raw in enumerate(graph.get("edges") or []):
                if not isinstance(raw, dict):
                    continue
                src = raw.get("source")
                tgt = raw.get("target")
                sh = raw.get("source_handle")
                th = raw.get("target_handle")
                print(
                    f"  [{i}] {src!r} -> {tgt!r}   "
                    f"source_handle={sh!r} target_handle={th!r}"
                )
        if args.summarize:
            _summarize_upsert_document_view(graph, id_to_label)
        info, errs = analyze_graph_dict(graph)
        print()
        for line in info:
            print(line)
        print()
        if errs:
            print("Validation issues:")
            for e in errs:
                print(f"  - {e}")
        else:
            print("Loop structure validation: OK")

        if args.run_id:
            run_uuid = _normalize_uuid(args.run_id)
            run = session.get(WorkflowRun, run_uuid)
            if run is None:
                print(f"\nWorkflowRun not found: {run_uuid}", file=sys.stderr)
                return 2
            if run.workflow_id != wf.id:
                print(
                    f"\nWarning: run.workflow_id ({run.workflow_id}) != requested workflow ({wf.id})",
                    file=sys.stderr,
                )
            print(f"\nRun {run.id}: status={run.status!r}")
            logs = session.exec(
                select(NodeRunLog)
                .where(NodeRunLog.run_id == run.id)
                .order_by(NodeRunLog.created_at)
            ).all()
            if not logs:
                print("node_run_logs: (none — often means validation failed before any step executed)")
            else:
                print(f"node_run_logs: {len(logs)} row(s)")
                for row in logs:
                    err = f" error={row.error!r}" if row.error else ""
                    lab = id_to_label.get(row.node_id, "?")
                    print(
                        f"  step={row.step_number} node={row.node_id!r} label={lab!r} status={row.status!r}{err}"
                    )

    return 0 if not errs else 3


if __name__ == "__main__":
    # Allow running without PYTHONPATH when cwd is backend/
    raise SystemExit(main())
