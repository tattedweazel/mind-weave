"""Workspace-scoped Companion pipeline configuration (``runtime_configuration[\"companion_pipeline\"]``)."""

from __future__ import annotations

import re
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

COMPANION_PIPELINE_KEY = "companion_pipeline"

_MAX_INSTRUCTIONS_CHARS = 24_000
_MAX_POST_STEPS = 8
_MAX_PROCESS_STEPS = 8
_MAX_POST_SYSTEM_CHARS = 12_000
_MAX_PROCESS_DESCRIPTION_CHARS = 12_000
_MAX_PROCESS_QUESTIONS = 20
_MAX_STEP_ID_LEN = 64
_MAX_OUTPUT_KEY_LEN = 64


class InterpretStageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    model_override: Optional[str] = None
    system_prompt_base: Optional[str] = None
    system_instructions_append: Optional[str] = None

    @field_validator("model_override")
    @classmethod
    def _strip_model(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @field_validator("system_prompt_base", "system_instructions_append")
    @classmethod
    def _strip_append(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v


class ComposeStageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    model_override: Optional[str] = None
    voice_override: Optional[str] = None
    instructions_append: Optional[str] = None

    @field_validator("model_override")
    @classmethod
    def _strip_model(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @field_validator("voice_override", "instructions_append")
    @classmethod
    def _strip_text(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v


class SessionSummaryStageConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    enabled: bool = True
    model_override: Optional[str] = None
    instructions_append: Optional[str] = None

    @field_validator("model_override")
    @classmethod
    def _strip_model(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @field_validator("instructions_append")
    @classmethod
    def _strip_append(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        return v


class PostComposeStepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=_MAX_STEP_ID_LEN)
    enabled: bool = True
    name: str = ""
    model: Optional[str] = None
    system_prompt: str = ""
    replace_streamed_reply: bool = False
    expose_in_traces: bool = True
    output_key: str = Field(default="text", max_length=_MAX_OUTPUT_KEY_LEN)

    @field_validator("id", "name", "output_key")
    @classmethod
    def _strip_ids(cls, v: str) -> str:
        return (v or "").strip()

    @field_validator("model")
    @classmethod
    def _strip_model(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None


class ProcessStepKind(str, Enum):
    review = "review"
    critique = "critique"
    summarize = "summarize"
    investigate = "investigate"
    analyze = "analyze"


class ProcessStepConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, max_length=_MAX_STEP_ID_LEN)
    kind: ProcessStepKind
    enabled: bool = True
    name: str = ""
    model: Optional[str] = None
    description: str = ""
    max_iterations: int = Field(default=3, ge=1, le=10)
    questions: List[str] = Field(default_factory=list)
    expose_in_traces: bool = True

    @field_validator("id", "name")
    @classmethod
    def _strip_ids(cls, v: str) -> str:
        return (v or "").strip()

    @field_validator("model")
    @classmethod
    def _strip_model(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        s = v.strip()
        return s or None

    @field_validator("questions")
    @classmethod
    def _limit_questions(cls, v: List[str]) -> List[str]:
        if len(v) > _MAX_PROCESS_QUESTIONS:
            raise ValueError(f"questions supports at most {_MAX_PROCESS_QUESTIONS} entries")
        return [q.strip() for q in v if q.strip()]


class CompanionPipelineStages(BaseModel):
    model_config = ConfigDict(extra="forbid")

    interpret: InterpretStageConfig = Field(default_factory=InterpretStageConfig)
    compose: ComposeStageConfig = Field(default_factory=ComposeStageConfig)
    session_summary: SessionSummaryStageConfig = Field(default_factory=SessionSummaryStageConfig)


class CompanionPipelineConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: int = 1
    stages: CompanionPipelineStages = Field(default_factory=CompanionPipelineStages)
    process: List[ProcessStepConfig] = Field(default_factory=list)
    post_compose: List[PostComposeStepConfig] = Field(default_factory=list)

    @field_validator("process")
    @classmethod
    def _limit_process_steps(cls, v: List[ProcessStepConfig]) -> List[ProcessStepConfig]:
        if len(v) > _MAX_PROCESS_STEPS:
            raise ValueError(f"process supports at most {_MAX_PROCESS_STEPS} steps")
        seen: set[str] = set()
        for step in v:
            if step.id in seen:
                raise ValueError(f"duplicate process id: {step.id!r}")
            seen.add(step.id)
        return v

    @field_validator("post_compose")
    @classmethod
    def _limit_steps(cls, v: List[PostComposeStepConfig]) -> List[PostComposeStepConfig]:
        if len(v) > _MAX_POST_STEPS:
            raise ValueError(f"post_compose supports at most {_MAX_POST_STEPS} steps")
        seen: set[str] = set()
        for step in v:
            if step.id in seen:
                raise ValueError(f"duplicate post_compose id: {step.id!r}")
            seen.add(step.id)
        return v


def companion_pipeline_from_runtime_configuration(raw: Any) -> CompanionPipelineConfig:
    """Parse ``companion_pipeline`` from workspace ``runtime_configuration`` (defaults if missing)."""
    if not isinstance(raw, dict):
        return CompanionPipelineConfig()
    blob = raw.get(COMPANION_PIPELINE_KEY)
    if blob is None:
        return CompanionPipelineConfig()
    if not isinstance(blob, dict):
        raise ValueError("companion_pipeline must be an object")
    return CompanionPipelineConfig.model_validate(blob)


def merge_runtime_configuration_with_pipeline(
    runtime_configuration: Dict[str, Any],
    pipeline: CompanionPipelineConfig,
) -> Dict[str, Any]:
    """Return a copy of runtime_configuration with ``companion_pipeline`` replaced."""
    rc = dict(runtime_configuration or {})
    rc[COMPANION_PIPELINE_KEY] = pipeline.model_dump(mode="json")
    return rc


_TEMPLATE_PLACEHOLDER = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def render_pipeline_template(template: str, context: Dict[str, str]) -> str:
    """Replace ``{{ key }}`` placeholders with values from ``context`` (missing keys → empty string)."""

    def _sub(m: re.Match[str]) -> str:
        key = m.group(1)
        return context.get(key, "")

    return _TEMPLATE_PLACEHOLDER.sub(_sub, template)


def validate_companion_pipeline_blob(blob: Any) -> CompanionPipelineConfig:
    """Validate a ``companion_pipeline`` JSON object; raises ValueError on failure."""
    if blob is None:
        return CompanionPipelineConfig()
    if not isinstance(blob, dict):
        raise ValueError("companion_pipeline must be an object")
    cfg = CompanionPipelineConfig.model_validate(blob)
    _validate_instruction_lengths(cfg)
    return cfg


def validate_runtime_configuration_has_valid_pipeline(rc: Any) -> None:
    """If ``runtime_configuration`` contains ``companion_pipeline``, validate it."""
    if not isinstance(rc, dict):
        return
    if COMPANION_PIPELINE_KEY not in rc:
        return
    validate_companion_pipeline_blob(rc.get(COMPANION_PIPELINE_KEY))


def _validate_instruction_lengths(cfg: CompanionPipelineConfig) -> None:
    b = cfg.stages.interpret.system_prompt_base or ""
    if len(b) > _MAX_INSTRUCTIONS_CHARS:
        raise ValueError("stages.interpret.system_prompt_base exceeds maximum length")
    i = cfg.stages.interpret.system_instructions_append or ""
    if len(i) > _MAX_INSTRUCTIONS_CHARS:
        raise ValueError("stages.interpret.system_instructions_append exceeds maximum length")
    c = cfg.stages.compose.instructions_append or ""
    if len(c) > _MAX_INSTRUCTIONS_CHARS:
        raise ValueError("stages.compose.instructions_append exceeds maximum length")
    s = cfg.stages.session_summary.instructions_append or ""
    if len(s) > _MAX_INSTRUCTIONS_CHARS:
        raise ValueError("stages.session_summary.instructions_append exceeds maximum length")
    for proc_step in cfg.process:
        if len(proc_step.description) > _MAX_PROCESS_DESCRIPTION_CHARS:
            raise ValueError(f"process step {proc_step.id!r}: description exceeds maximum length")
    for post_step in cfg.post_compose:
        if len(post_step.system_prompt) > _MAX_POST_SYSTEM_CHARS:
            raise ValueError(f"post_compose step {post_step.id!r}: system_prompt exceeds maximum length")


def effective_interpret_append(cfg: CompanionPipelineConfig) -> str:
    if not cfg.stages.interpret.enabled:
        return ""
    return (cfg.stages.interpret.system_instructions_append or "").strip()


def effective_compose_append(cfg: CompanionPipelineConfig) -> str:
    if not cfg.stages.compose.enabled:
        return ""
    return (cfg.stages.compose.instructions_append or "").strip()


def effective_session_summary_append(cfg: CompanionPipelineConfig) -> str:
    if not cfg.stages.session_summary.enabled:
        return ""
    return (cfg.stages.session_summary.instructions_append or "").strip()
