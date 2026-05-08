"""fetch_url skill: httpx and cache are mocked; no real network."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, select

from app.domain.services.workflow_executor import WorkflowExecutor
from app.persistence.tables import UrlFetchCache, User, WorkflowDefinition

_SUCCESS = {
    "status_code": 200,
    "final_url": "https://example.com/",
    "headers": {"content-type": "text/plain"},
    "body": "hello",
    "fetched_at": "2026-01-01T00:00:00Z",
    "duration_ms": 5,
    "cached": False,
}


def _fetch_url_graph() -> dict:
    return {
        "nodes": [
            {"id": "s", "kind": "start", "label": "S", "data": {}, "position": {}},
            {
                "id": "f",
                "kind": "skill",
                "skill_type": "fetch_url",
                "label": "Fetch",
                "data": {
                    "url": "https://example.com/",
                    "method": "GET",
                    "headers": {},
                    "cache_policy": "default",
                    "required_inputs": [{"key": "url", "type": "string", "value": None}],
                },
                "position": {},
            },
            {
                "id": "st",
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                "position": {},
            },
        ],
        "edges": [
            {"source": "s", "target": "f"},
            {"source": "f", "target": "st", "source_handle": "output", "target_handle": "output"},
        ],
    }


@pytest.mark.asyncio
async def test_fetch_url_skill_runs_with_mocked_http(db_session: Session):
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"fu_{uid.hex[:8]}", password_hash="h", is_admin=False))
    wf_id = uuid.uuid4()
    db_session.add(WorkflowDefinition(id=wf_id, user_id=uid, name="fetch test", graph=_fetch_url_graph()))
    db_session.commit()
    wf_row = db_session.get(WorkflowDefinition, wf_id)
    assert wf_row is not None

    with patch(
        "app.domain.workflow_executor.executor.perform_http_fetch",
        new_callable=AsyncMock,
    ) as m_fetch:
        m_fetch.return_value = dict(_SUCCESS)
        ex = WorkflowExecutor(db_session, uid)
        result = await ex.run(wf_row)

    assert result.status == "ok"
    m_fetch.assert_awaited_once()
    f_results = [nr for nr in result.node_results if nr.node_id == "f" and nr.status == "ok"]
    assert len(f_results) == 1
    out = f_results[0].output
    assert out is not None
    assert out.kind == "dictionary"
    assert out.data.get("body") == "hello"
    assert out.data.get("cached") is False


@pytest.mark.asyncio
async def test_fetch_url_default_uses_cache_on_second_run(db_session: Session):
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"fc_{uid.hex[:8]}", password_hash="h", is_admin=False))
    wf_id = uuid.uuid4()
    db_session.add(WorkflowDefinition(id=wf_id, user_id=uid, name="fetch cache", graph=_fetch_url_graph()))
    db_session.commit()
    wf_row = db_session.get(WorkflowDefinition, wf_id)
    assert wf_row is not None
    ex = WorkflowExecutor(db_session, uid)

    with patch(
        "app.domain.workflow_executor.executor.perform_http_fetch",
        new_callable=AsyncMock,
    ) as m_fetch:
        m_fetch.return_value = dict(_SUCCESS)
        r1 = await ex.run(wf_row)
        r2 = await ex.run(wf_row)

    assert r1.status == "ok" and r2.status == "ok"
    assert m_fetch.await_count == 1
    f2 = [nr for nr in r2.node_results if nr.node_id == "f" and nr.status == "ok"][0]
    assert f2.output is not None
    assert f2.output.data.get("cached") is True
    rows = db_session.exec(select(UrlFetchCache).where(UrlFetchCache.user_id == uid)).all()
    assert len(rows) == 1


def test_cache_key_ignores_header_key_order():
    from app.domain.workflow_executor.fetch_url_runtime import compute_cache_key, normalize_headers

    a = compute_cache_key("https://a.com", "GET", normalize_headers({"b": "2", "a": "1"}))
    b = compute_cache_key("https://a.com", "GET", normalize_headers({"a": "1", "b": "2"}))
    assert a == b
