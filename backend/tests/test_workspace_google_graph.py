"""Unit tests for workflow skill graph alias normalization."""

from __future__ import annotations

from app.domain.workspace.workspace_google_graph import (
    normalize_workflow_graph_skill_aliases_inplace,
    skill_node_skill_type,
)


def test_skill_node_skill_type_reads_camelCase_aliases():
    n = {"kind": "skill", "skillType": "gmail_list_messages"}
    assert skill_node_skill_type(n) == "gmail_list_messages"
    n2 = {"kind": "skill", "data": {"skillType": "calendar_list_events"}}
    assert skill_node_skill_type(n2) == "calendar_list_events"


def test_normalizes_camelCase_and_google_connection_id_alias():
    g = {
        "nodes": [
            {
                "kind": "skill",
                "skillType": "gmail_list_messages",
                "data": {
                    "googleConnectionId": "550e8400-e29b-41d4-a716-446655440000",
                },
            }
        ]
    }
    normalize_workflow_graph_skill_aliases_inplace(g)
    assert g["nodes"][0]["skill_type"] == "gmail_list_messages"
    assert g["nodes"][0]["data"]["google_connection_id"] == "550e8400-e29b-41d4-a716-446655440000"
