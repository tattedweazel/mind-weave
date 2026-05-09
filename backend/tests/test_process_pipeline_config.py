"""Unit tests for process step configuration parsing and validation."""

from __future__ import annotations

import pytest

from app.domain.workspace.companion_pipeline_config import (
    COMPANION_PIPELINE_KEY,
    CompanionPipelineConfig,
    ProcessStepConfig,
    ProcessStepKind,
    companion_pipeline_from_runtime_configuration,
    validate_companion_pipeline_blob,
)


def test_process_defaults_empty():
    cfg = companion_pipeline_from_runtime_configuration({})
    assert cfg.process == []


def test_process_step_parsing():
    raw = {
        COMPANION_PIPELINE_KEY: {
            "version": 1,
            "process": [
                {
                    "id": "sum1",
                    "kind": "summarize",
                    "enabled": True,
                    "description": "Summarize the emails.",
                }
            ],
        }
    }
    cfg = companion_pipeline_from_runtime_configuration(raw)
    assert len(cfg.process) == 1
    step = cfg.process[0]
    assert step.id == "sum1"
    assert step.kind == ProcessStepKind.summarize
    assert step.enabled is True
    assert step.description == "Summarize the emails."
    assert step.max_iterations == 3
    assert step.questions == []
    assert step.expose_in_traces is True


def test_all_process_step_kinds():
    for kind in ProcessStepKind:
        blob = {
            "version": 1,
            "process": [{"id": f"step_{kind.value}", "kind": kind.value}],
        }
        cfg = validate_companion_pipeline_blob(blob)
        assert cfg.process[0].kind == kind


def test_process_step_invalid_kind_rejected():
    blob = {
        "version": 1,
        "process": [{"id": "bad", "kind": "nonexistent"}],
    }
    with pytest.raises(Exception):
        validate_companion_pipeline_blob(blob)


def test_process_step_review_max_iterations():
    blob = {
        "version": 1,
        "process": [{"id": "rev", "kind": "review", "max_iterations": 5}],
    }
    cfg = validate_companion_pipeline_blob(blob)
    assert cfg.process[0].max_iterations == 5


def test_process_step_max_iterations_clamped():
    blob = {
        "version": 1,
        "process": [{"id": "rev", "kind": "review", "max_iterations": 0}],
    }
    with pytest.raises(Exception):
        validate_companion_pipeline_blob(blob)

    blob2 = {
        "version": 1,
        "process": [{"id": "rev", "kind": "review", "max_iterations": 11}],
    }
    with pytest.raises(Exception):
        validate_companion_pipeline_blob(blob2)


def test_process_step_investigate_questions():
    blob = {
        "version": 1,
        "process": [
            {
                "id": "inv",
                "kind": "investigate",
                "questions": ["What happened?", "When?"],
            }
        ],
    }
    cfg = validate_companion_pipeline_blob(blob)
    assert cfg.process[0].questions == ["What happened?", "When?"]


def test_process_step_questions_stripped():
    blob = {
        "version": 1,
        "process": [
            {
                "id": "inv",
                "kind": "investigate",
                "questions": ["  Q1  ", "", "  Q2  "],
            }
        ],
    }
    cfg = validate_companion_pipeline_blob(blob)
    assert cfg.process[0].questions == ["Q1", "Q2"]


def test_process_step_too_many_questions():
    blob = {
        "version": 1,
        "process": [
            {
                "id": "inv",
                "kind": "investigate",
                "questions": [f"Q{i}" for i in range(25)],
            }
        ],
    }
    with pytest.raises(Exception, match="questions"):
        validate_companion_pipeline_blob(blob)


def test_rejects_duplicate_process_ids():
    blob = {
        "version": 1,
        "process": [
            {"id": "a", "kind": "summarize"},
            {"id": "a", "kind": "critique"},
        ],
    }
    with pytest.raises(ValueError, match="duplicate"):
        validate_companion_pipeline_blob(blob)


def test_rejects_too_many_process_steps():
    blob = {
        "version": 1,
        "process": [{"id": f"p{i}", "kind": "summarize"} for i in range(12)],
    }
    with pytest.raises(ValueError, match="at most"):
        validate_companion_pipeline_blob(blob)


def test_rejects_oversized_process_description():
    blob = {
        "version": 1,
        "process": [{"id": "s1", "kind": "summarize", "description": "x" * 13_000}],
    }
    with pytest.raises(ValueError, match="description exceeds maximum length"):
        validate_companion_pipeline_blob(blob)


def test_process_step_model_strip():
    step = ProcessStepConfig(id="t", kind=ProcessStepKind.summarize, model="  gpt-4  ")
    assert step.model == "gpt-4"

    step2 = ProcessStepConfig(id="t", kind=ProcessStepKind.summarize, model="  ")
    assert step2.model is None


def test_process_step_id_strip():
    step = ProcessStepConfig(id="  myid  ", kind=ProcessStepKind.analyze)
    assert step.id == "myid"


def test_process_step_name_strip():
    step = ProcessStepConfig(id="t", kind=ProcessStepKind.critique, name="  My Step  ")
    assert step.name == "My Step"


def test_process_coexists_with_post_compose():
    blob = {
        "version": 1,
        "process": [{"id": "sum", "kind": "summarize", "description": "Summarize."}],
        "post_compose": [{"id": "tts", "system_prompt": "Convert to TTS."}],
    }
    cfg = validate_companion_pipeline_blob(blob)
    assert len(cfg.process) == 1
    assert len(cfg.post_compose) == 1
    assert cfg.process[0].kind == ProcessStepKind.summarize
    assert cfg.post_compose[0].id == "tts"


def test_process_extra_fields_rejected():
    blob = {
        "version": 1,
        "process": [{"id": "s", "kind": "summarize", "unexpected_field": True}],
    }
    with pytest.raises(Exception):
        validate_companion_pipeline_blob(blob)


def test_process_step_disabled():
    blob = {
        "version": 1,
        "process": [{"id": "s", "kind": "summarize", "enabled": False}],
    }
    cfg = validate_companion_pipeline_blob(blob)
    assert cfg.process[0].enabled is False


def test_process_step_expose_in_traces_default():
    blob = {
        "version": 1,
        "process": [{"id": "s", "kind": "summarize"}],
    }
    cfg = validate_companion_pipeline_blob(blob)
    assert cfg.process[0].expose_in_traces is True


def test_process_step_expose_in_traces_false():
    blob = {
        "version": 1,
        "process": [{"id": "s", "kind": "summarize", "expose_in_traces": False}],
    }
    cfg = validate_companion_pipeline_blob(blob)
    assert cfg.process[0].expose_in_traces is False


def test_pipeline_model_dump_roundtrip():
    cfg = CompanionPipelineConfig(
        version=1,
        process=[
            ProcessStepConfig(
                id="rev",
                kind=ProcessStepKind.review,
                description="Check quality.",
                max_iterations=5,
            ),
            ProcessStepConfig(
                id="sum",
                kind=ProcessStepKind.summarize,
                description="Summarize data.",
            ),
        ],
    )
    dumped = cfg.model_dump(mode="json")
    restored = CompanionPipelineConfig.model_validate(dumped)
    assert len(restored.process) == 2
    assert restored.process[0].kind == ProcessStepKind.review
    assert restored.process[0].max_iterations == 5
    assert restored.process[1].kind == ProcessStepKind.summarize
