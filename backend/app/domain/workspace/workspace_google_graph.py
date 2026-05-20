"""Skill node graph helpers (legacy alias normalization)."""

from __future__ import annotations

from typing import Any, Dict, Optional


def skill_node_skill_type(raw_node: Dict[str, Any]) -> Optional[str]:
    """Resolved skill_type for a raw skill node (snake_case or legacy camelCase, node or data)."""
    if raw_node.get("kind") != "skill":
        return None
    for key in ("skill_type", "skillType"):
        st = raw_node.get(key)
        if isinstance(st, str) and st.strip():
            return st.strip()
    data = raw_node.get("data")
    if not isinstance(data, dict):
        return None
    for key in ("skill_type", "skillType"):
        st = data.get(key)
        if isinstance(st, str) and st.strip():
            return st.strip()
    return None


def normalize_workflow_graph_skill_aliases_inplace(graph: Dict[str, Any]) -> None:
    """
    Mutate graph in place: canonical ``skill_type`` and legacy ``google_connection_id`` aliases on skill nodes.
    ``google_connection_id`` on nodes is ignored at run time; only alias keys are normalized for legacy graphs.
    """
    nodes = graph.get("nodes")
    if not isinstance(nodes, list):
        return
    for n in nodes:
        if not isinstance(n, dict) or n.get("kind") != "skill":
            continue
        st = n.get("skill_type")
        if not (isinstance(st, str) and st.strip()):
            alt = n.get("skillType")
            if isinstance(alt, str) and alt.strip():
                n["skill_type"] = alt.strip()
        data = n.get("data")
        if not isinstance(data, dict):
            continue
        st_d = data.get("skill_type")
        if not (isinstance(st_d, str) and st_d.strip()):
            alt_d = data.get("skillType")
            if isinstance(alt_d, str) and alt_d.strip():
                data["skill_type"] = alt_d.strip()
        raw_c = data.get("google_connection_id")
        blank_c = raw_c is None or (isinstance(raw_c, str) and not str(raw_c).strip())
        if blank_c:
            alt_c = data.get("googleConnectionId")
            if alt_c is not None and str(alt_c).strip():
                data["google_connection_id"] = str(alt_c).strip()
