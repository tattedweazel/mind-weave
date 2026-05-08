"""Text-to-Speech skill: bridge HTTP is mocked (no real synthesis)."""

from __future__ import annotations

import base64
import io
import uuid
import wave
from unittest.mock import AsyncMock, patch

import pytest
from sqlmodel import Session

from app.domain.services.workflow_executor import WorkflowExecutor
from app.persistence.tables import TtsModelArtifact, User, VoiceSample, WorkflowDefinition


def _mini_wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24_000)
        w.writeframes(b"\x00\x00" * 40)
    return buf.getvalue()


@pytest.mark.asyncio
async def test_text_to_speech_skill_runs_with_mocked_bridge(db_session: Session):
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"tts_{uid.hex[:8]}", password_hash="h", is_admin=False))
    artifact_id = uuid.uuid4()
    db_session.add(
        TtsModelArtifact(
            id=artifact_id,
            display_name="Mock model",
            engine="qwen_torch",
            source={"kind": "huggingface_repo", "repo_id": "dummy/dummy"},
            local_key="relative/key",
            status="ready",
            error_message=None,
        )
    )
    wf_id = uuid.uuid4()
    graph = {
        "nodes": [
            {"id": "s", "kind": "start", "label": "S", "data": {"text": ""}, "position": {}},
            {
                "id": "tts",
                "kind": "skill",
                "skill_type": "text_to_speech",
                "label": "TTS",
                "data": {
                    "tts_model_id": str(artifact_id),
                    "required_inputs": [{"key": "text", "type": "string", "value": "hello"}],
                    "tts_options": {},
                },
                "position": {},
            },
            {
                "id": "st",
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "audio"}]},
                "position": {},
            },
        ],
        "edges": [
            {"source": "s", "target": "tts"},
            {"source": "tts", "target": "st", "source_handle": "output", "target_handle": "output"},
        ],
    }
    db_session.add(WorkflowDefinition(id=wf_id, user_id=uid, name="TTS test", graph=graph))
    db_session.commit()

    wav = b"fake-wav-bytes"
    wf_row = db_session.get(WorkflowDefinition, wf_id)
    assert wf_row is not None

    with patch("app.domain.workflow_executor.executor.synthesize_wav", new_callable=AsyncMock) as m_syn:
        m_syn.return_value = wav
        ex = WorkflowExecutor(db_session, uid)
        result = await ex.run(wf_row)

    assert result.status == "ok"
    m_syn.assert_awaited_once()
    tts_results = [nr for nr in result.node_results if nr.node_id == "tts" and nr.status == "ok"]
    assert len(tts_results) == 1
    out = tts_results[0].output
    assert out is not None
    assert getattr(out, "kind", None) == "audio"
    assert out.audio_base64 == base64.b64encode(wav).decode("ascii")


@pytest.mark.asyncio
async def test_text_to_speech_with_voice_sample_passes_clone_options(db_session: Session):
    uid = uuid.uuid4()
    db_session.add(User(id=uid, username=f"tts_vs_{uid.hex[:8]}", password_hash="h", is_admin=False))
    artifact_id = uuid.uuid4()
    db_session.add(
        TtsModelArtifact(
            id=artifact_id,
            display_name="Base clone",
            engine="qwen_torch",
            source={"kind": "huggingface_repo", "repo_id": "dummy/dummy"},
            local_key="relative/key",
            status="ready",
            error_message=None,
        )
    )
    ref_wav = _mini_wav_bytes()
    vsid = uuid.uuid4()
    db_session.add(
        VoiceSample(
            id=vsid,
            user_id=uid,
            name="Ref",
            name_lower="ref",
            ref_text="reference script",
            ref_audio=ref_wav,
            language="English",
            instruct="",
            design_model_id=None,
        )
    )
    wf_id = uuid.uuid4()
    graph = {
        "nodes": [
            {"id": "s", "kind": "start", "label": "S", "data": {"text": ""}, "position": {}},
            {
                "id": "tts",
                "kind": "skill",
                "skill_type": "text_to_speech",
                "label": "TTS",
                "data": {
                    "tts_model_id": str(artifact_id),
                    "voice_sample_id": str(vsid),
                    "required_inputs": [{"key": "text", "type": "string", "value": "spoken line"}],
                    "tts_options": {"speaker": "Vivian"},
                },
                "position": {},
            },
            {
                "id": "st",
                "kind": "stop",
                "label": "Stop",
                "data": {"required_outputs": [{"key": "output", "type": "audio"}]},
                "position": {},
            },
        ],
        "edges": [
            {"source": "s", "target": "tts"},
            {"source": "tts", "target": "st", "source_handle": "output", "target_handle": "output"},
        ],
    }
    db_session.add(WorkflowDefinition(id=wf_id, user_id=uid, name="TTS clone test", graph=graph))
    db_session.commit()

    out_wav = b"out-wav"
    wf_row = db_session.get(WorkflowDefinition, wf_id)
    assert wf_row is not None

    with patch("app.domain.workflow_executor.executor.synthesize_wav", new_callable=AsyncMock) as m_syn:
        m_syn.return_value = out_wav
        ex = WorkflowExecutor(db_session, uid)
        result = await ex.run(wf_row)

    assert result.status == "ok"
    m_syn.assert_awaited_once()
    _engine, _key, text, opts = m_syn.call_args[0]
    assert text == "spoken line"
    assert opts["ref_text"] == "reference script"
    assert opts["ref_audio_base64"] == base64.b64encode(ref_wav).decode("ascii")
    assert opts["speaker"] == "Vivian"

    tts_results = [nr for nr in result.node_results if nr.node_id == "tts" and nr.status == "ok"]
    assert len(tts_results) == 1
    out = tts_results[0].output
    assert out is not None
    assert getattr(out, "kind", None) == "audio"
