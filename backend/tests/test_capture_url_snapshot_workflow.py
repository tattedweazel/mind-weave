"""capture_url_snapshot skill: Playwright is mocked; no real browser."""

from __future__ import annotations

import base64
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session, select

from app.domain.services.workflow_executor import WorkflowExecutor
from app.persistence.tables import UrlSnapshotArtifact, UrlSnapshotCache, User, WorkflowDefinition

_MIN_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+lmfkAAAAASUVORK5CYII="
)

_SUCCESS_RAW = {
    "_png_bytes": base64.b64decode(_MIN_PNG_B64),
    "_width": 1,
    "_height": 1,
    "final_url": "https://example.com/",
    "captured_at": "2026-01-01T00:00:00Z",
    "duration_ms": 12,
}


def _capture_graph(policy: str = "default") -> dict:
    return {
        "nodes": [
            {"id": "s", "kind": "start", "label": "S", "data": {}, "position": {}},
            {
                "id": "c",
                "kind": "skill",
                "skill_type": "capture_url_snapshot",
                "label": "Cap",
                "data": {
                    "url": "https://example.com/",
                    "full_page": True,
                    "wait_until": "load",
                    "cache_policy": policy,
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
            {"source": "s", "target": "c"},
            {"source": "c", "target": "st", "source_handle": "output", "target_handle": "output"},
        ],
    }


@pytest.mark.asyncio
async def test_capture_url_snapshot_runs_with_mocked_playwright(db_session: Session):
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"cs_{uid.hex[:8]}", password_hash="h", is_admin=False))
    wf_id = uuid.uuid4()
    db_session.add(WorkflowDefinition(id=wf_id, user_id=uid, name="cap test", graph=_capture_graph("bypass")))
    db_session.commit()
    wf_row = db_session.get(WorkflowDefinition, wf_id)
    assert wf_row is not None

    with patch(
        "app.domain.workflow_executor.executor.perform_url_snapshot_capture",
        new_callable=AsyncMock,
    ) as m_cap:
        m_cap.return_value = dict(_SUCCESS_RAW)
        ex = WorkflowExecutor(db_session, uid)
        result = await ex.run(wf_row)

    assert result.status == "ok"
    m_cap.assert_awaited_once()
    c_results = [nr for nr in result.node_results if nr.node_id == "c" and nr.status == "ok"]
    assert len(c_results) == 1
    out = c_results[0].output
    assert out is not None
    assert out.kind == "dictionary"
    img = out.data.get("image")
    assert isinstance(img, dict)
    assert "artifact_id" in img
    assert out.data.get("cached") is False
    arts = db_session.exec(select(UrlSnapshotArtifact).where(UrlSnapshotArtifact.user_id == uid)).all()
    assert len(arts) == 1
    assert arts[0].final_url == "https://example.com/"


@pytest.mark.asyncio
async def test_capture_url_default_uses_cache_on_second_run(db_session: Session):
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"cc_{uid.hex[:8]}", password_hash="h", is_admin=False))
    wf_id = uuid.uuid4()
    db_session.add(WorkflowDefinition(id=wf_id, user_id=uid, name="cap cache", graph=_capture_graph("default")))
    db_session.commit()
    wf_row = db_session.get(WorkflowDefinition, wf_id)
    assert wf_row is not None
    ex = WorkflowExecutor(db_session, uid)

    with patch(
        "app.domain.workflow_executor.executor.perform_url_snapshot_capture",
        new_callable=AsyncMock,
    ) as m_cap:
        m_cap.return_value = dict(_SUCCESS_RAW)
        r1 = await ex.run(wf_row)
        r2 = await ex.run(wf_row)

    assert r1.status == "ok" and r2.status == "ok"
    assert m_cap.await_count == 1
    c2 = [nr for nr in r2.node_results if nr.node_id == "c" and nr.status == "ok"][0]
    assert c2.output is not None
    assert c2.output.data.get("cached") is True
    assert c2.output.data.get("image", {}).get("width") == 1
    caches = db_session.exec(select(UrlSnapshotCache).where(UrlSnapshotCache.user_id == uid)).all()
    assert len(caches) == 1
