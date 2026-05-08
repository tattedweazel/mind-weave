"""Provider-abstracted Transcribe File skill: full-stack tests with mocked externals.

Covers:

* Provider directory endpoint + provider abstraction (`local_whisper`, `assemblyai`).
* Executor branches: pre-attached artifact + sync provider, runtime upload + async provider,
  cancellation/disconnect leaving the job non-terminal, error on missing API key.
* Persistence: ``transcription_jobs`` lifecycle via ``TranscriptionJobService`` and the
  lifespan poller (``poll_once``).
* Reattach stream: replays node logs and transcription_job state for the run owner only.
* Runtime upload route mirrors the audio_file_input route (mocked wait-key plumbing).

NO real network / STT bridge calls are made. The AssemblyAI adapter is exercised through
``httpx.MockTransport`` patched onto ``_build_async_client``; the local_whisper adapter
patches ``transcribe_audio_bytes`` directly.
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.core.config import settings
from app.domain.services.audio_file_artifact_service import AudioFileArtifactService
from app.domain.services.transcription_job_poller import TranscriptionJobPoller
from app.domain.services.transcription_job_service import (
    TranscriptionJobService,
    list_pending_jobs_for_poller,
)
from app.domain.services.workflow_executor import WorkflowExecutor
from app.domain.workflow_executor.transcribe_pending import (
    TranscribeWaitKey,
    complete_transcribe_wait,
)
from app.persistence.tables import (
    AudioFileArtifact,
    NodeRunLog,
    TranscriptionJob,
    User,
    WorkflowDefinition,
    WorkflowRun,
    utc_now,
)
from app.providers.transcription import (
    SpeechTranscriptionProvider,
    enabled_provider_ids,
    get_speech_provider,
    list_provider_descriptors,
)
from app.providers.transcription.assemblyai import (
    AssemblyAIProvider,
    _build_assemblyai_transcript,
    _build_create_payload,
)
from app.providers.transcription.base import (
    PollResult,
    SubmissionResult,
    TranscriptionOptions,
    TranscriptionProviderError,
)
from app.providers.transcription.local_whisper import LocalWhisperProvider

_STT_BRIDGE_RESPONSE: dict[str, Any] = {
    "text": "hello world",
    "language": "en",
    "duration_seconds": 1.5,
    "model": "tiny",
    "segments": [
        {"start": 0.0, "end": 0.7, "text": "hello"},
        {"start": 0.7, "end": 1.5, "text": "world"},
    ],
}


def _transcribe_file_graph(data: dict | None = None) -> dict:
    base = {"provider": "local_whisper", **(data or {})}
    return {
        "nodes": [
            {"id": "s", "kind": "start", "label": "S", "data": {"text": ""}, "position": {}},
            {
                "id": "tf",
                "kind": "skill",
                "skill_type": "transcribe_file",
                "label": "Transcribe File",
                "data": base,
                "position": {},
            },
            {
                "id": "n_stop",
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "dictionary"}]},
                "position": {},
            },
        ],
        "edges": [
            {"source": "s", "target": "tf"},
            {"source": "tf", "target": "n_stop", "source_handle": "output", "target_handle": "output"},
        ],
    }


# -----------------------------------------------------------------------------
# Provider registry / API endpoint
# -----------------------------------------------------------------------------


def test_provider_registry_default_includes_local_whisper_and_assemblyai() -> None:
    assert enabled_provider_ids()[:2] == ["local_whisper", "assemblyai"]
    descriptors = list_provider_descriptors()
    ids = {d.provider_id for d in descriptors}
    assert ids == {"local_whisper", "assemblyai"}
    aai = next(d for d in descriptors if d.provider_id == "assemblyai")
    assert aai.requires_api_key is True
    lw = next(d for d in descriptors if d.provider_id == "local_whisper")
    assert lw.requires_api_key is False
    aai_models = aai.models
    assert {m.id for m in aai_models} == {"universal-3-pro", "universal-2"}
    assert sum(1 for m in aai_models if m.is_default) == 1
    assert lw.models == ()


def test_get_speech_provider_unknown_raises() -> None:
    with pytest.raises(TranscriptionProviderError):
        get_speech_provider("nope_provider")


def test_transcription_providers_endpoint_returns_flat_list(client: TestClient) -> None:
    resp = client.get("/api/v1/transcription/providers")
    assert resp.status_code == 200
    body = resp.json()
    assert isinstance(body, list)
    assert any(p["id"] == "local_whisper" for p in body)
    lw = next(p for p in body if p["id"] == "local_whisper")
    assert lw["is_synchronous"] is True
    assert lw["requires_api_key"] is False
    assert "label" in lw and "capabilities" in lw
    aai = next(p for p in body if p["id"] == "assemblyai")
    assert aai["is_synchronous"] is False
    assert aai["requires_api_key"] is True
    assert aai["api_key_field"] == "assemblyai"
    aai_models = aai.get("models") or []
    assert {m["id"] for m in aai_models} == {"universal-3-pro", "universal-2"}
    lw_models = next(p for p in body if p["id"] == "local_whisper").get("models") or []
    assert lw_models == []


# -----------------------------------------------------------------------------
# Provider adapter: local_whisper
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.providers.transcription.local_whisper.transcribe_audio_bytes", new_callable=AsyncMock)
async def test_local_whisper_provider_normalizes_to_transcript_primitive(m_stt: AsyncMock) -> None:
    m_stt.return_value = _STT_BRIDGE_RESPONSE
    provider = LocalWhisperProvider()
    result = await provider.submit(
        audio=b"RIFF....WAVE",
        filename="clip.wav",
        content_type="audio/wav",
        options=TranscriptionOptions(language=None, task="transcribe"),
        api_key=None,
    )
    assert result.status == "completed"
    assert result.transcript is not None
    primitive = result.transcript
    assert primitive["type"] == "transcript"
    assert primitive["full_text"] == "hello world"
    assert primitive["provider"] == "local_whisper"
    assert primitive["language"] == "en"
    assert len(primitive["segments"]) == 2
    assert primitive["segments"][0]["start_ms"] == 0
    assert primitive["segments"][0]["end_ms"] == 700


@pytest.mark.asyncio
async def test_local_whisper_provider_poll_is_noop() -> None:
    provider = LocalWhisperProvider()
    result = await provider.poll(
        provider_job_id="lw_xyz",
        options=TranscriptionOptions(),
        api_key=None,
    )
    assert result.status == "completed"
    assert result.transcript is None


@pytest.mark.asyncio
@patch("app.providers.transcription.local_whisper.transcribe_audio_bytes", new_callable=AsyncMock)
async def test_local_whisper_provider_wraps_bridge_errors(m_stt: AsyncMock) -> None:
    from app.providers.stt_bridge import SttBridgeError

    m_stt.side_effect = SttBridgeError("offline")
    provider = LocalWhisperProvider()
    with pytest.raises(TranscriptionProviderError) as exc_info:
        await provider.submit(
            audio=b"RIFF....WAVE",
            filename="x.wav",
            content_type="audio/wav",
            options=TranscriptionOptions(),
            api_key=None,
        )
    assert exc_info.value.retryable is True


# -----------------------------------------------------------------------------
# Provider adapter: assemblyai
# -----------------------------------------------------------------------------


def _aai_transport(handler_log: list[tuple[str, str]]) -> httpx.MockTransport:
    """Build a mock transport for AssemblyAI v2 endpoints used by `submit` and `poll`."""

    state: dict[str, Any] = {"poll_count": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        handler_log.append((request.method, request.url.path))
        if request.method == "POST" and request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://aai.example/upload/abc"})
        if request.method == "POST" and request.url.path == "/v2/transcript":
            return httpx.Response(200, json={"id": "tr_test_123", "status": "queued"})
        if request.method == "GET" and request.url.path == "/v2/transcript/tr_test_123":
            state["poll_count"] += 1
            if state["poll_count"] < 2:
                return httpx.Response(200, json={"id": "tr_test_123", "status": "processing"})
            return httpx.Response(
                200,
                json={
                    "id": "tr_test_123",
                    "status": "completed",
                    "text": "hello world",
                    "language_code": "en",
                    "audio_duration": 1.5,
                    "speech_model": "best",
                    "utterances": [
                        {"speaker": "A", "start": 0, "end": 700, "text": "hello"},
                        {"speaker": "B", "start": 700, "end": 1500, "text": "world"},
                    ],
                    "words": [
                        {"text": "hello", "start": 0, "end": 700, "speaker": "A", "confidence": 0.95},
                        {"text": "world", "start": 700, "end": 1500, "speaker": "B", "confidence": 0.91},
                    ],
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@pytest.mark.asyncio
async def test_assemblyai_provider_submit_then_poll_full_cycle() -> None:
    handler_log: list[tuple[str, str]] = []
    transport = _aai_transport(handler_log)

    def fake_client(*, base_url: str, api_key: str, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={"authorization": api_key},
        )

    with patch("app.providers.transcription.assemblyai._build_async_client", fake_client):
        provider = AssemblyAIProvider()
        opts = TranscriptionOptions(diarization_enabled=True, include_word_timestamps=True)
        sub = await provider.submit(
            audio=b"audio-bytes",
            filename="clip.wav",
            content_type="audio/wav",
            options=opts,
            api_key="fake-aai-key",
        )
        assert sub.status == "queued"
        assert sub.provider_job_id == "tr_test_123"

        first_poll = await provider.poll(
            provider_job_id="tr_test_123",
            options=opts,
            api_key="fake-aai-key",
        )
        assert first_poll.status == "processing"

        second_poll = await provider.poll(
            provider_job_id="tr_test_123",
            options=opts,
            api_key="fake-aai-key",
        )
        assert second_poll.status == "completed"
        assert second_poll.transcript is not None
        primitive = second_poll.transcript
        assert primitive["full_text"] == "hello world"
        assert primitive["provider"] == "assemblyai"
        assert primitive["metadata"]["diarization_enabled"] is True
        assert len(primitive["segments"]) == 2
        assert primitive["segments"][0]["speaker"] == "A"
        assert len(primitive["words"]) == 2
        assert primitive["words"][1]["speaker"] == "B"

    assert ("POST", "/v2/upload") in handler_log
    assert ("POST", "/v2/transcript") in handler_log
    assert sum(1 for m, p in handler_log if m == "GET") == 2


@pytest.mark.asyncio
async def test_assemblyai_provider_requires_api_key() -> None:
    provider = AssemblyAIProvider()
    with pytest.raises(TranscriptionProviderError):
        await provider.submit(
            audio=b"x",
            filename="c.wav",
            content_type="audio/wav",
            options=TranscriptionOptions(),
            api_key=None,
        )


@pytest.mark.asyncio
async def test_assemblyai_provider_surfaces_provider_error_status() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.startswith("/v2/transcript/"):
            return httpx.Response(
                200,
                json={"id": "tr_err", "status": "error", "error": "audio decoded but unintelligible"},
            )
        return httpx.Response(404)

    transport = httpx.MockTransport(handler)

    def fake_client(*, base_url: str, api_key: str, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport,
        )

    with patch("app.providers.transcription.assemblyai._build_async_client", fake_client):
        provider = AssemblyAIProvider()
        result = await provider.poll(
            provider_job_id="tr_err",
            options=TranscriptionOptions(),
            api_key="ak",
        )
        assert result.status == "error"
        assert result.error_message and "unintelligible" in result.error_message


def test_assemblyai_build_create_payload_includes_speech_models(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _build_create_payload(
        audio_url="https://cdn.example/u.wav",
        options=TranscriptionOptions(),
    )
    assert payload["audio_url"] == "https://cdn.example/u.wav"
    assert payload["speech_models"] == ["universal-3-pro"]
    assert payload["punctuate"] is True

    monkeypatch.setattr(settings, "ASSEMBLYAI_SPEECH_MODELS", ["universal-2"])
    payload2 = _build_create_payload(audio_url="https://x", options=TranscriptionOptions())
    assert payload2["speech_models"] == ["universal-2"]

    monkeypatch.setattr(settings, "ASSEMBLYAI_SPEECH_MODELS", ["universal-3-pro"])
    payload_explicit = _build_create_payload(
        audio_url="https://y",
        options=TranscriptionOptions(provider_model_id="universal-2"),
    )
    assert payload_explicit["speech_models"] == ["universal-2"]


def test_assemblyai_normalization_reads_speech_models_array() -> None:
    primitive = _build_assemblyai_transcript(
        api_response={
            "text": "ok",
            "speech_models": ["universal-3-pro"],
            "audio_duration": 1.0,
        },
        options=TranscriptionOptions(),
    )
    assert primitive["metadata"]["model"] == "universal-3-pro"


def test_assemblyai_normalization_prefers_speech_models_over_legacy_acoustic_model() -> None:
    """AAI often returns ``acoustic_model`` = assemblyai_default alongside Universal tiers."""
    primitive = _build_assemblyai_transcript(
        api_response={
            "text": "ok",
            "speech_model": None,
            "acoustic_model": "assemblyai_default",
            "speech_models": ["universal-3-pro"],
            "audio_duration": 1.0,
        },
        options=TranscriptionOptions(),
    )
    assert primitive["metadata"]["model"] == "universal-3-pro"
    assert primitive["metadata"]["provider_metadata"]["speech_model"] == "universal-3-pro"


def test_assemblyai_normalization_prefers_speech_model_used() -> None:
    primitive = _build_assemblyai_transcript(
        api_response={
            "text": "ok",
            "speech_model_used": "universal-2",
            "speech_model": "universal-3-pro",
            "speech_models": ["universal-3-pro"],
            "acoustic_model": "assemblyai_default",
            "audio_duration": 1.0,
        },
        options=TranscriptionOptions(),
    )
    assert primitive["metadata"]["model"] == "universal-2"


def test_assemblyai_normalization_handles_minimal_response() -> None:
    primitive = _build_assemblyai_transcript(
        api_response={"id": "x", "status": "completed", "text": "hi"},
        options=TranscriptionOptions(),
    )
    assert primitive["full_text"] == "hi"
    assert len(primitive["segments"]) == 1
    assert primitive["segments"][0]["start_ms"] == 0
    assert primitive["words"] == []  # no word timestamps when option disabled


# -----------------------------------------------------------------------------
# Executor: synchronous local_whisper path (saved artifact)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.providers.transcription.local_whisper.transcribe_audio_bytes", new_callable=AsyncMock)
async def test_transcribe_file_saved_artifact_runs_with_local_whisper(
    m_stt: AsyncMock,
    db_session: Session,
) -> None:
    m_stt.return_value = _STT_BRIDGE_RESPONSE
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"tf_{uid.hex[:8]}", password_hash="h", is_admin=False))
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
            transient=False,
            created_at=now,
            updated_at=now,
        )
    )
    wf = WorkflowDefinition(
        id=uuid.uuid4(),
        user_id=uid,
        name="tf saved",
        graph=_transcribe_file_graph(
            {"audio_artifact_id": str(art_id), "diarization_enabled": False, "include_word_timestamps": False},
        ),
    )
    db_session.add(wf)
    db_session.commit()

    result = await WorkflowExecutor(db_session, uid).run(wf)
    assert result.status == "ok"
    tf_result = next(r for r in result.node_results if r.node_id == "tf")
    assert tf_result.output is not None
    assert tf_result.output.kind == "dictionary"
    primitive = tf_result.output.data
    assert primitive["type"] == "transcript"
    assert primitive["full_text"] == "hello world"
    assert primitive["provider"] == "local_whisper"
    m_stt.assert_awaited_once()

    # transcription_jobs row exists and is terminal.
    jobs = db_session.exec(select(TranscriptionJob).where(TranscriptionJob.user_id == uid)).all()
    assert len(jobs) == 1
    assert jobs[0].status == "completed"
    assert jobs[0].provider == "local_whisper"


def test_sync_run_rejects_transcribe_file_without_saved_file(client: TestClient) -> None:
    created = client.post(
        "/api/v1/workflow-definitions/",
        json={"name": "tf prompt wf", "graph": _transcribe_file_graph()},
    )
    assert created.status_code == 201
    run = client.post(f"/api/v1/workflow-definitions/{created.json()['id']}/run", json={})
    assert run.status_code == 422
    detail_lower = run.json()["detail"].lower()
    assert "transcribe" in detail_lower


# -----------------------------------------------------------------------------
# Executor: async assemblyai path (saved artifact)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_file_saved_artifact_runs_with_assemblyai(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ASSEMBLYAI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ASSEMBLYAI_POLL_INTERVAL", 0.05)
    monkeypatch.setattr(settings, "ASSEMBLYAI_JOB_TIMEOUT", 30.0)
    monkeypatch.setattr(
        settings,
        "TRANSCRIPTION_PROVIDERS_ENABLED",
        ["local_whisper", "assemblyai"],
    )
    handler_log: list[tuple[str, str]] = []
    transport = _aai_transport(handler_log)

    def fake_client(*, base_url: str, api_key: str, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport,
        )

    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"tfa_{uid.hex[:8]}", password_hash="h", is_admin=False))
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
            transient=False,
            created_at=now,
            updated_at=now,
        )
    )
    wf = WorkflowDefinition(
        id=uuid.uuid4(),
        user_id=uid,
        name="tf assemblyai saved",
        graph=_transcribe_file_graph(
            {
                "provider": "assemblyai",
                "audio_artifact_id": str(art_id),
                "diarization_enabled": True,
                "include_word_timestamps": True,
            },
        ),
    )
    db_session.add(wf)
    db_session.commit()

    with patch("app.providers.transcription.assemblyai._build_async_client", fake_client):
        result = await WorkflowExecutor(db_session, uid).run(wf)

    assert result.status == "ok"
    tf_result = next(r for r in result.node_results if r.node_id == "tf")
    assert tf_result.output is not None
    primitive = tf_result.output.data
    assert primitive["provider"] == "assemblyai"
    assert primitive["full_text"] == "hello world"
    assert primitive["metadata"]["diarization_enabled"] is True

    jobs = db_session.exec(select(TranscriptionJob).where(TranscriptionJob.user_id == uid)).all()
    assert len(jobs) == 1
    assert jobs[0].status == "completed"
    assert jobs[0].provider == "assemblyai"
    assert jobs[0].provider_job_id == "tr_test_123"


# -----------------------------------------------------------------------------
# Executor: missing API key surfaces a friendly error (no upload happens)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_transcribe_file_missing_assemblyai_key_short_circuits(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ASSEMBLYAI_API_KEY", "")
    monkeypatch.setattr(
        settings,
        "TRANSCRIPTION_PROVIDERS_ENABLED",
        ["local_whisper", "assemblyai"],
    )
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"tfm_{uid.hex[:8]}", password_hash="h", is_admin=False))
    art_id = uuid.uuid4()
    now = utc_now()
    db_session.add(
        AudioFileArtifact(
            id=art_id,
            user_id=uid,
            filename="c.wav",
            mime_type="audio/wav",
            size_bytes=12,
            audio_bytes=b"RIFF....WAVE",
            transient=False,
            created_at=now,
            updated_at=now,
        )
    )
    wf = WorkflowDefinition(
        id=uuid.uuid4(),
        user_id=uid,
        name="tf missing key",
        graph=_transcribe_file_graph(
            {"provider": "assemblyai", "audio_artifact_id": str(art_id)},
        ),
    )
    db_session.add(wf)
    db_session.commit()

    result = await WorkflowExecutor(db_session, uid).run(wf)
    # The workflow as a whole reports "partial" because the Stop node never runs after
    # the Transcribe File node fails; the relevant assertion is that the TF node itself
    # failed with the expected message.
    assert result.status in {"error", "partial"}
    tf_result = next(r for r in result.node_results if r.node_id == "tf")
    assert tf_result.status == "error"
    assert "api key" in (tf_result.error or "").lower()


@pytest.mark.asyncio
async def test_transcribe_file_unknown_speech_model_short_circuits(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ASSEMBLYAI_API_KEY", "test-key")
    monkeypatch.setattr(
        settings,
        "TRANSCRIPTION_PROVIDERS_ENABLED",
        ["local_whisper", "assemblyai"],
    )
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"tfx_{uid.hex[:8]}", password_hash="h", is_admin=False))
    art_id = uuid.uuid4()
    now = utc_now()
    db_session.add(
        AudioFileArtifact(
            id=art_id,
            user_id=uid,
            filename="c.wav",
            mime_type="audio/wav",
            size_bytes=12,
            audio_bytes=b"RIFF....WAVE",
            transient=False,
            created_at=now,
            updated_at=now,
        )
    )
    wf = WorkflowDefinition(
        id=uuid.uuid4(),
        user_id=uid,
        name="tf bad model",
        graph=_transcribe_file_graph(
            {
                "provider": "assemblyai",
                "audio_artifact_id": str(art_id),
                "provider_model_id": "not-a-listed-model",
            },
        ),
    )
    db_session.add(wf)
    db_session.commit()

    result = await WorkflowExecutor(db_session, uid).run(wf)
    assert result.status in {"error", "partial"}
    tf_result = next(r for r in result.node_results if r.node_id == "tf")
    assert tf_result.status == "error"
    assert "unknown speech model" in (tf_result.error or "").lower()


def test_options_from_row_preserves_provider_model_id() -> None:
    from types import SimpleNamespace

    from app.domain.services.transcription_job_poller import _options_from_row

    row = SimpleNamespace(
        options_json={
            "provider_model_id": "universal-2",
            "diarization_enabled": True,
            "task": "transcribe",
        },
    )
    opt = _options_from_row(row)  # type: ignore[arg-type]
    assert opt.provider_model_id == "universal-2"
    assert opt.diarization_enabled is True


# -----------------------------------------------------------------------------
# Executor: runtime upload path (mirrors audio_file_input)
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
@patch("app.providers.transcription.local_whisper.transcribe_audio_bytes", new_callable=AsyncMock)
async def test_transcribe_file_run_stream_runtime_upload_completes(
    m_stt: AsyncMock,
    db_session: Session,
) -> None:
    m_stt.return_value = _STT_BRIDGE_RESPONSE
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"tfs_{uid.hex[:8]}", password_hash="h", is_admin=False))
    wf_uuid = uuid.uuid4()
    db_session.add(
        WorkflowDefinition(id=wf_uuid, user_id=uid, name="tf stream", graph=_transcribe_file_graph()),
    )
    db_session.commit()
    wf = db_session.get(WorkflowDefinition, wf_uuid)
    assert wf is not None

    saw_input = False
    saw_complete = False
    end_ok = False
    t0 = time.monotonic()
    async for raw in WorkflowExecutor(db_session, uid).run_stream(wf):
        chunk = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
        for part in chunk.splitlines():
            if not part.strip():
                continue
            ev = json.loads(part)
            if ev.get("event") == "input_required" and ev.get("kind") == "transcribe_file":
                assert time.monotonic() - t0 < 5.0
                key = TranscribeWaitKey(
                    run_id=uuid.UUID(str(ev["run_id"])),
                    node_id="tf",
                    for_loop_id=None,
                    iteration=0,
                )
                assert complete_transcribe_wait(
                    key,
                    b"RIFF....WAVE",
                    filename="runtime.wav",
                    content_type="audio/wav",
                )
                saw_input = True
            if ev.get("event") == "node_end" and ev.get("node_id") == "tf":
                out = (ev.get("result") or {}).get("output") or {}
                if out.get("kind") == "dictionary":
                    saw_complete = (out.get("data") or {}).get("full_text") == "hello world"
            if ev.get("event") == "end" and (ev.get("result") or {}).get("status") == "ok":
                end_ok = True

    assert saw_input and saw_complete and end_ok
    m_stt.assert_awaited_once()


# -----------------------------------------------------------------------------
# Executor: client disconnect leaves async job non-terminal for the poller
# -----------------------------------------------------------------------------


class _PendingForeverProvider(SpeechTranscriptionProvider):
    provider_id = "assemblyai"
    is_synchronous = False
    display_name = "PendingForever"

    async def submit(
        self,
        *,
        audio: bytes,
        filename: str,
        content_type: str,
        options: TranscriptionOptions,
        api_key,
    ) -> SubmissionResult:
        return SubmissionResult(
            provider_job_id="tr_pending",
            status="processing",
            transcript=None,
            provider_metadata={},
        )

    async def poll(self, *, provider_job_id, options, api_key) -> PollResult:
        return PollResult(status="processing")

    async def cancel(self, *, provider_job_id, api_key) -> None:
        return None


@pytest.mark.asyncio
async def test_transcribe_file_client_disconnect_leaves_job_non_terminal(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ASSEMBLYAI_API_KEY", "test-key")
    monkeypatch.setattr(settings, "ASSEMBLYAI_POLL_INTERVAL", 0.05)
    monkeypatch.setattr(settings, "ASSEMBLYAI_JOB_TIMEOUT", 30.0)
    monkeypatch.setattr(
        settings,
        "TRANSCRIPTION_PROVIDERS_ENABLED",
        ["local_whisper", "assemblyai"],
    )

    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"tfx_{uid.hex[:8]}", password_hash="h", is_admin=False))
    art_id = uuid.uuid4()
    now = utc_now()
    db_session.add(
        AudioFileArtifact(
            id=art_id,
            user_id=uid,
            filename="c.wav",
            mime_type="audio/wav",
            size_bytes=12,
            audio_bytes=b"RIFF....WAVE",
            transient=False,
            created_at=now,
            updated_at=now,
        )
    )
    wf = WorkflowDefinition(
        id=uuid.uuid4(),
        user_id=uid,
        name="tf disconnect",
        graph=_transcribe_file_graph(
            {"provider": "assemblyai", "audio_artifact_id": str(art_id)},
        ),
    )
    db_session.add(wf)
    db_session.commit()

    pending_provider = _PendingForeverProvider()

    def fake_get_provider(provider_id: str) -> SpeechTranscriptionProvider:
        if provider_id == "assemblyai":
            return pending_provider
        raise TranscriptionProviderError(f"unknown provider {provider_id}")

    with patch(
        "app.domain.workflow_executor.executor.get_speech_provider",
        side_effect=fake_get_provider,
    ):
        executor = WorkflowExecutor(db_session, uid)
        run_task = asyncio.create_task(executor.run(wf))
        await asyncio.sleep(0.4)  # Let submit + at least one poll happen
        run_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await run_task

    db_session.expire_all()
    jobs = db_session.exec(select(TranscriptionJob).where(TranscriptionJob.user_id == uid)).all()
    assert len(jobs) == 1
    assert jobs[0].status in {"submitting", "queued", "processing"}
    assert jobs[0].provider_job_id == "tr_pending"


# -----------------------------------------------------------------------------
# transcription_job_service helpers
# -----------------------------------------------------------------------------


def test_transcription_job_service_lifecycle(db_session: Session) -> None:
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"tjs_{uid.hex[:8]}", password_hash="h", is_admin=False))
    db_session.commit()
    svc = TranscriptionJobService(db_session, uid)
    from app.domain.audio_file_validation import ValidatedAudioFile

    validated = ValidatedAudioFile(filename="c.wav", mime_type="audio/wav", size_bytes=12)
    row = svc.create_pending(
        run_id=None,
        node_id="tf",
        for_loop_id=None,
        for_loop_iteration=None,
        provider="assemblyai",
        options=TranscriptionOptions(),
        audio_artifact_id=None,
        validated_audio=validated,
    )
    assert row.status == "submitting"

    sub = SubmissionResult(provider_job_id="aai_id", status="queued", transcript=None)
    row = svc.apply_submission(row, sub)
    assert row.status == "queued"
    assert row.provider_job_id == "aai_id"

    poll = PollResult(
        status="completed",
        transcript={
            "type": "transcript",
            "version": 1,
            "full_text": "x",
            "language": None,
            "duration_seconds": None,
            "provider": "assemblyai",
            "segments": [],
            "words": [],
            "metadata": {
                "model": None,
                "diarization_enabled": False,
                "created_at": utc_now().isoformat(),
                "provider_metadata": {},
            },
        },
    )
    row = svc.apply_poll(row, poll)
    assert row.status == "completed"
    assert row.transcript_json is not None
    assert row.completed_at is not None

    # Idempotency: applying poll on terminal row is a no-op.
    again = svc.apply_poll(row, PollResult(status="processing"))
    assert again.status == "completed"


def test_transcription_job_service_find_existing_for_node(db_session: Session) -> None:
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"tjf_{uid.hex[:8]}", password_hash="h", is_admin=False))
    db_session.commit()
    svc = TranscriptionJobService(db_session, uid)
    from app.domain.audio_file_validation import ValidatedAudioFile

    validated = ValidatedAudioFile(filename="c.wav", mime_type="audio/wav", size_bytes=12)
    run_id = uuid.uuid4()
    db_session.add(
        WorkflowRun(
            id=run_id, workflow_id=uuid.uuid4(), started_by_user_id=uid, status="running",
        )
    )
    db_session.commit()

    first = svc.create_pending(
        run_id=run_id,
        node_id="tf",
        for_loop_id=None,
        for_loop_iteration=None,
        provider="assemblyai",
        options=TranscriptionOptions(),
        audio_artifact_id=None,
        validated_audio=validated,
    )
    found = svc.find_existing_for_node(
        run_id=run_id,
        node_id="tf",
        for_loop_id=None,
        for_loop_iteration=None,
    )
    assert found is not None and found.id == first.id

    # Different node id returns None.
    assert (
        svc.find_existing_for_node(
            run_id=run_id, node_id="other", for_loop_id=None, for_loop_iteration=None,
        )
        is None
    )


def test_transcription_job_service_cleans_up_transient_artifact(db_session: Session) -> None:
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"tjc_{uid.hex[:8]}", password_hash="h", is_admin=False))
    db_session.commit()

    artifact_service = AudioFileArtifactService(db_session, uid)
    from app.domain.audio_file_validation import ValidatedAudioFile

    validated = ValidatedAudioFile(filename="c.wav", mime_type="audio/wav", size_bytes=12)
    transient = artifact_service.create_transient(b"RIFF....WAVE", validated)
    assert transient.transient is True

    svc = TranscriptionJobService(db_session, uid)
    row = svc.create_pending(
        run_id=None,
        node_id="tf",
        for_loop_id=None,
        for_loop_iteration=None,
        provider="assemblyai",
        options=TranscriptionOptions(),
        audio_artifact_id=transient.id,
        validated_audio=validated,
    )
    # Pre-terminal: cleanup is a no-op.
    assert svc.cleanup_transient_audio(row) is False
    svc.mark_error(row, "sim error")
    assert svc.cleanup_transient_audio(row) is True
    leftover = db_session.get(AudioFileArtifact, transient.id)
    assert leftover is None


def test_audio_file_artifact_service_hides_transient_rows(db_session: Session) -> None:
    """Transient runtime uploads must not appear in My Audio Files listings."""
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"afh_{uid.hex[:8]}", password_hash="h", is_admin=False))
    db_session.commit()
    svc = AudioFileArtifactService(db_session, uid)
    from app.domain.audio_file_validation import ValidatedAudioFile

    validated = ValidatedAudioFile(filename="c.wav", mime_type="audio/wav", size_bytes=12)
    user_artifact = svc.create(b"RIFF....WAVE", validated)
    runtime_artifact = svc.create_transient(b"RIFF....WAVE", validated)

    listed_ids = {a.id for a in svc.list_artifacts()}
    assert user_artifact.id in listed_ids
    assert runtime_artifact.id not in listed_ids


# -----------------------------------------------------------------------------
# Lifespan poller
# -----------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_lifespan_poller_advances_pending_assemblyai_row(
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "ASSEMBLYAI_API_KEY", "test-key")

    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"pol_{uid.hex[:8]}", password_hash="h", is_admin=False))
    db_session.commit()
    svc = TranscriptionJobService(db_session, uid)
    from app.domain.audio_file_validation import ValidatedAudioFile

    validated = ValidatedAudioFile(filename="c.wav", mime_type="audio/wav", size_bytes=12)
    row = svc.create_pending(
        run_id=None,
        node_id="tf",
        for_loop_id=None,
        for_loop_iteration=None,
        provider="assemblyai",
        options=TranscriptionOptions(),
        audio_artifact_id=None,
        validated_audio=validated,
    )
    sub = SubmissionResult(provider_job_id="tr_test_123", status="processing", transcript=None)
    row = svc.apply_submission(row, sub)
    assert row.status == "processing"

    # local_whisper is excluded from the poller's "pending" view by design.
    pending = list_pending_jobs_for_poller(db_session)
    assert any(p.id == row.id for p in pending)

    # Ensure poller resolves session from app.persistence.db.engine.
    from app.persistence import db as app_db

    monkeypatch.setattr(
        app_db,
        "engine",
        db_session.bind,
        raising=True,
    )
    monkeypatch.setattr(
        "app.domain.services.transcription_job_poller.engine",
        db_session.bind,
        raising=True,
    )

    handler_log: list[tuple[str, str]] = []
    transport = _aai_transport(handler_log)

    def fake_client(*, base_url: str, api_key: str, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport,
        )

    poller = TranscriptionJobPoller(poll_interval_seconds=0.05)
    with patch("app.providers.transcription.assemblyai._build_async_client", fake_client):
        # Two ticks: first poll → processing, second poll → completed.
        await poller.poll_once()
        await poller.poll_once()

    db_session.expire_all()
    refreshed = db_session.get(TranscriptionJob, row.id)
    assert refreshed is not None
    assert refreshed.status == "completed"
    assert refreshed.transcript_json is not None
    assert refreshed.transcript_json.get("provider") == "assemblyai"


@pytest.mark.asyncio
async def test_lifespan_poller_skips_synchronous_providers(db_session: Session) -> None:
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"polsync_{uid.hex[:8]}", password_hash="h", is_admin=False))
    db_session.commit()
    svc = TranscriptionJobService(db_session, uid)
    from app.domain.audio_file_validation import ValidatedAudioFile

    validated = ValidatedAudioFile(filename="c.wav", mime_type="audio/wav", size_bytes=12)
    row = svc.create_pending(
        run_id=None,
        node_id="tf",
        for_loop_id=None,
        for_loop_iteration=None,
        provider="local_whisper",
        options=TranscriptionOptions(),
        audio_artifact_id=None,
        validated_audio=validated,
    )
    pending = list_pending_jobs_for_poller(db_session)
    assert all(p.id != row.id for p in pending)


@pytest.mark.asyncio
async def test_lifespan_poller_start_stop_idempotent() -> None:
    poller = TranscriptionJobPoller(poll_interval_seconds=0)
    await poller.start()
    assert poller.is_running is False  # disabled when interval <= 0
    await poller.stop()  # no error


# -----------------------------------------------------------------------------
# Reattach stream endpoint
# -----------------------------------------------------------------------------


def test_reattach_stream_replays_logs_and_jobs(client: TestClient, db_session: Session) -> None:
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    run_id = uuid.uuid4()
    workflow_id = uuid.uuid4()
    db_session.add(
        WorkflowRun(
            id=run_id,
            workflow_id=workflow_id,
            started_by_user_id=user.id,
            status="ok",
        )
    )
    log = NodeRunLog(
        id=uuid.uuid4(),
        run_id=run_id,
        workflow_id=workflow_id,
        user_id=user.id,
        step_number=1,
        node_id="tf",
        node_kind="skill",
        status="ok",
        latency_ms=10,
        output_data={"kind": "dictionary", "value": {"full_text": "hello"}},
        error=None,
        details={},
    )
    db_session.add(log)
    db_session.add(
        TranscriptionJob(
            id=uuid.uuid4(),
            user_id=user.id,
            run_id=run_id,
            node_id="tf",
            provider="assemblyai",
            provider_job_id="tr_x",
            status="completed",
            audio_filename="c.wav",
            audio_mime_type="audio/wav",
            audio_size_bytes=12,
            options_json={},
            transcript_json={"full_text": "hello"},
            provider_metadata={},
        )
    )
    db_session.commit()

    with client.stream("POST", f"/api/v1/workflow-runs/{run_id}/reattach-stream") as resp:
        assert resp.status_code == 200
        events: list[dict[str, Any]] = []
        for line in resp.iter_lines():
            if not line.strip():
                continue
            events.append(json.loads(line))
            if events[-1].get("event") == "end":
                break

    kinds = [e["event"] for e in events]
    assert kinds[0] == "reattach_start"
    assert "node_end" in kinds
    assert "transcription_job_status" in kinds
    assert kinds[-1] == "end"


def test_reattach_stream_404_for_other_users_run(
    client: TestClient,
    db_session: Session,
) -> None:
    other = User(id=uuid.uuid4(), username=f"other_{uuid.uuid4().hex[:8]}", password_hash="h")
    db_session.add(other)
    other_run_id = uuid.uuid4()
    db_session.add(
        WorkflowRun(
            id=other_run_id,
            workflow_id=uuid.uuid4(),
            started_by_user_id=other.id,
            status="running",
        )
    )
    db_session.commit()
    resp = client.post(f"/api/v1/workflow-runs/{other_run_id}/reattach-stream")
    assert resp.status_code == 404


# -----------------------------------------------------------------------------
# Runtime upload route mirrors audio_file_input
# -----------------------------------------------------------------------------


@patch("app.api.v1.workflow_run_transcribe_file.complete_taken_transcribe_wait", return_value=True)
@patch("app.api.v1.workflow_run_transcribe_file.take_transcribe_wait", return_value=object())
def test_transcribe_file_runtime_upload_route_accepts_multipart(
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
            id=run_id, workflow_id=uuid.uuid4(), started_by_user_id=user.id, status="running",
        )
    )
    db_session.commit()
    response = client.post(
        f"/api/v1/workflow-runs/{run_id}/transcribe-file-input",
        data={"node_id": "tf", "for_loop_iteration": "0"},
        files={"file": ("runtime.wav", b"RIFF....WAVE", "audio/wav")},
    )
    assert response.status_code == 204
    mock_take.assert_called_once()
    mock_complete.assert_called_once()


@patch("app.api.v1.workflow_run_transcribe_file.complete_taken_transcribe_wait", return_value=False)
@patch("app.api.v1.workflow_run_transcribe_file.take_transcribe_wait", return_value=object())
def test_transcribe_file_runtime_upload_route_rejects_stale_wait(
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
            id=run_id, workflow_id=uuid.uuid4(), started_by_user_id=user.id, status="running",
        )
    )
    db_session.commit()
    response = client.post(
        f"/api/v1/workflow-runs/{run_id}/transcribe-file-input",
        data={"node_id": "tf", "for_loop_iteration": "0"},
        files={"file": ("runtime.wav", b"RIFF....WAVE", "audio/wav")},
    )
    assert response.status_code == 409
    mock_take.assert_called_once()
    mock_complete.assert_called_once()
