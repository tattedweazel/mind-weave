"""Workflow skills: Gmail list messages + Calendar list events (Google API mocked)."""

import base64
import uuid
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.domain.workflow_executor.diagnostics import (
    GOOGLE_CALENDAR_LIST_EVENTS_MAX_ITEMS_FOR_DIAGNOSTICS,
)


def _b64url(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode()).decode().rstrip("=")


def test_gmail_list_messages_skill_mocked(client: TestClient):
    gmail_id = "n_gmail_001"
    conn_id = str(uuid.uuid4())
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Gmail mock skill",
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
                        "id": gmail_id,
                        "kind": "skill",
                        "skill_type": "gmail_list_messages",
                        "label": "Gmail",
                        "data": {
                            "google_connection_id": conn_id,
                            "max_results": 5,
                            "required_inputs": [
                                {"key": "query", "type": "string", "value": "is:unread"},
                                {"key": "max_results", "type": "int", "value": 5},
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": gmail_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]

    fake_api = {"messages": [{"id": "m1", "threadId": "t1"}], "resultSizeEstimate": 99}
    fake_full = {
        "id": "m1",
        "threadId": "t1",
        "snippet": "snip",
        "labelIds": ["UNREAD"],
        "payload": {
            "mimeType": "text/plain",
            "headers": [
                {"name": "Subject", "value": "Hi"},
                {"name": "From", "value": "a@b.com"},
            ],
            "body": {"data": _b64url("Mail content")},
        },
    }
    with (
        patch(
            "app.domain.workflow_executor.executor.ensure_workflow_google_access_token",
            new_callable=AsyncMock,
            return_value="access-token",
        ),
        patch(
            "app.domain.workflow_executor.executor.gmail_list_messages",
            new_callable=AsyncMock,
            return_value=fake_api,
        ) as mock_gmail,
        patch(
            "app.domain.workflow_executor.executor.gmail_get_message_full",
            new_callable=AsyncMock,
            return_value=fake_full,
        ) as mock_get,
    ):
        run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")

    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    gr = next((r for r in result["node_results"] if r["node_id"] == gmail_id), None)
    assert gr is not None
    assert gr["status"] == "ok"
    assert gr["output"]["kind"] == "list"
    assert gr["details"].get("gmail_result_size_estimate") == 99
    msg0 = gr["output"]["data"][0]
    assert msg0["id"] == "m1"
    assert msg0["threadId"] == "t1"
    assert msg0["subject"] == "Hi"
    assert msg0["from"] == "a@b.com"
    assert msg0["body_text"] == "Mail content"
    mock_gmail.assert_called_once()
    mock_get.assert_called_once_with("access-token", "m1")
    assert mock_gmail.call_args.kwargs.get("query") == "is:unread"
    diag = gr["details"]["skill_diagnostics"]["gmail_v1"]
    assert diag["operation"] == "users.messages.list"
    assert diag["q"] == "is:unread"
    gcf = diag["gmail_category_filters"]
    assert gcf["effective_inbox_focus"] == "off"
    assert gcf["effective_exclude_categories"] == []
    assert gcf["skip_account_category_filters"] is False
    assert diag["truncated"] is False
    assert diag["message_gets"] == {"attempted": 1, "ok": 1, "failed": 0}


def test_gmail_list_messages_composes_time_and_unread_in_q(client: TestClient):
    gmail_id = "n_gmail_filt"
    conn_id = str(uuid.uuid4())
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Gmail filters",
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
                        "id": gmail_id,
                        "kind": "skill",
                        "skill_type": "gmail_list_messages",
                        "label": "Gmail",
                        "data": {
                            "google_connection_id": conn_id,
                            "max_results": 10,
                            "unread_only": True,
                            "after": "2026-03-01T12:00:00Z",
                            "before": "2026-03-10T00:00:00Z",
                            "required_inputs": [
                                {"key": "after", "type": "string", "value": "2026-03-01T12:00:00Z"},
                                {"key": "before", "type": "string", "value": "2026-03-10T00:00:00Z"},
                                {"key": "unread_only", "type": "boolean", "value": True},
                                {"key": "query", "type": "string", "value": "has:attachment"},
                                {"key": "max_results", "type": "int", "value": 10},
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": gmail_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    fake_api = {"messages": [], "resultSizeEstimate": 0}
    with (
        patch(
            "app.domain.workflow_executor.executor.ensure_workflow_google_access_token",
            new_callable=AsyncMock,
            return_value="access-token",
        ),
        patch(
            "app.domain.workflow_executor.executor.gmail_list_messages",
            new_callable=AsyncMock,
            return_value=fake_api,
        ) as mock_gmail,
        patch(
            "app.domain.workflow_executor.executor.gmail_get_message_full",
            new_callable=AsyncMock,
        ) as mock_get,
    ):
        run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    mock_gmail.assert_called_once()
    mock_get.assert_not_called()
    q = mock_gmail.call_args.kwargs.get("query") or ""
    assert "is:unread" in q
    assert "after:2026/03/01" in q
    assert "before:2026/03/10" in q
    assert "has:attachment" in q


def test_calendar_list_events_skill_mocked(client: TestClient):
    cal_id = "n_cal_001"
    conn_id = str(uuid.uuid4())
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Calendar mock skill",
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
                        "id": cal_id,
                        "kind": "skill",
                        "skill_type": "calendar_list_events",
                        "label": "Cal",
                        "data": {
                            "google_connection_id": conn_id,
                            "calendar_id": "primary",
                            "required_inputs": [
                                {
                                    "key": "time_min",
                                    "type": "string",
                                    "value": "2026-03-01T00:00:00Z",
                                },
                                {
                                    "key": "time_max",
                                    "type": "string",
                                    "value": "2026-03-02T00:00:00Z",
                                },
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": cal_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]

    fake_api = {
        "items": [
            {
                "id": "ev1",
                "status": "confirmed",
                "summary": "Standup",
                "htmlLink": "https://www.google.com/calendar/event?eid=ev1",
                "location": "Online",
                "start": {"dateTime": "2026-03-01T10:00:00Z"},
                "end": {"dateTime": "2026-03-01T11:00:00Z"},
            },
        ],
        "nextSyncToken": "sync-1",
    }
    with (
        patch(
            "app.domain.workflow_executor.executor.ensure_workflow_google_access_token",
            new_callable=AsyncMock,
            return_value="access-token",
        ),
        patch(
            "app.domain.workflow_executor.executor.calendar_list_events",
            new_callable=AsyncMock,
            return_value=fake_api,
        ),
    ):
        run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")

    assert run_res.status_code == 200
    result = run_res.json()
    assert result["status"] == "ok"
    cr = next((r for r in result["node_results"] if r["node_id"] == cal_id), None)
    assert cr is not None
    assert cr["status"] == "ok"
    assert cr["output"]["kind"] == "dictionary"
    ev0 = cr["output"]["data"]["events"][0]
    assert ev0["id"] == "ev1"
    assert ev0["start"] == "2026-03-01T10:00:00Z"
    assert ev0["end"] == "2026-03-01T11:00:00Z"
    assert ev0["summary"] == "Standup"
    assert ev0["status"] == "confirmed"
    assert ev0["htmlLink"] == "https://www.google.com/calendar/event?eid=ev1"
    assert ev0["location"] == "Online"

    diag = cr["details"]["skill_diagnostics"]["google_calendar_v3"]
    assert diag["operation"] == "events.list"
    assert diag["truncated"] is False
    assert diag["omitted_event_count"] == 0
    assert diag["response"]["items"][0]["id"] == "ev1"
    assert diag["response"]["nextSyncToken"] == "sync-1"


def test_calendar_list_events_diagnostics_truncates_large_items(client: TestClient):
    """Vendor diagnostics cap items array; curated list still has all events."""
    cal_id = "n_cal_trunc"
    conn_id = str(uuid.uuid4())
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Calendar truncation",
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
                        "id": cal_id,
                        "kind": "skill",
                        "skill_type": "calendar_list_events",
                        "label": "Cal",
                        "data": {
                            "google_connection_id": conn_id,
                            "calendar_id": "primary",
                            "required_inputs": [
                                {"key": "time_min", "type": "string", "value": "2026-03-01T00:00:00Z"},
                                {"key": "time_max", "type": "string", "value": "2026-03-02T00:00:00Z"},
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": cal_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]

    n_items = 105
    fake_api = {
        "items": [
            {
                "id": f"ev{i}",
                "start": {"dateTime": "2026-03-01T10:00:00Z"},
                "end": {"dateTime": "2026-03-01T11:00:00Z"},
            }
            for i in range(n_items)
        ],
    }
    with (
        patch(
            "app.domain.workflow_executor.executor.ensure_workflow_google_access_token",
            new_callable=AsyncMock,
            return_value="access-token",
        ),
        patch(
            "app.domain.workflow_executor.executor.calendar_list_events",
            new_callable=AsyncMock,
            return_value=fake_api,
        ),
    ):
        run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")

    assert run_res.status_code == 200
    cr = next(
        (r for r in run_res.json()["node_results"] if r["node_id"] == cal_id),
        None,
    )
    assert cr is not None
    assert len(cr["output"]["data"]["events"]) == n_items
    diag = cr["details"]["skill_diagnostics"]["google_calendar_v3"]
    cap = GOOGLE_CALENDAR_LIST_EVENTS_MAX_ITEMS_FOR_DIAGNOSTICS
    assert diag["truncated"] is True
    assert diag["omitted_event_count"] == n_items - cap
    assert len(diag["response"]["items"]) == cap


def test_list_google_workflow_connections_returns_user_connection(client: TestClient):
    r = client.get("/api/v1/google-workflow/connections")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert "id" in rows[0]


def test_gmail_list_messages_applies_account_category_exclusions(client: TestClient):
    assert (
        client.put(
            "/api/v1/auth/me",
            json={
                "settings": {
                    "gmail_workflow_inbox_focus": "off",
                    "gmail_workflow_exclude_categories": ["promotions"],
                },
            },
        ).status_code
        == 200
    )
    gmail_id = "n_gmail_acct_ex"
    conn_id = str(uuid.uuid4())
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Gmail acct categories",
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
                        "id": gmail_id,
                        "kind": "skill",
                        "skill_type": "gmail_list_messages",
                        "label": "Gmail",
                        "data": {
                            "google_connection_id": conn_id,
                            "max_results": 5,
                            "required_inputs": [
                                {"key": "query", "type": "string", "value": "is:unread"},
                                {"key": "max_results", "type": "int", "value": 5},
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": gmail_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    fake_api = {"messages": [], "resultSizeEstimate": 0}
    with (
        patch(
            "app.domain.workflow_executor.executor.ensure_workflow_google_access_token",
            new_callable=AsyncMock,
            return_value="access-token",
        ),
        patch(
            "app.domain.workflow_executor.executor.gmail_list_messages",
            new_callable=AsyncMock,
            return_value=fake_api,
        ) as mock_gmail,
        patch(
            "app.domain.workflow_executor.executor.gmail_get_message_full",
            new_callable=AsyncMock,
        ),
    ):
        run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    q = mock_gmail.call_args.kwargs.get("query") or ""
    assert "is:unread" in q
    assert "-category:promotions" in q


def test_gmail_list_messages_node_exclude_overrides_account(client: TestClient):
    assert (
        client.put(
            "/api/v1/auth/me",
            json={
                "settings": {
                    "gmail_workflow_inbox_focus": "off",
                    "gmail_workflow_exclude_categories": ["promotions"],
                },
            },
        ).status_code
        == 200
    )
    gmail_id = "n_gmail_node_ex"
    conn_id = str(uuid.uuid4())
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Gmail node categories",
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
                        "id": gmail_id,
                        "kind": "skill",
                        "skill_type": "gmail_list_messages",
                        "label": "Gmail",
                        "data": {
                            "google_connection_id": conn_id,
                            "max_results": 5,
                            "gmail_exclude_categories": ["social"],
                            "required_inputs": [
                                {"key": "max_results", "type": "int", "value": 5},
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": gmail_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    fake_api = {"messages": [], "resultSizeEstimate": 0}
    with (
        patch(
            "app.domain.workflow_executor.executor.ensure_workflow_google_access_token",
            new_callable=AsyncMock,
            return_value="access-token",
        ),
        patch(
            "app.domain.workflow_executor.executor.gmail_list_messages",
            new_callable=AsyncMock,
            return_value=fake_api,
        ) as mock_gmail,
        patch(
            "app.domain.workflow_executor.executor.gmail_get_message_full",
            new_callable=AsyncMock,
        ),
    ):
        run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    q = mock_gmail.call_args.kwargs.get("query") or ""
    assert "-category:social" in q
    assert "-category:promotions" not in q


def test_gmail_list_messages_skip_account_category_filters(client: TestClient):
    assert (
        client.put(
            "/api/v1/auth/me",
            json={
                "settings": {
                    "gmail_workflow_inbox_focus": "off",
                    "gmail_workflow_exclude_categories": ["promotions"],
                },
            },
        ).status_code
        == 200
    )
    gmail_id = "n_gmail_skip"
    conn_id = str(uuid.uuid4())
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Gmail skip acct",
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
                        "id": gmail_id,
                        "kind": "skill",
                        "skill_type": "gmail_list_messages",
                        "label": "Gmail",
                        "data": {
                            "google_connection_id": conn_id,
                            "max_results": 5,
                            "gmail_skip_account_category_filters": True,
                            "required_inputs": [
                                {"key": "max_results", "type": "int", "value": 5},
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": gmail_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    fake_api = {"messages": [], "resultSizeEstimate": 0}
    with (
        patch(
            "app.domain.workflow_executor.executor.ensure_workflow_google_access_token",
            new_callable=AsyncMock,
            return_value="access-token",
        ),
        patch(
            "app.domain.workflow_executor.executor.gmail_list_messages",
            new_callable=AsyncMock,
            return_value=fake_api,
        ) as mock_gmail,
        patch(
            "app.domain.workflow_executor.executor.gmail_get_message_full",
            new_callable=AsyncMock,
        ),
    ):
        run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    q = mock_gmail.call_args.kwargs.get("query") or ""
    assert "-category:promotions" not in q
    gr = next(
        (r for r in run_res.json()["node_results"] if r["node_id"] == gmail_id),
        None,
    )
    assert (
        gr["details"]["skill_diagnostics"]["gmail_v1"]["gmail_category_filters"]["skip_account_category_filters"]
        is True
    )


def test_gmail_list_messages_account_primary_focus(client: TestClient):
    assert (
        client.put(
            "/api/v1/auth/me",
            json={
                "settings": {
                    "gmail_workflow_inbox_focus": "primary",
                    "gmail_workflow_exclude_categories": ["promotions"],
                },
            },
        ).status_code
        == 200
    )
    gmail_id = "n_gmail_pri"
    conn_id = str(uuid.uuid4())
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Gmail primary acct",
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
                        "id": gmail_id,
                        "kind": "skill",
                        "skill_type": "gmail_list_messages",
                        "label": "Gmail",
                        "data": {
                            "google_connection_id": conn_id,
                            "max_results": 3,
                            "required_inputs": [
                                {"key": "max_results", "type": "int", "value": 3},
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": gmail_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    fake_api = {"messages": [], "resultSizeEstimate": 0}
    with (
        patch(
            "app.domain.workflow_executor.executor.ensure_workflow_google_access_token",
            new_callable=AsyncMock,
            return_value="access-token",
        ),
        patch(
            "app.domain.workflow_executor.executor.gmail_list_messages",
            new_callable=AsyncMock,
            return_value=fake_api,
        ) as mock_gmail,
        patch(
            "app.domain.workflow_executor.executor.gmail_get_message_full",
            new_callable=AsyncMock,
        ),
    ):
        run_res = client.post(f"/api/v1/workflow-definitions/{wf_id}/run")
    assert run_res.status_code == 200
    q = mock_gmail.call_args.kwargs.get("query") or ""
    assert q == "category:primary"
    assert "-category:promotions" not in q


def test_gmail_list_uses_execution_time_zone_when_profile_system(client: TestClient):
    """browser-sent execution_time_zone resolves Gmail day when profile uses system."""
    gmail_id = "n_gmail_exec_tz"
    conn_id = str(uuid.uuid4())
    after_rfc = "2026-03-01T23:00:00Z"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Gmail exec tz",
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
                        "id": gmail_id,
                        "kind": "skill",
                        "skill_type": "gmail_list_messages",
                        "label": "Gmail",
                        "data": {
                            "google_connection_id": conn_id,
                            "max_results": 10,
                            "unread_only": False,
                            "after": after_rfc,
                            "before": None,
                            "required_inputs": [
                                {"key": "after", "type": "string", "value": after_rfc},
                                {"key": "before", "type": "string", "value": None},
                                {"key": "unread_only", "type": "boolean", "value": False},
                                {"key": "query", "type": "string", "value": None},
                                {"key": "max_results", "type": "int", "value": 10},
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": gmail_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    assert client.put("/api/v1/auth/me", json={"settings": {"workflow_time_zone": "system"}}).status_code == 200
    fake_api = {"messages": [], "resultSizeEstimate": 0}
    with (
        patch(
            "app.domain.workflow_executor.executor.ensure_workflow_google_access_token",
            new_callable=AsyncMock,
            return_value="access-token",
        ),
        patch(
            "app.domain.workflow_executor.executor.gmail_list_messages",
            new_callable=AsyncMock,
            return_value=fake_api,
        ) as mock_gmail,
        patch(
            "app.domain.workflow_executor.executor.gmail_get_message_full",
            new_callable=AsyncMock,
        ),
    ):
        run_res = client.post(
            f"/api/v1/workflow-definitions/{wf_id}/run",
            json={"execution_time_zone": "Asia/Tokyo"},
        )
    assert run_res.status_code == 200
    mock_gmail.assert_called_once()
    q = mock_gmail.call_args.kwargs.get("query") or ""
    assert "after:2026/03/02" in q


def test_gmail_list_profile_iana_wins_over_execution_time_zone(client: TestClient):
    client.put("/api/v1/auth/me", json={"settings": {"workflow_time_zone": "Europe/Paris"}})
    gmail_id = "n_gmail_prof_tz"
    conn_id = str(uuid.uuid4())
    after_rfc = "2026-03-01T11:00:00Z"
    workflow_res = client.post(
        "/api/v1/workflow-definitions/",
        json={
            "name": "Gmail profile tz wins",
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
                        "id": gmail_id,
                        "kind": "skill",
                        "skill_type": "gmail_list_messages",
                        "label": "Gmail",
                        "data": {
                            "google_connection_id": conn_id,
                            "max_results": 10,
                            "unread_only": False,
                            "after": after_rfc,
                            "before": None,
                            "required_inputs": [
                                {"key": "after", "type": "string", "value": after_rfc},
                                {"key": "before", "type": "string", "value": None},
                                {"key": "unread_only", "type": "boolean", "value": False},
                                {"key": "query", "type": "string", "value": None},
                                {"key": "max_results", "type": "int", "value": 10},
                            ],
                        },
                        "position": {"x": 200, "y": 0},
                    },
                ],
                "edges": [
                    {
                        "source": "n_start",
                        "target": gmail_id,
                        "source_handle": "signal_out",
                        "target_handle": "trigger",
                    },
                ],
            },
        },
    )
    assert workflow_res.status_code == 201
    wf_id = workflow_res.json()["id"]
    fake_api = {"messages": [], "resultSizeEstimate": 0}
    with (
        patch(
            "app.domain.workflow_executor.executor.ensure_workflow_google_access_token",
            new_callable=AsyncMock,
            return_value="access-token",
        ),
        patch(
            "app.domain.workflow_executor.executor.gmail_list_messages",
            new_callable=AsyncMock,
            return_value=fake_api,
        ) as mock_gmail,
        patch(
            "app.domain.workflow_executor.executor.gmail_get_message_full",
            new_callable=AsyncMock,
        ),
    ):
        run_res = client.post(
            f"/api/v1/workflow-definitions/{wf_id}/run",
            json={"execution_time_zone": "Pacific/Kiritimati"},
        )
    assert run_res.status_code == 200
    q = mock_gmail.call_args.kwargs.get("query") or ""
    assert "after:2026/03/01" in q
    assert "after:2026/03/02" not in q
