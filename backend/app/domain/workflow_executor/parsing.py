from typing import Any, Dict, Optional

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
    CaptureUrlSnapshotSkillNode,
    DateTimePrimitiveNode,
    DecisionActionPrimitiveNode,
    DictionaryPrimitiveNode,
    DictionarySetValueByKeyUtilityNode,
    DictionaryValueByKeyUtilityNode,
    DivideIntsUtilityNode,
    DocumentPrimitiveNode,
    FetchUrlSkillNode,
    ForLoopControlNode,
    ForLoopEndControlNode,
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
    SandboxAvailableCellsUtilityNode,
    SandboxBehaviorPrimitiveNode,
    SandboxClosestItemUtilityNode,
    SandboxDecisionIntentUtilityNode,
    SandboxDecisionMoveToUtilityNode,
    SandboxFilterItemsByTypeUtilityNode,
    SandboxFirstFoodWorldOrderUtilityNode,
    SandboxFirstNearbyFoodUtilityNode,
    SandboxIsNearby8UtilityNode,
    SandboxNearestItemByTypeUtilityNode,
    SandboxPetCellUtilityNode,
    SandboxPetEnergyUtilityNode,
    SandboxPetHungerUtilityNode,
    SandboxStarterDecisionUtilityNode,
    SandboxTickItemsUtilityNode,
    SandboxTickPetUtilityNode,
    SandboxTickPrimitiveNode,
    SandboxWorldGridUtilityNode,
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
    TryCatchControlNode,
    UpsertDocumentUtilityNode,
    ValidateAgainstStructureUtilityNode,
    WorkflowRefNode,
    WriteObjectToDocumentBodyUtilityNode,
    XorControlNode,
)


def _coerce_use_now_flag(val: Any) -> bool:
    """Interpret workflow JSON truthiness for DateTime ``use_now`` (bool, int, or common strings)."""
    if isinstance(val, bool):
        return val
    if val is None:
        return False
    if isinstance(val, (int, float)):
        return val == 1
    if isinstance(val, str):
        s = val.strip().lower()
        return s in ("true", "1", "yes", "on")
    return False


def _normalize_raw_datetime_primitive(raw: Dict[str, Any]) -> Dict[str, Any]:
    """
    Canonicalize ``use_now`` into ``data`` (snake_case). Accepts root-level ``use_now`` / ``useNow``
    and ``data.useNow`` so Pydantic does not drop flags stored outside ``data``.
    """
    out = dict(raw)
    raw_data = out.get("data")
    data: Dict[str, Any] = dict(raw_data) if isinstance(raw_data, dict) else {}
    picked: Optional[Any] = None
    for v in (
        data.get("use_now"),
        data.get("useNow"),
        out.get("use_now"),
        out.get("useNow"),
    ):
        if v is not None:
            picked = v
    if picked is not None:
        data["use_now"] = _coerce_use_now_flag(picked)
    data.pop("useNow", None)
    out["data"] = data
    return out


def _parse_node(raw: Dict[str, Any]):
    """
    Parse a raw graph node dict into a typed GraphNode.
    Returns None for editor-only annotation nodes (no log).
    Returns None and logs a warning for unrecognised kinds.
    """
    kind = raw.get("kind")
    if kind == "annotation":
        return None
    if kind == "primitive":
        ptype = raw.get("primitive_type")
        if ptype == "string":
            return StringPrimitiveNode(**raw)
        if ptype == "list":
            return ListPrimitiveNode(**raw)
        if ptype == "dictionary":
            return DictionaryPrimitiveNode(**raw)
        if ptype == "boolean":
            return BooleanPrimitiveNode(**raw)
        if ptype == "int":
            return IntPrimitiveNode(**raw)
        if ptype == "datetime":
            return DateTimePrimitiveNode(**_normalize_raw_datetime_primitive(raw))
        if ptype == "structure":
            return StructurePrimitiveNode(**raw)
        if ptype == "document":
            return DocumentPrimitiveNode(**raw)
        if ptype == "image":
            return ImagePrimitiveNode(**raw)
        if ptype == "gmail":
            return GmailPrimitiveNode(**raw)
        if ptype == "sandbox_behavior":
            return SandboxBehaviorPrimitiveNode(**raw)
        if ptype == "decision_action":
            return DecisionActionPrimitiveNode(**raw)
        if ptype == "sandbox_tick":
            return SandboxTickPrimitiveNode(**raw)
    if kind == "utility" and raw.get("utility_type") == "simple_llm_call":
        normalized = dict(raw)
        normalized["kind"] = "skill"
        normalized["skill_type"] = "simple_llm_call"
        normalized.pop("utility_type", None)
        return SimpleLLMCallSkillNode(**normalized)
    if kind == "skill":
        stype = raw.get("skill_type")
        if stype == "simple_llm_call":
            return SimpleLLMCallSkillNode(**raw)
        if stype == "multimodal_llm":
            return MultimodalLLMCallSkillNode(**raw)
        if stype == "text_to_speech":
            return TextToSpeechSkillNode(**raw)
        if stype == "transcribe_audio":
            return TranscribeAudioSkillNode(**raw)
        if stype == "audio_file_input":
            return AudioFileInputSkillNode(**raw)
        if stype == "transcribe_file":
            return TranscribeFileSkillNode(**raw)
        if stype == "gmail_list_messages":
            return GmailListMessagesSkillNode(**raw)
        if stype == "calendar_list_events":
            return CalendarListEventsSkillNode(**raw)
        if stype == "fetch_url":
            return FetchUrlSkillNode(**raw)
        if stype == "capture_url_snapshot":
            return CaptureUrlSnapshotSkillNode(**raw)
    if kind == "utility":
        utype = raw.get("utility_type")
        if utype == "list_to_string":
            return ListToStringUtilityNode(**raw)
        if utype == "string_to_list":
            return StringToListUtilityNode(**raw)
        if utype == "prepend_text":
            return PrependTextUtilityNode(**raw)
        if utype == "string_trunc":
            return StringTruncUtilityNode(**raw)
        if utype == "message":
            return MessageUtilityNode(**raw)
        if utype == "len_from_list":
            return LenFromListUtilityNode(**raw)
        if utype == "random_item_from_list":
            return RandomItemFromListUtilityNode(**raw)
        if utype == "sandbox_tick_items":
            return SandboxTickItemsUtilityNode(**raw)
        if utype == "sandbox_world_grid":
            return SandboxWorldGridUtilityNode(**raw)
        if utype == "sandbox_available_cells":
            return SandboxAvailableCellsUtilityNode(**raw)
        if utype == "sandbox_tick_pet":
            return SandboxTickPetUtilityNode(**raw)
        if utype == "sandbox_filter_items_by_type":
            return SandboxFilterItemsByTypeUtilityNode(**raw)
        if utype == "sandbox_nearest_item_by_type":
            return SandboxNearestItemByTypeUtilityNode(**raw)
        if utype == "sandbox_closest_item":
            return SandboxClosestItemUtilityNode(**raw)
        if utype == "sandbox_decision_intent":
            return SandboxDecisionIntentUtilityNode(**raw)
        if utype == "sandbox_decision_move_to":
            return SandboxDecisionMoveToUtilityNode(**raw)
        if utype == "sandbox_starter_decision":
            return SandboxStarterDecisionUtilityNode(**raw)
        if utype == "sandbox_pet_hunger":
            return SandboxPetHungerUtilityNode(**raw)
        if utype == "sandbox_pet_energy":
            return SandboxPetEnergyUtilityNode(**raw)
        if utype == "sandbox_pet_cell":
            return SandboxPetCellUtilityNode(**raw)
        if utype == "sandbox_is_nearby8":
            return SandboxIsNearby8UtilityNode(**raw)
        if utype == "sandbox_first_nearby_food":
            return SandboxFirstNearbyFoodUtilityNode(**raw)
        if utype == "sandbox_first_food_world_order":
            return SandboxFirstFoodWorldOrderUtilityNode(**raw)
        if utype == "int_to_string":
            return IntToStringUtilityNode(**raw)
        if utype == "list_item_by_index":
            return ListItemByIndexUtilityNode(**raw)
        if utype == "dictionary_value_by_key":
            return DictionaryValueByKeyUtilityNode(**raw)
        if utype == "dictionary_set_value_by_key":
            return DictionarySetValueByKeyUtilityNode(**raw)
        if utype == "read_document_property":
            return ReadDocumentPropertyUtilityNode(**raw)
        if utype == "load_document":
            return LoadDocumentUtilityNode(**raw)
        if utype == "upsert_document":
            return UpsertDocumentUtilityNode(**raw)
        if utype == "parse_document_body":
            return ParseDocumentBodyUtilityNode(**raw)
        if utype == "html_parse_basic":
            return HtmlParseBasicUtilityNode(**raw)
        if utype == "write_object_to_document_body":
            return WriteObjectToDocumentBodyUtilityNode(**raw)
        if utype == "append_value_to_document":
            return AppendValueToDocumentUtilityNode(**raw)
        if utype == "validate_against_structure":
            return ValidateAgainstStructureUtilityNode(**raw)
        if utype == "add_to_list":
            return AddToListUtilityNode(**raw)
        if utype == "add_days":
            return AddDaysUtilityNode(**raw)
        if utype == "add_ints":
            return AddIntsUtilityNode(**raw)
        if utype == "subtract_ints":
            return SubtractIntsUtilityNode(**raw)
        if utype == "multiply_ints":
            return MultiplyIntsUtilityNode(**raw)
        if utype == "divide_ints":
            return DivideIntsUtilityNode(**raw)
        if utype == "modulo_ints":
            return ModuloIntsUtilityNode(**raw)
        if utype == "min_ints":
            return MinIntsUtilityNode(**raw)
        if utype == "max_ints":
            return MaxIntsUtilityNode(**raw)
    if kind == "start":
        return StartGraphNode(**raw)
    if kind == "stop":
        return StopGraphNode(**raw)
    if kind == "workflow":
        return WorkflowRefNode(**raw)
    if kind == "control":
        ctype = raw.get("control_type")
        if ctype == "basic_conditional":
            return BasicConditionalControlNode(**raw)
        if ctype == "is":
            return IsControlNode(**raw)
        if ctype == "is_empty":
            return IsEmptyControlNode(**raw)
        if ctype == "gt":
            return GtControlNode(**raw)
        if ctype == "lt":
            return LtControlNode(**raw)
        if ctype == "gte":
            return GteControlNode(**raw)
        if ctype == "lte":
            return LteControlNode(**raw)
        if ctype == "and":
            return AndControlNode(**raw)
        if ctype == "or":
            return OrControlNode(**raw)
        if ctype == "xor":
            return XorControlNode(**raw)
        if ctype == "not":
            return NotControlNode(**raw)
        if ctype == "between":
            return BetweenControlNode(**raw)
        if ctype == "try_catch":
            return TryCatchControlNode(**raw)
        if ctype == "for_loop":
            return ForLoopControlNode(**raw)
        if ctype == "for_loop_end":
            return ForLoopEndControlNode(**raw)
    logger.warning(f"WorkflowExecutor: unrecognised node kind '{kind}' — skipping.")
    return None
