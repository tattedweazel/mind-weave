"""Staged Workspace turn runtime: interpret → route → execute → process → compose → deliver → persist."""

from __future__ import annotations

import asyncio
import json
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncIterator, Dict, List, Optional, Set, Tuple
from zoneinfo import ZoneInfo

from sqlmodel import Session, select

from app.core.logging import logger
from app.core.user_api_keys_crypto import decrypt_api_keys_store
from app.domain.persona_lm_options import persona_lm_chat_options
from app.domain.schemas.workflow_run import WorkflowRunResult
from app.domain.schemas.workspace_contracts import (
    CapabilityRunResult,
    CompositionPayload,
    ExecutionPayload,
    ExecutionResult,
    FinalUserResponsePayload,
    IntentPayload,
    InterpretationPayload,
    InterpretationResult,
    MemoryProposalCreate,
    PermissionChecksPayload,
    PolicyDecisionsPayload,
    ProcessPayload,
    ProcessResult,
    ProcessStepResult,
    ResponsePayloadContent,
    RoutingPayload,
    RoutingPlan,
    SelectedCapability,
    TurnOutcomeType,
)
from app.domain.schemas.workspace_contracts import (
    DeliveryPayload as DeliveryPayloadModel,
)
from app.domain.schemas.workspace_contracts import (
    DeliveryResult as DeliveryResultModel,
)
from app.domain.services.workflow_definition_service import WorkflowDefinitionService
from app.domain.services.workflow_executor import WorkflowExecutor
from app.domain.workflow_executor.executor import _effective_gmail_calendar_zone
from app.domain.workflow_executor.schema_normalizer import normalize_schema_for_structured_output
from app.domain.workspace.capability_resolution import (
    parse_workflow_id_from_capability_key,
    resolve_capability_for_user,
    workflow_capability_key,
)
from app.domain.workspace.companion_pipeline_config import (
    CompanionPipelineConfig,
    ProcessStepConfig,
    ProcessStepKind,
    companion_pipeline_from_runtime_configuration,
    effective_compose_append,
    effective_interpret_append,
    effective_session_summary_append,
    render_pipeline_template,
)
from app.domain.workspace.interpret_json_schema import interpret_json_schema_with_strict_candidate_bindings
from app.domain.workspace.start_inputs import (
    extract_start_input_slots_from_workflow_graph,
    filter_bindings_to_allowed,
    format_start_slots_for_capability_prompt,
    missing_required_start_binding_keys,
    start_slots_for_api,
    validate_capability_start_bindings,
)
from app.domain.workspace.workspace_google_graph import skill_node_skill_type
from app.domain.workspace.workspace_redaction import redact_workspace_trace
from app.persistence.tables import (
    Companion,
    CompanionMemoryEntry,
    Persona,
    User,
    WorkflowDefinition,
    Workspace,
    WorkspaceReplay,
    WorkspaceSession,
    WorkspaceTurn,
)
from app.providers.lmstudio import LMStudioProvider
from app.providers.lmstudio_http import resolve_lmstudio_bearer

CAPABILITY_PROPOSAL_STATE_KEY = "capability_proposal"

DEFAULT_INTERPRET_BASE_PROMPT = (
    "You classify the user's message for a conversational workspace. "
    "Follow the JSON schema exactly.\n\n"
    "outcome_type values:\n"
    "- respond_directly -- The user is chatting, asking a question, making small talk, "
    "asking about capabilities, or anything that does not require running a tool. "
    "This is the most common outcome.\n"
    "- clarify -- The user seems to want an action but their request is ambiguous or "
    "missing key details. Ask a clarifying question.\n"
    "- invoke_capabilities -- The user is explicitly requesting an action that maps to "
    "one of the available capabilities below. Only choose this when the intent to act "
    "is clear.\n"
    "- decline_or_block -- The request is unsafe, violates policy, or is outside scope.\n\n"
    "IMPORTANT: Do not invoke a capability just because one exists that could match. "
    "If the user is asking *about* a capability, discussing what's possible, or making "
    "conversation, use respond_directly.\n\n"
    "When outcome_type is invoke_capabilities, set candidate_capabilities with "
    "capability_key, confidence, and input_bindings. Each entry must match the schema "
    "branch for that capability_key: input_bindings must include every required Start "
    "key listed for that workflow (RFC3339 for datetimes). You may also set "
    "normalized_inputs for a single workflow when one capability matches — per-candidate "
    "input_bindings take precedence. Datetime values must be RFC3339. "
    "For every capability you select, include **all required** Start input keys in "
    "input_bindings (or normalized_inputs); omitting a required key will block execution. "
    "Use correct JSON types: arrays for list slots, objects for dictionary/structure/gmail, "
    "booleans for boolean, numbers for int, strings for string/datetime. "
    "Use **exact** Start input key spellings from each capability line (e.g. email_list, "
    "not emailList); wrong keys are ignored."
)
PROPOSAL_TTL_SECONDS = 900
_WORKSPACE_MAX_FAILED_NODE_SUMMARIES = 8
_WORKSPACE_MAX_NODE_ERROR_CHARS = 400
_MAX_NESTED_WORKFLOW_DEPTH_FOR_GMAIL_SCAN = 8
# Match workflow run_stream keepalive: bytes during long LM awaits so nginx / NAT (~60s idle) do not drop SSE.
_WORKSPACE_SSE_KEEPALIVE_INTERVAL_SEC = 25.0
_DEFAULT_SESSION_MEMORY_MAX_PROMPT_CHARS = 6000
_DEFAULT_SESSION_MEMORY_MAX_STORED_CHARS = 8000
_DEFAULT_SESSION_MEMORY_BACKFILL_TURNS = 12
_COMPOSE_STRUCTURED_OUTPUT_FALLBACK_CHARS = 1500

DEFAULT_COMPOSE_BASE_PROMPT = (
    "You compose the assistant reply for a Workspace turn.\n"
    "- reply_text: For each capability with status success, if a structured_output= line includes JSON, "
    "summarize the relevant facts in plain language for the user (counts, subjects, key fields—only what "
    "appears there; do not invent). For status error, include the specific error in reply_text.\n"
    "- When structured_output contains multiple items (e.g. emails, events), summarize ALL of them in "
    "reply_text—not only the first. Include the total count and key details from each item.\n"
    "- Do not paste large raw JSON blobs into reply_text. Do not echo internal field names or labels from "
    "this prompt (for example the structured_output prefix) as if they were user-visible placeholder text.\n"
    "- memory_candidates: only durable facts the user explicitly asked to remember or clearly stated as "
    "long-term; otherwise return an empty array. Do not invent private data."
)

DEFAULT_COMPOSE_WITH_PROCESS_PROMPT = (
    "You compose the assistant reply for a Workspace turn by cohering processed results.\n"
    "- reply_text: Merge the process step outputs below into a single coherent response. "
    "Each step has already analyzed, summarized, reviewed, or investigated the raw data. "
    "Your job is to unify them into one clear, user-facing reply. Preserve all key findings "
    "and details from each step. Do not invent data beyond what the steps provide.\n"
    "- memory_candidates: only durable facts the user explicitly asked to remember or clearly stated as "
    "long-term; otherwise return an empty array. Do not invent private data."
)


def _is_email_item(item: Dict[str, Any]) -> bool:
    if isinstance(item.get("id"), str) and isinstance(item.get("threadId"), str):
        return True
    return any(k in item for k in ("body_text", "snippet")) and any(k in item for k in ("from", "subject"))


def _is_calendar_item(item: Dict[str, Any]) -> bool:
    return isinstance(item.get("summary"), str) and ("start" in item or "end" in item)


def _compact_email_line(idx: int, item: Dict[str, Any]) -> str:
    parts: List[str] = [f"[{idx}]"]
    for key, label in (("from", "From"), ("subject", "Subject"), ("date", "Date")):
        val = item.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(f"{label}: {val.strip()}")
    if not any(k in item for k in ("from", "subject", "date")):
        snippet = item.get("body_text") or item.get("snippet") or ""
        if isinstance(snippet, str) and snippet.strip():
            parts.append(snippet.strip()[:80])
    return " | ".join(parts)


def _compact_calendar_line(idx: int, item: Dict[str, Any]) -> str:
    parts: List[str] = [f"[{idx}]"]
    for key, label in (("summary", "Summary"), ("start", "Start"), ("end", "End"), ("location", "Location")):
        val = item.get(key)
        if val is None:
            continue
        if isinstance(val, str) and val.strip():
            parts.append(f"{label}: {val.strip()}")
        elif isinstance(val, dict):
            dt = val.get("dateTime") or val.get("date") or ""
            if isinstance(dt, str) and dt.strip():
                parts.append(f"{label}: {dt.strip()}")
    return " | ".join(parts)


def _compact_generic_line(idx: int, item: Dict[str, Any]) -> str:
    parts: List[str] = [f"[{idx}]"]
    for key, val in list(item.items())[:6]:
        if isinstance(val, str) and val.strip():
            parts.append(f"{key}: {val.strip()[:60]}")
        elif isinstance(val, (int, float, bool)):
            parts.append(f"{key}: {val}")
    return " | ".join(parts)


def _extract_list_from_output(output: Dict[str, Any]) -> Optional[List[Any]]:
    """Try to find a list of items inside a capability output dict."""
    data = output.get("data")
    if isinstance(data, list):
        return data
    text = output.get("text")
    if isinstance(text, str):
        stripped = text.strip()
        if stripped.startswith("["):
            try:
                parsed = json.loads(stripped)
                if isinstance(parsed, list):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                pass
    return None


def _compact_capability_output_for_compose(output: Dict[str, Any]) -> str:
    """Produce a compact, LLM-friendly summary of a capability output for the compose step.

    For list-shaped results, extracts key fields per item so every item is visible to
    the compose LLM. Falls back to truncated JSON for non-list outputs.
    """
    items = _extract_list_from_output(output)
    if items is None or len(items) == 0:
        return json.dumps(output, ensure_ascii=False)[:_COMPOSE_STRUCTURED_OUTPUT_FALLBACK_CHARS]

    dict_items = [i for i in items if isinstance(i, dict)]
    if not dict_items:
        return json.dumps(output, ensure_ascii=False)[:_COMPOSE_STRUCTURED_OUTPUT_FALLBACK_CHARS]

    first = dict_items[0]
    if _is_email_item(first):
        lines = [_compact_email_line(i + 1, d) for i, d in enumerate(dict_items)]
    elif _is_calendar_item(first):
        lines = [_compact_calendar_line(i + 1, d) for i, d in enumerate(dict_items)]
    else:
        lines = [_compact_generic_line(i + 1, d) for i, d in enumerate(dict_items)]

    return f"{len(dict_items)} items: " + " ".join(lines)


async def iter_sse_keepalive_lines_while_task_pending(
    task: asyncio.Task,
    *,
    interval_sec: float = _WORKSPACE_SSE_KEEPALIVE_INTERVAL_SEC,
) -> AsyncIterator[str]:
    """Yield SSE comment lines while ``task`` runs (same idea as executor parallel-batch keepalive)."""
    while not task.done():
        done, _ = await asyncio.wait({task}, timeout=interval_sec, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            break
        yield ": sse-keepalive\n\n"


def format_workspace_stage_sse(
    stage: str,
    status: str,
    *,
    detail: Optional[Dict[str, Any]] = None,
    ms: Optional[float] = None,
) -> str:
    payload: Dict[str, Any] = {"event": "stage", "stage": stage, "status": status}
    if detail:
        payload["detail"] = detail
    if ms is not None:
        payload["ms"] = round(ms, 2)
    return f"data: {json.dumps(payload)}\n\n"


def _graph_has_gmail_list_messages_deep(
    session: Session,
    user_id: uuid.UUID,
    graph: Optional[Dict[str, Any]],
    *,
    depth: int = 0,
    visited_wf_ids: Optional[Set[uuid.UUID]] = None,
) -> bool:
    """True if this graph or a referenced sub-workflow (depth-limited) contains gmail_list_messages."""
    if not graph or not isinstance(graph, dict) or depth > _MAX_NESTED_WORKFLOW_DEPTH_FOR_GMAIL_SCAN:
        return False
    if visited_wf_ids is None:
        visited_wf_ids = set()
    svc = WorkflowDefinitionService(session, user_id)
    for n in graph.get("nodes") or []:
        if not isinstance(n, dict):
            continue
        if n.get("kind") == "skill" and skill_node_skill_type(n) == "gmail_list_messages":
            return True
        if n.get("kind") == "workflow":
            data = n.get("data") if isinstance(n.get("data"), dict) else {}
            raw_wid = data.get("workflow_id")
            if not raw_wid:
                continue
            try:
                wid = uuid.UUID(str(raw_wid))
            except (ValueError, TypeError):
                continue
            if wid in visited_wf_ids:
                continue
            sub = svc.get_workflow(wid)
            if sub is None:
                continue
            visited_wf_ids.add(wid)
            if _graph_has_gmail_list_messages_deep(
                session, user_id, sub.graph, depth=depth + 1, visited_wf_ids=visited_wf_ids
            ):
                return True
    return False


def _apply_email_list_default_for_gmail_workflow(
    session: Session,
    user_id: uuid.UUID,
    graph: Optional[Dict[str, Any]],
    bindings: Dict[str, Any],
) -> Dict[str, Any]:
    """If the graph (or nested refs) has Gmail List Messages and Start requires email_list, default to []."""
    if not _graph_has_gmail_list_messages_deep(session, user_id, graph):
        return bindings
    slots = extract_start_input_slots_from_workflow_graph(graph)
    out = dict(bindings)
    for s in slots:
        if s.key == "email_list" and not s.has_static_default:
            if "email_list" not in out or out.get("email_list") is None:
                out["email_list"] = []
            break
    return out


def format_workspace_temporal_context_for_llm(now_utc: datetime, workflow_iana: Optional[str]) -> str:
    """
    Fixed clock lines for interpret/compose prompts so relative phrases (e.g. \"last 5 days\")
    bind to real calendar time. ``now_utc`` should be timezone-aware; naive values are treated as UTC.
    """
    if now_utc.tzinfo is None:
        now_utc = now_utc.replace(tzinfo=timezone.utc)
    else:
        now_utc = now_utc.astimezone(timezone.utc)
    lines = [
        "Temporal context (use these clocks for relative dates like \"last 5 days\"; "
        "datetime Start inputs must be RFC3339 and consistent with this \"now\"):",
        f"- Current time (UTC): {now_utc.isoformat()}",
    ]
    z = (workflow_iana or "").strip()
    if z:
        try:
            local = now_utc.astimezone(ZoneInfo(z))
            lines.append(f"- Current time (user workflow timezone {z}): {local.isoformat()}")
        except Exception:
            logger.debug("Ignoring invalid workflow_time_zone for temporal context: %r", z)
    lines.append(
        "- When the user gives a relative window, compute after/before or other datetime bindings from the "
        "clocks above (prefer the workflow timezone line when present for calendar-day boundaries)."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Process-step prompt builders (module-level, one per ProcessStepKind)
# ---------------------------------------------------------------------------

_PROCESS_OUTPUT_CHARS_LIMIT = 6000


def _compact_execution_for_process(execution: Optional[ExecutionPayload]) -> str:
    """Build a compact text representation of capability execution results for process steps."""
    if not execution or not execution.capability_results:
        return "(no execution data)"
    parts: List[str] = []
    for r in execution.capability_results:
        line = f"- {r.capability_key} status={r.status}"
        if r.error:
            line += f" error={r.error}"
        if r.output:
            line += f" output={_compact_capability_output_for_compose(r.output)}"
        parts.append(line)
    return "\n".join(parts)


def _build_review_messages(
    execution_text: str, description: str, *, prior_output: str = "", feedback: str = ""
) -> tuple[str, str]:
    system = (
        "You are a quality-review step in a data pipeline. "
        "Evaluate whether the candidate content meets the desired output criteria. "
        "Return JSON with: reviewed_content (the content, revised if needed), "
        "approved (boolean: true if it meets criteria, false if not), "
        "and feedback (string: what needs improvement, empty if approved)."
    )
    user_parts = [f"Desired output:\n{description}\n"]
    if prior_output:
        user_parts.append(f"Previous attempt:\n{prior_output}\n")
    if feedback:
        user_parts.append(f"Prior feedback:\n{feedback}\n")
    user_parts.append(f"Execution data:\n{execution_text}")
    return system, "\n".join(user_parts)


def _build_critique_messages(execution_text: str, description: str) -> tuple[str, str]:
    system = (
        "You are a critique step in a data pipeline. "
        "Provide observations, notes, and recommendations about the data relative to the "
        "desired output description. Return JSON with: notes (string: your observations "
        "and recommendations)."
    )
    user = f"Desired output:\n{description}\n\nExecution data:\n{execution_text}"
    return system, user


def _build_summarize_messages(execution_text: str, description: str) -> tuple[str, str]:
    system = (
        "You are a summarization step in a data pipeline. "
        "Take the list of items from the execution data and produce a structured summary "
        "guided by the desired output description. Return JSON with: summary (string: "
        "your summary of the data)."
    )
    user = f"Desired output:\n{description}\n\nExecution data:\n{execution_text}"
    return system, user


def _build_investigate_messages(
    execution_text: str, description: str, questions: List[str]
) -> tuple[str, str]:
    system = (
        "You are an investigation step in a data pipeline. "
        "Using the provided data, attempt to answer each question. "
        "Return JSON with: answers (string: your consolidated answers to all questions, "
        "citing relevant data)."
    )
    q_block = "\n".join(f"- {q}" for q in questions) if questions else "- Provide relevant findings."
    user = (
        f"Desired output:\n{description}\n\n"
        f"Questions:\n{q_block}\n\n"
        f"Execution data:\n{execution_text}"
    )
    return system, user


def _build_analyze_messages(execution_text: str, description: str) -> tuple[str, str]:
    system = (
        "You are an analysis step in a data pipeline. "
        "Perform the requested analysis on the provided data: counts, distributions, "
        "trends, patterns, or other statistical observations as described. "
        "Return JSON with: analysis (string: your analysis results)."
    )
    user = f"Desired output / analysis instructions:\n{description}\n\nExecution data:\n{execution_text}"
    return system, user


_PROCESS_SCHEMAS: Dict[str, Dict[str, Any]] = {
    ProcessStepKind.review: {
        "type": "object",
        "properties": {
            "reviewed_content": {"type": "string"},
            "approved": {"type": "boolean"},
            "feedback": {"type": "string"},
        },
        "required": ["reviewed_content", "approved", "feedback"],
        "additionalProperties": False,
    },
    ProcessStepKind.critique: {
        "type": "object",
        "properties": {"notes": {"type": "string"}},
        "required": ["notes"],
        "additionalProperties": False,
    },
    ProcessStepKind.summarize: {
        "type": "object",
        "properties": {"summary": {"type": "string"}},
        "required": ["summary"],
        "additionalProperties": False,
    },
    ProcessStepKind.investigate: {
        "type": "object",
        "properties": {"answers": {"type": "string"}},
        "required": ["answers"],
        "additionalProperties": False,
    },
    ProcessStepKind.analyze: {
        "type": "object",
        "properties": {"analysis": {"type": "string"}},
        "required": ["analysis"],
        "additionalProperties": False,
    },
}

_PROCESS_OUTPUT_KEYS: Dict[str, str] = {
    ProcessStepKind.review: "reviewed_content",
    ProcessStepKind.critique: "notes",
    ProcessStepKind.summarize: "summary",
    ProcessStepKind.investigate: "answers",
    ProcessStepKind.analyze: "analysis",
}


class WorkspaceRuntimeService:
    """Orchestrates a single Workspace turn with streaming delivery of final text."""

    def __init__(self, session: Session, user_id: uuid.UUID):
        self.session = session
        self.user_id = user_id
        self._async_session_lock = asyncio.Lock()

    @staticmethod
    def _workflow_failure_summary(
        run_result: WorkflowRunResult,
    ) -> Tuple[str, List[Dict[str, Any]]]:
        """Human-readable error plus structured failed node list for partial/error runs."""
        failed = [nr for nr in run_result.node_results if nr.status == "error"]
        base = f"Workflow finished with status {run_result.status!r}."
        if not failed:
            return base, []
        steps_out: List[Dict[str, Any]] = []
        parts: List[str] = []
        cap = _WORKSPACE_MAX_FAILED_NODE_SUMMARIES
        for nr in failed[:cap]:
            err_t = (nr.error or "error").strip()
            if len(err_t) > _WORKSPACE_MAX_NODE_ERROR_CHARS:
                err_t = err_t[:_WORKSPACE_MAX_NODE_ERROR_CHARS] + "…"
            steps_out.append({"node_id": nr.node_id, "error": err_t})
            parts.append(f"{nr.node_id}: {err_t}")
        more = len(failed) - len(steps_out)
        detail = " | ".join(parts)
        if more > 0:
            detail = f"{detail} (+{more} more failed step(s))"
        return f"{base} {detail}", steps_out

    async def _lm_provider(self) -> LMStudioProvider:
        async with self._async_session_lock:
            user_row = self.session.get(User, self.user_id)
            if user_row is not None:
                self.session.refresh(user_row)
            decrypted = decrypt_api_keys_store(user_row.api_keys if user_row else None)
            token = resolve_lmstudio_bearer(decrypted_api_keys=decrypted)
        return LMStudioProvider(api_key=token)

    def _companion_system_prompt(self, companion: Companion) -> str:
        if companion.persona_id:
            p = self.session.get(Persona, companion.persona_id)
            if p:
                return p.system_prompt
        return "You are a helpful, concise assistant."

    def _companion_model(self, companion: Companion) -> Optional[str]:
        if companion.persona_id:
            p = self.session.get(Persona, companion.persona_id)
            if p and p.default_model:
                return p.default_model.strip() or None
        return None

    def _merge_companion_persona_lm_options(self, companion: Companion, options: Dict[str, Any]) -> None:
        """Apply Persona-driven LM Studio options (e.g. reasoning_effort) for this Companion."""
        if not companion.persona_id:
            return
        p = self.session.get(Persona, companion.persona_id)
        options.update(persona_lm_chat_options(p))

    def _pipeline_config(self, workspace: Workspace) -> CompanionPipelineConfig:
        return companion_pipeline_from_runtime_configuration(workspace.runtime_configuration)

    def _resolve_interpret_model(
        self, workspace: Workspace, companion: Companion, cfg: CompanionPipelineConfig
    ) -> Optional[str]:
        if cfg.stages.interpret.enabled and cfg.stages.interpret.model_override:
            return cfg.stages.interpret.model_override
        wm = (getattr(workspace, "interpretation_model", None) or "").strip()
        if wm:
            return wm
        return self._companion_model(companion)

    def _resolve_compose_model(
        self, workspace: Workspace, companion: Companion, cfg: CompanionPipelineConfig
    ) -> Optional[str]:
        if cfg.stages.compose.enabled and cfg.stages.compose.model_override:
            return cfg.stages.compose.model_override
        return self._companion_model(companion)

    def _companion_voice_for_compose(self, companion: Companion, cfg: CompanionPipelineConfig) -> str:
        if cfg.stages.compose.enabled and (cfg.stages.compose.voice_override or "").strip():
            return (cfg.stages.compose.voice_override or "").strip()
        return self._companion_system_prompt(companion)

    @staticmethod
    def _workflow_uuid_set_from_json(raw: Optional[List[str]]) -> Set[uuid.UUID]:
        out: Set[uuid.UUID] = set()
        for s in raw or []:
            try:
                out.add(uuid.UUID(str(s)))
            except ValueError:
                continue
        return out

    def _allowed_capability_keys(self, workspace: Workspace, companion: Companion) -> Set[str]:
        ws = self._workflow_uuid_set_from_json(getattr(workspace, "enabled_workflow_ids", None))
        comp = self._workflow_uuid_set_from_json(getattr(companion, "enabled_workflow_ids", None))
        return {workflow_capability_key(u) for u in (ws & comp)}

    def _execution_time_zone_str(self) -> Optional[str]:
        user_row = self.session.get(User, self.user_id)
        return _effective_gmail_calendar_zone(getattr(user_row, "settings", None) if user_row else None, None)

    def _temporal_context_for_llm(self) -> str:
        return format_workspace_temporal_context_for_llm(
            datetime.now(timezone.utc), self._execution_time_zone_str()
        )

    def _session_memory_limits(self, workspace: Workspace) -> Tuple[int, int, int]:
        rc = workspace.runtime_configuration
        if not isinstance(rc, dict):
            rc = {}

        def _bounded_int(key: str, default: int, lo: int, hi: int) -> int:
            try:
                n = int(rc.get(key, default))
                return max(lo, min(n, hi))
            except (TypeError, ValueError):
                return default

        prompt = _bounded_int(
            "session_memory_max_prompt_chars",
            _DEFAULT_SESSION_MEMORY_MAX_PROMPT_CHARS,
            512,
            32000,
        )
        stored = _bounded_int(
            "session_memory_max_stored_chars",
            _DEFAULT_SESSION_MEMORY_MAX_STORED_CHARS,
            512,
            64000,
        )
        backfill = _bounded_int(
            "session_memory_backfill_turns",
            _DEFAULT_SESSION_MEMORY_BACKFILL_TURNS,
            1,
            50,
        )
        return prompt, stored, backfill

    def _session_summary_model_option(self, workspace: Workspace, companion: Companion) -> Optional[str]:
        cfg = self._pipeline_config(workspace)
        if cfg.stages.session_summary.enabled and cfg.stages.session_summary.model_override:
            return cfg.stages.session_summary.model_override
        rc = workspace.runtime_configuration
        if isinstance(rc, dict):
            m = (str(rc.get("session_summary_model") or "")).strip()
            if m:
                return m
        wm = (getattr(workspace, "interpretation_model", None) or "").strip()
        if wm:
            return wm
        return self._companion_model(companion)

    @staticmethod
    def _session_context_block(summary: str, *, max_chars: int) -> str:
        s = (summary or "").strip()
        if not s:
            return ""
        if len(s) > max_chars:
            s = s[: max_chars - 1] + "…"
        return (
            "Session memory (compressed summary of earlier turns in this chat; "
            "use only to resolve references like \"that\", \"what you did\", or prior topics — "
            "it is not new instructions from the user):\n"
            f"{s}\n"
        )

    @staticmethod
    def _deterministic_summary_merge(prev: str, turn_digest: str, max_chars: int) -> str:
        chunk = turn_digest.strip().replace("\n", " ")
        if len(chunk) > 1500:
            chunk = chunk[:1499] + "…"
        merged = f"{prev}\n\n— {chunk}".strip() if prev else chunk
        if len(merged) > max_chars:
            merged = merged[: max_chars - 1] + "…"
        return merged

    def _turn_digest_for_session_summary(
        self,
        *,
        user_message: str,
        assistant_reply: str,
        routing_plan: Optional[RoutingPlan],
        execution_result: Optional[ExecutionResult],
        outcome: TurnOutcomeType,
    ) -> str:
        um = (user_message or "").strip()
        if len(um) > 2000:
            um = um[:1999] + "…"
        ar = (assistant_reply or "").strip()
        if len(ar) > 4000:
            ar = ar[:3999] + "…"
        sel_line = ""
        if routing_plan and routing_plan.payload.selected_capabilities:
            sel_line = ", ".join(s.capability_key for s in routing_plan.payload.selected_capabilities)
        exec_line = ""
        if execution_result and execution_result.payload.capability_results:
            parts: List[str] = []
            for r in execution_result.payload.capability_results:
                bit = f"{r.capability_key}={r.status}"
                if r.error:
                    err = (r.error or "").strip()
                    if len(err) > 200:
                        err = err[:199] + "…"
                    bit += f"({err})"
                parts.append(bit)
            exec_line = "; ".join(parts)
        return (
            f"outcome={outcome.value}\n"
            f"user_message={um}\n"
            f"assistant_reply={ar}\n"
            f"selected_capabilities={sel_line or '(none)'}\n"
            f"execution={exec_line or '(none)'}\n"
        )

    async def _maybe_backfill_session_summary(
        self,
        workspace: Workspace,
        companion: Companion,
        session_row: WorkspaceSession,
    ) -> None:
        if session_row.turn_count <= 0:
            return
        if (session_row.active_summary or "").strip():
            return
        _, _, backfill_n = self._session_memory_limits(workspace)
        rows = list(
            self.session.exec(
                select(WorkspaceTurn)
                .where(WorkspaceTurn.session_id == session_row.id)
                .order_by(WorkspaceTurn.turn_index.desc())  # type: ignore[union-attr]
                .limit(backfill_n)
            ).all()
        )
        if not rows:
            return
        rows.reverse()
        parts: List[str] = []
        for t in rows:
            u = (t.user_input or "").strip()
            if len(u) > 800:
                u = u[:799] + "…"
            dr = t.delivered_response or {}
            final = ""
            try:
                payload = dr.get("payload") if isinstance(dr, dict) else None
                if isinstance(payload, dict):
                    fur = payload.get("final_user_response")
                    if isinstance(fur, dict):
                        final = str(fur.get("rendered_text") or "")
            except Exception:
                final = ""
            final = final.strip()
            if len(final) > 1200:
                final = final[:1199] + "…"
            parts.append(f"user: {u}\nassistant: {final}\n")
        digest = "BACKFILL_FROM_STORED_TURNS:\n" + "\n".join(parts)
        await self._refresh_active_summary(
            workspace=workspace,
            companion=companion,
            session_row=session_row,
            turn_digest=digest,
        )

    async def _refresh_active_summary(
        self,
        *,
        workspace: Workspace,
        companion: Companion,
        session_row: WorkspaceSession,
        turn_digest: str,
    ) -> None:
        _, stored_max, _ = self._session_memory_limits(workspace)
        prev = (session_row.active_summary or "").strip()
        if len(prev) > stored_max * 2:
            prev = prev[: stored_max * 2 - 1] + "…"

        schema = normalize_schema_for_structured_output(
            {
                "type": "object",
                "properties": {"summary": {"type": "string"}},
                "required": ["summary"],
                "additionalProperties": False,
            }
        )
        cfg = self._pipeline_config(workspace)
        base = (
            "You maintain a rolling session summary for a workspace chat assistant.\n"
            "Merge PRIOR_SUMMARY with NEW_TURN into one concise narrative.\n"
            "Use **only** information explicitly present in PRIOR_SUMMARY and NEW_TURN. "
            "Do not add facts, timelines, or tasks from outside those blocks (no outside recall or inference).\n"
            "Preserve: what the user asked for, which workflows/capabilities were selected or run "
            "(use capability keys if no friendly name is given), success vs failure, and outcomes "
            "the user would care about.\n"
            "Do not invent details. Drop redundant phrasing and minor old details when trimming.\n"
            f"The summary field must be at most {stored_max} characters (shorter is fine).\n"
            "Return JSON only matching the schema."
        )
        append = effective_session_summary_append(cfg)
        if append:
            system = f"{base}\n\n{append}"
        else:
            system = base
        user_block = f"PRIOR_SUMMARY:\n{(prev or '(none)')}\n\nNEW_TURN:\n{turn_digest.strip()}"
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user_block}]
        options: Dict[str, Any] = {
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "session_summary", "strict": True, "schema": schema},
            },
        }
        model = self._session_summary_model_option(workspace, companion)
        if model:
            options["model"] = model
        self._merge_companion_persona_lm_options(companion, options)
        provider = await self._lm_provider()
        new_summary = ""
        try:
            resp = await provider.chat(messages, options=options)
            data = resp.parsed if isinstance(resp.parsed, dict) else None
            if data is None and resp.raw_text:
                try:
                    data = json.loads(resp.raw_text)
                except json.JSONDecodeError:
                    data = None
            if isinstance(data, dict) and data.get("summary") is not None:
                new_summary = str(data.get("summary") or "").strip()
        except Exception as exc:
            logger.warning("Session summary refresh failed: %s", exc)
            new_summary = ""

        if not new_summary:
            new_summary = self._deterministic_summary_merge(prev, turn_digest, stored_max)
        elif len(new_summary) > stored_max:
            new_summary = new_summary[: stored_max - 1] + "…"

        now = datetime.now(timezone.utc)
        session_row.active_summary = new_summary
        session_row.updated_at = now
        self.session.add(session_row)
        self.session.commit()
        self.session.refresh(session_row)

    @staticmethod
    def _pick_workflow_capability_output(wf: WorkflowDefinition, run_result: WorkflowRunResult) -> Dict[str, Any]:
        graph = wf.graph or {}
        stop_ids: List[str] = []
        stop_priority: Dict[str, int] = {}
        for n in graph.get("nodes") or []:
            if isinstance(n, dict) and n.get("kind") == "stop":
                nid = n.get("id")
                if isinstance(nid, str):
                    stop_ids.append(nid)
                    pri_raw = (n.get("data") or {}).get("stop_priority", 0)
                    try:
                        stop_priority[nid] = int(pri_raw)
                    except (TypeError, ValueError):
                        stop_priority[nid] = 0
        best_step = -1
        best_pri = -(10**9)
        best_out: Any = None
        for nr in run_result.node_results:
            if nr.status != "ok" or nr.output is None:
                continue
            if nr.node_id not in stop_ids:
                continue
            pri = stop_priority.get(nr.node_id, 0)
            if pri > best_pri or (pri == best_pri and nr.step_number > best_step):
                best_pri = pri
                best_step = nr.step_number
                best_out = nr.output
        if best_out is not None:
            md = getattr(best_out, "model_dump", None)
            if callable(md):
                return md(mode="json")
            return {"result": str(best_out)}
        for nr in reversed(run_result.node_results):
            if nr.status == "ok" and nr.output is not None:
                md2 = getattr(nr.output, "model_dump", None)
                if callable(md2):
                    return md2(mode="json")
                return {"result": str(nr.output)}
        return {}

    def _allowed_capability_prompt_lines(self, workspace: Workspace, companion: Companion) -> str:
        keys = sorted(self._allowed_capability_keys(workspace, companion))
        if not keys:
            return "(none — enable workflows on this Workspace and on the Companion)"
        lines: List[str] = []
        for key in keys:
            wf_id = parse_workflow_id_from_capability_key(key)
            if wf_id is None:
                continue
            wf = self.session.get(WorkflowDefinition, wf_id)
            label = wf.name if wf else "unknown"
            slots = extract_start_input_slots_from_workflow_graph(wf.graph if wf else None)
            slot_hint = format_start_slots_for_capability_prompt(slots)
            lines.append(f"  {key} — {label}\n    Start inputs: {slot_hint}")
        return "\n".join(lines)

    def _interpret_canonical_system(
        self, workspace: Workspace, companion: Companion, cfg: CompanionPipelineConfig
    ) -> str:
        base = (cfg.stages.interpret.system_prompt_base or "").strip()
        if not base:
            base = DEFAULT_INTERPRET_BASE_PROMPT
        return (
            f"{base}\n"
            f"{self._temporal_context_for_llm()}\n\n"
            "Use only these capability_key values (Workspace ∩ Companion workflows):\n"
            f"{self._allowed_capability_prompt_lines(workspace, companion)}"
        )

    def _build_interpret_system(
        self,
        workspace: Workspace,
        companion: Companion,
        cfg: CompanionPipelineConfig,
        session_context: str,
    ) -> str:
        body = self._interpret_canonical_system(workspace, companion, cfg)
        append = effective_interpret_append(cfg)
        if append:
            system = f"{append}\n\n{body}"
        else:
            system = body
        ctx = (session_context or "").strip()
        if ctx:
            system = f"{system}\n\n{ctx}"
        return system

    async def _interpret(
        self,
        user_message: str,
        workspace: Workspace,
        companion: Companion,
        *,
        session_context: str = "",
        pipeline_cfg: Optional[CompanionPipelineConfig] = None,
    ) -> InterpretationPayload:
        cfg = pipeline_cfg if pipeline_cfg is not None else self._pipeline_config(workspace)
        schema = normalize_schema_for_structured_output(
            interpret_json_schema_with_strict_candidate_bindings(
                self.session, self.user_id, self._allowed_capability_keys(workspace, companion)
            )
        )
        system = self._build_interpret_system(workspace, companion, cfg, session_context)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user_message},
        ]
        options: Dict[str, Any] = {
            "temperature": 0.2,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": "interpretation",
                    "strict": True,
                    "schema": schema,
                },
            },
        }
        model = self._resolve_interpret_model(workspace, companion, cfg)
        if model:
            options["model"] = model
        self._merge_companion_persona_lm_options(companion, options)
        provider = await self._lm_provider()
        try:
            resp = await provider.chat(messages, options=options)
        except Exception as exc:
            logger.warning("Workspace interpret LLM failed, falling back to respond_directly: %s", exc)
            return InterpretationPayload(
                intent=IntentPayload(key="chat", summary=user_message[:200]),
                outcome_type=TurnOutcomeType.respond_directly,
                confidence=0.5,
                debug={"fallback": True, "error": str(exc)},
            )
        parsed: Any = resp.parsed
        if parsed is None and resp.raw_text:
            try:
                parsed = json.loads(resp.raw_text)
            except json.JSONDecodeError:
                parsed = None
        if not isinstance(parsed, dict):
            return InterpretationPayload(
                intent=IntentPayload(key="chat", summary=user_message[:200]),
                outcome_type=TurnOutcomeType.respond_directly,
                confidence=0.5,
                debug={"parse_fallback": True},
            )
        try:
            return InterpretationPayload.model_validate(parsed)
        except Exception as exc:
            logger.warning("Interpretation validate failed: %s", exc)
            return InterpretationPayload(
                intent=IntentPayload(key="chat", summary=user_message[:200]),
                outcome_type=TurnOutcomeType.respond_directly,
                confidence=0.4,
                debug={"validate_error": str(exc)},
            )

    async def _compose_and_memory(
        self,
        *,
        user_message: str,
        companion: Companion,
        workspace: Workspace,
        interpretation: InterpretationPayload,
        execution: Optional[ExecutionPayload],
        outcome: TurnOutcomeType,
        session_context: str = "",
        pipeline_cfg: Optional[CompanionPipelineConfig] = None,
        process_payload: Optional[ProcessPayload] = None,
    ) -> tuple[CompositionPayload, List[MemoryProposalCreate]]:
        cfg = pipeline_cfg if pipeline_cfg is not None else self._pipeline_config(workspace)
        voice = self._companion_voice_for_compose(companion, cfg)

        has_process_results = (
            process_payload is not None
            and process_payload.step_results
            and any(r.status == "success" and r.output for r in process_payload.step_results)
        )

        exec_summary = ""
        per_capability_lines: List[str] = []
        if execution and execution.capability_results:
            exec_summary = json.dumps(
                [r.model_dump(mode="json") for r in execution.capability_results],
                ensure_ascii=False,
            )[:12000]
            for r in execution.capability_results:
                out_snip = ""
                if r.output:
                    out_snip = _compact_capability_output_for_compose(r.output)
                line = f"- {r.capability_key} status={r.status}"
                if r.error:
                    line += f" error={r.error}"
                if out_snip:
                    line += f" structured_output={out_snip}"
                per_capability_lines.append(line)

        schema = normalize_schema_for_structured_output(
            {
                "type": "object",
                "properties": {
                    "reply_text": {"type": "string"},
                    "memory_candidates": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "content": {"type": "string"},
                                "memory_type": {"type": "string"},
                            },
                            "required": ["content", "memory_type"],
                        },
                    },
                },
                "required": ["reply_text", "memory_candidates"],
                "additionalProperties": False,
            }
        )

        if has_process_results:
            base_compose = f"{voice}\n\n{DEFAULT_COMPOSE_WITH_PROCESS_PROMPT}"
        else:
            base_compose = f"{voice}\n\n{DEFAULT_COMPOSE_BASE_PROMPT}"
        c_append = effective_compose_append(cfg)
        if c_append:
            system = f"{base_compose}\n\n{c_append}"
        else:
            system = base_compose

        ctx = (session_context or "").strip()
        ctx_prefix = f"{ctx}\n\n" if ctx else ""

        if has_process_results:
            process_lines: List[str] = []
            for sr in process_payload.step_results:
                if sr.status == "success" and sr.output:
                    process_lines.append(f"- [{sr.kind}] {sr.step_id}: {sr.output}")
            process_block = "\n".join(process_lines) if process_lines else "(none)"
            user_block = (
                f"{ctx_prefix}"
                f"{self._temporal_context_for_llm()}\n\n"
                f"User message:\n{user_message}\n\n"
                f"Interpretation outcome: {outcome.value}\n"
                f"Intent summary: {interpretation.intent.summary}\n\n"
                f"Process step outputs (cohere these into reply_text):\n{process_block}\n"
            )
        else:
            diag = "\n".join(per_capability_lines) if per_capability_lines else "(none)"
            user_block = (
                f"{ctx_prefix}"
                f"{self._temporal_context_for_llm()}\n\n"
                f"User message:\n{user_message}\n\n"
                f"Interpretation outcome: {outcome.value}\n"
                f"Intent summary: {interpretation.intent.summary}\n\n"
                "Per capability (each line may include structured_output= with truncated JSON for successes). "
                "reply_text must give concrete, user-facing details from that JSON when status is success—not only "
                "when status is error:\n"
                f"{diag}\n\n"
                f"Capability execution summary (JSON):\n{exec_summary or '(none)'}\n"
            )
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user_block}]
        options: Dict[str, Any] = {
            "temperature": 0.6,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": "compose", "strict": True, "schema": schema},
            },
        }
        model = self._resolve_compose_model(workspace, companion, cfg)
        if model:
            options["model"] = model
        self._merge_companion_persona_lm_options(companion, options)
        provider = await self._lm_provider()
        reply_text = ""
        memory_candidates: List[MemoryProposalCreate] = []
        try:
            resp = await provider.chat(messages, options=options)
            data = resp.parsed if isinstance(resp.parsed, dict) else None
            if data is None and resp.raw_text:
                try:
                    data = json.loads(resp.raw_text)
                except json.JSONDecodeError:
                    data = None
            if isinstance(data, dict):
                reply_text = str(data.get("reply_text") or "").strip()
                for item in data.get("memory_candidates") or []:
                    if isinstance(item, dict) and item.get("content"):
                        memory_candidates.append(
                            MemoryProposalCreate(
                                content=str(item["content"])[:8000],
                                memory_type=str(item.get("memory_type") or "fact"),
                            )
                        )
        except Exception as exc:
            logger.warning("Workspace compose LLM failed: %s", exc)
            if execution and execution.capability_results:
                parts = []
                for r in execution.capability_results:
                    if r.error:
                        parts.append(r.error[:4000])
                    elif r.status == "success" and r.output:
                        parts.append(json.dumps(r.output, ensure_ascii=False)[:2000])
                reply_text = " ".join(parts) or "Here is what I found."
            else:
                summary = (interpretation.intent.summary or "").strip()
                um = user_message.strip()
                if summary and summary != um:
                    reply_text = summary
                else:
                    reply_text = (
                        "I'm having trouble reaching the AI service right now. "
                        "Check that your language model is running and configured, then try again."
                    )
        if not reply_text:
            cl = (interpretation.clarification or "").strip()
            if cl and cl != user_message.strip():
                reply_text = interpretation.clarification
            else:
                reply_text = "Could you clarify what you need?"
        comp = CompositionPayload(
            response_payload=ResponsePayloadContent(
                response_type="conversational",
                content=reply_text,
                structured_blocks=[],
            ),
            internal_notes={"workspace_id": str(workspace.id)},
            memory_candidates=[m.model_dump() for m in memory_candidates],
            debug={},
        )
        return comp, memory_candidates

    def _resolve_post_compose_model(
        self,
        workspace: Workspace,
        companion: Companion,
        cfg: CompanionPipelineConfig,
        step_model: Optional[str],
    ) -> Optional[str]:
        if (step_model or "").strip():
            return step_model.strip()
        return self._resolve_compose_model(workspace, companion, cfg)

    async def _run_post_compose_pipeline(
        self,
        *,
        pipeline_cfg: CompanionPipelineConfig,
        user_message: str,
        workspace: Workspace,
        companion: Companion,
        execution: Optional[ExecutionPayload],
        composed_reply: str,
    ) -> tuple[str, Dict[str, str], List[Dict[str, Any]], List[str]]:
        """Transform composed reply; return stream text, metadata keys, trace rows, extra SSE lines."""
        sse_lines: List[str] = []
        delivery_text = composed_reply
        meta: Dict[str, str] = {}
        traces: List[Dict[str, Any]] = []
        exec_summary = ""
        if execution and execution.capability_results:
            exec_summary = json.dumps(
                [r.model_dump(mode="json") for r in execution.capability_results],
                ensure_ascii=False,
            )[:12000]
        last_output = ""
        post_schema = normalize_schema_for_structured_output(
            {
                "type": "object",
                "properties": {"output_text": {"type": "string"}},
                "required": ["output_text"],
                "additionalProperties": False,
            }
        )
        for step in pipeline_cfg.post_compose:
            if not step.enabled:
                continue
            t0 = time.monotonic()
            sse_lines.append(
                format_workspace_stage_sse(
                    f"post_compose:{step.id}",
                    "started",
                    detail={"name": step.name or step.id},
                )
            )
            ctx = {
                "composed_reply": composed_reply,
                "reply_text": composed_reply,
                "stream_text": delivery_text,
                "last_output": last_output,
                "user_message": user_message,
                "execution_summary": exec_summary or "(none)",
            }
            user_prompt = render_pipeline_template(step.system_prompt, ctx)
            if not user_prompt.strip():
                user_prompt = (
                    "Transform the assistant reply for downstream use.\n\n"
                    f"Assistant reply:\n{composed_reply}\n"
                )
            system_pc = (
                "You are a post-processing step for a conversational assistant. "
                "Return JSON only matching the schema exactly. "
                "The output_text field must contain your complete result as plain text."
            )
            messages = [
                {"role": "system", "content": system_pc},
                {"role": "user", "content": user_prompt},
            ]
            options: Dict[str, Any] = {
                "temperature": 0.3,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "post_compose", "strict": True, "schema": post_schema},
                },
            }
            m = self._resolve_post_compose_model(workspace, companion, pipeline_cfg, step.model)
            if m:
                options["model"] = m
            self._merge_companion_persona_lm_options(companion, options)
            provider = await self._lm_provider()
            out = ""
            err: Optional[str] = None
            try:
                resp = await provider.chat(messages, options=options)
                data = resp.parsed if isinstance(resp.parsed, dict) else None
                if data is None and resp.raw_text:
                    try:
                        data = json.loads(resp.raw_text)
                    except json.JSONDecodeError:
                        data = None
                if isinstance(data, dict):
                    out = str(data.get("output_text") or "").strip()
            except Exception as exc:
                logger.warning("Workspace post-compose step %s failed: %s", step.id, exc)
                err = str(exc)
            key = (step.output_key or "text").strip() or "text"
            ok = err is None and bool(out)
            if out:
                meta[key] = out
                last_output = out
                if step.replace_streamed_reply:
                    delivery_text = out
            trace: Dict[str, Any] = {
                "id": step.id,
                "output_key": key,
                "ok": ok,
                "error": err,
                "replaced_reply": bool(out and step.replace_streamed_reply),
            }
            if step.expose_in_traces and out:
                trace["output_preview"] = out[:1999] + "…" if len(out) > 2000 else out
            traces.append(trace)
            elapsed_ms = (time.monotonic() - t0) * 1000
            sse_lines.append(
                format_workspace_stage_sse(
                    f"post_compose:{step.id}",
                    "completed",
                    detail={"output_key": key, "ok": ok},
                    ms=elapsed_ms,
                )
            )
        return delivery_text, meta, traces, sse_lines

    async def _finalize_composition_with_post_compose(
        self,
        *,
        comp: CompositionPayload,
        pipeline_cfg: CompanionPipelineConfig,
        user_message: str,
        workspace: Workspace,
        companion: Companion,
        execution: Optional[ExecutionPayload],
    ) -> tuple[CompositionPayload, List[str]]:
        composed_reply = comp.response_payload.content
        stream_text, meta, traces, sse_lines = await self._run_post_compose_pipeline(
            pipeline_cfg=pipeline_cfg,
            user_message=user_message,
            workspace=workspace,
            companion=companion,
            execution=execution,
            composed_reply=composed_reply,
        )
        rp = comp.response_payload.model_copy(update={"content": stream_text})
        dbg = dict(comp.debug or {})
        if meta:
            dbg["pipeline_delivery_metadata"] = meta
        if traces:
            dbg["post_compose"] = traces
        return comp.model_copy(update={"response_payload": rp, "debug": dbg}), sse_lines

    def _resolve_process_model(
        self,
        workspace: Workspace,
        companion: Companion,
        cfg: CompanionPipelineConfig,
        step_model: Optional[str],
    ) -> Optional[str]:
        if (step_model or "").strip():
            return step_model.strip()
        return self._resolve_compose_model(workspace, companion, cfg)

    async def _run_process_pipeline(
        self,
        *,
        pipeline_cfg: CompanionPipelineConfig,
        workspace: Workspace,
        companion: Companion,
        execution: Optional[ExecutionPayload],
    ) -> tuple[ProcessPayload, List[str]]:
        """Run configured process steps on execution output; return payload + SSE lines."""
        sse_lines: List[str] = []
        step_results: List[ProcessStepResult] = []
        traces: List[Dict[str, Any]] = []

        enabled_steps = [s for s in pipeline_cfg.process if s.enabled]
        if not enabled_steps:
            return ProcessPayload(), sse_lines

        execution_text = _compact_execution_for_process(execution)

        for step in enabled_steps:
            t0 = time.monotonic()
            sse_lines.append(
                format_workspace_stage_sse(
                    f"process:{step.id}",
                    "started",
                    detail={"name": step.name or step.id, "kind": step.kind.value},
                )
            )
            result = await self._run_single_process_step(
                step=step,
                execution_text=execution_text,
                workspace=workspace,
                companion=companion,
                pipeline_cfg=pipeline_cfg,
            )
            step_results.append(result)

            trace: Dict[str, Any] = {
                "id": step.id,
                "kind": step.kind.value,
                "status": result.status,
                "iterations_used": result.iterations_used,
            }
            if result.approved is not None:
                trace["approved"] = result.approved
            if result.error:
                trace["error"] = result.error
            if step.expose_in_traces and result.output:
                preview = result.output
                trace["output_preview"] = preview[:1999] + "\u2026" if len(preview) > 2000 else preview
            traces.append(trace)

            elapsed_ms = (time.monotonic() - t0) * 1000
            sse_lines.append(
                format_workspace_stage_sse(
                    f"process:{step.id}",
                    "completed",
                    detail={
                        "kind": step.kind.value,
                        "status": result.status,
                        "iterations_used": result.iterations_used,
                    },
                    ms=elapsed_ms,
                )
            )

        debug = {"process_traces": traces} if traces else {}
        return ProcessPayload(step_results=step_results, debug=debug), sse_lines

    async def _run_single_process_step(
        self,
        *,
        step: ProcessStepConfig,
        execution_text: str,
        workspace: Workspace,
        companion: Companion,
        pipeline_cfg: CompanionPipelineConfig,
    ) -> ProcessStepResult:
        """Execute one process step, handling review iteration."""
        kind = step.kind
        description = step.description or "Process the data as appropriate."
        provider = await self._lm_provider()
        model = self._resolve_process_model(workspace, companion, pipeline_cfg, step.model)

        raw_schema = _PROCESS_SCHEMAS.get(kind)
        if not raw_schema:
            return ProcessStepResult(
                step_id=step.id, kind=kind.value, status="error",
                error=f"Unknown process kind: {kind.value}",
            )
        schema = normalize_schema_for_structured_output(raw_schema)
        output_key = _PROCESS_OUTPUT_KEYS[kind]

        if kind == ProcessStepKind.review:
            return await self._run_review_loop(
                step=step, execution_text=execution_text, description=description,
                provider=provider, model=model, schema=schema, companion=companion,
            )

        if kind == ProcessStepKind.critique:
            system, user = _build_critique_messages(execution_text, description)
        elif kind == ProcessStepKind.summarize:
            system, user = _build_summarize_messages(execution_text, description)
        elif kind == ProcessStepKind.investigate:
            system, user = _build_investigate_messages(execution_text, description, step.questions)
        else:
            system, user = _build_analyze_messages(execution_text, description)

        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        options: Dict[str, Any] = {
            "temperature": 0.4,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": f"process_{kind.value}", "strict": True, "schema": schema},
            },
        }
        if model:
            options["model"] = model
        self._merge_companion_persona_lm_options(companion, options)

        try:
            resp = await provider.chat(messages, options=options)
            data = resp.parsed if isinstance(resp.parsed, dict) else None
            if data is None and resp.raw_text:
                try:
                    data = json.loads(resp.raw_text)
                except json.JSONDecodeError:
                    data = None
            if isinstance(data, dict):
                out = str(data.get(output_key) or "").strip()
                return ProcessStepResult(
                    step_id=step.id, kind=kind.value, status="success",
                    output=out[:_PROCESS_OUTPUT_CHARS_LIMIT],
                )
            return ProcessStepResult(
                step_id=step.id, kind=kind.value, status="error",
                error="LLM returned unparseable response",
            )
        except Exception as exc:
            logger.warning("Process step %s (%s) failed: %s", step.id, kind.value, exc)
            return ProcessStepResult(
                step_id=step.id, kind=kind.value, status="error", error=str(exc),
            )

    async def _run_review_loop(
        self,
        *,
        step: ProcessStepConfig,
        execution_text: str,
        description: str,
        provider: LMStudioProvider,
        model: Optional[str],
        schema: Dict[str, Any],
        companion: Companion,
    ) -> ProcessStepResult:
        """Iterative review: loop until approved or max_iterations reached."""
        prior_output = ""
        feedback = ""
        for iteration in range(1, step.max_iterations + 1):
            system, user = _build_review_messages(
                execution_text, description, prior_output=prior_output, feedback=feedback,
            )
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
            options: Dict[str, Any] = {
                "temperature": 0.4,
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "process_review", "strict": True, "schema": schema},
                },
            }
            if model:
                options["model"] = model
            self._merge_companion_persona_lm_options(companion, options)

            try:
                resp = await provider.chat(messages, options=options)
                data = resp.parsed if isinstance(resp.parsed, dict) else None
                if data is None and resp.raw_text:
                    try:
                        data = json.loads(resp.raw_text)
                    except json.JSONDecodeError:
                        data = None
                if not isinstance(data, dict):
                    return ProcessStepResult(
                        step_id=step.id, kind="review", status="error",
                        error="LLM returned unparseable response",
                        iterations_used=iteration,
                    )
                content = str(data.get("reviewed_content") or "").strip()
                approved = bool(data.get("approved", False))
                fb = str(data.get("feedback") or "").strip()

                if approved or iteration == step.max_iterations:
                    return ProcessStepResult(
                        step_id=step.id, kind="review", status="success",
                        output=content[:_PROCESS_OUTPUT_CHARS_LIMIT],
                        iterations_used=iteration, approved=approved,
                    )
                prior_output = content
                feedback = fb
            except Exception as exc:
                logger.warning("Process review step %s iteration %d failed: %s", step.id, iteration, exc)
                return ProcessStepResult(
                    step_id=step.id, kind="review", status="error",
                    error=str(exc), iterations_used=iteration,
                )
        return ProcessStepResult(
            step_id=step.id, kind="review", status="error",
            error="Review loop exhausted without result",
            iterations_used=step.max_iterations,
        )

    def build_pipeline_preview(
        self,
        *,
        workspace: Workspace,
        companion: Companion,
    ) -> Dict[str, Any]:
        """Effective prompts and resolved models for the Pipeline settings UI (no LLM calls)."""
        cfg = self._pipeline_config(workspace)
        interpret_system = self._build_interpret_system(workspace, companion, cfg, session_context="")
        voice = self._companion_voice_for_compose(companion, cfg)
        base_compose = f"{voice}\n\n{DEFAULT_COMPOSE_BASE_PROMPT}"
        c_append = effective_compose_append(cfg)
        if c_append:
            compose_system = f"{base_compose}\n\n{c_append}"
        else:
            compose_system = base_compose
        _, stored_max, _ = self._session_memory_limits(workspace)
        base_sum = (
            "You maintain a rolling session summary for a workspace chat assistant.\n"
            "Merge PRIOR_SUMMARY with NEW_TURN into one concise narrative.\n"
            "Use **only** information explicitly present in PRIOR_SUMMARY and NEW_TURN. "
            "Do not add facts, timelines, or tasks from outside those blocks (no outside recall or inference).\n"
            "Preserve: what the user asked for, which workflows/capabilities were selected or run "
            "(use capability keys if no friendly name is given), success vs failure, and outcomes "
            "the user would care about.\n"
            "Do not invent details. Drop redundant phrasing and minor old details when trimming.\n"
            f"The summary field must be at most {stored_max} characters (shorter is fine).\n"
            "Return JSON only matching the schema."
        )
        s_append = effective_session_summary_append(cfg)
        if s_append:
            session_summary_system = f"{base_sum}\n\n{s_append}"
        else:
            session_summary_system = base_sum
        ph = "[preview placeholder]"
        exec_ph = "(none)"

        process_previews: List[Dict[str, Any]] = []
        for step in cfg.process:
            process_previews.append(
                {
                    "id": step.id,
                    "kind": step.kind.value,
                    "enabled": step.enabled,
                    "name": step.name,
                    "model": self._resolve_process_model(workspace, companion, cfg, step.model),
                    "description": step.description,
                    "max_iterations": step.max_iterations,
                    "questions": step.questions,
                }
            )

        post_previews: List[Dict[str, Any]] = []
        for step in cfg.post_compose:
            ctx = {
                "composed_reply": ph,
                "reply_text": ph,
                "stream_text": ph,
                "last_output": "",
                "user_message": ph,
                "execution_summary": exec_ph,
            }
            post_previews.append(
                {
                    "id": step.id,
                    "enabled": step.enabled,
                    "name": step.name,
                    "model": self._resolve_post_compose_model(workspace, companion, cfg, step.model),
                    "output_key": step.output_key,
                    "replace_streamed_reply": step.replace_streamed_reply,
                    "user_prompt_rendered": render_pipeline_template(step.system_prompt, ctx),
                }
            )
        return {
            "version": cfg.version,
            "models": {
                "interpret": self._resolve_interpret_model(workspace, companion, cfg),
                "compose": self._resolve_compose_model(workspace, companion, cfg),
                "session_summary": self._session_summary_model_option(workspace, companion),
            },
            "interpret_system": interpret_system,
            "compose_system": compose_system,
            "session_summary_system": session_summary_system,
            "process": process_previews,
            "post_compose": post_previews,
        }

    def _build_routing_plan(
        self,
        interpretation: InterpretationPayload,
        allowed: Set[str],
    ) -> RoutingPayload:
        selected: List[SelectedCapability] = []
        order: List[str] = []
        for cand in interpretation.candidate_capabilities:
            if cand.capability_key in allowed:
                merged: Dict[str, Any] = {}
                if interpretation.normalized_inputs:
                    merged.update(dict(interpretation.normalized_inputs))
                if cand.input_bindings:
                    merged.update(dict(cand.input_bindings))
                selected.append(
                    SelectedCapability(
                        capability_key=cand.capability_key,
                        input_bindings=merged,
                    )
                )
                order.append(cand.capability_key)
        blocked_no_match = (
            interpretation.outcome_type == TurnOutcomeType.invoke_capabilities
            and not selected
            and bool(interpretation.candidate_capabilities)
        )
        blocked = interpretation.policy_flags.blocked or blocked_no_match
        return RoutingPayload(
            selected_capabilities=selected,
            execution_order=order,
            permission_checks=PermissionChecksPayload(
                workspace_allows=True,
                companion_allows=True,
                blocked_reasons=(["no_matching_capability"] if blocked_no_match else []),
            ),
            policy_decisions=PolicyDecisionsPayload(
                blocked=blocked,
                confirmation_required=bool(selected),
                fallback_allowed=False,
            ),
            debug={},
        )

    def _validate_confirm_capability_bindings(
        self,
        interpretation: InterpretationPayload,
        routing: RoutingPayload,
    ) -> None:
        """Reject confirm when required Start inputs or binding shapes are invalid."""
        for sel in routing.selected_capabilities:
            wf_id = parse_workflow_id_from_capability_key(sel.capability_key)
            wf = self.session.get(WorkflowDefinition, wf_id) if wf_id else None
            merged: Dict[str, Any] = {}
            if interpretation.normalized_inputs:
                merged.update(dict(interpretation.normalized_inputs))
            merged.update(dict(sel.input_bindings))
            merged = _apply_email_list_default_for_gmail_workflow(
                self.session, self.user_id, wf.graph if wf else None, merged
            )
            slots = extract_start_input_slots_from_workflow_graph(wf.graph if wf else None)
            err = validate_capability_start_bindings(slots, merged)
            if err:
                raise ValueError(f"{sel.capability_key}: {err}")

    async def _execute_capabilities(
        self,
        routing: RoutingPayload,
        user_message: str,
        workspace: Workspace,
    ) -> ExecutionPayload:
        results: List[CapabilityRunResult] = []
        executor = WorkflowExecutor(
            self.session,
            self.user_id,
            default_google_workflow_connection_id=workspace.default_google_workflow_connection_id,
        )
        etz = self._execution_time_zone_str()
        for sel in routing.selected_capabilities:
            key = sel.capability_key
            spec = resolve_capability_for_user(self.session, self.user_id, key)
            if spec is None:
                results.append(
                    CapabilityRunResult(
                        capability_key=key,
                        status="error",
                        error="Unknown capability",
                        validation={},
                    )
                )
                continue
            if spec.backing == "workflow" and spec.workflow_id:
                wf = self.session.get(WorkflowDefinition, spec.workflow_id)
                if not wf:
                    results.append(
                        CapabilityRunResult(
                            capability_key=key,
                            status="error",
                            error="Workflow not found",
                            validation={},
                        )
                    )
                    continue
                raw_bindings = dict(sel.input_bindings or {})
                raw_bindings = _apply_email_list_default_for_gmail_workflow(
                    self.session, self.user_id, wf.graph, raw_bindings
                )
                slots = extract_start_input_slots_from_workflow_graph(wf.graph)
                if not slots:
                    filtered = dict(raw_bindings)
                    err = None
                else:
                    err = validate_capability_start_bindings(slots, raw_bindings)
                    filtered = filter_bindings_to_allowed(slots, raw_bindings)
                if err:
                    results.append(
                        CapabilityRunResult(
                            capability_key=key,
                            status="error",
                            error=err,
                            validation={
                                "start_slots": [
                                    {
                                        "key": s.key,
                                        "input_type": s.input_type,
                                        "has_static_default": s.has_static_default,
                                    }
                                    for s in slots
                                ]
                            },
                        )
                    )
                    continue
                try:
                    run_result = await executor.run(
                        wf,
                        input_overrides=filtered,
                        execution_time_zone=etz,
                    )
                    data = self._pick_workflow_capability_output(wf, run_result)
                    ok = run_result.status == "ok"
                    if ok:
                        err_msg: Optional[str] = None
                        validation: Dict[str, Any] = {"passed": True}
                    else:
                        err_msg, failed_steps = self._workflow_failure_summary(run_result)
                        validation = {"passed": False, "failed_steps": failed_steps}
                    results.append(
                        CapabilityRunResult(
                            capability_key=key,
                            status="success" if ok else "error",
                            output=data if data is not None else None,
                            error=err_msg,
                            validation=validation,
                        )
                    )
                except Exception as exc:
                    results.append(
                        CapabilityRunResult(
                            capability_key=key,
                            status="error",
                            error=str(exc),
                            validation={},
                        )
                    )
        summary = {
            "total_capabilities": len(results),
            "successful": sum(1 for r in results if r.status == "success"),
            "failed": sum(1 for r in results if r.status == "error"),
        }
        return ExecutionPayload(capability_results=results, execution_summary=summary, debug={})

    def _load_capability_proposal(self, session_row: WorkspaceSession, proposal_id: str) -> Dict[str, Any]:
        raw = (session_row.transient_state or {}).get(CAPABILITY_PROPOSAL_STATE_KEY)
        if not raw or not isinstance(raw, dict):
            raise ValueError("No pending capability proposal for this session.")
        if str(raw.get("id")) != str(proposal_id):
            raise ValueError("Proposal id does not match the pending proposal.")
        created_raw = raw.get("created_at")
        if not created_raw:
            raise ValueError("Invalid proposal.")
        cstr = str(created_raw).replace("Z", "+00:00")
        try:
            created = datetime.fromisoformat(cstr)
        except ValueError as exc:
            raise ValueError("Invalid proposal timestamp.") from exc
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - created > timedelta(seconds=PROPOSAL_TTL_SECONDS):
            raise ValueError("This proposal has expired. Send a new message.")
        return raw

    def _clear_capability_proposal(self, session_row: WorkspaceSession) -> None:
        ts = dict(session_row.transient_state or {})
        ts.pop(CAPABILITY_PROPOSAL_STATE_KEY, None)
        session_row.transient_state = ts

    def _persist_workspace_turn(
        self,
        *,
        session: WorkspaceSession,
        workspace: Workspace,
        companion: Companion,
        user_message: str,
        trace_id: str,
        turn_index: int,
        outcome: TurnOutcomeType,
        interp_result: InterpretationResult,
        routing_plan: Optional[RoutingPlan],
        execution_result: Optional[ExecutionResult],
        comp: CompositionPayload,
        memory_proposals: List[MemoryProposalCreate],
        process_result: Optional[ProcessResult] = None,
    ) -> Tuple[WorkspaceTurn, WorkspaceReplay]:
        final_text = comp.response_payload.content
        indicators: List[str] = []
        if routing_plan and routing_plan.payload.selected_capabilities:
            indicators = [s.capability_key for s in routing_plan.payload.selected_capabilities]

        pipe_meta: Dict[str, Any] = {}
        if isinstance(comp.debug, dict):
            raw_pm = comp.debug.get("pipeline_delivery_metadata")
            if isinstance(raw_pm, dict):
                pipe_meta = dict(raw_pm)

        delivery = DeliveryResultModel(
            payload=DeliveryPayloadModel(
                final_user_response=FinalUserResponsePayload(
                    rendered_text=final_text,
                    render_mode="chat_message",
                    visible_capability_indicators=indicators,
                ),
                applied_companion_mode=companion.default_mode,
                delivery_metadata={"streamed": True, **pipe_meta},
                debug={},
            )
        )

        now = datetime.now(timezone.utc)
        turn = WorkspaceTurn(
            session_id=session.id,
            turn_index=turn_index,
            trace_id=trace_id,
            user_input=user_message,
            outcome_type=outcome.value,
            interpretation_result=interp_result.model_dump(mode="json"),
            routing_plan=routing_plan.model_dump(mode="json") if routing_plan else None,
            execution_results=execution_result.model_dump(mode="json") if execution_result else None,
            process_results=process_result.payload.model_dump(mode="json") if process_result else None,
            composition_result=comp.model_dump(mode="json"),
            delivered_response=delivery.model_dump(mode="json"),
            created_at=now,
        )
        self.session.add(turn)
        self.session.commit()
        self.session.refresh(turn)

        replay = WorkspaceReplay(
            turn_id=turn.id,
            workspace_id=workspace.id,
            session_id=session.id,
            interpretation_trace=redact_workspace_trace(interp_result.model_dump(mode="json")),
            routing_trace=redact_workspace_trace(routing_plan.model_dump(mode="json") if routing_plan else None),
            execution_trace=redact_workspace_trace(
                execution_result.model_dump(mode="json") if execution_result else None
            ),
            process_trace=redact_workspace_trace(
                process_result.payload.model_dump(mode="json") if process_result else None
            ),
            composition_trace=redact_workspace_trace(comp.model_dump(mode="json")),
            delivery_trace=redact_workspace_trace(delivery.model_dump(mode="json")),
            state_update_summary={"turn_count": session.turn_count + 1},
            created_at=now,
        )
        self.session.add(replay)

        session.turn_count = turn_index + 1
        session.last_turn_at = now
        session.updated_at = now
        self.session.add(session)

        for mem in memory_proposals:
            self.session.add(
                CompanionMemoryEntry(
                    companion_id=companion.id,
                    memory_type=mem.memory_type,
                    content=mem.content,
                    salience=0.5,
                    source_session_id=session.id,
                    source_turn_id=turn.id,
                    visibility_policy="user_only",
                    approval_status="proposed",
                    created_at=now,
                    updated_at=now,
                )
            )

        self.session.commit()
        return turn, replay

    async def run_turn_stream(
        self,
        *,
        workspace: Workspace,
        session: WorkspaceSession,
        companion: Companion,
        user_message: str,
        chunk_size: int = 28,
    ) -> AsyncIterator[str]:
        """Yield SSE `data: {...}\\n\\n` lines; stream final reply text in chunks, then persist."""
        trace_id = secrets.token_hex(16)
        turn_index = session.turn_count
        allowed = self._allowed_capability_keys(workspace, companion)

        self.session.refresh(session)
        await self._maybe_backfill_session_summary(workspace, companion, session)
        prompt_max, _, _ = self._session_memory_limits(workspace)
        session_context = self._session_context_block(session.active_summary, max_chars=prompt_max)
        pipeline_cfg = self._pipeline_config(workspace)

        yield format_workspace_stage_sse("interpret", "started")
        t_interp = time.monotonic()
        interp_task = asyncio.create_task(
            self._interpret(
                user_message,
                workspace,
                companion,
                session_context=session_context,
                pipeline_cfg=pipeline_cfg,
            )
        )
        try:
            async for _ka in iter_sse_keepalive_lines_while_task_pending(interp_task):
                yield _ka
            interpretation = interp_task.result()
        except BaseException:
            interp_task.cancel()
            raise
        yield format_workspace_stage_sse(
            "interpret",
            "completed",
            ms=(time.monotonic() - t_interp) * 1000,
        )
        interp_result = InterpretationResult(payload=interpretation)

        routing_plan: Optional[RoutingPlan] = None
        execution_result: Optional[ExecutionResult] = None

        outcome = interpretation.outcome_type
        if outcome == TurnOutcomeType.invoke_capabilities:
            routing_plan = RoutingPlan(payload=self._build_routing_plan(interpretation, allowed))
            rp = routing_plan.payload
            if rp.policy_decisions.blocked and not rp.selected_capabilities:
                outcome = TurnOutcomeType.respond_directly
            elif rp.selected_capabilities:
                proposal_id = str(uuid.uuid4())
                now = datetime.now(timezone.utc)
                proposal = {
                    "id": proposal_id,
                    "created_at": now.isoformat().replace("+00:00", "Z"),
                    "user_message": user_message,
                    "interpretation_result": interp_result.model_dump(mode="json"),
                    "routing_plan": routing_plan.model_dump(mode="json"),
                    "trace_id": trace_id,
                }
                ts = dict(session.transient_state or {})
                ts[CAPABILITY_PROPOSAL_STATE_KEY] = proposal
                session.transient_state = ts
                session.updated_at = now
                self.session.add(session)
                self.session.commit()
                self.session.refresh(session)

                names: List[str] = []
                proposal_caps: List[Dict[str, Any]] = []
                for s in rp.selected_capabilities:
                    wf_id2 = parse_workflow_id_from_capability_key(s.capability_key)
                    wf2 = self.session.get(WorkflowDefinition, wf_id2) if wf_id2 else None
                    names.append(wf2.name if wf2 else s.capability_key)
                    merged_preview: Dict[str, Any] = {}
                    if interpretation.normalized_inputs:
                        merged_preview.update(dict(interpretation.normalized_inputs))
                    merged_preview.update(dict(s.input_bindings))
                    merged_preview = _apply_email_list_default_for_gmail_workflow(
                        self.session, self.user_id, wf2.graph if wf2 else None, merged_preview
                    )
                    slots2 = extract_start_input_slots_from_workflow_graph(wf2.graph if wf2 else None)
                    miss2 = missing_required_start_binding_keys(slots2, merged_preview)
                    proposal_caps.append(
                        {
                            "capability_key": s.capability_key,
                            "name": wf2.name if wf2 else s.capability_key,
                            "input_bindings": s.input_bindings,
                            "start_slots": start_slots_for_api(slots2),
                            "missing_start_binding_keys": miss2,
                        }
                    )

                final_text = (
                    f"I'm ready to run: {', '.join(names)}. Review the parameters and confirm to execute, "
                    "or cancel to stop."
                )
                for i in range(0, len(final_text), chunk_size):
                    chunk = final_text[i : i + chunk_size]
                    yield f"data: {json.dumps({'event': 'token', 'text': chunk})}\n\n"

                yield f"data: {json.dumps({'event': 'capability_proposal', 'proposal_id': proposal_id, 'capabilities': proposal_caps})}\n\n"

                yield f"data: {json.dumps({'event': 'done', 'phase': 'proposal', 'proposal_id': proposal_id, 'memory_proposed': 0})}\n\n"
                return
            outcome = TurnOutcomeType.respond_directly

        if outcome == TurnOutcomeType.invoke_capabilities:
            outcome = TurnOutcomeType.respond_directly

        memory_proposals: List[MemoryProposalCreate] = []

        if outcome == TurnOutcomeType.decline_or_block:
            comp = CompositionPayload(
                response_payload=ResponsePayloadContent(
                    response_type="conversational",
                    content="I can't help with that request.",
                    structured_blocks=[],
                ),
                memory_candidates=[],
                debug={"blocked": True},
            )
        elif outcome == TurnOutcomeType.clarify:
            q = interpretation.clarification or "Could you provide more detail?"
            comp = CompositionPayload(
                response_payload=ResponsePayloadContent(
                    response_type="conversational",
                    content=q,
                    structured_blocks=[],
                ),
                memory_candidates=[],
                debug={},
            )
        else:
            ex_payload = execution_result.payload if execution_result else None
            yield format_workspace_stage_sse("compose", "started")
            t_comp = time.monotonic()
            compose_task = asyncio.create_task(
                self._compose_and_memory(
                    user_message=user_message,
                    companion=companion,
                    workspace=workspace,
                    interpretation=interpretation,
                    execution=ex_payload,
                    outcome=outcome,
                    session_context=session_context,
                    pipeline_cfg=pipeline_cfg,
                )
            )
            try:
                async for _ka in iter_sse_keepalive_lines_while_task_pending(compose_task):
                    yield _ka
                comp, memory_proposals = compose_task.result()
            except BaseException:
                compose_task.cancel()
                raise
            yield format_workspace_stage_sse(
                "compose",
                "completed",
                ms=(time.monotonic() - t_comp) * 1000,
            )

        comp, post_sse_lines = await self._finalize_composition_with_post_compose(
            comp=comp,
            pipeline_cfg=pipeline_cfg,
            user_message=user_message,
            workspace=workspace,
            companion=companion,
            execution=execution_result.payload if execution_result else None,
        )
        for _line in post_sse_lines:
            yield _line

        final_text = comp.response_payload.content
        for i in range(0, len(final_text), chunk_size):
            chunk = final_text[i : i + chunk_size]
            yield f"data: {json.dumps({'event': 'token', 'text': chunk})}\n\n"

        turn, replay = self._persist_workspace_turn(
            session=session,
            workspace=workspace,
            companion=companion,
            user_message=user_message,
            trace_id=trace_id,
            turn_index=turn_index,
            outcome=outcome,
            interp_result=interp_result,
            routing_plan=routing_plan,
            execution_result=execution_result,
            comp=comp,
            memory_proposals=memory_proposals,
            process_result=None,
        )

        digest = self._turn_digest_for_session_summary(
            user_message=user_message,
            assistant_reply=final_text,
            routing_plan=routing_plan,
            execution_result=execution_result,
            outcome=outcome,
        )
        yield format_workspace_stage_sse("session_summary", "started")
        t_sum = time.monotonic()
        await self._refresh_active_summary(
            workspace=workspace,
            companion=companion,
            session_row=session,
            turn_digest=digest,
        )
        yield format_workspace_stage_sse(
            "session_summary",
            "completed",
            ms=(time.monotonic() - t_sum) * 1000,
        )

        yield f"data: {json.dumps({'event': 'done', 'phase': 'completed', 'turn_id': str(turn.id), 'replay_id': str(replay.id), 'memory_proposed': len(memory_proposals)})}\n\n"

    async def run_confirm_capability_stream(
        self,
        *,
        workspace: Workspace,
        session: WorkspaceSession,
        companion: Companion,
        proposal_id: str,
        cancel: bool = False,
        chunk_size: int = 28,
    ) -> AsyncIterator[str]:
        """Execute or cancel a pending capability proposal (see `run_turn_stream`)."""
        proposal = self._load_capability_proposal(session, proposal_id)
        now = datetime.now(timezone.utc)

        if cancel:
            self._clear_capability_proposal(session)
            session.updated_at = now
            self.session.add(session)
            self.session.commit()
            self.session.refresh(session)
            final_text = "Okay — I won't run those workflows."
            for i in range(0, len(final_text), chunk_size):
                chunk = final_text[i : i + chunk_size]
                yield f"data: {json.dumps({'event': 'token', 'text': chunk})}\n\n"
            yield f"data: {json.dumps({'event': 'done', 'phase': 'cancelled', 'memory_proposed': 0})}\n\n"
            return

        allowed = self._allowed_capability_keys(workspace, companion)
        interp_result = InterpretationResult.model_validate(proposal["interpretation_result"])
        routing_plan = RoutingPlan.model_validate(proposal["routing_plan"])
        rp = routing_plan.payload
        for s in rp.selected_capabilities:
            if s.capability_key not in allowed:
                self._clear_capability_proposal(session)
                session.updated_at = now
                self.session.add(session)
                self.session.commit()
                raise ValueError("A workflow is no longer enabled on this workspace or companion.")

        interpretation = interp_result.payload
        user_message = str(proposal.get("user_message") or "")
        trace_id = str(proposal.get("trace_id") or secrets.token_hex(16))
        turn_index = session.turn_count
        outcome = TurnOutcomeType.invoke_capabilities

        self.session.refresh(session)
        await self._maybe_backfill_session_summary(workspace, companion, session)
        prompt_max, _, _ = self._session_memory_limits(workspace)
        session_context = self._session_context_block(session.active_summary, max_chars=prompt_max)
        pipeline_cfg = self._pipeline_config(workspace)

        yield format_workspace_stage_sse("execute", "started")
        t_ex = time.monotonic()
        exec_task = asyncio.create_task(self._execute_capabilities(rp, user_message, workspace))
        try:
            async for _ka in iter_sse_keepalive_lines_while_task_pending(exec_task):
                yield _ka
            ex = exec_task.result()
        except BaseException:
            exec_task.cancel()
            raise
        yield format_workspace_stage_sse(
            "execute",
            "completed",
            ms=(time.monotonic() - t_ex) * 1000,
            detail={
                "capability_results": [
                    {
                        "capability_key": r.capability_key,
                        "status": r.status,
                        "error": r.error,
                    }
                    for r in ex.capability_results
                ],
            },
        )
        execution_result = ExecutionResult(payload=ex)

        process_result: Optional[ProcessResult] = None
        process_payload_for_compose: Optional[ProcessPayload] = None
        if pipeline_cfg.process:
            proc_payload, proc_sse = await self._run_process_pipeline(
                pipeline_cfg=pipeline_cfg,
                workspace=workspace,
                companion=companion,
                execution=execution_result.payload,
            )
            for _line in proc_sse:
                yield _line
            if proc_payload.step_results:
                process_result = ProcessResult(payload=proc_payload)
                process_payload_for_compose = proc_payload

        yield format_workspace_stage_sse("compose", "started")
        t_comp = time.monotonic()
        compose_task = asyncio.create_task(
            self._compose_and_memory(
                user_message=user_message,
                companion=companion,
                workspace=workspace,
                interpretation=interpretation,
                execution=execution_result.payload,
                outcome=outcome,
                session_context=session_context,
                pipeline_cfg=pipeline_cfg,
                process_payload=process_payload_for_compose,
            )
        )
        try:
            async for _ka in iter_sse_keepalive_lines_while_task_pending(compose_task):
                yield _ka
            comp, memory_proposals = compose_task.result()
        except BaseException:
            compose_task.cancel()
            raise
        yield format_workspace_stage_sse(
            "compose",
            "completed",
            ms=(time.monotonic() - t_comp) * 1000,
        )

        comp, post_sse_lines = await self._finalize_composition_with_post_compose(
            comp=comp,
            pipeline_cfg=pipeline_cfg,
            user_message=user_message,
            workspace=workspace,
            companion=companion,
            execution=execution_result.payload,
        )
        for _line in post_sse_lines:
            yield _line

        self._clear_capability_proposal(session)
        session.updated_at = now
        self.session.add(session)

        final_text = comp.response_payload.content
        for i in range(0, len(final_text), chunk_size):
            chunk = final_text[i : i + chunk_size]
            yield f"data: {json.dumps({'event': 'token', 'text': chunk})}\n\n"

        turn, replay = self._persist_workspace_turn(
            session=session,
            workspace=workspace,
            companion=companion,
            user_message=user_message,
            trace_id=trace_id,
            turn_index=turn_index,
            outcome=outcome,
            interp_result=interp_result,
            routing_plan=routing_plan,
            execution_result=execution_result,
            comp=comp,
            memory_proposals=memory_proposals,
            process_result=process_result,
        )

        digest = self._turn_digest_for_session_summary(
            user_message=user_message,
            assistant_reply=final_text,
            routing_plan=routing_plan,
            execution_result=execution_result,
            outcome=outcome,
        )
        yield format_workspace_stage_sse("session_summary", "started")
        t_sum = time.monotonic()
        await self._refresh_active_summary(
            workspace=workspace,
            companion=companion,
            session_row=session,
            turn_digest=digest,
        )
        yield format_workspace_stage_sse(
            "session_summary",
            "completed",
            ms=(time.monotonic() - t_sum) * 1000,
        )

        yield f"data: {json.dumps({'event': 'done', 'phase': 'completed', 'turn_id': str(turn.id), 'replay_id': str(replay.id), 'memory_proposed': len(memory_proposals)})}\n\n"
