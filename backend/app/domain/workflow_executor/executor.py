"""
Workflow Executor
=================
Runs a WorkflowDefinition DAG, producing a WorkflowRunResult.

Execution model:
  1. Validate the graph: detect cycles, verify all step_id references exist.
  2. Topologically sort nodes (Kahn's algorithm).
  3. Execute nodes in level-based (wave) batches:
       - Nodes whose dependencies are satisfied run concurrently via asyncio.gather, up to the
         per-user cap in User.settings max_concurrent_lm_studio_calls (default 3). The same cap
         batches parallel For Loop iterations when parallel_iterations is enabled (otherwise N
         iterations would all run at once and bypass the wave limit).
       - Value nodes resolve immediately (no LLM call).
       - Collection nodes gather all upstream outputs.
       - SimpleLLMCall skill nodes call the LLM with system_prompt and user_prompt.
  4. Parallel siblings (nodes sharing the same source) execute simultaneously,
     enabling concurrent LLM calls to LM Studio. A failing sibling is recorded
     but does not halt its peers (return_exceptions=True).
"""

import asyncio
import contextlib
import copy
import json
import time
import uuid
from collections import deque
from collections.abc import Awaitable, Callable
from typing import Any, Dict, List, Optional, Sequence, cast

from sqlmodel import Session

from app.core.config import settings
from app.core.logging import logger
from app.core.workflow_execution_hub import SSE_KEEPALIVE_INTERVAL_SEC, sse_comment_keepalive
from app.core.run_log_redaction import redact_node_log_for_storage
from app.domain.schemas import (
    AudioFileInputSkillNode,
    AudioNodeOutput,
    BasicConditionalControlNode,
    BetweenControlNode,
    BooleanNodeOutput,
    ConditionalNodeOutput,
    DateTimeNodeOutput,
    DictionaryNodeOutput,
    DocumentNodeOutput,
    ForLoopControlNode,
    ForLoopEndControlNode,
    GmailNodeOutput,
    GraphEdge,
    GtControlNode,
    GteControlNode,
    IntNodeOutput,
    IsControlNode,
    IsEmptyControlNode,
    ListNodeOutput,
    LtControlNode,
    LteControlNode,
    NodeOutputUnion,
    NodeRunResult,
    ResponseNodeOutput,
    StartNodeOutput,
    StopNodeOutput,
    StringNodeOutput,
    StructureNodeOutput,
    TranscribeAudioSkillNode,
    TranscribeFileSkillNode,
    WorkflowRunResult,
    gmail_dict_to_node_output,
)
from app.domain.user_settings import resolve_max_concurrent_lm_studio_calls
from app.domain.workflow_executor.transcribe_pending import (
    TranscribeWaitKey,
    cancel_transcribe_wait,
)
from app.domain.workflow_executor.concurrency import workflow_node_extra_concurrency_bucket
from app.domain.workflow_run_status import terminal_status_for_aggregate
from app.domain.workspace.workspace_google_graph import workflow_graph_with_default_google_connection
from app.persistence.tables import (
    NodeRunLog,
    User,
    WorkflowDefinition,
    WorkflowRun,
    utc_now,
)

from .executor_resolver_mixin import WorkflowExecutorResolverMixin
from .graph import (
    _build_in_degree_and_adjacency,
    _detect_cycle,
    _topological_order,
    edges_with_both_endpoints_in,
    main_schedule_node_ids,
    validate_for_loop_bodies,
    validate_for_loop_end_configuration,
    validate_parallel_for_loop_no_nested_loop,
)
from .helpers import (
    _format_exception,
    parse_rfc3339_datetime_string,
    pop_wave_batch,
    split_batch_isolating_audio_steps,
)
from .inputs import (
    _resolve_upstream_for_node,
)
from .output_explorer import (
    attach_output_explorer_after_redact,
    merge_details_with_output_explorer,
)
from .parsing import _parse_node
from .skills_runner_mixin import WorkflowExecutorSkillsRunnerMixin


def __getattr__(name: str) -> Any:
    """Lazy bindings for ``patch("app.domain.workflow_executor.executor.<name>")`` in tests."""
    if name == "secrets":
        import secrets as _secrets_mod

        return _secrets_mod
    if name == "LMStudioProvider":
        from app.providers.lmstudio import LMStudioProvider as _v

        return _v
    if name == "transcribe_audio_bytes":
        from app.providers.stt_bridge import transcribe_audio_bytes as _v

        return _v
    if name == "synthesize_wav":
        from app.providers.tts_bridge import synthesize_wav as _v

        return _v
    if name == "get_speech_provider":
        from app.providers.transcription import get_speech_provider as _v

        return _v
    if name == "perform_url_snapshot_capture":
        from app.domain.workflow_executor.capture_url_snapshot_runtime import (
            perform_url_snapshot_capture as _v,
        )

        return _v
    if name == "perform_http_fetch":
        from app.domain.workflow_executor.fetch_url_runtime import perform_http_fetch as _v

        return _v
    if name == "ensure_workflow_google_access_token":
        from app.integrations.google_workspace import ensure_workflow_google_access_token as _v

        return _v
    if name == "gmail_list_messages":
        from app.integrations.google_workspace import gmail_list_messages as _v

        return _v
    if name == "gmail_get_message_full":
        from app.integrations.google_workspace import gmail_get_message_full as _v

        return _v
    if name == "calendar_list_events":
        from app.integrations.google_workspace import calendar_list_events as _v

        return _v
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


def __dir__() -> list[str]:
    _PATCH_NAMES = frozenset(
        {
            "LMStudioProvider",
            "calendar_list_events",
            "ensure_workflow_google_access_token",
            "get_speech_provider",
            "gmail_get_message_full",
            "gmail_list_messages",
            "perform_http_fetch",
            "perform_url_snapshot_capture",
            "secrets",
            "synthesize_wav",
            "transcribe_audio_bytes",
        },
    )
    return sorted(set(globals()) | set(_PATCH_NAMES))


def _sandbox_tick_dict_from_upstream(upstream: list[NodeOutputUnion]) -> dict | None:
    """Pick a dict-shaped ``SandboxTickInput`` from upstream node outputs."""
    for out in upstream:
        if isinstance(out, DictionaryNodeOutput):
            d = dict(out.data)
            if "world" in d and "pet" in d and "tick" in d:
                return d
        if isinstance(out, StartNodeOutput):
            st = out.outputs.get("sandbox_tick")
            if isinstance(st, dict):
                return st
    return None


def _paired_for_loop_end_id(for_loop_id: str, nodes_by_id: Dict[str, Any]) -> Optional[str]:
    for nid, n in nodes_by_id.items():
        if isinstance(n, ForLoopEndControlNode) and (n.data or {}).get("for_loop_id") == for_loop_id:
            return nid
    return None


def _node_output_to_json_dict(o: Any) -> Any:
    """Serialize a node output for ``resolved_inputs`` / run logs (JSON-friendly)."""
    md = getattr(o, "model_dump", None)
    if callable(md):
        return md(mode="json")
    return str(o)


def _resolved_inputs_value_for_log(v: Any) -> Any:
    """JSON-serialize one value for ``details.resolved_inputs`` (Run Logs / Last Run)."""
    if v is None or isinstance(v, (str, int, float, bool)):
        return v
    if isinstance(v, dict):
        return {str(kk): _resolved_inputs_value_for_log(vv) for kk, vv in v.items()}
    if isinstance(v, list):
        return [_resolved_inputs_value_for_log(x) for x in v]
    md = getattr(v, "model_dump", None)
    if callable(md):
        return md(mode="json")
    return _node_output_to_json_dict(v)


def _resolved_inputs_dict_for_log(resolved: dict[str, Any]) -> dict[str, Any]:
    """Normalize a resolved-input map for run logs (JSON-friendly)."""
    return {str(k): _resolved_inputs_value_for_log(val) for k, val in resolved.items()}


def _error_with_resolved_inputs(error_msg: str, resolved: dict[str, Any] | None = None) -> dict[str, Any]:
    """Structured error with optional ``details.resolved_inputs`` for troubleshooting failed steps."""
    out: dict[str, Any] = {"status": "error", "error": error_msg}
    if resolved is not None:
        out["details"] = {"resolved_inputs": _resolved_inputs_dict_for_log(resolved)}
    return out


def _error_with_structured(
    error_msg: str,
    *,
    err_type: str,
    retryable: bool,
    resolved: dict[str, Any] | None = None,
) -> dict[str, Any]:
    details: dict[str, Any] = {
        "structured_error": {"type": err_type, "message": error_msg, "retryable": retryable},
    }
    if resolved is not None:
        details["resolved_inputs"] = _resolved_inputs_dict_for_log(resolved)
    return {"status": "error", "error": error_msg, "details": details}


MESSAGE_UTILITY_MAX_LEN = 2048

STRING_TRUNC_RESOLVED_TARGET_MAX_CHARS = 4096
STRING_TRUNC_RESOLVED_PREFIX_LEN = 200


def _string_trunc_resolved_inputs_payload(text: str, start_used: int, end_used: int, *, result: str) -> dict[str, Any]:
    n = len(text)
    out: dict[str, Any] = {
        "start_index": start_used,
        "end_index": end_used,
        "target_chars": n,
        "result_chars": len(result),
    }
    if n <= STRING_TRUNC_RESOLVED_TARGET_MAX_CHARS:
        out["target_string"] = text
    else:
        out["target_truncated"] = True
        out["target_prefix"] = text[:STRING_TRUNC_RESOLVED_PREFIX_LEN]
    return out


def _string_trunc_error_resolved(resolved: dict[str, Any]) -> dict[str, Any]:
    """Omit or cap ``target_string`` in error snapshots for huge inputs."""
    raw_target = resolved.get("target_string")
    text = raw_target if isinstance(raw_target, str) else ("" if raw_target is None else str(raw_target))
    snap = {k: v for k, v in resolved.items() if k != "target_string"}
    n = len(text)
    snap["target_chars"] = n
    if n <= STRING_TRUNC_RESOLVED_TARGET_MAX_CHARS:
        snap["target_string"] = text
    elif n:
        snap["target_truncated"] = True
        snap["target_prefix"] = text[:STRING_TRUNC_RESOLVED_PREFIX_LEN]
    return snap


def _coerce_message_display_text(raw: Any) -> str:
    """Best-effort string for Message utility display and ``details.user_message``."""
    if raw is None:
        return ""
    if isinstance(raw, str):
        return raw
    if isinstance(raw, (int, float, bool)):
        return str(raw)
    if isinstance(raw, (dict, list)):
        return json.dumps(raw, indent=2)
    return str(raw)


def _text_from_stringish_output(out: NodeOutputUnion) -> Optional[str]:
    if isinstance(out, (StringNodeOutput, ResponseNodeOutput, StopNodeOutput)):
        return out.text
    if isinstance(out, StartNodeOutput):
        return out.text
    return None


def _list_item_to_join_token(item: Any) -> str:
    """Stringify one list element for List-to-String join mode (prompt-friendly)."""
    if isinstance(item, str):
        return item
    try:
        return json.dumps(item, ensure_ascii=False, separators=(",", ":"))
    except (TypeError, ValueError):
        return str(item)


def _json_text_to_fallback_string(out: NodeOutputUnion) -> str:
    """Best-effort string for ``StopNodeOutput`` when typed coercion fails."""
    if isinstance(out, (StringNodeOutput, ResponseNodeOutput, StopNodeOutput)):
        return out.text
    if isinstance(out, StartNodeOutput):
        return out.text
    if isinstance(out, (ListNodeOutput, DictionaryNodeOutput)):
        return json.dumps(out.data, indent=2)
    if isinstance(out, (BooleanNodeOutput, IntNodeOutput)):
        return str(out.value)
    if isinstance(out, DateTimeNodeOutput):
        return out.iso
    if isinstance(out, GmailNodeOutput):
        return json.dumps(out.model_dump(mode="json", by_alias=True), indent=2)
    if isinstance(out, AudioNodeOutput):
        return "[audio]"
    return str(out)


def coerce_stop_output(node_id: str, expected_type: str, out: NodeOutputUnion) -> NodeOutputUnion:
    """Return a typed node output matching Stop ``required_outputs[0].type`` for workflow chaining.

    Historically Stop always emitted ``StopNodeOutput`` with JSON/text, which broke List/Dict/boolean/int
    wiring into workflow refs and downstream nodes. When the expected type matches the upstream shape,
    pass through as ``ListNodeOutput`` / ``DictionaryNodeOutput`` / ``IntNodeOutput`` / ``BooleanNodeOutput``;
    string-like targets still use ``StopNodeOutput`` with ``text``.
    """
    et = (expected_type or "string").strip().lower() or "string"

    if et == "any":
        if isinstance(out, ListNodeOutput):
            return ListNodeOutput(node_id=node_id, data=list(out.data))
        if isinstance(out, DictionaryNodeOutput):
            return DictionaryNodeOutput(node_id=node_id, data=dict(out.data))
        if isinstance(out, BooleanNodeOutput):
            return BooleanNodeOutput(node_id=node_id, value=out.value)
        if isinstance(out, IntNodeOutput):
            return IntNodeOutput(node_id=node_id, value=int(out.value))
        if isinstance(out, DateTimeNodeOutput):
            return DateTimeNodeOutput(node_id=node_id, iso=out.iso)
        if isinstance(out, StructureNodeOutput):
            return StructureNodeOutput(node_id=node_id, schema_dict=dict(out.schema_dict))
        if isinstance(out, DocumentNodeOutput):
            return DocumentNodeOutput(
                node_id=node_id,
                document_id=out.document_id,
                name=out.name,
                description=out.description,
                markdown=out.markdown,
            )
        if isinstance(out, GmailNodeOutput):
            return gmail_dict_to_node_output(node_id, out.model_dump(mode="json", by_alias=True))
        if isinstance(out, AudioNodeOutput):
            return AudioNodeOutput(node_id=node_id, mime_type=out.mime_type, audio_base64=out.audio_base64)
        if isinstance(out, (StringNodeOutput, ResponseNodeOutput, StopNodeOutput)):
            return StopNodeOutput(node_id=node_id, text=out.text)
        if isinstance(out, StartNodeOutput):
            return StopNodeOutput(node_id=node_id, text=out.text)
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "list":
        if isinstance(out, ListNodeOutput):
            return ListNodeOutput(node_id=node_id, data=list(out.data))
        if isinstance(out, DictionaryNodeOutput):
            msgs = out.data.get("messages")
            if isinstance(msgs, list):
                return ListNodeOutput(node_id=node_id, data=list(msgs))
        t = _text_from_stringish_output(out)
        if t is not None:
            try:
                parsed = json.loads(t) if t.strip() else []
                if isinstance(parsed, dict) and isinstance(parsed.get("messages"), list):
                    return ListNodeOutput(node_id=node_id, data=list(parsed["messages"]))
                if not isinstance(parsed, list):
                    parsed = [parsed]
                return ListNodeOutput(node_id=node_id, data=parsed)
            except (json.JSONDecodeError, TypeError):
                pass
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "dictionary":
        if isinstance(out, DictionaryNodeOutput):
            return DictionaryNodeOutput(node_id=node_id, data=dict(out.data))
        t = _text_from_stringish_output(out)
        if t is not None:
            if not t.strip():
                # Empty string must not become {} — that breaks sandbox Stop (DecisionIntent) and hides wiring bugs.
                return StopNodeOutput(node_id=node_id, text=t)
            try:
                parsed = json.loads(t)
                if not isinstance(parsed, dict):
                    parsed = {}
                return DictionaryNodeOutput(node_id=node_id, data=parsed)
            except (json.JSONDecodeError, TypeError):
                pass
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "int":
        if isinstance(out, IntNodeOutput):
            return IntNodeOutput(node_id=node_id, value=int(out.value))
        t = _text_from_stringish_output(out)
        if t is not None:
            try:
                v = int(t.strip()) if t.strip() else 0
                return IntNodeOutput(node_id=node_id, value=v)
            except ValueError:
                return StopNodeOutput(node_id=node_id, text=t)
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "boolean":
        if isinstance(out, BooleanNodeOutput):
            return BooleanNodeOutput(node_id=node_id, value=out.value)
        ft = _json_text_to_fallback_string(out)
        val = (ft or "").strip().lower() in ("true", "yes", "1")
        return BooleanNodeOutput(node_id=node_id, value=val)

    if et == "structure":
        if isinstance(out, StructureNodeOutput):
            return StructureNodeOutput(node_id=node_id, schema_dict=dict(out.schema_dict))
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "document":
        if isinstance(out, DocumentNodeOutput):
            return DocumentNodeOutput(
                node_id=node_id,
                document_id=out.document_id,
                name=out.name,
                description=out.description,
                markdown=out.markdown,
            )
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "datetime":
        if isinstance(out, DateTimeNodeOutput):
            return DateTimeNodeOutput(node_id=node_id, iso=out.iso)
        t = _text_from_stringish_output(out)
        if t is not None:
            norm = parse_rfc3339_datetime_string(t)
            if norm is not None:
                return DateTimeNodeOutput(node_id=node_id, iso=norm)
            return StopNodeOutput(node_id=node_id, text=t)
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "gmail":
        if isinstance(out, GmailNodeOutput):
            return gmail_dict_to_node_output(node_id, out.model_dump(mode="json", by_alias=True))
        if isinstance(out, DictionaryNodeOutput):
            return gmail_dict_to_node_output(node_id, dict(out.data))
        t = _text_from_stringish_output(out)
        if t is not None and t.strip():
            try:
                parsed = json.loads(t)
                if isinstance(parsed, dict):
                    return gmail_dict_to_node_output(node_id, parsed)
            except (json.JSONDecodeError, TypeError):
                pass
            return StopNodeOutput(node_id=node_id, text=t)
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    if et == "audio":
        if isinstance(out, AudioNodeOutput):
            return AudioNodeOutput(node_id=node_id, mime_type=out.mime_type, audio_base64=out.audio_base64)
        return StopNodeOutput(node_id=node_id, text=_json_text_to_fallback_string(out))

    # string (default): preserve text shell for LLM / text workflows
    final_text: str
    if isinstance(out, (StringNodeOutput, ResponseNodeOutput, StopNodeOutput)):
        final_text = out.text
    elif isinstance(out, StartNodeOutput):
        final_text = out.text
    elif isinstance(out, (ListNodeOutput, DictionaryNodeOutput)):
        final_text = json.dumps(out.data, indent=2)
    elif isinstance(out, (BooleanNodeOutput, IntNodeOutput)):
        final_text = str(out.value)
    elif isinstance(out, DateTimeNodeOutput):
        final_text = out.iso
    elif isinstance(out, GmailNodeOutput):
        final_text = json.dumps(out.model_dump(mode="json", by_alias=True), indent=2)
    elif isinstance(out, AudioNodeOutput):
        final_text = "[audio]"
    else:
        final_text = str(out)
    return StopNodeOutput(node_id=node_id, text=final_text)


class _StepRecorder:
    __slots__ = ("_n",)

    def __init__(self) -> None:
        self._n = 0

    def next_step(self) -> int:
        self._n += 1
        return self._n


def _effective_gmail_calendar_zone(
    user_settings: Optional[Dict[str, Any]],
    execution_time_zone: Optional[str],
) -> Optional[str]:
    """Prefer explicit profile IANA; else optional per-run client zone (for profile 'system')."""
    st = user_settings or {}
    pref = st.get("workflow_time_zone")
    if isinstance(pref, str):
        p = pref.strip()
        if p and p.casefold() != "system":
            return p
    ex = (execution_time_zone or "").strip()
    return ex if ex else None


_UPSERT_CONTENT_HANDLE_ALIASES = frozenset({"output", "text", "body", "markdown"})


def _normalize_edges_for_upsert_document(node_id: str, edges: List[GraphEdge]) -> List[GraphEdge]:
    """
    Map legacy/wrong ``target_handle`` values onto ``content`` so pass-1 resolution matches.
    Does not alter ``trigger`` or null/empty handles (implicit pass still applies).
    """
    out: List[GraphEdge] = []
    for e in edges:
        if e.target != node_id:
            out.append(e)
            continue
        th = (e.target_handle or "").strip()
        if th == "trigger" or th == "":
            out.append(e)
            continue
        if th in _UPSERT_CONTENT_HANDLE_ALIASES:
            out.append(e.model_copy(update={"target_handle": "content"}))
            continue
        out.append(e)
    return out


def _explorer_upsert_name_from_required_inputs(raw_inputs: Sequence[Dict[str, Any]]) -> str:
    for item in raw_inputs:
        if isinstance(item, dict) and item.get("key") == "name":
            v = item.get("value")
            if v is None:
                return ""
            return str(v).strip()
    return ""


def _upsert_content_resolved_blank(val: Any) -> bool:
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip() == ""
    return False


def _recover_upsert_miswired_body_into_content(
    node_id: str,
    edges: List[GraphEdge],
    resolved: Dict[str, Any],
    raw_inputs: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Recover graphs where ``target_handle: "name"`` was persisted for what was intended as body text
    (null-handle default in older editor conversions). Explorer title wins; wired text moves to
    ``content`` when there is no explicit ``content`` edge.
    """
    if not _upsert_content_resolved_blank(resolved.get("content")):
        return resolved
    explorer_name = _explorer_upsert_name_from_required_inputs(raw_inputs)
    if not explorer_name:
        return resolved
    resolved_name = resolved.get("name")
    if resolved_name is None:
        return resolved
    rs = str(resolved_name).strip()
    if rs == explorer_name:
        return resolved
    has_content_edge = False
    has_name_edge = False
    for e in edges:
        if e.target != node_id:
            continue
        th = (e.target_handle or "").strip()
        if th == "trigger":
            continue
        if th == "content":
            has_content_edge = True
        if th == "name":
            has_name_edge = True
    if not has_name_edge or has_content_edge:
        return resolved
    out = dict(resolved)
    out["name"] = explorer_name
    out["content"] = resolved_name
    return out


def _decrement_signal_out_triggers(
    node_id: str,
    main_edges: List[GraphEdge],
    main_ids: set[str],
    in_degree: Dict[str, int],
    ready: deque[str],
) -> None:
    """After a branching control completes, schedule nodes connected via signal_out → trigger."""
    for edge in main_edges:
        if edge.source != node_id:
            continue
        if edge.source_handle != "signal_out":
            continue
        th = (edge.target_handle or "").strip()
        if th != "trigger":
            continue
        succ = edge.target
        if succ in main_ids:
            in_degree[succ] -= 1
            if in_degree[succ] == 0:
                ready.append(succ)


@contextlib.asynccontextmanager
async def _workflow_acquire_sem(sem: asyncio.Semaphore):
    await sem.acquire()
    try:
        yield
    finally:
        sem.release()


class WorkflowExecutor(WorkflowExecutorResolverMixin, WorkflowExecutorSkillsRunnerMixin):
    """Executes a WorkflowDefinition and returns a WorkflowRunResult."""

    def __init__(
        self,
        session: Session,
        user_id: uuid.UUID,
        default_google_workflow_connection_id: Optional[uuid.UUID] = None,
    ):
        self.session = session
        self.user_id = user_id
        self.default_google_workflow_connection_id = default_google_workflow_connection_id
        # Serialize ORM access: parallel waves run multiple nodes concurrently (asyncio.gather);
        # SQLAlchemy Session is not safe for concurrent use from overlapping asyncio tasks.
        # Simple LLM loads User/api_keys under this lock; httpx to LM Studio runs outside it.
        self._async_session_lock = asyncio.Lock()
        # Cleared at the start of each run; then cached from User.settings + env concurrency caps.
        self._max_concurrent_wave_cap: Optional[int] = None
        self._pending_interstitial_tuples: deque[tuple[str, dict[str, Any]]] = deque()
        self._stream_interstitial_sink: Optional[list[tuple[str, dict[str, Any]]]] = None
        self._active_transcribe_wait_keys: set[TranscribeWaitKey] = set()
        self._streaming_ctx_workflow_id: Optional[uuid.UUID] = None
        self._streaming_ctx_run_id: Optional[uuid.UUID] = None
        self._sem_node: asyncio.Semaphore | None = None
        self._sem_llm: asyncio.Semaphore | None = None
        self._sem_browser: asyncio.Semaphore | None = None
        self._sem_external: asyncio.Semaphore | None = None

    def _ensure_run_execution_semaphores(self) -> None:
        u = self.session.get(User, self.user_id)
        user_lm = resolve_max_concurrent_lm_studio_calls(getattr(u, "settings", None) if u else None)
        llm_eff = min(max(1, settings.WORKFLOW_MAX_CONCURRENT_LLM_CALLS), max(1, user_lm))
        gn = max(1, settings.WORKFLOW_MAX_CONCURRENT_NODES)
        br = max(1, settings.WORKFLOW_MAX_CONCURRENT_BROWSER_TASKS)
        ex = max(1, settings.WORKFLOW_MAX_CONCURRENT_EXTERNAL_SKILL_TASKS)
        self._sem_node = asyncio.Semaphore(gn)
        self._sem_llm = asyncio.Semaphore(llm_eff)
        self._sem_browser = asyncio.Semaphore(br)
        self._sem_external = asyncio.Semaphore(ex)

    def _clear_run_execution_semaphores(self) -> None:
        self._sem_node = None
        self._sem_llm = None
        self._sem_browser = None
        self._sem_external = None

    @contextlib.asynccontextmanager
    async def _node_execution_scope(self, node: Any):
        """Global node slot plus optional LLM / browser / external slot (mutually exclusive extras)."""
        if self._sem_node is None:
            yield
            return
        extra = workflow_node_extra_concurrency_bucket(node)
        async with contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(_workflow_acquire_sem(self._sem_node))
            if extra == "llm" and self._sem_llm is not None:
                await stack.enter_async_context(_workflow_acquire_sem(self._sem_llm))
            elif extra == "browser" and self._sem_browser is not None:
                await stack.enter_async_context(_workflow_acquire_sem(self._sem_browser))
            elif extra == "external" and self._sem_external is not None:
                await stack.enter_async_context(_workflow_acquire_sem(self._sem_external))
            yield

    @contextlib.contextmanager
    def _transcribe_stream_sink(self, stream_evt_acc: Optional[list[tuple[str, dict[str, Any]]]]):
        """While in a For loop body, mirror interstitial payloads into the parent event buffer."""
        prev = self._stream_interstitial_sink
        if stream_evt_acc is not None:
            self._stream_interstitial_sink = stream_evt_acc
        try:
            yield
        finally:
            self._stream_interstitial_sink = prev

    def _emit_interstitial(self, obj: Dict[str, Any]) -> None:
        ev = str(obj.get("event", "message"))
        rest = {k: v for k, v in obj.items() if k != "event"}
        self._pending_interstitial_tuples.append((ev, rest))
        sink = self._stream_interstitial_sink
        if sink is not None:
            sink.append((ev, dict(rest)))

    async def _flush_interstitial_sse(
        self,
        sse_publish: Callable[[str, dict[str, object]], Awaitable[int]],
        persist_run_record: WorkflowRun | None,
    ) -> None:
        while self._pending_interstitial_tuples:
            ev, payload = self._pending_interstitial_tuples.popleft()
            pl = dict(payload)
            if self._streaming_ctx_workflow_id is not None and "workflow_id" not in pl:
                pl["workflow_id"] = str(self._streaming_ctx_workflow_id)
            if self._streaming_ctx_run_id is not None and "run_id" not in pl:
                pl["run_id"] = str(self._streaming_ctx_run_id)
            seq = await sse_publish(ev, pl)
            if persist_run_record is not None:
                persist_run_record.last_event_seq = seq
                self.session.add(persist_run_record)
                self.session.commit()

    @contextlib.asynccontextmanager
    async def _scoped_run_semaphores(self):
        self._ensure_run_execution_semaphores()
        try:
            yield
        finally:
            self._clear_run_execution_semaphores()

    def _track_transcribe_wait(self, key: TranscribeWaitKey) -> None:
        self._active_transcribe_wait_keys.add(key)

    def _untrack_transcribe_wait(self, key: TranscribeWaitKey) -> None:
        self._active_transcribe_wait_keys.discard(key)

    def _cancel_active_transcribe_waits(self) -> None:
        for key in list(self._active_transcribe_wait_keys):
            cancel_transcribe_wait(key)
        self._active_transcribe_wait_keys.clear()

    def _inject_google_into_workflow(self, workflow: WorkflowDefinition) -> WorkflowDefinition:
        """Return a shallow copy whose graph has workspace default Google ids injected (no-op if unset)."""
        if self.default_google_workflow_connection_id is None:
            return workflow
        adj = workflow_graph_with_default_google_connection(
            self.session,
            user_id=self.user_id,
            graph=workflow.graph,
            default_connection_id=self.default_google_workflow_connection_id,
        )
        wf = copy.copy(workflow)
        wf.graph = adj
        return wf

    def _wave_cap_for_run(self) -> int:
        if self._max_concurrent_wave_cap is not None:
            return self._max_concurrent_wave_cap
        u = self.session.get(User, self.user_id)
        user_lm = resolve_max_concurrent_lm_studio_calls(getattr(u, "settings", None) if u else None)
        lm_eff = min(max(1, settings.WORKFLOW_MAX_CONCURRENT_LLM_CALLS), max(1, user_lm))
        cap = min(lm_eff, max(1, settings.WORKFLOW_MAX_CONCURRENT_NODES))
        self._max_concurrent_wave_cap = cap
        return self._max_concurrent_wave_cap

    async def run(
        self,
        workflow: WorkflowDefinition,
        input_overrides: Optional[Dict[str, Any]] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
        execution_stack: Optional[frozenset] = None,
        execution_time_zone: Optional[str] = None,
    ) -> WorkflowRunResult:
        """
        Validate, sort, and execute the workflow graph.
        Returns a WorkflowRunResult regardless of whether individual nodes fail.
        Raises ValueError for structural errors (cycles, missing steps).
        execution_stack: workflow IDs currently being executed (for cycle detection in workflow nodes).
        """
        stack = execution_stack or frozenset()
        etz = (execution_time_zone or "").strip() or None
        workflow = self._inject_google_into_workflow(workflow)
        graph = workflow.graph
        raw_nodes: list[Dict[str, Any]] = graph.get("nodes", [])
        raw_edges: list[Dict[str, Any]] = graph.get("edges", [])

        # Parse nodes and edges.
        nodes_by_id: Dict[str, Any] = {}
        for raw_node in raw_nodes:
            parsed = _parse_node(raw_node)
            if parsed is not None:
                nodes_by_id[parsed.id] = parsed

        edges = [GraphEdge(**e) for e in raw_edges]

        # --- Validation: cycle detection ---
        cycle = _detect_cycle(list(nodes_by_id.keys()), edges)
        if cycle:
            raise ValueError(f"Workflow graph contains a cycle involving nodes: {cycle}")

        fl_bodies = validate_for_loop_bodies(nodes_by_id, edges)
        validate_for_loop_end_configuration(nodes_by_id, edges)
        validate_parallel_for_loop_no_nested_loop(nodes_by_id, edges)
        union_body: set[str] = set()
        for _fid, bset in fl_bodies.items():
            union_body |= bset
        main_ids = main_schedule_node_ids(set(nodes_by_id.keys()), union_body)
        main_edges = edges_with_both_endpoints_in(main_ids, edges)

        # --- Execution (level-based parallel, main schedule only) ---
        order = _topological_order(sorted(main_ids), main_edges)
        order_index = {nid: i for i, nid in enumerate(order)}
        in_degree, adjacency = _build_in_degree_and_adjacency(sorted(main_ids), main_edges, nodes_by_id)
        ready: deque[str] = deque(nid for nid, deg in in_degree.items() if deg == 0)

        outputs: Dict[str, NodeOutputUnion] = {}
        node_results: list[NodeRunResult] = []
        recorder = _StepRecorder()
        om = output_overrides_map or {}
        self._max_concurrent_wave_cap = None
        wave_cap = self._wave_cap_for_run()

        for _nid, _n in nodes_by_id.items():
            if isinstance(_n, TranscribeAudioSkillNode) and _nid not in om:
                raise ValueError(
                    "This workflow includes Voice input (transcribe_audio). Use the streaming Run from the "
                    "workflow editor, or provide an output override for that node."
                )
            if isinstance(_n, AudioFileInputSkillNode) and _nid not in om:
                data = _n.data or {}
                if not (isinstance(data.get("audio_artifact_id"), str) and data["audio_artifact_id"].strip()):
                    raise ValueError(
                        "This workflow includes Audio File Input without a saved file. Use the streaming Run from the "
                        "workflow editor, attach an audio file artifact to the node, or provide an output override."
                    )
            if isinstance(_n, TranscribeFileSkillNode) and _nid not in om:
                data = _n.data or {}
                if not (isinstance(data.get("audio_artifact_id"), str) and data["audio_artifact_id"].strip()):
                    raise ValueError(
                        "This workflow includes Transcribe File without a saved file. Use the streaming Run from the "
                        "workflow editor, attach an audio file artifact to the node, or provide an output override."
                    )

        async with self._scoped_run_semaphores():
            while ready:
                batch = pop_wave_batch(ready, order_index, wave_cap)
                batch = split_batch_isolating_audio_steps(batch, ready, order_index, nodes_by_id)

                async def run_node(node_id: str):
                    node = nodes_by_id[node_id]
                    t0 = time.monotonic()
                    if isinstance(node, ForLoopControlNode):
                        result = await self._run_for_loop_node(
                            node_id,
                            node,
                            edges,
                            outputs,
                            input_overrides,
                            workflow,
                            stack,
                            nodes_by_id,
                            recorder,
                            node_results,
                            execution_time_zone=etz,
                            output_overrides_map=om,
                        )
                    elif isinstance(node, ForLoopEndControlNode):
                        result = self._resolve_for_loop_end_node(node_id, node, edges, outputs, output_overrides_map=om)
                    else:
                        upstream = _resolve_upstream_for_node(node_id, edges, outputs)
                        result = await self._execute_node(
                            node_id,
                            node,
                            upstream,
                            edges,
                            outputs,
                            input_overrides,
                            workflow=workflow,
                            execution_stack=stack,
                            execution_time_zone=etz,
                            output_overrides_map=om,
                            stream_run_id=None,
                            for_loop_id=None,
                            for_loop_iteration=None,
                        )
                    elapsed_ms = (time.monotonic() - t0) * 1000
                    return result, elapsed_ms

                gathered = await asyncio.gather(
                    *[run_node(node_id) for node_id in batch],
                    return_exceptions=True,
                )

                for node_id, raw in zip(batch, gathered):
                    if isinstance(raw, BaseException):
                        result = {"status": "error", "error": _format_exception(raw)}
                        elapsed_ms = 0.0
                    else:
                        result, elapsed_ms = cast(tuple[dict[str, Any], float], raw)

                    out_for_result: Any = result.get("output")
                    raw_output_result: dict[str, Any] | None = None
                    if out_for_result is not None:
                        md_r = getattr(out_for_result, "model_dump", None)
                        if callable(md_r):
                            raw_output_result = md_r(mode="json")
                    raw_det_result = cast(dict[str, Any], result.get("details") or {})
                    details_for_client = merge_details_with_output_explorer(raw_det_result, raw_output_result)

                    node_results.append(
                        NodeRunResult(
                            node_id=node_id,
                            status=result["status"],
                            output=result.get("output"),
                            error=result.get("error"),
                            latency_ms=round(elapsed_ms, 2),
                            details=details_for_client,
                            step_number=recorder.next_step(),
                        )
                    )

                    if result["status"] == "ok" and result.get("output"):
                        outputs[node_id] = cast(NodeOutputUnion, result["output"])

                    node_exec: Any = nodes_by_id[node_id]
                    output_val: Any = result.get("output")
                    if isinstance(
                        node_exec,
                        (
                            BasicConditionalControlNode,
                            BetweenControlNode,
                            IsControlNode,
                            IsEmptyControlNode,
                            GtControlNode,
                            LtControlNode,
                            GteControlNode,
                            LteControlNode,
                        ),
                    ) and isinstance(output_val, ConditionalNodeOutput):
                        for edge in main_edges:
                            if edge.source == node_id and edge.source_handle == output_val.branch:
                                succ = edge.target
                                if succ in main_ids:
                                    in_degree[succ] -= 1
                                    if in_degree[succ] == 0:
                                        ready.append(succ)
                        _decrement_signal_out_triggers(node_id, main_edges, main_ids, in_degree, ready)
                    else:
                        for succ in adjacency.get(node_id, []):
                            in_degree[succ] -= 1
                            if in_degree[succ] == 0:
                                ready.append(succ)

            # Overall status: ok if all succeeded, partial if some failed, error if all failed.
            statuses = {r.status for r in node_results}
            if statuses == {"ok"}:
                overall = "ok"
            elif "ok" in statuses:
                overall = "partial"
            else:
                overall = "error"

            return WorkflowRunResult(
                workflow_id=workflow.id,
                status=overall,
                node_results=node_results,
            )

    async def execute_scheduled_run(
        self,
        workflow: WorkflowDefinition,
        *,
        persist_run_record: WorkflowRun,
        input_overrides: Optional[Dict[str, Any]] = None,
        output_overrides_map: Optional[Dict[str, NodeOutputUnion]] = None,
        execution_stack: Optional[frozenset] = None,
        execution_time_zone: Optional[str] = None,
        sse_publish: Callable[[str, dict[str, object]], Awaitable[int]],
        sse_raw: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> WorkflowRunResult:
        """Execute a persisted workflow run row and stream lifecycle events via ``sse_publish``."""
        stack = execution_stack or frozenset()
        workflow = self._inject_google_into_workflow(workflow)
        graph = workflow.graph
        raw_nodes: list[Dict[str, Any]] = graph.get("nodes", [])
        raw_edges: list[Dict[str, Any]] = graph.get("edges", [])

        run_id = persist_run_record.id
        self._streaming_ctx_workflow_id = workflow.id
        self._streaming_ctx_run_id = run_id
        self._pending_interstitial_tuples.clear()
        self._active_transcribe_wait_keys.clear()
        _run_tasks: list[asyncio.Task[Any]] = []

        async def _cancel_run_tasks() -> None:
            pending_tasks = [task for task in _run_tasks if not task.done()]
            if not pending_tasks:
                return
            for task in pending_tasks:
                task.cancel()
            await asyncio.gather(*pending_tasks, return_exceptions=True)

        def _persist_failed(msg: str) -> WorkflowRunResult:
            try:
                persist_run_record.status = "failed"
                persist_run_record.completed_at = utc_now()
                self.session.add(persist_run_record)
                self.session.commit()
            except Exception:
                logger.exception("failed to persist terminal failed for run_id=%s", run_id)
            return WorkflowRunResult(workflow_id=workflow.id, status="error", node_results=[])

        async def _emit(event: str, payload: dict[str, object]) -> int:
            seq = await sse_publish(event, payload)
            persist_run_record.last_event_seq = seq
            self.session.add(persist_run_record)
            self.session.commit()
            return seq

        try:
            etz = (execution_time_zone or "").strip() or None

            nodes_by_id: Dict[str, Any] = {}
            for raw_node in raw_nodes:
                parsed = _parse_node(raw_node)
                if parsed is not None:
                    nodes_by_id[parsed.id] = parsed

            edges = [GraphEdge(**e) for e in raw_edges]

            cycle = _detect_cycle(list(nodes_by_id.keys()), edges)
            if cycle:
                await _emit(
                    "workflow.failed",
                    {
                        "workflow_id": str(workflow.id),
                        "run_id": str(run_id),
                        "error": f"Workflow graph contains a cycle involving nodes: {cycle}",
                    },
                )
                return _persist_failed("cycle")

            try:
                fl_bodies = validate_for_loop_bodies(nodes_by_id, edges)
                validate_for_loop_end_configuration(nodes_by_id, edges)
                validate_parallel_for_loop_no_nested_loop(nodes_by_id, edges)
            except ValueError as exc:
                await _emit(
                    "workflow.failed",
                    {"workflow_id": str(workflow.id), "run_id": str(run_id), "error": str(exc)},
                )
                return _persist_failed(str(exc))

            await _emit(
                "workflow.started",
                {"workflow_id": str(workflow.id), "run_id": str(run_id)},
            )

            union_body: set[str] = set()
            for _fid, bset in fl_bodies.items():
                union_body |= bset
            main_ids = main_schedule_node_ids(set(nodes_by_id.keys()), union_body)
            main_edges = edges_with_both_endpoints_in(main_ids, edges)

            order = _topological_order(sorted(main_ids), main_edges)
            order_index = {nid: i for i, nid in enumerate(order)}
            in_degree, adjacency = _build_in_degree_and_adjacency(sorted(main_ids), main_edges, nodes_by_id)
            ready = deque[str](nid for nid, deg in in_degree.items() if deg == 0)

            outputs: Dict[str, NodeOutputUnion] = {}
            node_results: list[NodeRunResult] = []
            recorder = _StepRecorder()
            om = output_overrides_map or {}
            self._max_concurrent_wave_cap = None
            wave_cap = self._wave_cap_for_run()

            async with self._scoped_run_semaphores():
                while ready:
                    batch = pop_wave_batch(ready, order_index, wave_cap)
                    batch = split_batch_isolating_audio_steps(batch, ready, order_index, nodes_by_id)

                    await _emit("node.queued", {"node_ids": list(batch), "run_id": str(run_id)})
                    for node_id in batch:
                        await _emit(
                            "node.started",
                            {"workflow_id": str(workflow.id), "run_id": str(run_id), "node_id": node_id},
                        )

                    async def run_node(node_id: str):
                        node = nodes_by_id[node_id]
                        t0 = time.monotonic()
                        stream_bucket: list[tuple[str, dict[str, Any]]] = []
                        if isinstance(node, ForLoopControlNode):
                            result = await self._run_for_loop_node(
                                node_id,
                                node,
                                edges,
                                outputs,
                                input_overrides,
                                workflow,
                                stack,
                                nodes_by_id,
                                recorder,
                                node_results,
                                run_id,
                                stream_bucket,
                                execution_time_zone=etz,
                                output_overrides_map=om,
                            )
                        elif isinstance(node, ForLoopEndControlNode):
                            result = self._resolve_for_loop_end_node(
                                node_id, node, edges, outputs, output_overrides_map=om
                            )
                        else:
                            upstream = _resolve_upstream_for_node(node_id, edges, outputs)
                            result = await self._execute_node(
                                node_id,
                                node,
                                upstream,
                                edges,
                                outputs,
                                input_overrides,
                                workflow=workflow,
                                execution_stack=stack,
                                execution_time_zone=etz,
                                output_overrides_map=om,
                                stream_run_id=run_id,
                                for_loop_id=None,
                                for_loop_iteration=None,
                            )
                        elapsed_ms = (time.monotonic() - t0) * 1000
                        return result, elapsed_ms, stream_bucket

                    _run_tasks = [asyncio.create_task(run_node(node_id)) for node_id in batch]
                    await asyncio.sleep(0)
                    _pending: set[asyncio.Task[Any]] = set(_run_tasks)
                    ka_sec = SSE_KEEPALIVE_INTERVAL_SEC
                    while _pending:
                        await self._flush_interstitial_sse(sse_publish, persist_run_record)
                        _, _pending = await asyncio.wait(_pending, timeout=ka_sec)
                        if _pending and sse_raw is not None:
                            await sse_raw(sse_comment_keepalive())
                    await self._flush_interstitial_sse(sse_publish, persist_run_record)

                    gathered = []
                    for _t in _run_tasks:
                        try:
                            gathered.append(_t.result())
                        except BaseException as _exc:
                            gathered.append(_exc)

                    for node_id, raw in zip(batch, gathered):
                        stream_bucket: list[tuple[str, dict[str, Any]]] = []
                        if isinstance(raw, BaseException):
                            result = {"status": "error", "error": _format_exception(raw)}
                            elapsed_ms = 0.0
                        else:
                            result, elapsed_ms, stream_bucket = cast(
                                tuple[dict[str, Any], float, list[tuple[str, dict[str, Any]]]], raw
                            )

                        for evn, tpl in stream_bucket:
                            seq = await sse_publish(evn, dict(tpl))
                            persist_run_record.last_event_seq = seq
                            self.session.add(persist_run_record)
                            self.session.commit()

                        out_for_log: Any = result.get("output")
                        raw_output: dict[str, Any] | None = None
                        if out_for_log is not None:
                            md = getattr(out_for_log, "model_dump", None)
                            if callable(md):
                                raw_output = md(mode="json")
                        raw_details: dict[str, Any] = cast(dict[str, Any], result.get("details") or {})
                        details_for_client = merge_details_with_output_explorer(raw_details, raw_output)

                        node_run_result = NodeRunResult(
                            node_id=node_id,
                            status=result["status"],
                            output=result.get("output"),
                            error=result.get("error"),
                            latency_ms=round(elapsed_ms, 2),
                            details=details_for_client,
                            step_number=recorder.next_step(),
                        )
                        node_results.append(node_run_result)

                        ev_done = "node.completed" if result["status"] == "ok" else "node.failed"
                        await _emit(
                            ev_done,
                            {
                                "workflow_id": str(workflow.id),
                                "run_id": str(run_id),
                                "node_id": node_id,
                                "result": node_run_result.model_dump(mode="json", serialize_as_any=True),
                            },
                        )

                        safe_out, safe_det = redact_node_log_for_storage(raw_output, raw_details)
                        safe_det = attach_output_explorer_after_redact(safe_out, safe_det)
                        node_log = NodeRunLog(
                            run_id=run_id,
                            node_id=node_id,
                            step_number=node_run_result.step_number,
                            status=result["status"],
                            output_data=safe_out,
                            error=result.get("error"),
                            latency_ms=round(elapsed_ms, 2),
                            details=safe_det,
                        )
                        self.session.add(node_log)
                        self.session.commit()

                        if result["status"] == "ok" and result.get("output"):
                            outputs[node_id] = cast(NodeOutputUnion, result["output"])

                        node_exec: Any = nodes_by_id[node_id]
                        output_val: Any = result.get("output")
                        if isinstance(
                            node_exec,
                            (
                                BasicConditionalControlNode,
                                BetweenControlNode,
                                IsControlNode,
                                IsEmptyControlNode,
                                GtControlNode,
                                LtControlNode,
                                GteControlNode,
                                LteControlNode,
                            ),
                        ) and isinstance(output_val, ConditionalNodeOutput):
                            for edge in main_edges:
                                if edge.source == node_id and edge.source_handle == output_val.branch:
                                    succ = edge.target
                                    if succ in main_ids:
                                        in_degree[succ] -= 1
                                        if in_degree[succ] == 0:
                                            ready.append(succ)
                            _decrement_signal_out_triggers(node_id, main_edges, main_ids, in_degree, ready)
                        else:
                            for succ in adjacency.get(node_id, []):
                                in_degree[succ] -= 1
                                if in_degree[succ] == 0:
                                    ready.append(succ)
                    _run_tasks = []

                statuses = {r.status for r in node_results}
                if statuses == {"ok"}:
                    overall = "ok"
                elif "ok" in statuses:
                    overall = "partial"
                else:
                    overall = "error"

                final_result = WorkflowRunResult(
                    workflow_id=workflow.id,
                    status=overall,
                    node_results=node_results,
                )

                persist_run_record.status = terminal_status_for_aggregate(overall)
                persist_run_record.completed_at = utc_now()
                self.session.add(persist_run_record)
                self.session.commit()
                self._cancel_active_transcribe_waits()

                await _emit(
                    "workflow.completed",
                    {"workflow_id": str(workflow.id), "run_id": str(run_id), "result": final_result.model_dump(mode="json", serialize_as_any=True)},
                )
                return final_result

        except asyncio.CancelledError:
            logger.info("execute_scheduled_run cancelled workflow %s run_id=%s", workflow.id, run_id)
            await _cancel_run_tasks()
            self._cancel_active_transcribe_waits()
            _persist_failed("cancelled")
            raise
        except Exception as exc:
            logger.exception("execute_scheduled_run failed workflow %s run_id=%s", workflow.id, run_id)
            await _cancel_run_tasks()
            self._cancel_active_transcribe_waits()
            try:
                await sse_publish(
                    "workflow.failed",
                    {
                        "workflow_id": str(workflow.id),
                        "run_id": str(run_id),
                        "error": _format_exception(exc),
                    },
                )
            except Exception:
                logger.exception("failed to emit workflow.failed for run_id=%s", run_id)
            _persist_failed(str(exc))
            raise
        finally:
            self._streaming_ctx_workflow_id = None
            self._streaming_ctx_run_id = None
