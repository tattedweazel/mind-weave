"""Canonical built-in starter sandbox workflow graph + idempotent DB seed.

Alembic and app startup both rely on the same graph and id constant as
``builtins.STARTER_SANDBOX_WORKFLOW_ID``.

The graph JSON is kept in sync with ``sandbox-behavior-imported.json`` (repo
root) so the default matches a workflow editor export. The default brain uses
the ``sandbox_starter_decision`` utility (same deterministic policy as the
legacy ``sandbox_behavior`` primitive).

**Regenerating the fixture** after you change ``_STARTER_GRAPH_JSON`` /
``STARTER_SANDBOX_WORKFLOW_GRAPH``: from ``backend/`` (writes
``../sandbox-behavior-imported.json``), run:

    uv run python <<'PY'
    import json
    from pathlib import Path
    from app.domain.sandbox.starter_workflow_seed import STARTER_SANDBOX_WORKFLOW_GRAPH
    Path("../sandbox-behavior-imported.json").write_text(
        json.dumps({"definition": {"graph": STARTER_SANDBOX_WORKFLOW_GRAPH}}, indent=2) + "\n",
        encoding="utf-8",
    )
    PY

Then run ``pytest tests/test_starter_workflow_seed.py`` and commit both the
Python change and the JSON. Maintainer notes also live under **Starter graph
export fixture** in ``docs/SANDBOX.md``.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime, timezone
from typing import Any

from sqlmodel import Session, select

from app.domain.sandbox.builtins import STARTER_SANDBOX_WORKFLOW_ID
from app.persistence.tables import WorkflowDefinition

STARTER_BUILTIN_SLUG = "starter_sandbox_behavior"

# Minified graph (definition.graph); control flow: signal_out → trigger; data: sandbox_tick → input.
_STARTER_GRAPH_JSON = (
    '{"nodes":[{"id":"sandbox_start","kind":"start","label":"Start","data":{"required_inputs":'
    '[{"key":"sandbox_tick","type":"dictionary","value":null}]},"position":{"x":0,"y":0}},'
    '{"id":"sandbox_brain","kind":"utility","utility_type":"sandbox_starter_decision",'
    '"label":"Starter sandbox decision","data":{},"position":{"x":220,"y":0}},'
    '{"id":"sandbox_stop","kind":"stop","label":"Stop","data":{"required_outputs":'
    '[{"key":"output","type":"dictionary"}]},"position":{"x":480,"y":0}}],'
    '"edges":['
    '{"source":"sandbox_start","target":"sandbox_brain","source_handle":"signal_out","target_handle":"trigger"},'
    '{"source":"sandbox_start","target":"sandbox_brain","source_handle":"sandbox_tick","target_handle":"input"},'
    '{"source":"sandbox_brain","target":"sandbox_stop","source_handle":"signal_out","target_handle":"trigger"},'
    '{"source":"sandbox_brain","target":"sandbox_stop","source_handle":"output","target_handle":"output"}'
    "]}"
)

STARTER_SANDBOX_WORKFLOW_GRAPH: dict = json.loads(_STARTER_GRAPH_JSON)


def _normalize_value(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {k: _normalize_value(v) for k, v in sorted(obj.items())}
    if isinstance(obj, list):
        return [_normalize_value(x) for x in obj]
    if isinstance(obj, float) and obj.is_integer():
        return int(obj)
    return obj


def _normalize_edges(edges: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for e in edges:
        if not isinstance(e, dict):
            continue
        if "source" not in e or "target" not in e:
            continue
        out.append(
            {
                "source": e["source"],
                "target": e["target"],
                "source_handle": e.get("source_handle"),
                "target_handle": e.get("target_handle"),
            }
        )
    out.sort(
        key=lambda e: (
            e["source"],
            e["target"],
            e["source_handle"] or "",
            e["target_handle"] or "",
        )
    )
    return out


def _normalize_graph_for_compare(graph: dict | None) -> dict[str, Any]:
    """Semantic shape for equality (DB JSON may use floats, omit null keys, or add schema_version)."""
    if not isinstance(graph, dict):
        return {"edges": [], "nodes": []}
    g = {k: v for k, v in graph.items() if k != "schema_version"}
    nodes = g.get("nodes")
    edges = g.get("edges")
    if not isinstance(nodes, list):
        nodes = []
    if not isinstance(edges, list):
        edges = []
    return {
        "edges": _normalize_edges(edges),
        "nodes": _normalize_value(nodes),
    }


def graphs_equivalent(a: dict | None, b: dict | None) -> bool:
    """True if two workflow graphs match semantically (ignores key order and int/float drift)."""
    sa = json.dumps(_normalize_graph_for_compare(a), sort_keys=True, separators=(",", ":"))
    sb = json.dumps(_normalize_graph_for_compare(b), sort_keys=True, separators=(",", ":"))
    return sa == sb


STARTER_SANDBOX_NAME = "Starter Sandbox Behavior"
STARTER_SANDBOX_DESCRIPTION = "Built-in deterministic pet brain (sandbox_starter_decision utility; legacy sandbox_behavior primitive remains available)."


def ensure_starter_sandbox_workflow(session: Session) -> None:
    """Insert the system starter workflow if missing (dev DBs, tests without Alembic seed, etc.)."""
    canonical = STARTER_SANDBOX_WORKFLOW_GRAPH
    now = datetime.now(timezone.utc)
    existing = session.exec(
        select(WorkflowDefinition).where(WorkflowDefinition.builtin_slug == STARTER_BUILTIN_SLUG)
    ).first()
    if existing is not None:
        # Compare as str so SQLite UUID storage remains idempotent with Alembic-seeded rows.
        if str(existing.id) == str(STARTER_SANDBOX_WORKFLOW_ID):
            stored = existing.graph if isinstance(existing.graph, dict) else {}
            # Strip legacy top-level schema_version etc. even if nodes/edges match semantically.
            needs_cleanup = isinstance(stored, dict) and "schema_version" in stored
            if not needs_cleanup and graphs_equivalent(stored, canonical):
                return
            existing.graph = copy.deepcopy(canonical)
            existing.updated_at = now
            session.add(existing)
            session.commit()
            return
        session.delete(existing)
        session.commit()
    session.add(
        WorkflowDefinition(
            id=STARTER_SANDBOX_WORKFLOW_ID,
            user_id=None,
            name=STARTER_SANDBOX_NAME,
            description=STARTER_SANDBOX_DESCRIPTION,
            palette_id=None,
            project_id=None,
            expose_as_custom_skill=False,
            is_system=True,
            builtin_slug=STARTER_BUILTIN_SLUG,
            graph=copy.deepcopy(STARTER_SANDBOX_WORKFLOW_GRAPH),
            created_at=now,
            updated_at=now,
        )
    )
    session.commit()
