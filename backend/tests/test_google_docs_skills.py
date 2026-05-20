"""Google Docs get skill + parse utility (mocked Google API)."""

import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.domain.schemas.graph_nodes import GoogleDocsParseDocumentUtilityNode
from app.domain.workflow_executor.parsing import _parse_node

def _minimal_docs_api_response() -> dict:
    return {
        "documentId": "doc123",
        "title": "Test Doc",
        "revisionId": "rev1",
        "tabs": [
            {
                "tabProperties": {"tabId": "tab1", "title": "Main"},
                "documentTab": {
                    "body": {
                        "content": [
                            {
                                "paragraph": {
                                    "elements": [
                                        {"textRun": {"content": "Line one\n"}},
                                    ]
                                }
                            }
                        ]
                    },
                    "inlineObjects": {},
                },
            }
        ],
    }


def test_google_docs_get_and_parse_mocked(client: TestClient):
    get_id = "n_gdocs_get"
    parse_id = "n_gdocs_parse"
    conn_id = str(uuid.uuid4())
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Google Docs mock",
            "graph": {
                "nodes": [
                    {
                        "id": "n_start",
                        "kind": "start",
                        "label": "Start",
                        "data": {"required_inputs": []},
                        "position": {"x": 0, "y": 0},
                    },
                    {
                        "id": get_id,
                        "kind": "skill",
                        "skill_type": "google_docs_get_document",
                        "label": "Get Doc",
                        "data": {
                            "google_connection_id": conn_id,
                            "document_url_or_id": "https://docs.google.com/document/d/doc123/edit",
                            "include_tabs_content": True,
                            "required_inputs": [
                                {
                                    "key": "document_url_or_id",
                                    "type": "string",
                                    "value": "https://docs.google.com/document/d/doc123/edit",
                                },
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                    {
                        "id": parse_id,
                        "kind": "utility",
                        "utility_type": "google_docs_parse_document",
                        "label": "Parse",
                        "data": {
                            "chunk_strategy": "structure",
                            "required_inputs": [
                                {"key": "document", "type": "dictionary", "value": None},
                            ],
                        },
                        "position": {"x": 400, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": get_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                    {
                        "source": get_id,
                        "target": parse_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                    {
                        "source": get_id,
                        "target": parse_id,
                        "source_handle": "output",
                        "target_handle": "document",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]

    raw = _minimal_docs_api_response()

    async def _fake_build(session, user_id, access_token, raw_document, *, document_id):
        _ = (session, user_id, access_token)
        return (
            {
                "document_id": document_id,
                "title": raw_document.get("title") or "",
                "revision_id": raw_document.get("revisionId"),
                "tabs": [
                    {
                        "tab_id": "tab1",
                        "title": "Main",
                        "body": {"blocks": [{"type": "paragraph", "text": "Line one"}]},
                    }
                ],
                "tab_count": 1,
                "image_count": 0,
                "fetch_errors": [],
            },
            [],
        )

    with (
        patch(
            "app.domain.workflow_executor.executor.ensure_workflow_google_access_token",
            new_callable=AsyncMock,
            return_value="access-token",
        ),
        patch(
            "app.domain.workflow_executor.executor.docs_get_document",
            new_callable=AsyncMock,
            return_value=raw,
        ) as mock_get,
        patch(
            "app.domain.workflow_executor.skills_runner_mixin.build_document_payload",
            new_callable=AsyncMock,
            side_effect=_fake_build,
        ),
    ):
        run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")

    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    gr = next((r for r in result["node_results"] if r["node_id"] == get_id), None)
    pr = next((r for r in result["node_results"] if r["node_id"] == parse_id), None)
    assert gr is not None and gr["status"] == "ok"
    assert pr is not None and pr["status"] == "ok"
    assert gr["output"]["kind"] == "dictionary"
    assert "document_payload" in gr["output"]["data"]
    assert gr["output"]["data"]["document_payload"]["document_id"] == "doc123"
    mock_get.assert_called_once()
    assert pr["output"]["kind"] == "list"
    assert len(pr["output"]["data"]) >= 1
    assert pr["output"]["data"][0]["kind"] in ("text", "table", "image")


def test_legacy_google_docs_parse_skill_kind_normalizes_to_utility():
    node = _parse_node(
        {
            "id": "n_parse",
            "kind": "skill",
            "skill_type": "google_docs_parse_document",
            "label": "Parse",
            "data": {"chunk_strategy": "structure"},
            "position": {"x": 0, "y": 0},
        }
    )
    assert isinstance(node, GoogleDocsParseDocumentUtilityNode)
    assert node.utility_type == "google_docs_parse_document"
