#!/usr/bin/env python3
"""
End-to-end: create and run **Audio File Input → Stop** workflows in-process.

This script proves the workflow node actually executes, not just that schemas
parse. It covers both supported V1 paths:

1. saved artifact: `audio_file_artifacts` row -> sync WorkflowExecutor.run
2. run-time upload: `run_stream` -> `input_required` -> deliver file bytes

Default mode mocks STT, so no external service calls are made. Pass
`--real-stt --audio-file /path/to/clip.wav` to call the real STT bridge.

Examples::

  cd backend && uv run python scripts/run_audio_file_input_workflow_e2e.py
  cd backend && uv run python scripts/run_audio_file_input_workflow_e2e.py --real-stt --audio-file ../sample.wav
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
from app.domain.workflow_executor.transcribe_pending import TranscribeWaitKey, complete_transcribe_wait  # noqa: E402
from app.persistence.db import engine  # noqa: E402
from app.persistence.tables import AudioFileArtifact, User, WorkflowDefinition, utc_now  # noqa: E402

NODE_ID = "audio_file"
_MOCK_STT_TEXT = "audio file input e2e mock transcript from script"


def _silent_wav_bytes() -> bytes:
    """Small valid WAV; useful for mocked STT and route/handoff sanity checks."""
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
    return _silent_wav_bytes(), "audio-file-input-e2e.wav", "audio/wav"


def _graph(*, artifact_id: uuid.UUID | None) -> dict[str, Any]:
    data: dict[str, Any] = {"task": "transcribe"}
    if artifact_id is not None:
        data["audio_artifact_id"] = str(artifact_id)
    return {
        "nodes": [
            {"id": "s", "kind": "start", "label": "Start", "data": {"text": ""}, "position": {}},
            {
                "id": NODE_ID,
                "kind": "skill",
                "skill_type": "audio_file_input",
                "label": "Audio File Input",
                "data": data,
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


def _node_text(result: Any) -> str | None:
    for node_result in result.node_results:
        if node_result.node_id != NODE_ID or node_result.output is None:
            continue
        out = node_result.output
        if getattr(out, "kind", None) == "string":
            return str(getattr(out, "text", "")).strip()
    return None


async def _run_saved_artifact(session: Session, user_id: uuid.UUID, audio: bytes, filename: str, content_type: str) -> tuple[uuid.UUID, uuid.UUID, str]:
    validated = validate_audio_upload(audio, filename=filename, content_type=content_type)
    now = utc_now()
    artifact = AudioFileArtifact(
        user_id=user_id,
        filename=validated.filename,
        mime_type=validated.mime_type,
        size_bytes=validated.size_bytes,
        audio_bytes=audio,
        created_at=now,
        updated_at=now,
    )
    session.add(artifact)
    session.commit()
    session.refresh(artifact)

    wf = WorkflowDefinition(
        user_id=user_id,
        name=f"audio file input saved e2e {uuid.uuid4().hex[:8]}",
        graph=_graph(artifact_id=artifact.id),
    )
    session.add(wf)
    session.commit()
    session.refresh(wf)

    result = await WorkflowExecutor(session, user_id).run(wf)
    text = _node_text(result)
    if result.status != "ok" or not text:
        raise RuntimeError(f"saved artifact workflow failed: status={result.status} text={text!r}")
    return wf.id, artifact.id, text


async def _run_runtime_upload(session: Session, user_id: uuid.UUID, audio: bytes, filename: str, content_type: str) -> tuple[uuid.UUID, str]:
    validate_audio_upload(audio, filename=filename, content_type=content_type)
    wf = WorkflowDefinition(
        user_id=user_id,
        name=f"audio file input runtime e2e {uuid.uuid4().hex[:8]}",
        graph=_graph(artifact_id=None),
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
            if ev.get("event") == "input_required" and ev.get("kind") == "audio_file_input":
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
                    key,
                    audio,
                    filename=filename,
                    content_type=content_type,
                )
                if not ok:
                    raise RuntimeError("complete_transcribe_wait returned False for runtime upload")
            if ev.get("event") == "node_end" and ev.get("node_id") == NODE_ID:
                out = (ev.get("result") or {}).get("output") or {}
                if out.get("kind") == "string":
                    text = (out.get("text") or "").strip()
            if ev.get("event") == "end" and (ev.get("result") or {}).get("status") == "ok":
                end_ok = True

    if not input_required_seen or not end_ok or not text:
        raise RuntimeError(f"runtime upload workflow failed: input_required={input_required_seen} end_ok={end_ok} text={text!r}")
    return wf.id, text


async def _run(args: argparse.Namespace) -> int:
    mock_stt = not args.real_stt
    if args.real_stt and not _stt_healthy():
        print(
            f"STT bridge not reachable at {settings.STT_BRIDGE_URL!r} (/health). "
            "Start services/stt-bridge or omit --real-stt.",
            file=sys.stderr,
        )
        return 1

    audio, filename, content_type = _audio_bytes_from_args(args)

    ctx = contextlib.nullcontext()
    m_stt: AsyncMock | None = None
    if mock_stt:

        async def _stt(_data: bytes, **_kwargs: Any) -> dict[str, Any]:
            return {"text": _MOCK_STT_TEXT, "language": "en", "segments": [], "duration_seconds": 1.0}

        m_stt = AsyncMock(side_effect=_stt)
        ctx = patch("app.domain.workflow_executor.executor.transcribe_audio_bytes", m_stt)

    created_workflows: list[uuid.UUID] = []
    created_artifacts: list[uuid.UUID] = []
    with Session(engine) as session, ctx:
        user_id = _resolve_user_id(session, args.user_id)
        saved_wf, artifact_id, saved_text = await _run_saved_artifact(session, user_id, audio, filename, content_type)
        created_workflows.append(saved_wf)
        created_artifacts.append(artifact_id)

        runtime_wf, runtime_text = await _run_runtime_upload(session, user_id, audio, filename, content_type)
        created_workflows.append(runtime_wf)

        if mock_stt and m_stt is not None and m_stt.await_count != 2:
            raise RuntimeError(f"Expected mocked STT to be awaited twice, got {m_stt.await_count}")
        if mock_stt and (_MOCK_STT_TEXT not in saved_text or _MOCK_STT_TEXT not in runtime_text):
            raise RuntimeError(f"Unexpected mock transcripts: saved={saved_text!r} runtime={runtime_text!r}")

        if args.cleanup:
            for wf_id in created_workflows:
                row = session.get(WorkflowDefinition, wf_id)
                if row is not None:
                    session.delete(row)
            for artifact_id in created_artifacts:
                row = session.get(AudioFileArtifact, artifact_id)
                if row is not None:
                    session.delete(row)
            session.commit()

    print(
        "ok — Audio File Input workflows completed "
        f"(saved_chars={len(saved_text)}, runtime_chars={len(runtime_text)}, mock_stt={mock_stt}, file={filename})",
        file=sys.stderr,
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Create and run Audio File Input workflows in-process (saved artifact + runtime upload).",
    )
    p.add_argument("--user-id", default=None, help="User UUID (default: first user in the database).")
    p.add_argument("--real-stt", action="store_true", help="Call the real STT bridge (default: mock in-process).")
    p.add_argument("--audio-file", default=None, help="Audio file to upload/transcribe (default: tiny WAV, good for mocked STT).")
    p.add_argument("--no-cleanup", action="store_true", help="Keep created workflow/artifact rows.")
    args = p.parse_args()
    args.cleanup = not args.no_cleanup
    if args.real_stt and not args.audio_file:
        print("Warning: --real-stt without --audio-file uses silence and may return an empty transcript.", file=sys.stderr)

    print(
        f"run_audio_file_input_workflow_e2e: cwd={os.getcwd()!r} "
        f"DATABASE_URL={settings.DATABASE_URL!r} STT_BRIDGE_URL={settings.STT_BRIDGE_URL!r}",
        file=sys.stderr,
    )
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
