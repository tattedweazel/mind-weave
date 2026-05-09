"""Voice input (transcribe_audio): STT and resume path mocked — no real bridge or model."""

from __future__ import annotations

import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session

from app.domain.services.workflow_executor import WorkflowExecutor
from app.domain.workflow_executor.transcribe_pending import (
    TranscribeWaitKey,
    complete_transcribe_wait,
)
from app.persistence.tables import User, WorkflowDefinition, WorkflowRun
from tests.executor_scheduled_helpers import execute_scheduled_collect_sse
from tests.workflow_sse_legacy import iter_sse_pairs_as_ndjson

_TRANSCRIBE_GRAPH = {
    "nodes": [
        {"id": "s", "kind": "start", "label": "S", "data": {"text": ""}, "position": {}},
        {
            "id": "tr",
            "kind": "skill",
            "skill_type": "transcribe_audio",
            "label": "Voice",
            "data": {"task": "transcribe"},
            "position": {},
        },
        {
            "id": "n_stop",
            "kind": "stop",
            "label": "Stop",
            "data": {"required_outputs": [{"key": "output", "type": "string"}]},
            "position": {},
        },
    ],
    "edges": [
        {"source": "s", "target": "tr"},
        {"source": "tr", "target": "n_stop", "source_handle": "output", "target_handle": "output"},
    ],
}

_STT_JSON = {"text": "hello from mock", "language": "en", "segments": []}


def _create_transcribe_workflow(client: TestClient) -> str:
    r = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "transcribe test wf", "graph": _TRANSCRIBE_GRAPH},
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_sync_run_rejects_transcribe_without_output_override(client: TestClient):
    wf_id = _create_transcribe_workflow(client)
    r = client.post(f"/api/v1/workflow-definitions/{wf_id}/run", json={})
    assert r.status_code == 422
    detail = (r.json().get("detail") or "").lower()
    assert "transcribe_audio" in detail or "voice" in detail or "streaming" in detail


@pytest.mark.asyncio
@patch("app.domain.workflow_executor.executor.transcribe_audio_bytes", new_callable=AsyncMock)
async def test_transcribe_run_stream_emits_input_required_and_completes(m_stt: AsyncMock, db_session: Session) -> None:
    """Same event loop: flush input_required, complete bytes wait, then mocked STT returns transcript."""
    m_stt.return_value = _STT_JSON
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"stt_{uid.hex[:8]}", password_hash="h", is_admin=False))
    wf_uuid = uuid.uuid4()
    db_session.add(
        WorkflowDefinition(id=wf_uuid, user_id=uid, name="transcribe stream", graph=_TRANSCRIBE_GRAPH),
    )
    db_session.commit()
    wf = db_session.get(WorkflowDefinition, wf_uuid)
    assert wf is not None

    run_uid = uuid.uuid4()
    db_session.add(
        WorkflowRun(
            id=run_uid,
            workflow_id=wf.id,
            started_by_user_id=uid,
            status="queued",
        )
    )
    db_session.commit()
    persist = db_session.get(WorkflowRun, run_uid)
    assert persist is not None

    ex = WorkflowExecutor(db_session, uid)

    def _complete_voice_upload(en: str, pl: dict[str, Any]) -> None:
        if (
            en == "input_required"
            and pl.get("kind") == "transcribe_audio"
            and str(pl.get("node_id")) == "tr"
        ):
            k = TranscribeWaitKey(
                run_id=uuid.UUID(str(pl["run_id"])),
                node_id="tr",
                for_loop_id=None,
                iteration=0,
            )
            assert complete_transcribe_wait(k, b"\x00\x01")

    _, sse = await execute_scheduled_collect_sse(
        ex, wf, persist_run_record=persist, on_sse_event=_complete_voice_upload
    )

    saw_input = False
    tr_end_ok = False
    end_ok = False
    t0 = time.monotonic()
    for ev in iter_sse_pairs_as_ndjson(sse):
        if ev.get("event") == "input_required" and ev.get("node_id") == "tr":
            # Must not be delayed until executor keepalive waits (~25s); see asyncio.sleep(0) after spawning tasks.
            assert time.monotonic() - t0 < 5.0, "input_required should flush immediately after node_start"
            saw_input = True
        if ev.get("event") == "node_end" and ev.get("node_id") == "tr":
            out = (ev.get("result") or {}).get("output") or {}
            if out.get("kind") == "string" and "hello from mock" in (out.get("text") or ""):
                tr_end_ok = True
        if ev.get("event") == "end" and (ev.get("result") or {}).get("status") == "ok":
            end_ok = True
    m_stt.assert_awaited_once()
    assert saw_input and tr_end_ok and end_ok
