#!/usr/bin/env python3
"""
End-to-end: create and run **Transcribe File → Stop** workflows in-process.

The provider-abstracted ``transcribe_file`` skill emits a rich Transcript primitive
(segments, optional words, optional speakers). This script proves both supported
provider backends and both source modes work end-to-end against the real
``WorkflowExecutor``:

1. saved artifact + ``local_whisper`` (sync, mocked STT bridge by default)
2. runtime upload + ``local_whisper`` (run_stream → input_required → deliver bytes)
3. saved artifact + ``assemblyai`` (async, AssemblyAI httpx calls mocked by default)

Default mode mocks every external service so no live calls fire. Pass
``--real-stt --audio-file /path/to/clip.wav`` to call the real STT bridge or
``--real-assemblyai --assemblyai-key <key> --audio-file /path/to/clip.wav`` to
exercise the live AssemblyAI pipeline.

Examples::

  cd backend && uv run python scripts/run_transcribe_file_workflow_e2e.py
  cd backend && uv run python scripts/run_transcribe_file_workflow_e2e.py --real-stt --audio-file ../sample.wav
  cd backend && uv run python scripts/run_transcribe_file_workflow_e2e.py --real-assemblyai --assemblyai-key ${ASSEMBLYAI_API_KEY} --audio-file ../sample.wav
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import mimetypes
import os
import re
import sys
import uuid
import wave
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

# Match API startup convention: load settings and sqlite:// paths from backend/.
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
os.chdir(_BACKEND_ROOT)

import httpx  # noqa: E402
from sqlmodel import Session, select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.domain.audio_file_validation import validate_audio_upload  # noqa: E402
from app.domain.services.workflow_executor import WorkflowExecutor  # noqa: E402
from app.domain.workflow_executor.transcribe_pending import (  # noqa: E402
    TranscribeWaitKey,
    complete_transcribe_wait,
)
from app.persistence.db import engine  # noqa: E402
from app.persistence.tables import (  # noqa: E402
    AudioFileArtifact,
    TranscriptionJob,
    User,
    WorkflowDefinition,
    utc_now,
)

NODE_ID = "transcribe_file"
_MOCK_STT_TEXT = "transcribe file e2e mock transcript from script"
_MOCK_AAI_TEXT = "transcribe file e2e mock transcript from assemblyai"


def _silent_wav_bytes() -> bytes:
    """Small valid WAV; useful for mocked providers and route/handoff sanity checks."""

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(b"\x00\x00" * 3_200)
    return buf.getvalue()


def _content_type_for(path: Path | None) -> str:
    if path is None:
        return "audio/wav"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def _audio_bytes_from_args(args: argparse.Namespace) -> tuple[bytes, str, str]:
    if args.audio_file:
        path = Path(args.audio_file).expanduser().resolve()
        data = path.read_bytes()
        return data, path.name, _content_type_for(path)
    return _silent_wav_bytes(), "transcribe-file-e2e.wav", "audio/wav"


def _graph(*, provider: str, artifact_id: uuid.UUID | None) -> dict[str, Any]:
    data: dict[str, Any] = {
        "provider": provider,
        "task": "transcribe",
        "diarization_enabled": False,
        "include_word_timestamps": False,
    }
    if artifact_id is not None:
        data["audio_artifact_id"] = str(artifact_id)
    return {
        "nodes": [
            {"id": "s", "kind": "start", "label": "Start", "data": {"text": ""}, "position": {}},
            {
                "id": NODE_ID,
                "kind": "skill",
                "skill_type": "transcribe_file",
                "label": "Transcribe File",
                "data": data,
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
            {"source": "s", "target": NODE_ID},
            {"source": NODE_ID, "target": "n_stop", "source_handle": "output", "target_handle": "output"},
        ],
    }


def _normalize_uuid(s: str) -> uuid.UUID:
    t = s.strip()
    if re.fullmatch(r"[0-9a-fA-F]{32}", t):
        t = f"{t[:8]}-{t[8:12]}-{t[12:16]}-{t[16:20]}-{t[20:]}"
    return uuid.UUID(t)


def _resolve_user_id(session: Session, explicit: str | None) -> uuid.UUID:
    if explicit:
        return _normalize_uuid(explicit)
    u = session.exec(select(User).limit(1)).first()
    if u is None:
        raise SystemExit("No user in the database; create a user or pass --user-id <uuid>.")
    return u.id


def _stt_healthy() -> bool:
    base = (settings.STT_BRIDGE_URL or "").rstrip("/")
    if not base:
        return False
    try:
        r = httpx.get(f"{base}/health", timeout=4.0)
        return r.is_success
    except httpx.RequestError:
        return False


def _node_transcript(result: Any) -> dict[str, Any] | None:
    for node_result in result.node_results:
        if node_result.node_id != NODE_ID or node_result.output is None:
            continue
        out = node_result.output
        if getattr(out, "kind", None) == "dictionary":
            data = getattr(out, "data", None)
            if isinstance(data, dict) and data.get("type") == "transcript":
                return data
    return None


async def _run_saved_artifact(
    session: Session,
    user_id: uuid.UUID,
    *,
    provider: str,
    audio: bytes,
    filename: str,
    content_type: str,
) -> tuple[uuid.UUID, uuid.UUID, str]:
    validated = validate_audio_upload(audio, filename=filename, content_type=content_type)
    now = utc_now()
    artifact = AudioFileArtifact(
        user_id=user_id,
        filename=validated.filename,
        mime_type=validated.mime_type,
        size_bytes=validated.size_bytes,
        audio_bytes=audio,
        transient=False,
        created_at=now,
        updated_at=now,
    )
    session.add(artifact)
    session.commit()
    session.refresh(artifact)

    wf = WorkflowDefinition(
        user_id=user_id,
        name=f"transcribe file saved {provider} e2e {uuid.uuid4().hex[:8]}",
        graph=_graph(provider=provider, artifact_id=artifact.id),
    )
    session.add(wf)
    session.commit()
    session.refresh(wf)

    result = await WorkflowExecutor(session, user_id).run(wf)
    primitive = _node_transcript(result)
    if result.status != "ok" or not primitive:
        raise RuntimeError(
            f"saved artifact workflow failed: provider={provider} status={result.status} primitive={primitive!r}",
        )
    return wf.id, artifact.id, str(primitive.get("full_text", "")).strip()


async def _run_runtime_upload(
    session: Session,
    user_id: uuid.UUID,
    *,
    provider: str,
    audio: bytes,
    filename: str,
    content_type: str,
) -> tuple[uuid.UUID, str]:
    validate_audio_upload(audio, filename=filename, content_type=content_type)
    wf = WorkflowDefinition(
        user_id=user_id,
        name=f"transcribe file runtime {provider} e2e {uuid.uuid4().hex[:8]}",
        graph=_graph(provider=provider, artifact_id=None),
    )
    session.add(wf)
    session.commit()
    session.refresh(wf)

    text: str | None = None
    end_ok = False
    input_required_seen = False
    t0 = asyncio.get_event_loop().time()

    async for raw in WorkflowExecutor(session, user_id).run_stream(wf):
        chunk = raw.decode() if isinstance(raw, (bytes, bytearray)) else str(raw)
        for part in chunk.splitlines():
            if not part.strip():
                continue
            ev = json.loads(part)
            if ev.get("event") == "input_required" and ev.get("kind") == "transcribe_file":
                input_required_seen = True
                elapsed = asyncio.get_event_loop().time() - t0
                if elapsed > 5.0:
                    print(f"Warning: input_required arrived after {elapsed:.1f}s", file=sys.stderr)
                key = TranscribeWaitKey(
                    run_id=uuid.UUID(str(ev["run_id"])),
                    node_id=NODE_ID,
                    for_loop_id=None,
                    iteration=int(ev.get("for_loop_iteration") or 0),
                )
                ok = complete_transcribe_wait(
                    key, audio, filename=filename, content_type=content_type,
                )
                if not ok:
                    raise RuntimeError("complete_transcribe_wait returned False for runtime upload")
            if ev.get("event") == "node_end" and ev.get("node_id") == NODE_ID:
                out = (ev.get("result") or {}).get("output") or {}
                if out.get("kind") == "dictionary":
                    data = out.get("data") or {}
                    if data.get("type") == "transcript":
                        text = str(data.get("full_text") or "").strip()
            if ev.get("event") == "end" and (ev.get("result") or {}).get("status") == "ok":
                end_ok = True

    if not input_required_seen or not end_ok or not text:
        raise RuntimeError(
            "runtime upload workflow failed: "
            f"input_required={input_required_seen} end_ok={end_ok} text={text!r}",
        )
    return wf.id, text


def _build_assemblyai_mock_transport() -> httpx.MockTransport:
    """Mock the three AAI endpoints used by the adapter (upload/create/get)."""

    state: dict[str, Any] = {"poll_count": 0}
    transcript_id = "tr_mock_e2e"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/v2/upload":
            return httpx.Response(200, json={"upload_url": "https://aai.example/upload/abc"})
        if request.method == "POST" and request.url.path == "/v2/transcript":
            return httpx.Response(200, json={"id": transcript_id, "status": "queued"})
        if (
            request.method == "GET"
            and request.url.path == f"/v2/transcript/{transcript_id}"
        ):
            state["poll_count"] += 1
            if state["poll_count"] < 2:
                return httpx.Response(200, json={"id": transcript_id, "status": "processing"})
            return httpx.Response(
                200,
                json={
                    "id": transcript_id,
                    "status": "completed",
                    "text": _MOCK_AAI_TEXT,
                    "language_code": "en",
                    "audio_duration": 1.0,
                    "speech_model": "best",
                    "utterances": [
                        {"speaker": "A", "start": 0, "end": 1000, "text": _MOCK_AAI_TEXT},
                    ],
                    "words": [],
                },
            )
        return httpx.Response(404)

    return httpx.MockTransport(handler)


@contextlib.contextmanager
def _maybe_mock_assemblyai(*, enable: bool) -> Any:
    if not enable:
        yield
        return
    transport = _build_assemblyai_mock_transport()

    def fake_client(*, base_url: str, api_key: str, timeout: float) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout, transport=transport,
        )

    with patch("app.providers.transcription.assemblyai._build_async_client", fake_client):
        yield


@contextlib.contextmanager
def _maybe_mock_local_whisper(*, enable: bool) -> Any:
    if not enable:
        yield
        return

    async def _stt(_data: bytes, **_kwargs: Any) -> dict[str, Any]:
        return {"text": _MOCK_STT_TEXT, "language": "en", "segments": [], "duration_seconds": 1.0}

    m_stt = AsyncMock(side_effect=_stt)
    with patch("app.providers.transcription.local_whisper.transcribe_audio_bytes", m_stt):
        yield m_stt


async def _run(args: argparse.Namespace) -> int:
    mock_stt = not args.real_stt
    mock_aai = not args.real_assemblyai

    if args.real_stt and not _stt_healthy():
        print(
            f"STT bridge not reachable at {settings.STT_BRIDGE_URL!r} (/health). "
            "Start services/stt-bridge or omit --real-stt.",
            file=sys.stderr,
        )
        return 1
    if args.real_assemblyai and not (args.assemblyai_key or settings.ASSEMBLYAI_API_KEY):
        print(
            "--real-assemblyai requires --assemblyai-key or ASSEMBLYAI_API_KEY in env.",
            file=sys.stderr,
        )
        return 1

    audio, filename, content_type = _audio_bytes_from_args(args)

    # Make sure the executor allows the AAI path (configurable in production via
    # TRANSCRIPTION_PROVIDERS_ENABLED). Local mode always works.
    enabled_before = list(settings.TRANSCRIPTION_PROVIDERS_ENABLED)
    if "assemblyai" not in settings.TRANSCRIPTION_PROVIDERS_ENABLED:
        settings.TRANSCRIPTION_PROVIDERS_ENABLED = list({*enabled_before, "assemblyai"})

    aai_key_before = settings.ASSEMBLYAI_API_KEY
    if args.assemblyai_key:
        settings.ASSEMBLYAI_API_KEY = args.assemblyai_key
    elif mock_aai and not settings.ASSEMBLYAI_API_KEY:
        settings.ASSEMBLYAI_API_KEY = "mock-aai-key-for-e2e"

    aai_poll_before = settings.ASSEMBLYAI_POLL_INTERVAL
    if mock_aai:
        settings.ASSEMBLYAI_POLL_INTERVAL = 0.05

    created_workflows: list[uuid.UUID] = []
    created_artifacts: list[uuid.UUID] = []
    saved_text_lw: str | None = None
    runtime_text_lw: str | None = None
    saved_text_aai: str | None = None

    try:
        with Session(engine) as session, _maybe_mock_local_whisper(enable=mock_stt) as m_stt:
            user_id = _resolve_user_id(session, args.user_id)

            saved_wf, artifact_id, saved_text_lw = await _run_saved_artifact(
                session,
                user_id,
                provider="local_whisper",
                audio=audio,
                filename=filename,
                content_type=content_type,
            )
            created_workflows.append(saved_wf)
            created_artifacts.append(artifact_id)

            runtime_wf, runtime_text_lw = await _run_runtime_upload(
                session,
                user_id,
                provider="local_whisper",
                audio=audio,
                filename=filename,
                content_type=content_type,
            )
            created_workflows.append(runtime_wf)

            if mock_stt and m_stt is not None and m_stt.await_count != 2:
                raise RuntimeError(
                    f"Expected mocked STT to be awaited twice, got {m_stt.await_count}",
                )

            with _maybe_mock_assemblyai(enable=mock_aai):
                saved_aai_wf, saved_aai_artifact, saved_text_aai = await _run_saved_artifact(
                    session,
                    user_id,
                    provider="assemblyai",
                    audio=audio,
                    filename=filename,
                    content_type=content_type,
                )
                created_workflows.append(saved_aai_wf)
                created_artifacts.append(saved_aai_artifact)

            if args.cleanup:
                for wf_id in created_workflows:
                    row = session.get(WorkflowDefinition, wf_id)
                    if row is not None:
                        session.delete(row)
                for artifact_id in created_artifacts:
                    row = session.get(AudioFileArtifact, artifact_id)
                    if row is not None:
                        session.delete(row)
                # Clean up the transcription_jobs rows we created (one per run).
                for tj in session.exec(
                    select(TranscriptionJob).where(TranscriptionJob.user_id == user_id),
                ).all():
                    session.delete(tj)
                session.commit()
    finally:
        settings.TRANSCRIPTION_PROVIDERS_ENABLED = enabled_before
        settings.ASSEMBLYAI_API_KEY = aai_key_before
        settings.ASSEMBLYAI_POLL_INTERVAL = aai_poll_before

    print(
        "ok — Transcribe File workflows completed "
        f"(local_saved_chars={len(saved_text_lw or '')}, "
        f"local_runtime_chars={len(runtime_text_lw or '')}, "
        f"aai_saved_chars={len(saved_text_aai or '')}, "
        f"mock_stt={mock_stt}, mock_aai={mock_aai}, file={filename})",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description=(
            "Create and run Transcribe File workflows in-process "
            "(local_whisper saved + runtime upload, AssemblyAI saved)."
        ),
    )
    p.add_argument("--user-id", default=None, help="User UUID (default: first user in the database).")
    p.add_argument("--real-stt", action="store_true", help="Call the real STT bridge (default: mock in-process).")
    p.add_argument(
        "--real-assemblyai",
        action="store_true",
        help="Call the real AssemblyAI API (default: mock in-process).",
    )
    p.add_argument(
        "--assemblyai-key",
        default=None,
        help="API key for AssemblyAI (overrides ASSEMBLYAI_API_KEY env when --real-assemblyai).",
    )
    p.add_argument(
        "--audio-file",
        default=None,
        help="Audio file to upload/transcribe (default: tiny WAV, good for mocked providers).",
    )
    p.add_argument("--no-cleanup", action="store_true", help="Keep created workflow/artifact/job rows.")
    args = p.parse_args()
    args.cleanup = not args.no_cleanup
    if (args.real_stt or args.real_assemblyai) and not args.audio_file:
        print(
            "Warning: --real-stt/--real-assemblyai without --audio-file uses silence and may "
            "return an empty transcript.",
            file=sys.stderr,
        )
    print(
        f"run_transcribe_file_workflow_e2e: cwd={os.getcwd()!r} "
        f"DATABASE_URL={settings.DATABASE_URL!r} STT_BRIDGE_URL={settings.STT_BRIDGE_URL!r} "
        f"ASSEMBLYAI_BASE_URL={settings.ASSEMBLYAI_BASE_URL!r}",
        file=sys.stderr,
    )
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
