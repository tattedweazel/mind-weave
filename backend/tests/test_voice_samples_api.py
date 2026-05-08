"""Voice samples API: list, preview-design, create, get, audio, delete (bridge mocked)."""

from __future__ import annotations

import base64
import io
import uuid
import wave
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient
from sqlmodel import Session, select

from app.persistence.tables import TtsModelArtifact, User, VoiceSample


def _mini_wav_bytes() -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(24_000)
        w.writeframes(b"\x00\x00" * 80)
    return buf.getvalue()


def _test_user_id(session: Session) -> uuid.UUID:
    u = session.exec(select(User).where(User.username == "testuser")).first()
    assert u is not None
    return u.id


def test_voice_samples_list_empty(client: TestClient):
    r = client.get("/api/v1/voice-samples/")
    assert r.status_code == 200
    assert r.json() == []


def test_voice_preview_design_mocked_bridge(client: TestClient, db_session: Session):
    aid = uuid.uuid4()
    db_session.add(
        TtsModelArtifact(
            id=aid,
            display_name="Design",
            engine="qwen_torch",
            source={"kind": "huggingface_repo", "repo_id": "x/y"},
            local_key="k",
            status="ready",
            error_message=None,
        )
    )
    db_session.commit()
    wav = _mini_wav_bytes()
    with patch("app.api.v1.voice_samples.synthesize_wav", new_callable=AsyncMock) as m:
        m.return_value = wav
        r = client.post(
            "/api/v1/voice-samples/preview-design",
            json={
                "design_model_id": str(aid),
                "text": "Hello preview",
                "language": "English",
                "instruct": "Calm",
            },
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mime_type"] == "audio/wav"
    assert body["audio_base64"] == base64.b64encode(wav).decode("ascii")
    m.assert_awaited_once()


def test_voice_sample_create_list_get_audio_delete(client: TestClient, db_session: Session):
    _test_user_id(db_session)
    aid = uuid.uuid4()
    db_session.add(
        TtsModelArtifact(
            id=aid,
            display_name="Design",
            engine="qwen_torch",
            source={},
            local_key="k",
            status="ready",
            error_message=None,
        )
    )
    db_session.commit()
    wav = _mini_wav_bytes()
    b64 = base64.b64encode(wav).decode("ascii")
    r = client.post(
        "/api/v1/voice-samples/",
        json={
            "name": "Narrator",
            "ref_text": "Same as spoken",
            "language": "English",
            "instruct": "Warm",
            "design_model_id": str(aid),
            "audio_base64": b64,
        },
    )
    assert r.status_code == 201, r.text
    row = r.json()
    sid = row["id"]
    assert row["name"] == "Narrator"
    assert row["ref_text"] == "Same as spoken"

    listed = client.get("/api/v1/voice-samples/").json()
    assert len(listed) == 1
    assert listed[0]["id"] == sid

    one = client.get(f"/api/v1/voice-samples/{sid}").json()
    assert one["name"] == "Narrator"

    audio = client.get(f"/api/v1/voice-samples/{sid}/audio")
    assert audio.status_code == 200
    assert audio.content == wav

    d = client.delete(f"/api/v1/voice-samples/{sid}")
    assert d.status_code == 204
    assert client.get("/api/v1/voice-samples/").json() == []

    # Row gone
    assert db_session.get(VoiceSample, uuid.UUID(sid)) is None


def test_voice_sample_forbidden_other_user_voice_not_listed(client: TestClient, db_session: Session):
    """Voice rows are scoped by user_id; listing never leaks other users' samples."""
    _test_user_id(db_session)
    other = uuid.uuid4()
    db_session.add(User(id=other, username=f"other_{other.hex[:6]}", password_hash="h", is_admin=False))
    sid = uuid.uuid4()
    wav = _mini_wav_bytes()
    db_session.add(
        VoiceSample(
            id=sid,
            user_id=other,
            name="Secret",
            name_lower="secret",
            ref_text="x",
            ref_audio=wav,
            language="English",
            instruct="",
            design_model_id=None,
        )
    )
    db_session.commit()

    listed = client.get("/api/v1/voice-samples/").json()
    assert listed == []

    assert client.get(f"/api/v1/voice-samples/{sid}").status_code == 404
    assert client.get(f"/api/v1/voice-samples/{sid}/audio").status_code == 404
