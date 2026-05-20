"""Inject Workspace default Google workflow connection into skill node graphs (Workspace capability runs)."""

from __future__ import annotations

import copy
import uuid
from typing import Any, Dict, Optional

from sqlmodel import Session

from app.persistence.tables import GoogleWorkflowConnection

_GOOGLE_SKILL_TYPES = frozenset(
    {"gmail_list_messages", "calendar_list_events", "google_docs_get_document"}
)


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
    Mutate graph in place: canonical ``skill_type`` and ``google_connection_id`` on skill nodes.
    Use only on copies (e.g. after deepcopy), never on persisted workflow rows in-session.
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


def _google_workflow_connection_valid_for_user(
    session: Session,
    raw_c: Any,
    user_id: uuid.UUID,
) -> bool:
    """True when ``raw_c`` parses to a UUID and a GoogleWorkflowConnection row exists for ``user_id``."""
    if raw_c is None:
        return False
    s = str(raw_c).strip()
    if not s:
        return False
    try:
        cid = uuid.UUID(s)
    except (ValueError, TypeError):
        return False
    row = session.get(GoogleWorkflowConnection, cid)
    return row is not None and row.user_id == user_id


def workflow_graph_with_default_google_connection(
    session: Session,
    *,
    user_id: uuid.UUID,
    graph: Optional[Dict[str, Any]],
    default_connection_id: Optional[uuid.UUID],
) -> Dict[str, Any]:
    """
    Return a deep copy of ``graph`` where Gmail/Calendar skill nodes receive
    ``default_connection_id`` when they have no **usable** connection id.

    A node id is replaced when it is missing, blank/whitespace, not a valid UUID,
    not found in the database, or not owned by ``user_id``. Valid owned ids are kept.
    """
    if not graph or not isinstance(graph, dict):
        return dict(graph or {})
    if default_connection_id is None:
        out = copy.deepcopy(graph)
        normalize_workflow_graph_skill_aliases_inplace(out)
        return out

    row = session.get(GoogleWorkflowConnection, default_connection_id)
    if row is None or row.user_id != user_id:
        out = copy.deepcopy(graph)
        normalize_workflow_graph_skill_aliases_inplace(out)
        return out

    cid_str = str(row.id)
    out = copy.deepcopy(graph)
    normalize_workflow_graph_skill_aliases_inplace(out)
    nodes = out.get("nodes")
    if not isinstance(nodes, list):
        return out

    for n in nodes:
        if not isinstance(n, dict):
            continue
        if n.get("kind") != "skill":
            continue
        data = n.get("data")
        if not isinstance(data, dict):
            data = {}
            n["data"] = data
        if skill_node_skill_type(n) not in _GOOGLE_SKILL_TYPES:
            continue
        raw_c = data.get("google_connection_id")
        if _google_workflow_connection_valid_for_user(session, raw_c, user_id):
            continue
        data["google_connection_id"] = cid_str

    return out
