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

  uv run python scripts/analyze_workflow_definition.py \\
    --workflow-id <uuid> --wiring-issues

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


def _start_output_handles(raw: dict[str, Any]) -> list[str]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    req = data.get("required_inputs")
    if req is None:
        keys = ["user_input"]
    elif isinstance(req, list) and len(req) == 0:
        keys = ["output"]
    elif isinstance(req, list):
        keys = [str(r.get("key")) for r in req if isinstance(r, dict) and r.get("key")]
    else:
        keys = ["output"]
    return ["signal_out", *keys]


def _stop_target_handles(raw: dict[str, Any]) -> list[str]:
    data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
    outs = data.get("required_outputs")
    if isinstance(outs, list) and outs and isinstance(outs[0], dict):
        data_key = outs[0].get("key") or "output"
    else:
        data_key = "output"
    return ["trigger", str(data_key)]


def _node_target_handles(raw: dict[str, Any]) -> list[str] | None:
    kind = raw.get("kind")
    if kind == "start":
        return []
    if kind == "stop":
        return _stop_target_handles(raw)
    if kind == "annotation":
        return []
    if kind == "control" and raw.get("control_type") == "for_loop_end":
        data = raw.get("data") if isinstance(raw.get("data"), dict) else {}
        exports = data.get("exports")
        if isinstance(exports, list) and exports:
            keys = [str(x) for x in exports]
        else:
            keys = ["export"]
        return ["trigger", *keys]
    if kind == "workflow":
        return None
    # Common static inputs (+ trigger) for offline checks
    ut = raw.get("utility_type")
    sk = raw.get("skill_type")
    pt = raw.get("primitive_type")
    ct = raw.get("control_type")
    static: dict[tuple[str, str], list[str]] = {
        ("utility", "broadcast_message"): ["trigger", "message", "title"],
        ("utility", "add_to_list"): ["trigger", "list", "value"],
        ("utility", "dictionary_value_by_key"): ["trigger", "key", "dictionary", "fallback"],
        ("skill", "simple_llm_call"): ["trigger", "additional_context", "user_prompt", "structure"],
        ("skill", "gmail_list_messages"): ["trigger", "after", "before", "unread_only", "query", "max_results"],
        ("primitive", "string"): ["trigger", "input"],
        ("primitive", "list"): ["trigger", "input"],
        ("primitive", "dictionary"): ["trigger", "input"],
        ("control", "for_loop"): ["trigger", "input"],
        ("control", "basic_conditional"): ["trigger", "condition"],
        ("control", "is"): ["trigger", "input_a", "input_b"],
        ("control", "is_empty"): ["trigger", "value"],
    }
    if ut and ("utility", ut) in static:
        return static[("utility", ut)]
    if sk and ("skill", sk) in static:
        return static[("skill", sk)]
    if pt and ("primitive", pt) in static:
        return static[("primitive", pt)]
    if ct and ("control", ct) in static:
        return static[("control", ct)]
    if kind in ("utility", "skill", "primitive", "control"):
        return ["trigger", "input"]
    return None


def _node_source_handles(raw: dict[str, Any]) -> list[str] | None:
    kind = raw.get("kind")
    if kind in ("start", "stop", "annotation"):
        if kind == "start":
            return _start_output_handles(raw)
        return []
    if kind == "workflow":
        return None
    ct = raw.get("control_type")
    if kind == "control":
        if ct in ("basic_conditional", "is", "is_empty", "gt", "lt", "gte", "lte", "between"):
            return ["signal_out", "true", "false"]
        if ct == "for_loop":
            return ["signal_out", "item", "summary"]
        if ct == "for_loop_end":
            return ["signal_out", "output"]
        if ct == "try_catch":
            return ["signal_out", "try", "catch", "output", "envelope"]
        if ct in ("and", "or", "xor", "not"):
            return ["signal_out", "output"]
    if kind in ("utility", "skill", "primitive"):
        return ["signal_out", "output"]
    return None


def _normalize_handles(
    raw_edge: dict[str, Any],
    src_raw: dict[str, Any] | None,
    tgt_raw: dict[str, Any] | None,
) -> tuple[str | None, str | None]:
    sh = raw_edge.get("source_handle")
    th = raw_edge.get("target_handle")
    source_handle = sh if sh not in (None, "") else None
    target_handle = th if th not in (None, "") else None
    if src_raw and source_handle is None and src_raw.get("kind") == "start":
        data = src_raw.get("data") if isinstance(src_raw.get("data"), dict) else {}
        req = data.get("required_inputs")
        if isinstance(req, list) and req and isinstance(req[0], dict):
            source_handle = str(req[0].get("key") or "user_input")
        else:
            source_handle = "output"
    if tgt_raw and tgt_raw.get("kind") == "stop" and target_handle not in ("trigger",):
        data = tgt_raw.get("data") if isinstance(tgt_raw.get("data"), dict) else {}
        outs = data.get("required_outputs")
        if target_handle in (None, ""):
            if isinstance(outs, list) and outs and isinstance(outs[0], dict):
                target_handle = str(outs[0].get("key") or "output")
            else:
                target_handle = "output"
    return source_handle, target_handle


def find_graph_wiring_issues(graph: dict[str, Any]) -> list[str]:
    """Return human-readable wiring issue lines (subset aligned with SPA graph issues panel)."""
    node_by_id: dict[str, dict[str, Any]] = {}
    for raw in graph.get("nodes") or []:
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            node_by_id[raw["id"]] = raw
    id_to_label = _node_id_to_label(graph)
    issues: list[str] = []
    for i, raw_e in enumerate(graph.get("edges") or []):
        if not isinstance(raw_e, dict):
            continue
        src_id = raw_e.get("source")
        tgt_id = raw_e.get("target")
        if not isinstance(src_id, str) or not isinstance(tgt_id, str):
            continue
        src_raw = node_by_id.get(src_id)
        tgt_raw = node_by_id.get(tgt_id)
        prefix = f"[edge {i}] {src_id!r} -> {tgt_id!r}"
        if src_raw is None:
            issues.append(f"{prefix}: missing source node")
            continue
        if tgt_raw is None:
            issues.append(f"{prefix}: missing target node")
            continue
        if src_raw.get("kind") == "annotation" or tgt_raw.get("kind") == "annotation":
            issues.append(f"{prefix}: annotation nodes cannot be wired")
            continue
        source_handle, target_handle = _normalize_handles(raw_e, src_raw, tgt_raw)
        src_handles = _node_source_handles(src_raw)
        tgt_handles = _node_target_handles(tgt_raw)
        src_label = id_to_label.get(src_id, src_id)
        tgt_label = id_to_label.get(tgt_id, tgt_id)
        if src_handles is None:
            issues.append(
                f"{prefix}: source {src_label!r} is a nested workflow — open in the editor Graph issues panel for full handle checks"
            )
        elif source_handle and source_handle not in src_handles:
            issues.append(
                f"{prefix}: source {src_label!r} has no output {source_handle!r}; valid: {', '.join(src_handles)}"
            )
        if tgt_handles is None:
            issues.append(
                f"{prefix}: target {tgt_label!r} is a nested workflow — open in the editor Graph issues panel for full handle checks"
            )
        elif target_handle and target_handle not in tgt_handles:
            issues.append(
                f"{prefix}: target {tgt_label!r} has no input {target_handle!r}; valid: {', '.join(tgt_handles)}"
            )
    return issues


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
    p.add_argument(
        "--wiring-issues",
        action="store_true",
        help="List edge handle mismatches (missing nodes, unknown source_handle/target_handle).",
    )
    args = p.parse_args()
    wf_uuid = _normalize_uuid(args.workflow_id)

    wiring_issues: list[str] = []
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
        wiring_issues: list[str] = []
        if args.wiring_issues:
            wiring_issues = find_graph_wiring_issues(graph)
            print("\nGraph wiring issues (--wiring-issues):")
            if wiring_issues:
                for line in wiring_issues:
                    print(f"  - {line}")
            else:
                print("  (none detected by offline handle checks)")
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

    if errs or (args.wiring_issues and wiring_issues):
        return 3
    return 0


if __name__ == "__main__":
    # Allow running without PYTHONPATH when cwd is backend/
    raise SystemExit(main())
