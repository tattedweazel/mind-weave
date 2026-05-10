"""Audio File Input skill: artifacts and STT paths mocked, no real bridge calls."""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.domain.services.workflow_executor import WorkflowExecutor
from app.domain.workflow_executor.transcribe_pending import TranscribeWaitKey, complete_transcribe_wait
from app.persistence.tables import AudioFileArtifact, User, WorkflowDefinition, WorkflowRun, utc_now
from tests.executor_scheduled_helpers import execute_scheduled_collect_sse
from tests.workflow_sse_legacy import iter_sse_pairs_as_ndjson

_STT_JSON = {"text": "file transcript", "language": "en", "segments": [], "duration_seconds": 1.25}


def _audio_file_graph(data: dict | None = None) -> dict:
    return {
        "nodes": [
            {"id": "s", "kind": "start", "label": "S", "data": {"text": ""}, "position": {}},
            {
                "id": "af",
                "kind": "skill",
                "skill_type": "audio_file_input",
                "label": "Audio File",
                "data": {"task": "transcribe", **(data or {})},
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
            {"source": "s", "target": "af"},
            {"source": "af", "target": "n_stop", "source_handle": "output", "target_handle": "output"},
        ],
    }


def test_audio_file_artifact_crud_and_validation(client: TestClient) -> None:
    bad = client.post(
        "/api/v1/audio-file-artifacts/",
        files={"file": ("notes.txt", b"not audio", "text/plain")},
    )
    assert bad.status_code == 400
    assert "unsupported audio format" in bad.json()["detail"].lower()

    created = client.post(
        "/api/v1/audio-file-artifacts/",
        files={"file": ("clip.wav", b"RIFF....WAVE", "audio/wav")},
    )
    assert created.status_code == 201
    artifact = created.json()
    assert artifact["filename"] == "clip.wav"
    assert artifact["mime_type"] == "audio/wav"

    listed = client.get("/api/v1/audio-file-artifacts/")
    assert listed.status_code == 200
    assert [row["id"] for row in listed.json()] == [artifact["id"]]

    audio = client.get(f"/api/v1/audio-file-artifacts/{artifact['id']}/audio")
    assert audio.status_code == 200
    assert audio.content == b"RIFF....WAVE"

    deleted = client.delete(f"/api/v1/audio-file-artifacts/{artifact['id']}")
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/audio-file-artifacts/{artifact['id']}").status_code == 404


@pytest.mark.asyncio
@patch("app.domain.workflow_executor.executor.transcribe_audio_bytes", new_callable=AsyncMock)
async def test_audio_file_input_saved_artifact_runs_sync(m_stt: AsyncMock, db_session: Session) -> None:
    m_stt.return_value = _STT_JSON
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"audio_{uid.hex[:8]}", password_hash="h", is_admin=False))
    art_id = uuid.uuid4()
    now = utc_now()
    db_session.add(
        AudioFileArtifact(
            id=art_id,
            user_id=uid,
            filename="clip.wav",
            mime_type="audio/wav",
            size_bytes=12,
            audio_bytes=b"RIFF....WAVE",
            created_at=now,
            updated_at=now,
        )
    )
    wf = WorkflowDefinition(
        id=uuid.uuid4(),
        user_id=uid,
        name="audio file saved",
        graph=_audio_file_graph({"audio_artifact_id": str(art_id)}),
    )
    db_session.add(wf)
    db_session.commit()

    result = await WorkflowExecutor(db_session, uid).run(wf)

    assert result.status == "ok"
    af_result = next(r for r in result.node_results if r.node_id == "af")
    assert af_result.output is not None
    assert af_result.output.kind == "string"
    assert getattr(af_result.output, "text") == "file transcript"
    assert af_result.details["resolved_inputs"]["filename"] == "clip.wav"
    assert af_result.details["resolved_inputs"]["audio_artifact_id"] == str(art_id)
    m_stt.assert_awaited_once()


def test_sync_run_rejects_audio_file_input_without_saved_file(client: TestClient) -> None:
    created = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "audio file prompt wf", "graph": _audio_file_graph()},
    )
    assert created.status_code == 201
    run = client.post(f"/api/v1/workflow-definitions/{created.json()['id']}/run", json={})
    assert run.status_code == 422
    assert "audio file input" in run.json()["detail"].lower()


@patch("app.api.v1.workflow_run_audio_file_input.complete_taken_transcribe_wait", return_value=True)
@patch("app.api.v1.workflow_run_audio_file_input.take_transcribe_wait", return_value=object())
def test_audio_file_input_runtime_upload_route_accepts_multipart(
    mock_take,
    mock_complete,
    client: TestClient,
    db_session: Session,
) -> None:
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    run_id = uuid.uuid4()
    db_session.add(
        WorkflowRun(
            id=run_id,
            workflow_id=uuid.uuid4(),
            started_by_user_id=user.id,
            status="running",
        )
    )
    db_session.commit()

    response = client.post(
        f"/api/v1/workflow-runs/{run_id}/audio-file-input",
        data={"node_id": "af", "for_loop_iteration": "0"},
        files={"file": ("runtime.wav", b"RIFF....WAVE", "audio/wav")},
    )

    assert response.status_code == 204
    mock_take.assert_called_once()
    mock_complete.assert_called_once()


@patch("app.api.v1.workflow_run_audio_file_input.complete_taken_transcribe_wait", return_value=False)
@patch("app.api.v1.workflow_run_audio_file_input.take_transcribe_wait", return_value=object())
def test_audio_file_input_runtime_upload_route_rejects_stale_wait(
    mock_take,
    mock_complete,
    client: TestClient,
    db_session: Session,
) -> None:
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    run_id = uuid.uuid4()
    db_session.add(
        WorkflowRun(
            id=run_id,
            workflow_id=uuid.uuid4(),
            started_by_user_id=user.id,
            status="running",
        )
    )
    db_session.commit()

    response = client.post(
        f"/api/v1/workflow-runs/{run_id}/audio-file-input",
        data={"node_id": "af", "for_loop_iteration": "0"},
        files={"file": ("runtime.wav", b"RIFF....WAVE", "audio/wav")},
    )

    assert response.status_code == 409
    assert "no longer waiting" in response.json()["detail"].lower()
    mock_take.assert_called_once()
    mock_complete.assert_called_once()


@pytest.mark.asyncio
@patch("app.domain.workflow_executor.executor.transcribe_audio_bytes", new_callable=AsyncMock)
async def test_audio_file_input_run_stream_upload_completes(m_stt: AsyncMock, db_session: Session) -> None:
    m_stt.return_value = _STT_JSON
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"audio_stream_{uid.hex[:8]}", password_hash="h", is_admin=False))
    wf_uuid = uuid.uuid4()
    db_session.add(
        WorkflowDefinition(id=wf_uuid, user_id=uid, name="audio file stream", graph=_audio_file_graph()),
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

    def _complete_af_upload(en: str, pl: dict[str, Any]) -> None:
        if (
            en == "input_required"
            and pl.get("kind") == "audio_file_input"
            and str(pl.get("node_id")) == "af"
        ):
            key = TranscribeWaitKey(
                run_id=uuid.UUID(str(pl["run_id"])),
                node_id="af",
                for_loop_id=None,
                iteration=0,
            )
            assert complete_transcribe_wait(
                key,
                b"RIFF....WAVE",
                filename="runtime.wav",
                content_type="audio/wav",
            )

    ex = WorkflowExecutor(db_session, uid)
    _, sse = await execute_scheduled_collect_sse(
        ex,
        wf,
        persist_run_record=persist,
        on_sse_event=_complete_af_upload,
    )
    events = iter_sse_pairs_as_ndjson(sse)
    saw_input = False
    node_ok = False
    end_ok = False
    t0 = time.monotonic()
    for ev in events:
        if ev.get("event") == "input_required" and ev.get("kind") == "audio_file_input":
            assert time.monotonic() - t0 < 5.0
            saw_input = True
        if ev.get("event") == "node_end" and ev.get("node_id") == "af":
            out = (ev.get("result") or {}).get("output") or {}
            node_ok = out.get("kind") == "string" and out.get("text") == "file transcript"
        if ev.get("event") == "end" and (ev.get("result") or {}).get("status") == "ok":
            end_ok = True

    assert saw_input and node_ok and end_ok
    m_stt.assert_awaited_once()


@pytest.mark.asyncio
@patch("app.domain.workflow_executor.executor.transcribe_audio_bytes", new_callable=AsyncMock)
async def test_audio_file_input_run_stream_timeout_clears_pending_wait(
    m_stt: AsyncMock,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "STT_AUDIO_WAIT_TIMEOUT", 0.01)
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"audio_timeout_{uid.hex[:8]}", password_hash="h", is_admin=False))
    wf_uuid = uuid.uuid4()
    db_session.add(
        WorkflowDefinition(id=wf_uuid, user_id=uid, name="audio file timeout", graph=_audio_file_graph()),
    )
    db_session.commit()
    wf = db_session.get(WorkflowDefinition, wf_uuid)
    assert wf is not None

    run_uid = uuid.uuid4()
    db_session.add(
        WorkflowRun(id=run_uid, workflow_id=wf.id, started_by_user_id=uid, status="queued")
    )
    db_session.commit()
    persist = db_session.get(WorkflowRun, run_uid)
    assert persist is not None

    _, sse = await execute_scheduled_collect_sse(WorkflowExecutor(db_session, uid), wf, persist_run_record=persist)
    events = iter_sse_pairs_as_ndjson(sse)
    saw_input = False
    run_id: uuid.UUID | None = None
    terminal_status: str | None = None
    for ev in events:
        if ev.get("event") == "input_required" and ev.get("kind") == "audio_file_input":
            run_id = uuid.UUID(str(ev["run_id"]))
            saw_input = True
        if ev.get("event") == "node_end" and ev.get("node_id") == "af":
            assert (ev.get("result") or {}).get("status") == "error"
            assert "timed out" in ((ev.get("result") or {}).get("error") or "").lower()
        if ev.get("event") == "end":
            terminal_status = (ev.get("result") or {}).get("status")

    assert saw_input and terminal_status in {"error", "partial"} and run_id is not None
    assert not complete_transcribe_wait(
        TranscribeWaitKey(run_id=run_id, node_id="af", for_loop_id=None, iteration=0),
        b"RIFF....WAVE",
        filename="late.wav",
        content_type="audio/wav",
    )
    m_stt.assert_not_awaited()


@pytest.mark.asyncio
async def test_audio_file_input_run_stream_abort_marks_run_error_and_clears_wait(db_session: Session) -> None:
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"audio_abort_{uid.hex[:8]}", password_hash="h", is_admin=False))
    wf_uuid = uuid.uuid4()
    db_session.add(
        WorkflowDefinition(id=wf_uuid, user_id=uid, name="audio file abort", graph=_audio_file_graph()),
    )
    db_session.commit()
    wf = db_session.get(WorkflowDefinition, wf_uuid)
    assert wf is not None

    run_uid = uuid.uuid4()
    db_session.add(
        WorkflowRun(id=run_uid, workflow_id=wf.id, started_by_user_id=uid, status="queued"),
    )
    db_session.commit()
    persist = db_session.get(WorkflowRun, run_uid)
    assert persist is not None

    executor = WorkflowExecutor(db_session, uid)
    collected: list[tuple[str, dict[str, object]]] = []

    async def pub(en: str, payload: dict[str, object]) -> int:
        collected.append((en, dict(payload)))
        return len(collected)

    task = asyncio.create_task(
        executor.execute_scheduled_run(
            wf,
            persist_run_record=persist,
            sse_publish=pub,
        )
    )

    captured_id: uuid.UUID | None = None
    while not task.done():
        await asyncio.sleep(0)
        for en, payload in list(collected):
            if en == "input_required" and payload.get("kind") == "audio_file_input":
                captured_id = uuid.UUID(str(payload["run_id"]))
                task.cancel()
                break
        if captured_id is not None:
            break
        await asyncio.sleep(0.001)

    with pytest.raises(asyncio.CancelledError):
        await task

    assert captured_id is not None
    db_session.expire_all()
    run = db_session.get(WorkflowRun, captured_id)
    assert run is not None
    assert run.status == "canceled"
    assert not complete_transcribe_wait(
        TranscribeWaitKey(run_id=captured_id, node_id="af", for_loop_id=None, iteration=0),
        b"RIFF....WAVE",
        filename="late.wav",
        content_type="audio/wav",
    )
