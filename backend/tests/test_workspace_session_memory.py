"""Session-scoped workspace memory (active_summary, prompt injection, summarization fallbacks)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import cast

import pytest
from sqlmodel import Session, select

from app.domain.schemas.workspace_contracts import (
    CapabilityRunResult,
    ExecutionPayload,
    ExecutionResult,
    IntentPayload,
    InterpretationPayload,
    RoutingPayload,
    RoutingPlan,
    SelectedCapability,
    TurnOutcomeType,
)
from app.domain.services.workspace_runtime_service import (
    _DEFAULT_SESSION_MEMORY_BACKFILL_TURNS,
    _DEFAULT_SESSION_MEMORY_MAX_PROMPT_CHARS,
    _DEFAULT_SESSION_MEMORY_MAX_STORED_CHARS,
    WorkspaceRuntimeService,
)
from app.persistence.tables import Companion, User, Workspace, WorkspaceSession, WorkspaceTurn
from app.providers.base import ProviderResponse


def test_session_context_block_empty():
    assert WorkspaceRuntimeService._session_context_block("", max_chars=100) == ""
    assert WorkspaceRuntimeService._session_context_block("   ", max_chars=100) == ""


def test_session_context_block_truncates():
    long = "x" * 100
    out = WorkspaceRuntimeService._session_context_block(long, max_chars=20)
    assert "Session memory" in out
    assert len(out) < len(long) + 200
    assert out.endswith("…\n") or "…" in out


def test_deterministic_summary_merge_respects_max():
    prev = "a" * 50
    digest = "b" * 100
    merged = WorkspaceRuntimeService._deterministic_summary_merge(prev, digest, max_chars=80)
    assert len(merged) <= 80


def test_deterministic_summary_merge_truncates_long_digest_chunk():
    digest = "z\n" * 900
    merged = WorkspaceRuntimeService._deterministic_summary_merge("", digest, max_chars=5000)
    assert "…" in merged
    assert len(merged) < len(digest)


def test_turn_digest_includes_execution_status():
    svc = WorkspaceRuntimeService.__new__(WorkspaceRuntimeService)  # type: ignore[misc]
    rp = RoutingPlan(
        payload=RoutingPayload(
            selected_capabilities=[
                SelectedCapability(capability_key="wf:11111111-1111-1111-1111-111111111111", input_bindings={})
            ]
        )
    )
    er = ExecutionResult(
        payload=ExecutionPayload(
            capability_results=[
                CapabilityRunResult(
                    capability_key="wf:11111111-1111-1111-1111-111111111111",
                    status="success",
                    validation={"passed": True},
                )
            ]
        )
    )
    d = svc._turn_digest_for_session_summary(
        user_message="check mail",
        assistant_reply="here is a summary",
        routing_plan=rp,
        execution_result=er,
        outcome=TurnOutcomeType.invoke_capabilities,
    )
    assert "check mail" in d
    assert "here is a summary" in d
    assert "success" in d
    assert "wf:11111111-1111-1111-1111-111111111111" in d


def test_turn_digest_truncates_long_user_and_assistant_and_errors():
    svc = WorkspaceRuntimeService.__new__(WorkspaceRuntimeService)  # type: ignore[misc]
    long_u = "U" * 5000
    long_a = "A" * 6000
    er = ExecutionResult(
        payload=ExecutionPayload(
            capability_results=[
                CapabilityRunResult(
                    capability_key="wf:11111111-1111-1111-1111-111111111111",
                    status="error",
                    error="E" * 500,
                    validation={},
                )
            ]
        )
    )
    d = svc._turn_digest_for_session_summary(
        user_message=long_u,
        assistant_reply=long_a,
        routing_plan=None,
        execution_result=er,
        outcome=TurnOutcomeType.respond_directly,
    )
    assert d.endswith("\n")
    assert "…" in d
    assert "E" * 250 not in d


def test_session_memory_limits_non_dict_runtime_configuration_uses_defaults():
    svc = WorkspaceRuntimeService.__new__(WorkspaceRuntimeService)  # type: ignore[misc]
    fake_ws = cast(Workspace, SimpleNamespace(runtime_configuration=[]))
    p, s, b = svc._session_memory_limits(fake_ws)
    assert p == _DEFAULT_SESSION_MEMORY_MAX_PROMPT_CHARS
    assert s == _DEFAULT_SESSION_MEMORY_MAX_STORED_CHARS
    assert b == _DEFAULT_SESSION_MEMORY_BACKFILL_TURNS


def test_session_memory_limits_invalid_int_values_use_defaults():
    ws = Workspace(
        id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        name="BadInts",
        runtime_configuration={"session_memory_max_prompt_chars": "nope"},
    )
    svc = WorkspaceRuntimeService.__new__(WorkspaceRuntimeService)  # type: ignore[misc]
    p, _, _ = svc._session_memory_limits(ws)
    assert p == _DEFAULT_SESSION_MEMORY_MAX_PROMPT_CHARS


def test_session_memory_limits_read_runtime_configuration():
    ws = Workspace(
        id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        name="Cfg",
        runtime_configuration={
            "session_memory_max_prompt_chars": 900,
            "session_memory_max_stored_chars": 1200,
            "session_memory_backfill_turns": 5,
        },
    )
    svc = WorkspaceRuntimeService.__new__(WorkspaceRuntimeService)  # type: ignore[misc]
    p, s, b = svc._session_memory_limits(ws)
    assert p == 900
    assert s == 1200
    assert b == 5


@pytest.mark.asyncio
async def test_interpret_system_includes_session_context(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    captured: list = []

    class CaptureProvider:
        async def chat(self, messages, options=None):
            captured.extend(messages)
            return ProviderResponse(
                raw_text='{"intent":{"key":"chat","summary":"Hi"},"outcome_type":"respond_directly","confidence":0.9}',
                parsed={
                    "intent": {"key": "chat", "summary": "Hi"},
                    "outcome_type": "respond_directly",
                    "confidence": 0.9,
                    "candidate_capabilities": [],
                    "normalized_inputs": {},
                },
                provider_name="lmstudio",
                usage=None,
            )

    svc = WorkspaceRuntimeService(db_session, user.id)

    async def _lm():
        return CaptureProvider()

    monkeypatch.setattr(svc, "_lm_provider", _lm)
    ws = Workspace(id=uuid.uuid4(), owner_user_id=user.id, name="MemWS")
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    block = WorkspaceRuntimeService._session_context_block("Earlier you checked email.", max_chars=500)
    await svc._interpret("What did we do?", ws, companion, session_context=block)
    assert captured
    system = captured[0]["content"]
    assert "Session memory" in system
    assert "Earlier you checked email" in system


@pytest.mark.asyncio
async def test_compose_user_block_includes_session_context(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    captured: list = []

    class CaptureProvider:
        async def chat(self, messages, options=None):
            captured.extend(messages)
            return ProviderResponse(
                raw_text='{"reply_text":"ok","memory_candidates":[]}',
                parsed={"reply_text": "ok", "memory_candidates": []},
                provider_name="lmstudio",
                usage=None,
            )

    svc = WorkspaceRuntimeService(db_session, user.id)

    async def _lm():
        return CaptureProvider()

    monkeypatch.setattr(svc, "_lm_provider", _lm)
    ws = Workspace(id=uuid.uuid4(), owner_user_id=user.id, name="MemWS2")
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    block = WorkspaceRuntimeService._session_context_block("Prior topic: inbox.", max_chars=500)
    interp = InterpretationPayload(
        intent=IntentPayload(key="chat", summary="q"),
        outcome_type=TurnOutcomeType.respond_directly,
    )
    await svc._compose_and_memory(
        user_message="again?",
        companion=companion,
        workspace=ws,
        interpretation=interp,
        execution=None,
        outcome=TurnOutcomeType.respond_directly,
        session_context=block,
    )
    user_content = captured[1]["content"]
    assert "Session memory" in user_content
    assert "Prior topic: inbox" in user_content


@pytest.mark.asyncio
async def test_refresh_active_summary_llm_success(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None

    class OkProvider:
        async def chat(self, messages, options=None):
            return ProviderResponse(
                raw_text=json.dumps({"summary": "Merged one line."}),
                parsed={"summary": "Merged one line."},
                provider_name="lmstudio",
                usage=None,
            )

    svc = WorkspaceRuntimeService(db_session, user.id)

    async def _lm():
        return OkProvider()

    monkeypatch.setattr(svc, "_lm_provider", _lm)
    ws = Workspace(id=uuid.uuid4(), owner_user_id=user.id, name="Sum")
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    sess = WorkspaceSession(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        companion_id=companion.id,
        title="t",
        turn_count=0,
        transient_state={},
        active_summary="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(ws)
    db_session.add(companion)
    db_session.add(sess)
    db_session.commit()
    db_session.refresh(sess)

    await svc._refresh_active_summary(
        workspace=ws,
        companion=companion,
        session_row=sess,
        turn_digest="user_message=hi\nassistant_reply=yo\n",
    )
    db_session.refresh(sess)
    assert sess.active_summary == "Merged one line."


@pytest.mark.asyncio
async def test_refresh_active_summary_llm_failure_uses_deterministic(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None

    class BoomProvider:
        async def chat(self, messages, options=None):
            raise RuntimeError("no lm")

    svc = WorkspaceRuntimeService(db_session, user.id)

    async def _lm():
        return BoomProvider()

    monkeypatch.setattr(svc, "_lm_provider", _lm)
    ws = Workspace(id=uuid.uuid4(), owner_user_id=user.id, name="Sum2")
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    sess = WorkspaceSession(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        companion_id=companion.id,
        title="t",
        turn_count=0,
        transient_state={},
        active_summary="seed",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(ws)
    db_session.add(companion)
    db_session.add(sess)
    db_session.commit()

    await svc._refresh_active_summary(
        workspace=ws,
        companion=companion,
        session_row=sess,
        turn_digest="user_message=do thing\n",
    )
    db_session.refresh(sess)
    assert "seed" in sess.active_summary
    assert "user_message=do thing" in sess.active_summary


@pytest.mark.asyncio
async def test_maybe_backfill_builds_summary_from_turns(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    ws = Workspace(id=uuid.uuid4(), owner_user_id=user.id, name="Bf")
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    sid = uuid.uuid4()
    sess = WorkspaceSession(
        id=sid,
        workspace_id=ws.id,
        companion_id=companion.id,
        title="t",
        turn_count=1,
        transient_state={},
        active_summary="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(ws)
    db_session.add(companion)
    db_session.add(sess)
    delivery = {
        "payload": {"final_user_response": {"rendered_text": "I summarized your inbox.", "render_mode": "chat_message"}}
    }
    turn = WorkspaceTurn(
        session_id=sid,
        turn_index=0,
        trace_id="t1",
        user_input="Check my email",
        outcome_type="invoke_capabilities",
        delivered_response=delivery,
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(turn)
    db_session.commit()

    calls: list[str] = []

    async def capture_refresh(self, *, workspace, companion, session_row, turn_digest):
        calls.append(turn_digest)
        session_row.active_summary = "backfilled"
        session_row.updated_at = datetime.now(timezone.utc)
        self.session.add(session_row)
        self.session.commit()
        self.session.refresh(session_row)

    svc = WorkspaceRuntimeService(db_session, user.id)
    monkeypatch.setattr(WorkspaceRuntimeService, "_refresh_active_summary", capture_refresh)

    await svc._maybe_backfill_session_summary(ws, companion, sess)
    assert len(calls) == 1
    assert "BACKFILL_FROM_STORED_TURNS" in calls[0]
    assert "Check my email" in calls[0]
    assert "summarized your inbox" in calls[0]
    db_session.refresh(sess)
    assert sess.active_summary == "backfilled"


@pytest.mark.asyncio
async def test_session_summary_model_option_prefers_runtime_configuration(db_session: Session):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    ws = Workspace(
        id=uuid.uuid4(),
        owner_user_id=user.id,
        name="M",
        interpretation_model="interp-x",
        runtime_configuration={"session_summary_model": "summary-special"},
    )
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    svc = WorkspaceRuntimeService(db_session, user.id)
    assert svc._session_summary_model_option(ws, companion) == "summary-special"


@pytest.mark.asyncio
async def test_session_summary_model_option_falls_back_to_companion_model(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    ws = Workspace(
        id=uuid.uuid4(),
        owner_user_id=user.id,
        name="M3",
        interpretation_model=None,
        runtime_configuration={},
    )
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    svc = WorkspaceRuntimeService(db_session, user.id)
    monkeypatch.setattr(svc, "_companion_model", lambda _c: "persona-mm")
    assert svc._session_summary_model_option(ws, companion) == "persona-mm"


@pytest.mark.asyncio
async def test_session_summary_model_option_falls_back_to_interpretation_model(db_session: Session):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    ws = Workspace(
        id=uuid.uuid4(),
        owner_user_id=user.id,
        name="M2",
        interpretation_model="interp-only",
        runtime_configuration={},
    )
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    svc = WorkspaceRuntimeService(db_session, user.id)
    assert svc._session_summary_model_option(ws, companion) == "interp-only"


@pytest.mark.asyncio
async def test_refresh_active_summary_parses_raw_text_when_parsed_missing(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None

    class RawProvider:
        async def chat(self, messages, options=None):
            return ProviderResponse(
                raw_text=json.dumps({"summary": " from raw "}),
                parsed=None,
                provider_name="lmstudio",
                usage=None,
            )

    svc = WorkspaceRuntimeService(db_session, user.id)

    async def _lm():
        return RawProvider()

    monkeypatch.setattr(svc, "_lm_provider", _lm)
    ws = Workspace(id=uuid.uuid4(), owner_user_id=user.id, name="Raw")
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    sess = WorkspaceSession(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        companion_id=companion.id,
        title="t",
        turn_count=0,
        transient_state={},
        active_summary="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(ws)
    db_session.add(companion)
    db_session.add(sess)
    db_session.commit()

    await svc._refresh_active_summary(
        workspace=ws,
        companion=companion,
        session_row=sess,
        turn_digest="x",
    )
    db_session.refresh(sess)
    assert sess.active_summary == "from raw"


@pytest.mark.asyncio
async def test_refresh_active_summary_truncates_very_long_prior_before_llm(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None

    captured: list = []

    class CaptureProvider:
        async def chat(self, messages, options=None):
            captured.append(messages[1]["content"])
            return ProviderResponse(
                raw_text=json.dumps({"summary": "short"}),
                parsed={"summary": "short"},
                provider_name="lmstudio",
                usage=None,
            )

    svc = WorkspaceRuntimeService(db_session, user.id)

    async def _lm():
        return CaptureProvider()

    monkeypatch.setattr(svc, "_lm_provider", _lm)
    ws = Workspace(
        id=uuid.uuid4(),
        owner_user_id=user.id,
        name="PrevLong",
        runtime_configuration={"session_memory_max_stored_chars": 100},
    )
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    prev = "P" * 500
    sess = WorkspaceSession(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        companion_id=companion.id,
        title="t",
        turn_count=0,
        transient_state={},
        active_summary=prev,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(ws)
    db_session.add(companion)
    db_session.add(sess)
    db_session.commit()

    await svc._refresh_active_summary(
        workspace=ws,
        companion=companion,
        session_row=sess,
        turn_digest="new",
    )
    assert captured
    user_block = captured[0]
    assert "PRIOR_SUMMARY:" in user_block
    assert len(user_block) < len(prev) + 500


@pytest.mark.asyncio
async def test_refresh_active_summary_truncates_overlong_llm_summary(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None

    class LongProvider:
        async def chat(self, messages, options=None):
            return ProviderResponse(
                raw_text=json.dumps({"summary": "Z" * 20000}),
                parsed={"summary": "Z" * 20000},
                provider_name="lmstudio",
                usage=None,
            )

    svc = WorkspaceRuntimeService(db_session, user.id)

    async def _lm():
        return LongProvider()

    monkeypatch.setattr(svc, "_lm_provider", _lm)
    ws = Workspace(
        id=uuid.uuid4(),
        owner_user_id=user.id,
        name="Long",
        # Below the runtime floor (512); limits clamp to 512.
        runtime_configuration={"session_memory_max_stored_chars": 400},
    )
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    sess = WorkspaceSession(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        companion_id=companion.id,
        title="t",
        turn_count=0,
        transient_state={},
        active_summary="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(ws)
    db_session.add(companion)
    db_session.add(sess)
    db_session.commit()

    await svc._refresh_active_summary(
        workspace=ws,
        companion=companion,
        session_row=sess,
        turn_digest="x",
    )
    db_session.refresh(sess)
    assert len(sess.active_summary) <= 520


@pytest.mark.asyncio
async def test_maybe_backfill_ignores_malformed_delivered_response_payload(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    ws = Workspace(id=uuid.uuid4(), owner_user_id=user.id, name="BadDr")
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    sid = uuid.uuid4()
    sess = WorkspaceSession(
        id=sid,
        workspace_id=ws.id,
        companion_id=companion.id,
        title="t",
        turn_count=1,
        transient_state={},
        active_summary="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(ws)
    db_session.add(companion)
    db_session.add(sess)

    class _Bad(dict):
        def get(self, key, default=None):  # type: ignore[override]
            if key == "final_user_response":
                raise RuntimeError("bad structure")
            return super().get(key, default)

    turn = WorkspaceTurn(
        session_id=sid,
        turn_index=0,
        trace_id="t1",
        user_input="Hi",
        outcome_type="respond_directly",
        delivered_response={"payload": _Bad()},
        created_at=datetime.now(timezone.utc),
    )
    db_session.add(turn)
    db_session.commit()

    calls: list[str] = []

    async def capture_refresh(self, *, workspace, companion, session_row, turn_digest):
        calls.append(turn_digest)

    monkeypatch.setattr(WorkspaceRuntimeService, "_refresh_active_summary", capture_refresh)
    svc = WorkspaceRuntimeService(db_session, user.id)
    await svc._maybe_backfill_session_summary(ws, companion, sess)
    assert len(calls) == 1
    assert "user: Hi" in calls[0]
    assert "assistant:" in calls[0]


@pytest.mark.asyncio
async def test_maybe_backfill_skips_when_summary_already_set(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    ws = Workspace(id=uuid.uuid4(), owner_user_id=user.id, name="SkipBf")
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    sess = WorkspaceSession(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        companion_id=companion.id,
        title="t",
        turn_count=3,
        transient_state={},
        active_summary="already",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(ws)
    db_session.add(companion)
    db_session.add(sess)
    db_session.commit()

    called = []

    async def no_refresh(self, **kwargs):
        called.append(True)

    monkeypatch.setattr(WorkspaceRuntimeService, "_refresh_active_summary", no_refresh)
    svc = WorkspaceRuntimeService(db_session, user.id)
    await svc._maybe_backfill_session_summary(ws, companion, sess)
    assert called == []


@pytest.mark.asyncio
async def test_maybe_backfill_noop_when_no_turn_rows(db_session: Session, monkeypatch):
    user = db_session.exec(select(User).where(User.username == "testuser")).first()
    assert user is not None
    ws = Workspace(id=uuid.uuid4(), owner_user_id=user.id, name="EmptyBf")
    companion = Companion(id=uuid.uuid4(), owner_user_id=user.id)
    sess = WorkspaceSession(
        id=uuid.uuid4(),
        workspace_id=ws.id,
        companion_id=companion.id,
        title="t",
        turn_count=1,
        transient_state={},
        active_summary="",
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    db_session.add(ws)
    db_session.add(companion)
    db_session.add(sess)
    db_session.commit()

    called = []

    async def no_refresh(self, **kwargs):
        called.append(True)

    monkeypatch.setattr(WorkspaceRuntimeService, "_refresh_active_summary", no_refresh)
    svc = WorkspaceRuntimeService(db_session, user.id)
    await svc._maybe_backfill_session_summary(ws, companion, sess)
    assert called == []
