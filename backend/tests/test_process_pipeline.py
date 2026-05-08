"""Unit tests for _run_process_pipeline and related process step logic."""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

import pytest

from app.domain.schemas.workspace_contracts import (
    CapabilityRunResult,
    ExecutionPayload,
)
from app.domain.services.workspace_runtime_service import (
    _PROCESS_OUTPUT_KEYS,
    _PROCESS_SCHEMAS,
    WorkspaceRuntimeService,
    _build_analyze_messages,
    _build_critique_messages,
    _build_investigate_messages,
    _build_review_messages,
    _build_summarize_messages,
    _compact_execution_for_process,
)
from app.domain.workspace.companion_pipeline_config import (
    CompanionPipelineConfig,
    ProcessStepConfig,
    ProcessStepKind,
)
from app.persistence.tables import Companion, Workspace
from app.providers.base import ProviderResponse

# ---------------------------------------------------------------------------
# Mock LM provider
# ---------------------------------------------------------------------------

class _MockProvider:
    """Fake LM provider that returns canned responses based on the schema name."""

    def __init__(self, responses: Optional[List[Dict[str, Any]]] = None, fail: bool = False):
        self._responses = list(responses or [])
        self._call_idx = 0
        self._fail = fail
        self.calls: List[Dict[str, Any]] = []

    async def chat(self, messages, *, options=None):
        self.calls.append({"messages": messages, "options": options or {}})
        if self._fail:
            raise RuntimeError("LLM unavailable")
        if self._call_idx < len(self._responses):
            data = self._responses[self._call_idx]
        else:
            data = self._responses[-1] if self._responses else {}
        self._call_idx += 1
        return ProviderResponse(
            raw_text=json.dumps(data),
            parsed=data,
            provider_name="mock",
        )


def _make_svc() -> WorkspaceRuntimeService:
    svc = WorkspaceRuntimeService.__new__(WorkspaceRuntimeService)
    return svc


def _make_workspace(**overrides) -> Workspace:
    defaults = dict(
        id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
        name="TestWS",
        runtime_configuration={},
    )
    defaults.update(overrides)
    return Workspace(**defaults)


def _make_companion(**overrides) -> Companion:
    defaults = dict(
        id=uuid.uuid4(),
        owner_user_id=uuid.uuid4(),
    )
    defaults.update(overrides)
    return Companion(**defaults)


def _execution_with_output(output: Dict[str, Any]) -> ExecutionPayload:
    return ExecutionPayload(
        capability_results=[
            CapabilityRunResult(
                capability_key="wf:00000000-0000-0000-0000-000000000001",
                status="success",
                output=output,
            )
        ]
    )


# ---------------------------------------------------------------------------
# Tests: module-level prompt builders
# ---------------------------------------------------------------------------


def test_compact_execution_for_process_with_data():
    ex = _execution_with_output({"data": [{"name": "Alice"}, {"name": "Bob"}]})
    text = _compact_execution_for_process(ex)
    assert "wf:" in text
    assert "success" in text
    assert "Alice" in text


def test_compact_execution_for_process_none():
    text = _compact_execution_for_process(None)
    assert text == "(no execution data)"


def test_compact_execution_for_process_empty():
    ex = ExecutionPayload(capability_results=[])
    text = _compact_execution_for_process(ex)
    assert text == "(no execution data)"


def test_build_review_messages():
    sys, usr = _build_review_messages("exec data", "Desired: summary")
    assert "quality-review" in sys
    assert "Desired: summary" in usr
    assert "exec data" in usr


def test_build_review_messages_with_prior():
    sys, usr = _build_review_messages("exec", "desc", prior_output="prior", feedback="fix it")
    assert "prior" in usr
    assert "fix it" in usr


def test_build_critique_messages():
    sys, usr = _build_critique_messages("exec data", "Desired: critique")
    assert "critique" in sys
    assert "Desired: critique" in usr


def test_build_summarize_messages():
    sys, usr = _build_summarize_messages("exec data", "Desired: summary")
    assert "summarization" in sys
    assert "Desired: summary" in usr


def test_build_investigate_messages():
    sys, usr = _build_investigate_messages("exec data", "Desired: answers", ["Q1", "Q2"])
    assert "investigation" in sys
    assert "Q1" in usr
    assert "Q2" in usr


def test_build_investigate_messages_no_questions():
    sys, usr = _build_investigate_messages("exec data", "desc", [])
    assert "relevant findings" in usr


def test_build_analyze_messages():
    sys, usr = _build_analyze_messages("exec data", "Desired: analysis")
    assert "analysis" in sys
    assert "Desired: analysis" in usr


def test_process_schemas_all_kinds_present():
    for kind in ProcessStepKind:
        assert kind in _PROCESS_SCHEMAS
        assert kind in _PROCESS_OUTPUT_KEYS


# ---------------------------------------------------------------------------
# Tests: _run_process_pipeline
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_process_pipeline_no_steps():
    svc = _make_svc()
    cfg = CompanionPipelineConfig(version=1, process=[])
    payload, sse = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=None,
    )
    assert payload.step_results == []
    assert sse == []


@pytest.mark.asyncio
async def test_run_process_pipeline_disabled_step_skipped():
    svc = _make_svc()
    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(id="s1", kind=ProcessStepKind.summarize, enabled=False, description="Sum.")
        ],
    )
    payload, sse = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=None,
    )
    assert payload.step_results == []
    assert sse == []


@pytest.mark.asyncio
async def test_run_process_pipeline_summarize(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(responses=[{"summary": "Here is the summary."}])

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(id="sum1", kind=ProcessStepKind.summarize, description="Summarize emails.")
        ],
    )
    ex = _execution_with_output({"data": [{"subject": "Hello"}]})
    payload, sse = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=ex,
    )
    assert len(payload.step_results) == 1
    r = payload.step_results[0]
    assert r.step_id == "sum1"
    assert r.kind == "summarize"
    assert r.status == "success"
    assert r.output == "Here is the summary."
    assert r.iterations_used == 1
    assert len(sse) == 2
    assert "started" in sse[0]
    assert "completed" in sse[1]


@pytest.mark.asyncio
async def test_run_process_pipeline_critique(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(responses=[{"notes": "The data looks reasonable."}])

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(id="crit1", kind=ProcessStepKind.critique, description="Critique the output.")
        ],
    )
    payload, sse = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=_execution_with_output({"text": "some results"}),
    )
    assert len(payload.step_results) == 1
    assert payload.step_results[0].kind == "critique"
    assert payload.step_results[0].output == "The data looks reasonable."


@pytest.mark.asyncio
async def test_run_process_pipeline_investigate(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(responses=[{"answers": "Q1: Yes. Q2: No."}])

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(
                id="inv1", kind=ProcessStepKind.investigate,
                description="Answer questions.", questions=["Q1?", "Q2?"],
            )
        ],
    )
    payload, _ = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=_execution_with_output({"text": "data"}),
    )
    assert payload.step_results[0].output == "Q1: Yes. Q2: No."


@pytest.mark.asyncio
async def test_run_process_pipeline_analyze(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(responses=[{"analysis": "3 items, avg score 4.5."}])

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(id="an1", kind=ProcessStepKind.analyze, description="Analyze scores.")
        ],
    )
    payload, _ = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=_execution_with_output({"data": [{"score": 5}, {"score": 4}]}),
    )
    assert payload.step_results[0].output == "3 items, avg score 4.5."


@pytest.mark.asyncio
async def test_run_process_pipeline_review_approved_first_iteration(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(responses=[
        {"reviewed_content": "Looks good.", "approved": True, "feedback": ""},
    ])

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(
                id="rev1", kind=ProcessStepKind.review,
                description="Review quality.", max_iterations=3,
            )
        ],
    )
    payload, _ = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=_execution_with_output({"text": "content"}),
    )
    r = payload.step_results[0]
    assert r.kind == "review"
    assert r.status == "success"
    assert r.approved is True
    assert r.iterations_used == 1
    assert r.output == "Looks good."


@pytest.mark.asyncio
async def test_run_process_pipeline_review_iterates_then_approves(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(responses=[
        {"reviewed_content": "Draft 1", "approved": False, "feedback": "Needs more detail."},
        {"reviewed_content": "Draft 2", "approved": False, "feedback": "Almost there."},
        {"reviewed_content": "Final draft", "approved": True, "feedback": ""},
    ])

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(
                id="rev2", kind=ProcessStepKind.review,
                description="Check quality.", max_iterations=5,
            )
        ],
    )
    payload, _ = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=_execution_with_output({"text": "raw"}),
    )
    r = payload.step_results[0]
    assert r.approved is True
    assert r.iterations_used == 3
    assert r.output == "Final draft"
    assert len(provider.calls) == 3


@pytest.mark.asyncio
async def test_run_process_pipeline_review_max_iterations_reached(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(responses=[
        {"reviewed_content": "Draft", "approved": False, "feedback": "Not good enough."},
    ])

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(
                id="rev3", kind=ProcessStepKind.review,
                description="Strict review.", max_iterations=2,
            )
        ],
    )
    payload, _ = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=_execution_with_output({"text": "raw"}),
    )
    r = payload.step_results[0]
    assert r.iterations_used == 2
    assert r.approved is False
    assert r.status == "success"
    assert len(provider.calls) == 2


@pytest.mark.asyncio
async def test_run_process_pipeline_llm_error(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(fail=True)

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(id="fail1", kind=ProcessStepKind.summarize, description="X")
        ],
    )
    payload, sse = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=None,
    )
    r = payload.step_results[0]
    assert r.status == "error"
    assert "LLM unavailable" in r.error
    assert len(sse) == 2


@pytest.mark.asyncio
async def test_run_process_pipeline_review_llm_error_mid_loop(monkeypatch):
    svc = _make_svc()

    call_count = 0

    class _FailOnSecond:
        async def chat(self, messages, *, options=None):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                data = {"reviewed_content": "Draft", "approved": False, "feedback": "Revise."}
                return ProviderResponse(raw_text=json.dumps(data), parsed=data, provider_name="mock")
            raise RuntimeError("Connection lost")

    async def _lm():
        return _FailOnSecond()

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(id="rev_fail", kind=ProcessStepKind.review, description="R", max_iterations=5)
        ],
    )
    payload, _ = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=_execution_with_output({"text": "raw"}),
    )
    r = payload.step_results[0]
    assert r.status == "error"
    assert r.iterations_used == 2
    assert "Connection lost" in r.error


@pytest.mark.asyncio
async def test_run_process_pipeline_unparseable_response(monkeypatch):
    svc = _make_svc()

    class _BadProvider:
        async def chat(self, messages, *, options=None):
            return ProviderResponse(raw_text="not json", parsed=None, provider_name="mock")

    async def _lm():
        return _BadProvider()

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(id="bad1", kind=ProcessStepKind.summarize, description="S")
        ],
    )
    payload, _ = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=None,
    )
    assert payload.step_results[0].status == "error"
    assert "unparseable" in payload.step_results[0].error


@pytest.mark.asyncio
async def test_run_process_pipeline_multiple_steps(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(responses=[
        {"summary": "Summary output."},
        {"notes": "Critique notes."},
    ])

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(id="sum", kind=ProcessStepKind.summarize, description="Sum."),
            ProcessStepConfig(id="crit", kind=ProcessStepKind.critique, description="Crit."),
        ],
    )
    payload, sse = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=_execution_with_output({"text": "data"}),
    )
    assert len(payload.step_results) == 2
    assert payload.step_results[0].kind == "summarize"
    assert payload.step_results[1].kind == "critique"
    assert len(sse) == 4


@pytest.mark.asyncio
async def test_run_process_pipeline_sse_events(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(responses=[{"summary": "S"}])

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(id="s1", kind=ProcessStepKind.summarize, description="D")
        ],
    )
    _, sse = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=None,
    )
    assert len(sse) == 2
    started = json.loads(sse[0].replace("data: ", "").strip())
    completed = json.loads(sse[1].replace("data: ", "").strip())
    assert started["stage"] == "process:s1"
    assert started["status"] == "started"
    assert started["detail"]["kind"] == "summarize"
    assert completed["stage"] == "process:s1"
    assert completed["status"] == "completed"
    assert "ms" in completed


@pytest.mark.asyncio
async def test_run_process_pipeline_expose_in_traces(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(responses=[{"summary": "Short summary."}])

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(
                id="t1", kind=ProcessStepKind.summarize,
                description="D", expose_in_traces=True,
            )
        ],
    )
    payload, _ = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=None,
    )
    traces = payload.debug.get("process_traces", [])
    assert len(traces) == 1
    assert traces[0]["output_preview"] == "Short summary."


@pytest.mark.asyncio
async def test_run_process_pipeline_trace_no_preview_when_disabled(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(responses=[{"summary": "Hidden."}])

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(
                id="t2", kind=ProcessStepKind.summarize,
                description="D", expose_in_traces=False,
            )
        ],
    )
    payload, _ = await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=None,
    )
    traces = payload.debug.get("process_traces", [])
    assert len(traces) == 1
    assert "output_preview" not in traces[0]


@pytest.mark.asyncio
async def test_run_process_pipeline_model_override(monkeypatch):
    svc = _make_svc()
    provider = _MockProvider(responses=[{"summary": "OK"}])

    async def _lm():
        return provider

    monkeypatch.setattr(svc, "_lm_provider", _lm)

    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(
                id="m1", kind=ProcessStepKind.summarize,
                description="D", model="custom-model-v1",
            )
        ],
    )
    await svc._run_process_pipeline(
        pipeline_cfg=cfg,
        workspace=_make_workspace(),
        companion=_make_companion(),
        execution=None,
    )
    assert provider.calls[0]["options"].get("model") == "custom-model-v1"
