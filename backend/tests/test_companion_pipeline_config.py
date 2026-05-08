"""Unit tests for workspace ``companion_pipeline`` configuration parsing and validation."""

from __future__ import annotations

import pytest

from app.domain.workspace.companion_pipeline_config import (
    COMPANION_PIPELINE_KEY,
    CompanionPipelineConfig,
    companion_pipeline_from_runtime_configuration,
    effective_compose_append,
    effective_interpret_append,
    render_pipeline_template,
    validate_companion_pipeline_blob,
    validate_runtime_configuration_has_valid_pipeline,
)


def test_companion_pipeline_defaults_when_missing():
    cfg = companion_pipeline_from_runtime_configuration({})
    assert cfg.version == 1
    assert cfg.post_compose == []
    assert effective_interpret_append(cfg) == ""


def test_interpret_append_when_enabled():
    raw = {
        COMPANION_PIPELINE_KEY: {
            "version": 1,
            "stages": {
                "interpret": {
                    "enabled": True,
                    "system_instructions_append": "  Focus on safety.  ",
                }
            },
        }
    }
    cfg = companion_pipeline_from_runtime_configuration(raw)
    assert effective_interpret_append(cfg) == "Focus on safety."


def test_interpret_append_disabled_ignored():
    raw = {
        COMPANION_PIPELINE_KEY: {
            "stages": {"interpret": {"enabled": False, "system_instructions_append": "X"}},
        }
    }
    cfg = companion_pipeline_from_runtime_configuration(raw)
    assert effective_interpret_append(cfg) == ""


def test_compose_append():
    raw = {
        COMPANION_PIPELINE_KEY: {
            "stages": {"compose": {"enabled": True, "instructions_append": "Be brief."}},
        }
    }
    cfg = companion_pipeline_from_runtime_configuration(raw)
    assert effective_compose_append(cfg) == "Be brief."


def test_render_pipeline_template():
    s = render_pipeline_template("Hello {{user_message}} — {{reply_text}}", {"user_message": "U", "reply_text": "R"})
    assert s == "Hello U — R"
    assert render_pipeline_template("{{missing}}", {}) == ""


def test_rejects_duplicate_post_compose_ids():
    blob = {
        "version": 1,
        "post_compose": [
            {"id": "a", "system_prompt": "x"},
            {"id": "a", "system_prompt": "y"},
        ],
    }
    with pytest.raises(ValueError, match="duplicate"):
        validate_companion_pipeline_blob(blob)


def test_rejects_too_many_post_steps():
    blob = {
        "version": 1,
        "post_compose": [{"id": f"s{i}", "system_prompt": "p"} for i in range(12)],
    }
    with pytest.raises(ValueError, match="at most"):
        validate_companion_pipeline_blob(blob)


def test_validate_runtime_configuration_noop_without_key():
    validate_runtime_configuration_has_valid_pipeline({"other": 1})


def test_validate_runtime_configuration_rejects_non_object_pipeline():
    with pytest.raises(ValueError):
        validate_runtime_configuration_has_valid_pipeline({COMPANION_PIPELINE_KEY: "nope"})


def test_interpret_system_prompt_base_parsed():
    raw = {
        COMPANION_PIPELINE_KEY: {
            "version": 1,
            "stages": {
                "interpret": {
                    "enabled": True,
                    "system_prompt_base": "Custom classifier prompt.",
                }
            },
        }
    }
    cfg = companion_pipeline_from_runtime_configuration(raw)
    assert cfg.stages.interpret.system_prompt_base == "Custom classifier prompt."


def test_interpret_system_prompt_base_defaults_to_none():
    cfg = companion_pipeline_from_runtime_configuration({})
    assert cfg.stages.interpret.system_prompt_base is None


def test_interpret_system_prompt_base_length_validation():
    blob = {
        "version": 1,
        "stages": {
            "interpret": {
                "system_prompt_base": "x" * 25_000,
            }
        },
    }
    with pytest.raises(ValueError, match="system_prompt_base exceeds maximum length"):
        validate_companion_pipeline_blob(blob)


def test_extra_forbidden():
    with pytest.raises(Exception):
        CompanionPipelineConfig.model_validate({"version": 1, "unknown": True})
