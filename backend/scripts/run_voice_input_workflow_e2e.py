#!/usr/bin/env python3
"""
End-to-end: create a **Start → Voice input → Stop** graph in the DB, run
``WorkflowExecutor.execute_scheduled_run`` (NDJSON-compat events), and supply audio by calling
``complete_transcribe_wait`` the same way the API does after
``POST .../transcribe-audio``.

No browser and no HTTP to the app — only the same SQLite + ``.env`` as
``uvicorn`` when started from ``backend/`` (this script **chdir**s to
``backend/`` first).

**Default (CI / quick sanity):** STT is **mocked**; upload bytes are a tiny
placeholder WAV. Exits 0 if the run completes with **ok** and the voice step
succeeds.

**With real STT (and usually TTS for audio):** pass ``--real-stt`` and ensure
``STT_BRIDGE_URL`` points at a running stt-bridge. Use ``--audio tts`` to
synthesize a short line via the **TTS bridge** (same pattern as
``tests/test_tts_workflow_e2e_optional.py``) so the microphone is not required.
TTS model discovery: ``TTS_E2E_MODEL_KEY`` or a ``qwen_torch`` **base**
artifact under ``TTS_E2E_MODEL_ROOT`` (default: repo ``.local/tts-models``).

Examples::

  # Fast, no external services (mocks STT in-process)
  cd backend && uv run python scripts/run_voice_input_workflow_e2e.py

  # Full path: tts-bridge (speech) + stt-bridge (Whisper) + same .env as API
  cd backend && uv run python scripts/run_voice_input_workflow_e2e.py --real-stt --audio tts
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import io
import json
import os
import re
import sys
import uuid
import wave
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

# --- Match API: cwd is backend/ before loading Settings + SQLite URL. ---
_BACKEND_ROOT = Path(__file__).resolve().parent.parent
os.chdir(_BACKEND_ROOT)

import httpx
from sqlmodel import Session, select

from app.core.config import settings
from app.domain.services.workflow_executor import WorkflowExecutor
from app.domain.workflow_inprocess_ndjson import iterate_scheduled_run_ndjson_dicts, start_persisted_run_row
from app.domain.workflow_executor.transcribe_pending import TranscribeWaitKey, complete_transcribe_wait
from app.persistence.db import engine
from app.persistence.tables import User, WorkflowDefinition
from app.providers.tts_bridge import TtsBridgeError, synthesize_wav

REPO = _BACKEND_ROOT.parent
DEFAULT_TTS_ROOT = REPO / ".local" / "tts-models"
VOICE_NODE_ID = "vi"

_VOICE_GRAPH: dict[str, Any] = {
    "nodes": [
        {"id": "s", "kind": "start", "label": "S", "data": {"text": ""}, "position": {}},
        {
            "id": VOICE_NODE_ID,
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
        {"source": "s", "target": VOICE_NODE_ID},
        {
            "source": VOICE_NODE_ID,
            "target": "n_stop",
            "source_handle": "output",
            "target_handle": "output",
        },
    ],
}

_MOCK_STT_TEXT = "voice e2e mock transcript from script"


def _silent_wav_bytes() -> bytes:
    """~0.2s of silence, valid WAV, small upload."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(b"\x00\x00" * 3_200)
    return buf.getvalue()


def _discover_tts_model_key() -> str:
    key = (os.environ.get("TTS_E2E_MODEL_KEY") or "").strip()
    if key:
        return key
    root = Path(os.environ.get("TTS_E2E_MODEL_ROOT", str(DEFAULT_TTS_ROOT)))
    cfgs = sorted((root / "qwen_torch").glob("*/config.json")) if (root / "qwen_torch").is_dir() else []
    candidates: list[Path] = []
    for cfg in cfgs:
        base = cfg.parent
        if (base / "speech_tokenizer" / "config.json").is_file():
            candidates.append(base)
    if not candidates:
        raise RuntimeError(
            f"No qwen_torch model under {root} (config.json + speech_tokenizer). "
            "Set TTS_E2E_MODEL_KEY or TTS_E2E_MODEL_ROOT, or use --audio minimal with --real-stt only if your STT accepts the clip (often empty transcript).",
        )
    for base in candidates:
        try:
            with open(base / "config.json", encoding="utf-8") as f:
                meta = json.load(f)
        except (OSError, json.JSONDecodeError):
            continue
        if str(meta.get("tts_model_type") or "").lower() == "base":
            return f"qwen_torch/{base.name}"
    return f"qwen_torch/{candidates[0].name}"


def _stt_healthy() -> bool:
    base = (settings.STT_BRIDGE_URL or "").rstrip("/")
    if not base:
        return False
    try:
        r = httpx.get(f"{base}/health", timeout=4.0)
        return r.is_success
    except httpx.RequestError:
        return False


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
        raise SystemExit("No user in the database; import data or use --user-id <uuid>.")
    return u.id


async def _synthesize_utterance_wav() -> bytes:
    mkey = _discover_tts_model_key()
    return await synthesize_wav("qwen_torch", mkey, "One two three. Voice input end to end test.", None)


async def _run(args: argparse.Namespace) -> int:
    mock_stt = not args.real_stt
    use_tts = args.audio == "tts"

    if not mock_stt and not _stt_healthy():
        print(
            f"STT bridge not reachable at {settings.STT_BRIDGE_URL!r} (/health). "
            "Start services/stt-bridge or set STT_BRIDGE_URL.",
            file=sys.stderr,
        )
        return 1

    if use_tts and mock_stt:
        print("Note: with mocked STT, --audio tts still exercises the TTS bridge (upload bytes to transcribe).", file=sys.stderr)

    if use_tts and not _tts_bridge_smoke():
        return 1

    audio_task: asyncio.Task[bytes] | None = None
    if use_tts:

        async def _load() -> bytes:
            try:
                return await _synthesize_utterance_wav()
            except (RuntimeError, TtsBridgeError) as e:
                print(f"TTS failed: {e}", file=sys.stderr)
                raise

        audio_task = asyncio.create_task(_load())

    ctx = contextlib.nullcontext()
    m_stt: AsyncMock | None = None
    if mock_stt:

        async def _stt(_data: bytes, **_kwargs: Any) -> dict[str, Any]:
            return {"text": _MOCK_STT_TEXT, "language": "en", "segments": []}

        m_stt = AsyncMock(side_effect=_stt)
        ctx = patch("app.domain.workflow_executor.executor.transcribe_audio_bytes", m_stt)

    wf_id: uuid.UUID | None = None
    voice_text_out: str | None = None
    end_ok = False
    t_input_required: float | None = None
    t0 = asyncio.get_event_loop().time()

    with Session(engine) as session, ctx:
        user_id = _resolve_user_id(session, args.user_id)
        wf = WorkflowDefinition(
            user_id=user_id,
            name=f"voice input e2e {uuid.uuid4().hex[:8]}",
            graph=_VOICE_GRAPH,
        )
        session.add(wf)
        session.commit()
        session.refresh(wf)
        wf_id = wf.id

        run_row = start_persisted_run_row(session, workflow_id=wf.id, user_id=user_id)

        executor = WorkflowExecutor(session, user_id)

        async for ev in iterate_scheduled_run_ndjson_dicts(executor, wf, persist_run_record=run_row):
            if ev.get("event") == "input_required" and ev.get("node_id") == VOICE_NODE_ID:
                t_input_required = asyncio.get_event_loop().time() - t0
                if audio_task is not None:
                    abytes = await audio_task
                else:
                    abytes = _silent_wav_bytes()
                rid = uuid.UUID(str(ev["run_id"]))
                fl = ev.get("for_loop_id")
                it = int(ev.get("for_loop_iteration") or 0)
                k = TranscribeWaitKey(
                    run_id=rid,
                    node_id=VOICE_NODE_ID,
                    for_loop_id=fl if isinstance(fl, str) and fl.strip() else None,
                    iteration=it,
                )
                if not complete_transcribe_wait(k, abytes):
                    print("complete_transcribe_wait returned False (stale or duplicate key).", file=sys.stderr)
                    return 1
            if ev.get("event") == "node_end" and ev.get("node_id") == VOICE_NODE_ID and ev.get("result"):
                r = ev["result"] or {}
                out = r.get("output") or {}
                if out.get("kind") == "string":
                    voice_text_out = (out.get("text") or "").strip()
            if ev.get("event") == "end" and (ev.get("result") or {}).get("status") == "ok":
                end_ok = True

    if t_input_required is not None and t_input_required > 5.0:
        print(
            f"Warning: input_required arrived only after {t_input_required:.1f}s; expect under a few seconds.",
            file=sys.stderr,
        )
    if mock_stt and m_stt is not None:
        m_stt.assert_awaited_once()
    if not end_ok or not voice_text_out:
        print(f"Run did not complete ok or voice had no text. end_ok={end_ok} text={voice_text_out!r}", file=sys.stderr)
        return 1
    if mock_stt and _MOCK_STT_TEXT not in voice_text_out:
        print(f"Expected mock transcript; got: {voice_text_out!r}", file=sys.stderr)
        return 1

    if wf_id and args.cleanup:
        with Session(engine) as session2:
            row = session2.get(WorkflowDefinition, wf_id)
            if row is not None:
                session2.delete(row)
                session2.commit()

    print(
        f"ok — voice input step transcript ({len(voice_text_out)} chars). "
        f"workflow_id={wf_id} mock_stt={mock_stt} audio={args.audio}",
        file=sys.stderr,
    )
    return 0


def _tts_bridge_smoke() -> bool:
    base = (settings.TTS_BRIDGE_URL or "").rstrip("/")
    if not base:
        print("TTS_BRIDGE_URL is empty; cannot use --audio tts.", file=sys.stderr)
        return False
    try:
        r = httpx.get(f"{base}/health", timeout=4.0)
        r.raise_for_status()
    except Exception as e:  # noqa: BLE001
        print(f"TTS bridge not reachable at {base}: {e}", file=sys.stderr)
        return False
    return True


def main() -> int:
    p = argparse.ArgumentParser(
        description="Create and run Start → Voice input → Stop in-process (transcribe_audio e2e).",
    )
    p.add_argument(
        "--user-id",
        default=None,
        help="User UUID (default: first user in the database).",
    )
    p.add_argument(
        "--real-stt",
        action="store_true",
        help="Call the real STT bridge (default: mock in-process, no stt-bridge).",
    )
    p.add_argument(
        "--audio",
        choices=("minimal", "tts"),
        default="minimal",
        help="Source of upload bytes: tiny silence WAV, or TTS-synthesized speech (use with --real-stt).",
    )
    p.add_argument(
        "--no-cleanup",
        action="store_true",
        help="Keep the created WorkflowDefinition row (default: delete it after a successful run).",
    )
    args = p.parse_args()
    args.cleanup = not args.no_cleanup
    if args.real_stt and args.audio == "minimal":
        print(
            "Warning: --real-stt with --audio minimal often yields an empty transcript (Whisper on silence). "
            "Prefer: --real-stt --audio tts",
            file=sys.stderr,
        )

    print(
        f"run_voice_input_workflow_e2e: cwd={os.getcwd()!r} "
        f"DATABASE_URL={settings.DATABASE_URL!r} "
        f"STT_BRIDGE_URL={settings.STT_BRIDGE_URL!r} "
        f"TTS_BRIDGE_URL={settings.TTS_BRIDGE_URL!r}",
        file=sys.stderr,
    )
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
