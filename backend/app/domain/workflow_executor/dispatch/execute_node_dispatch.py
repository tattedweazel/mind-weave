from __future__ import annotations

from typing import Any

from app.core.logging import logger
from app.domain.schemas import (
    AddDaysUtilityNode,
    AddIntsUtilityNode,
    AddToListUtilityNode,
    AndControlNode,
    AppendValueToDocumentUtilityNode,
    AudioFileInputSkillNode,
    BasicConditionalControlNode,
    BetweenControlNode,
    BooleanPrimitiveNode,
    CalendarListEventsSkillNode,
    GoogleDocsGetDocumentSkillNode,
    GoogleDocsParseDocumentUtilityNode,
    CaptureUrlSnapshotSkillNode,
    DateTimePrimitiveNode,
    DictionaryPrimitiveNode,
    DictionarySetValueByKeyUtilityNode,
    DictionaryValueByKeyUtilityNode,
    DivideIntsUtilityNode,
    DocumentPrimitiveNode,
    FetchUrlSkillNode,
    GmailListMessagesSkillNode,
    GmailPrimitiveNode,
    GtControlNode,
    GteControlNode,
    HtmlParseBasicUtilityNode,
    ImagePrimitiveNode,
    IntPrimitiveNode,
    IntToStringUtilityNode,
    IsControlNode,
    IsEmptyControlNode,
    LenFromListUtilityNode,
    ListItemByIndexUtilityNode,
    ListPrimitiveNode,
    ListToStringUtilityNode,
    LoadDocumentUtilityNode,
    LtControlNode,
    LteControlNode,
    MaxIntsUtilityNode,
    MessageUtilityNode,
    MinIntsUtilityNode,
    ModuloIntsUtilityNode,
    MultimodalLLMCallSkillNode,
    MultiplyIntsUtilityNode,
    NotControlNode,
    OrControlNode,
    ParseDocumentBodyUtilityNode,
    PrependTextUtilityNode,
    RandomItemFromListUtilityNode,
    ReadDocumentPropertyUtilityNode,
    SandboxGetFacingUtilityNode,
    SandboxGetNearbyUtilityNode,
    SandboxGetPositionUtilityNode,
    SandboxIdleUtilityNode,
    SandboxMoveForwardUtilityNode,
    SandboxTurnLeftUtilityNode,
    SandboxTurnRightUtilityNode,
    SandboxTickPrimitiveNode,
    SimpleLLMCallSkillNode,
    StartGraphNode,
    StopGraphNode,
    StringPrimitiveNode,
    StringToListUtilityNode,
    StringTruncUtilityNode,
    StructurePrimitiveNode,
    SubtractIntsUtilityNode,
    TextToSpeechSkillNode,
    TranscribeAudioSkillNode,
    TranscribeFileSkillNode,
    UpsertDocumentUtilityNode,
    ValidateAgainstStructureUtilityNode,
    WorkflowRefNode,
    WriteObjectToDocumentBodyUtilityNode,
    XorControlNode,
)

from .execution_context import ExecutionNodeContext


async def dispatch_execute_node(executor: Any, ctx: ExecutionNodeContext) -> Any:
    """Dispatch a parsed graph step to WorkflowExecutor `_resolve_*` / `_run_*` handlers."""
    overrides = ctx.input_overrides or {}
    om = ctx.output_overrides_map or {}
    if ctx.node_id in om:
        forced = om[ctx.node_id]
        return {
            "status": "ok",
            "output": forced,
            "details": {"resolved_inputs": {}, "forced_output": True},
        }
    stack = ctx.execution_stack or frozenset()
    node = ctx.node
    try:
        if isinstance(node, SandboxTickPrimitiveNode):
            return executor._resolve_sandbox_tick_primitive_node(node, ctx.upstream, overrides)
        if isinstance(node, StringPrimitiveNode):
            return executor._resolve_string_primitive_node(node, ctx.upstream)
        if isinstance(node, ListPrimitiveNode):
            return executor._resolve_list_primitive_node(node, ctx.upstream)
        if isinstance(node, DictionaryPrimitiveNode):
            return executor._resolve_dictionary_primitive_node(node, ctx.edges, ctx.outputs)
        if isinstance(node, BooleanPrimitiveNode):
            return executor._resolve_boolean_primitive_node(node, ctx.upstream)
        if isinstance(node, IntPrimitiveNode):
            return executor._resolve_int_primitive_node(node, ctx.upstream)
        if isinstance(node, DateTimePrimitiveNode):
            return executor._resolve_datetime_primitive_node(node, ctx.upstream)
        if isinstance(node, StructurePrimitiveNode):
            return executor._resolve_structure_primitive_node(node)
        if isinstance(node, DocumentPrimitiveNode):
            return executor._resolve_document_primitive_node(node)
        if isinstance(node, ImagePrimitiveNode):
            return executor._resolve_image_primitive_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, GmailPrimitiveNode):
            return executor._resolve_gmail_primitive_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, StartGraphNode):
            return executor._resolve_start_node(node, overrides)
        if isinstance(node, StopGraphNode):
            return executor._resolve_stop_node(node, ctx.upstream)
        if isinstance(node, SimpleLLMCallSkillNode):
            return await executor._run_simple_llm_call_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, MultimodalLLMCallSkillNode):
            return await executor._run_multimodal_llm_call_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, TextToSpeechSkillNode):
            return await executor._run_text_to_speech_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, TranscribeAudioSkillNode):
            return await executor._run_transcribe_audio_node(
                node,
                ctx.node_id,
                stream_run_id=ctx.stream_run_id,
                for_loop_id=ctx.for_loop_id,
                for_loop_iteration=ctx.for_loop_iteration,
            )
        if isinstance(node, AudioFileInputSkillNode):
            return await executor._run_audio_file_input_node(
                node,
                ctx.node_id,
                stream_run_id=ctx.stream_run_id,
                for_loop_id=ctx.for_loop_id,
                for_loop_iteration=ctx.for_loop_iteration,
            )
        if isinstance(node, TranscribeFileSkillNode):
            return await executor._run_transcribe_file_node(
                node,
                ctx.node_id,
                stream_run_id=ctx.stream_run_id,
                for_loop_id=ctx.for_loop_id,
                for_loop_iteration=ctx.for_loop_iteration,
            )
        if isinstance(node, GmailListMessagesSkillNode):
            return await executor._run_gmail_list_messages_node(
                node,
                ctx.edges,
                ctx.outputs,
                overrides,
                execution_time_zone=ctx.execution_time_zone,
            )
        if isinstance(node, CalendarListEventsSkillNode):
            return await executor._run_calendar_list_events_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, GoogleDocsGetDocumentSkillNode):
            return await executor._run_google_docs_get_document_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, FetchUrlSkillNode):
            return await executor._run_fetch_url_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, CaptureUrlSnapshotSkillNode):
            return await executor._run_capture_url_snapshot_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, ListToStringUtilityNode):
            return executor._resolve_list_to_string_node(node, ctx.upstream)
        if isinstance(node, StringToListUtilityNode):
            return executor._resolve_string_to_list_node(node, ctx.upstream)
        if isinstance(node, IntToStringUtilityNode):
            return executor._resolve_int_to_string_node(node, ctx.upstream)
        if isinstance(node, LenFromListUtilityNode):
            return executor._resolve_len_from_list_node(node, ctx.upstream)
        if isinstance(node, RandomItemFromListUtilityNode):
            return executor._resolve_random_item_from_list_node(node, ctx.upstream)
        if isinstance(node, SandboxGetPositionUtilityNode):
            return executor._resolve_sandbox_get_position_node(node, ctx.upstream)
        if isinstance(node, SandboxGetFacingUtilityNode):
            return executor._resolve_sandbox_get_facing_node(node, ctx.upstream)
        if isinstance(node, SandboxGetNearbyUtilityNode):
            return executor._resolve_sandbox_get_nearby_node(node, ctx.upstream)
        if isinstance(node, SandboxMoveForwardUtilityNode):
            return executor._resolve_sandbox_move_forward_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, SandboxTurnLeftUtilityNode):
            return executor._resolve_sandbox_turn_left_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, SandboxTurnRightUtilityNode):
            return executor._resolve_sandbox_turn_right_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, SandboxIdleUtilityNode):
            return executor._resolve_sandbox_idle_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, ListItemByIndexUtilityNode):
            return executor._resolve_list_item_by_index_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, DictionaryValueByKeyUtilityNode):
            return executor._resolve_dictionary_value_by_key_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, DictionarySetValueByKeyUtilityNode):
            return executor._resolve_dictionary_set_value_by_key_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, ReadDocumentPropertyUtilityNode):
            return executor._resolve_read_document_property_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, LoadDocumentUtilityNode):
            return executor._resolve_load_document_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, UpsertDocumentUtilityNode):
            return executor._resolve_upsert_document_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, ParseDocumentBodyUtilityNode):
            return executor._resolve_parse_document_body_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, HtmlParseBasicUtilityNode):
            return executor._resolve_html_parse_basic_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, GoogleDocsParseDocumentUtilityNode):
            return executor._resolve_google_docs_parse_document_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, WriteObjectToDocumentBodyUtilityNode):
            return executor._resolve_write_object_to_document_body_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, AppendValueToDocumentUtilityNode):
            return executor._resolve_append_value_to_document_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, ValidateAgainstStructureUtilityNode):
            return executor._resolve_validate_against_structure_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, AddToListUtilityNode):
            return executor._resolve_add_to_list_node(
                node,
                ctx.edges,
                ctx.outputs,
                overrides,
                loop_list_carry=ctx.loop_list_carry,
                for_loop_id=ctx.for_loop_id,
            )
        if isinstance(node, PrependTextUtilityNode):
            return executor._resolve_prepend_text_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, StringTruncUtilityNode):
            return executor._resolve_string_trunc_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, MessageUtilityNode):
            return executor._resolve_message_utility_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, AddDaysUtilityNode):
            return executor._resolve_add_days_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, AddIntsUtilityNode):
            return executor._resolve_binary_int_math_node(node, ctx.edges, ctx.outputs, overrides, "add")
        if isinstance(node, SubtractIntsUtilityNode):
            return executor._resolve_binary_int_math_node(node, ctx.edges, ctx.outputs, overrides, "sub")
        if isinstance(node, MultiplyIntsUtilityNode):
            return executor._resolve_binary_int_math_node(node, ctx.edges, ctx.outputs, overrides, "mul")
        if isinstance(node, DivideIntsUtilityNode):
            return executor._resolve_binary_int_math_node(node, ctx.edges, ctx.outputs, overrides, "div")
        if isinstance(node, ModuloIntsUtilityNode):
            return executor._resolve_binary_int_math_node(node, ctx.edges, ctx.outputs, overrides, "mod")
        if isinstance(node, MinIntsUtilityNode):
            return executor._resolve_binary_int_math_node(node, ctx.edges, ctx.outputs, overrides, "min")
        if isinstance(node, MaxIntsUtilityNode):
            return executor._resolve_binary_int_math_node(node, ctx.edges, ctx.outputs, overrides, "max")
        if isinstance(node, BasicConditionalControlNode):
            return executor._resolve_basic_conditional_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, IsControlNode):
            return executor._resolve_is_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, IsEmptyControlNode):
            return executor._resolve_is_empty_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, GtControlNode):
            return executor._resolve_gt_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, LtControlNode):
            return executor._resolve_lt_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, GteControlNode):
            return executor._resolve_gte_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, LteControlNode):
            return executor._resolve_lte_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, AndControlNode):
            return executor._resolve_and_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, OrControlNode):
            return executor._resolve_or_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, XorControlNode):
            return executor._resolve_xor_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, NotControlNode):
            return executor._resolve_not_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, BetweenControlNode):
            return executor._resolve_between_node(node, ctx.edges, ctx.outputs, overrides)
        if isinstance(node, WorkflowRefNode):
            return await executor._resolve_workflow_node(
                node,
                ctx.edges,
                ctx.outputs,
                overrides,
                ctx.workflow,
                stack,
                ctx.execution_time_zone,
                output_overrides_map=ctx.output_overrides_map,
            )

    except Exception as exc:
        logger.error(f"WorkflowExecutor: node {node.id} failed — {exc}")
        return {"status": "error", "error": str(exc)}

    return {"status": "error", "error": f"Unknown node kind for node {node.id}"}
