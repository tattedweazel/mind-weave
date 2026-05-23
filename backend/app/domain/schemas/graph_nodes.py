"""Graph node and edge models (WorkflowDefinition.graph)."""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, Field


class StringPrimitiveNode(BaseModel):
    """A graph node providing a static string input."""

    id: str
    kind: Literal["primitive"] = "primitive"
    primitive_type: Literal["string"] = "string"
    label: str
    data: Dict[str, str] = Field(default_factory=dict)  # {"text": "..."}
    position: Dict[str, float] = Field(default_factory=dict)


class SimpleLLMCallSkillNode(BaseModel):
    """A skill node that calls the LLM with persona system prompt and user_prompt as required inputs."""

    id: str
    kind: Literal["skill"] = "skill"
    skill_type: Literal["simple_llm_call"] = "simple_llm_call"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs, persona_id, structure_id, ...
    position: Dict[str, float] = Field(default_factory=dict)


class TextToSpeechSkillNode(BaseModel):
    """Synthesize speech via the local TTS bridge using a registry-backed model."""

    id: str
    kind: Literal["skill"] = "skill"
    skill_type: Literal["text_to_speech"] = "text_to_speech"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # tts_model_id, optional voice_sample_id (clone ref), optional tts_playback_when / auto_play_tts_on_node_end (editor-only), engine override, tts_options, required_inputs (text)
    position: Dict[str, float] = Field(default_factory=dict)


class TranscribeAudioSkillNode(BaseModel):
    """Record audio in the browser at run time and transcribe via the local STT bridge (faster-whisper)."""

    id: str
    kind: Literal["skill"] = "skill"
    skill_type: Literal["transcribe_audio"] = "transcribe_audio"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # optional language, task (transcribe|translate), optional model (reserved for future bridge support)
    position: Dict[str, float] = Field(default_factory=dict)


class AudioFileInputSkillNode(BaseModel):
    """Select an audio file and transcribe it via the local STT bridge."""

    id: str
    kind: Literal["skill"] = "skill"
    skill_type: Literal["audio_file_input"] = "audio_file_input"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # optional audio_artifact_id, language, task (transcribe|translate), optional model (reserved)
    position: Dict[str, float] = Field(default_factory=dict)


class TranscribeFileSkillNode(BaseModel):
    """Provider-abstracted file transcription emitting a normalized Transcript Primitive.

    Unlike `audio_file_input` (which emits a plain `StringNodeOutput`), this skill emits a
    `DictionaryNodeOutput` carrying the full TranscriptPrimitive shape, with provider
    selection (`local_whisper`, `assemblyai`, future providers) and richer options
    (diarization, prompt biasing, word timestamps).
    """

    id: str
    kind: Literal["skill"] = "skill"
    skill_type: Literal["transcribe_file"] = "transcribe_file"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # provider (default local_whisper), provider_model_id, audio_artifact_id, language, task, prompt, diarization_enabled, include_word_timestamps
    position: Dict[str, float] = Field(default_factory=dict)


class GmailListMessagesSkillNode(BaseModel):
    """Read-only Gmail: list message ids; optional after/before (RFC3339), unread_only, Gmail search query, and category filters (composed into API q)."""

    id: str
    kind: Literal["skill"] = "skill"
    skill_type: Literal["gmail_list_messages"] = "gmail_list_messages"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # google_connection_id (legacy, ignored at runtime), max_results, after, before, query, ...
    position: Dict[str, float] = Field(default_factory=dict)


class CalendarListEventsSkillNode(BaseModel):
    """Read-only Calendar: list events in a time window. Requires a workflow Google connection."""

    id: str
    kind: Literal["skill"] = "skill"
    skill_type: Literal["calendar_list_events"] = "calendar_list_events"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # google_connection_id (legacy, ignored at runtime), calendar_id, required_inputs (time_min, time_max)
    position: Dict[str, float] = Field(default_factory=dict)


class GoogleDocsGetDocumentSkillNode(BaseModel):
    """Read-only Google Docs: fetch document structure and inline images via workflow OAuth."""

    id: str
    kind: Literal["skill"] = "skill"
    skill_type: Literal["google_docs_get_document"] = "google_docs_get_document"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # google_connection_id (legacy, ignored at runtime), document_url_or_id, include_tabs_content, required_inputs
    position: Dict[str, float] = Field(default_factory=dict)


class FetchUrlSkillNode(BaseModel):
    """HTTP fetch of a URL: raw text body and response metadata. Optional per-user response cache."""

    id: str
    kind: Literal["skill"] = "skill"
    skill_type: Literal["fetch_url"] = "fetch_url"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # url, method, headers, timeout_ms, cache_policy (default|refresh|bypass), required_inputs (optional url)
    position: Dict[str, float] = Field(default_factory=dict)


class CaptureUrlSnapshotSkillNode(BaseModel):
    """Render a URL in headless Chromium and store a PNG artifact; optional per-user cache of captures."""

    id: str
    kind: Literal["skill"] = "skill"
    skill_type: Literal["capture_url_snapshot"] = "capture_url_snapshot"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # url, full_page, viewport_width/height, wait_until, timeout_ms, cache_policy, required_inputs (optional url)
    position: Dict[str, float] = Field(default_factory=dict)


class MultimodalLLMCallSkillNode(BaseModel):
    """Vision LLM step: persona system prompt, user prompt, and image artifact refs (e.g. url_snapshot_artifacts)."""

    id: str
    kind: Literal["skill"] = "skill"
    skill_type: Literal["multimodal_llm"] = "multimodal_llm"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # required_inputs (user_prompt, images), persona_id, optional model override, structure_id, ...
    position: Dict[str, float] = Field(default_factory=dict)


class ListToStringUtilityNode(BaseModel):
    """A utility node that converts a list input to its string representation for passing to prompts."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["list_to_string"] = "list_to_string"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class StringToListUtilityNode(BaseModel):
    """A utility node that parses a string (JSON array) into a list output."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["string_to_list"] = "string_to_list"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class PrependTextUtilityNode(BaseModel):
    """A utility node that prepends text to a target string, with optional blank line between."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["prepend_text"] = "prepend_text"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs, add_additional_line
    position: Dict[str, float] = Field(default_factory=dict)


class StringTruncUtilityNode(BaseModel):
    """Substring by inclusive ``end_index`` (0-based); ``end_index`` of ``-1`` means through end of string."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["string_trunc"] = "string_trunc"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs: target_string, start_index, end_index
    position: Dict[str, float] = Field(default_factory=dict)


class MessageUtilityNode(BaseModel):
    """Display a string to the user at run time (client surfaces ``details.user_message``); no data output."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["message"] = "message"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs: message (string)
    position: Dict[str, float] = Field(default_factory=dict)


class LenFromListUtilityNode(BaseModel):
    """A utility node that returns the length of a list input."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["len_from_list"] = "len_from_list"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class RandomItemFromListUtilityNode(BaseModel):
    """A utility node that returns one uniformly random element from a list input (cryptographic index choice)."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["random_item_from_list"] = "random_item_from_list"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class SandboxGetPositionUtilityNode(BaseModel):
    """Focused creature ``position`` as ``{x, y}`` from a wired ``SandboxTickInput`` dictionary."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["sandbox_get_position"] = "sandbox_get_position"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class SandboxGetFacingUtilityNode(BaseModel):
    """Focused creature ``facing`` (``N`` | ``E`` | ``S`` | ``W``) from a wired tick dictionary."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["sandbox_get_facing"] = "sandbox_get_facing"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class SandboxGetNearbyUtilityNode(BaseModel):
    """Eight neighbors clockwise from facing; each entry is ``{x, y, kind}``."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["sandbox_get_nearby"] = "sandbox_get_nearby"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class SandboxMoveForwardUtilityNode(BaseModel):
    """Emit a validated ``move_forward`` ``DecisionIntent`` dictionary for Stop."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["sandbox_move_forward"] = "sandbox_move_forward"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class SandboxTurnLeftUtilityNode(BaseModel):
    """Emit a validated ``turn_left`` ``DecisionIntent`` dictionary for Stop."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["sandbox_turn_left"] = "sandbox_turn_left"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class SandboxTurnRightUtilityNode(BaseModel):
    """Emit a validated ``turn_right`` ``DecisionIntent`` dictionary for Stop."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["sandbox_turn_right"] = "sandbox_turn_right"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class SandboxIdleUtilityNode(BaseModel):
    """Emit a validated ``idle`` ``DecisionIntent`` dictionary for Stop."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["sandbox_idle"] = "sandbox_idle"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class SandboxPickUpItemUtilityNode(BaseModel):
    """Emit a validated ``pick_up_item`` ``DecisionIntent`` dictionary for Stop."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["sandbox_pick_up_item"] = "sandbox_pick_up_item"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class SandboxPlaceItemUtilityNode(BaseModel):
    """Emit a validated ``place_item`` ``DecisionIntent`` dictionary for Stop."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["sandbox_place_item"] = "sandbox_place_item"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class SandboxGetInventoryUtilityNode(BaseModel):
    """Emit focused creature inventory as a list of dictionaries."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["sandbox_get_inventory"] = "sandbox_get_inventory"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class SandboxPromptUserActionUtilityNode(BaseModel):
    """Emit a ``DecisionIntent`` from a simulation user action (``sandbox_user_action`` run override)."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["sandbox_prompt_user_action"] = "sandbox_prompt_user_action"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class IntToStringUtilityNode(BaseModel):
    """A utility node that converts an integer input to its decimal string form."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["int_to_string"] = "int_to_string"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class ListItemByIndexUtilityNode(BaseModel):
    """A utility node that returns the item at a given index in a list."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["list_item_by_index"] = "list_item_by_index"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs: index (int), list (list)
    position: Dict[str, float] = Field(default_factory=dict)


class DictionaryValueByKeyUtilityNode(BaseModel):
    """
    A utility node that reads a value by key from a dictionary with a declared output type.

    Optional: ``data.fallback_value`` (JSON), a non-``None`` value on the ``required_inputs`` entry for key
    ``fallback`` (``any``), and/or an optional wire to the ``fallback`` handle. Resolution order: input
    override, first wired upstream with output, then ``data.fallback_value``, then ``required_inputs.fallback.value``.
    When the key is missing, null, or lookup raises ``KeyError``, a configured fallback is used. Wrong type
    at an existing key still errors (fallback is not used). A wire that has no upstream output yet falls
    through to the static sources.
    """

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["dictionary_value_by_key"] = "dictionary_value_by_key"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # see class docstring
    position: Dict[str, float] = Field(default_factory=dict)


class DictionarySetValueByKeyUtilityNode(BaseModel):
    """Shallow-copy a dictionary and assign a top-level key to an arbitrary value (output is a dictionary)."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["dictionary_set_value_by_key"] = "dictionary_set_value_by_key"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # required_inputs: dictionary, key (string), value (any)
    position: Dict[str, float] = Field(default_factory=dict)


class ReadDocumentPropertyUtilityNode(BaseModel):
    """Read a property from a Document primitive output by name (e.g. body, name)."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["read_document_property"] = "read_document_property"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # required_inputs: document, target_property; output_value_type
    position: Dict[str, float] = Field(default_factory=dict)


class LoadDocumentUtilityNode(BaseModel):
    """Load a Document at runtime by id or by name (exactly one)."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["load_document"] = "load_document"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # required_inputs: document_id?, document_name?
    position: Dict[str, float] = Field(default_factory=dict)


class UpsertDocumentUtilityNode(BaseModel):
    """Create or update a Document (replace, append, or merge_json body)."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["upsert_document"] = "upsert_document"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # required_inputs: name, content; optional existing_document_id; write_mode
    position: Dict[str, float] = Field(default_factory=dict)


class ParseDocumentBodyUtilityNode(BaseModel):
    """Parse document body text as JSON into structured output."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["parse_document_body"] = "parse_document_body"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # required_inputs: document
    position: Dict[str, float] = Field(default_factory=dict)


class HtmlParseBasicUtilityNode(BaseModel):
    """Parse raw HTML into title, text blocks, and links (structural, no main-content heuristics).

    Run output dictionary includes ``text_blocks`` as a list of ``{tag, text}`` per emitted element.
    """

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["html_parse_basic"] = "html_parse_basic"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # required_inputs: html; optional: granularity (default|list_items|articles), content_root_css
    position: Dict[str, float] = Field(default_factory=dict)


class GoogleDocsParseDocumentUtilityNode(BaseModel):
    """Parse curated Google Docs document_payload into generic chunks for downstream steps."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["google_docs_parse_document"] = "google_docs_parse_document"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # required_inputs: document; chunk_strategy (structure|tab|flat), max_chunk_text_chars
    position: Dict[str, float] = Field(default_factory=dict)


class WriteObjectToDocumentBodyUtilityNode(BaseModel):
    """Serialize a dict or list to deterministic JSON text for document body."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["write_object_to_document_body"] = "write_object_to_document_body"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # required_inputs: value
    position: Dict[str, float] = Field(default_factory=dict)


class AppendValueToDocumentUtilityNode(BaseModel):
    """Append serialized value to document body text (non-persisting)."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["append_value_to_document"] = "append_value_to_document"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # required_inputs: document, value
    position: Dict[str, float] = Field(default_factory=dict)


class ValidateAgainstStructureUtilityNode(BaseModel):
    """Validate a value against a Structure JSON Schema."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["validate_against_structure"] = "validate_against_structure"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # structure_id optional; required_inputs: value, structure?
    position: Dict[str, float] = Field(default_factory=dict)


class AddToListUtilityNode(BaseModel):
    """Append a value to a list. In a For loop body, list state carries across iterations."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["add_to_list"] = "add_to_list"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # required_inputs: list (list), value (any)
    position: Dict[str, float] = Field(default_factory=dict)


class AddIntsUtilityNode(BaseModel):
    """Binary int utility: input_a + input_b → IntNodeOutput."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["add_ints"] = "add_ints"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs: input_a, input_b (int)
    position: Dict[str, float] = Field(default_factory=dict)


class AddDaysUtilityNode(BaseModel):
    """Shift an RFC3339 instant by a signed whole-day delta → DateTimeNodeOutput."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["add_days"] = "add_days"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs: input (datetime), days (int)
    position: Dict[str, float] = Field(default_factory=dict)


class SubtractIntsUtilityNode(BaseModel):
    """Binary int utility: input_a - input_b → IntNodeOutput."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["subtract_ints"] = "subtract_ints"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class MultiplyIntsUtilityNode(BaseModel):
    """Binary int utility: input_a * input_b → IntNodeOutput."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["multiply_ints"] = "multiply_ints"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class DivideIntsUtilityNode(BaseModel):
    """Binary int utility: int(input_a / input_b) (truncation toward zero); divisor 0 → error."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["divide_ints"] = "divide_ints"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class ModuloIntsUtilityNode(BaseModel):
    """Binary int utility: input_a % input_b; divisor 0 → error."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["modulo_ints"] = "modulo_ints"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class MinIntsUtilityNode(BaseModel):
    """Binary int utility: min(input_a, input_b) → IntNodeOutput."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["min_ints"] = "min_ints"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class MaxIntsUtilityNode(BaseModel):
    """Binary int utility: max(input_a, input_b) → IntNodeOutput."""

    id: str
    kind: Literal["utility"] = "utility"
    utility_type: Literal["max_ints"] = "max_ints"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class ListPrimitiveNode(BaseModel):
    """A graph node providing a static python List input."""

    id: str
    kind: Literal["primitive"] = "primitive"
    primitive_type: Literal["list"] = "list"
    label: str
    data: List[Any] = Field(default_factory=list)
    position: Dict[str, float] = Field(default_factory=dict)


class DictionaryPrimitiveNode(BaseModel):
    """A graph node providing a static python Dictionary input."""

    id: str
    kind: Literal["primitive"] = "primitive"
    primitive_type: Literal["dictionary"] = "dictionary"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class BooleanPrimitiveNode(BaseModel):
    """A graph node providing a static boolean input."""

    id: str
    kind: Literal["primitive"] = "primitive"
    primitive_type: Literal["boolean"] = "boolean"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # {"value": True/False}
    position: Dict[str, float] = Field(default_factory=dict)


class IntPrimitiveNode(BaseModel):
    """A graph node providing a static integer input."""

    id: str
    kind: Literal["primitive"] = "primitive"
    primitive_type: Literal["int"] = "int"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # {"value": 0}
    position: Dict[str, float] = Field(default_factory=dict)


class DateTimePrimitiveNode(BaseModel):
    """A graph node providing a static RFC3339 datetime (instant) or wired upstream datetime/string.

    ``data`` may include ``iso`` (RFC3339 string) and optional ``use_now`` (bool). When there is no
    upstream edge, ``use_now`` true emits ``datetime.now(UTC)`` normalized like ``iso``; an upstream
    wire still takes precedence over ``use_now``.
    """

    id: str
    kind: Literal["primitive"] = "primitive"
    primitive_type: Literal["datetime"] = "datetime"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # {"iso": "..." | null, optional "use_now": bool}
    position: Dict[str, float] = Field(default_factory=dict)


class StructurePrimitiveNode(BaseModel):
    """A graph node providing a Structure (JSON schema) for structured LLM outputs."""

    id: str
    kind: Literal["primitive"] = "primitive"
    primitive_type: Literal["structure"] = "structure"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # {"structure_id": "uuid"}
    position: Dict[str, float] = Field(default_factory=dict)


class DocumentPrimitiveNode(BaseModel):
    """A graph node referencing a stored Document (body text and metadata)."""

    id: str
    kind: Literal["primitive"] = "primitive"
    primitive_type: Literal["document"] = "document"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # {"document_id": "uuid"}
    position: Dict[str, float] = Field(default_factory=dict)


class ImagePrimitiveNode(BaseModel):
    """Holds a user-owned ``url_snapshot_artifacts`` ref; emits normalized image metadata (no transforms)."""

    id: str
    kind: Literal["primitive"] = "primitive"
    primitive_type: Literal["image"] = "image"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # optional artifact_id (after upload), required_inputs (wired image)
    position: Dict[str, float] = Field(default_factory=dict)


class GmailPrimitiveNode(BaseModel):
    """A graph node holding one curated Gmail message object (static ``message`` in data and/or wired input)."""

    id: str
    kind: Literal["primitive"] = "primitive"
    primitive_type: Literal["gmail"] = "gmail"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # message (dict), optional required_inputs for wired gmail
    position: Dict[str, float] = Field(default_factory=dict)


class SandboxTickPrimitiveNode(BaseModel):
    """Emits the current ``SandboxTickInput`` as a dictionary (fan-out from run overrides or wired Start/tick)."""

    id: str
    kind: Literal["primitive"] = "primitive"
    primitive_type: Literal["sandbox_tick"] = "sandbox_tick"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class StartGraphNode(BaseModel):
    """The entry point for a workflow execution. data.required_inputs defines wireable slots."""

    id: str
    kind: Literal["start"] = "start"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs or legacy text
    position: Dict[str, float] = Field(default_factory=dict)


class StopGraphNode(BaseModel):
    """The exit point for a workflow execution. data.required_outputs defines expected output type(s).

    When a graph has multiple Stop nodes, ``data.stop_priority`` (int, default 0) breaks ties for
    which Stop defines the sandbox ``DecisionIntent``: higher priority wins; equal priority uses
    execution step order (later first), then node id.
    """

    id: str
    kind: Literal["stop"] = "stop"
    label: str
    data: Dict[str, Any] = Field(default_factory=lambda: {"required_outputs": [{"key": "output", "type": "string"}]})
    position: Dict[str, float] = Field(default_factory=dict)


class WorkflowRefNode(BaseModel):
    """A graph node that executes a referenced sub-workflow. Output is the sub-workflow's Stop node text."""

    id: str
    kind: Literal["workflow"] = "workflow"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # workflow_id (required)
    position: Dict[str, float] = Field(default_factory=dict)


class BasicConditionalControlNode(BaseModel):
    """A control node that evaluates a condition and triggers either the True or False output branch."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["basic_conditional"] = "basic_conditional"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs (condition slot), optional condition
    position: Dict[str, float] = Field(default_factory=dict)


class IsControlNode(BaseModel):
    """A control node that compares input_a and input_b for equality and triggers True or False branch."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["is"] = "is"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs (input_a, input_b)
    position: Dict[str, float] = Field(default_factory=dict)


class IsEmptyControlNode(BaseModel):
    """A control node that branches True when the wired value is an empty list or empty dict."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["is_empty"] = "is_empty"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs (value)
    position: Dict[str, float] = Field(default_factory=dict)


class GtControlNode(BaseModel):
    """A control node that checks input_a > input_b and triggers True or False branch."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["gt"] = "gt"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class LtControlNode(BaseModel):
    """A control node that checks input_a < input_b and triggers True or False branch."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["lt"] = "lt"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class GteControlNode(BaseModel):
    """A control node that checks input_a >= input_b and triggers True or False branch."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["gte"] = "gte"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class LteControlNode(BaseModel):
    """A control node that checks input_a <= input_b and triggers True or False branch."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["lte"] = "lte"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class AndControlNode(BaseModel):
    """A control node that outputs True when both input_a and input_b are true."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["and"] = "and"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class OrControlNode(BaseModel):
    """A control node that outputs True when either input_a or input_b is true."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["or"] = "or"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class XorControlNode(BaseModel):
    """A control node that outputs True when exactly one of input_a or input_b is true."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["xor"] = "xor"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class NotControlNode(BaseModel):
    """A control node that outputs the logical NOT of a single boolean input."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["not"] = "not"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs: input (boolean)
    position: Dict[str, float] = Field(default_factory=dict)


class BetweenControlNode(BaseModel):
    """A control node: true branch when low <= value <= high (inclusive); low > high → error."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["between"] = "between"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)  # required_inputs: low, value, high (int)
    position: Dict[str, float] = Field(default_factory=dict)


class ForLoopControlNode(BaseModel):
    """A control node that iterates over a list and runs its body subgraph once per item."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["for_loop"] = "for_loop"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # required_inputs: list on key "input"; parallel_iterations (bool, legacy parallel);
    # iteration_mode: sequential | parallel | batched; batch_size; continue_on_error; max_iterations
    position: Dict[str, float] = Field(default_factory=dict)


class TryCatchControlNode(BaseModel):
    """Runs try subgraph; structured failure triggers catch branch and envelope output."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["try_catch"] = "try_catch"
    label: str
    data: Dict[str, Any] = Field(default_factory=dict)
    position: Dict[str, float] = Field(default_factory=dict)


class ForLoopEndControlNode(BaseModel):
    """Runs once after its paired For Loop finishes; aggregates named exports into one dictionary output."""

    id: str
    kind: Literal["control"] = "control"
    control_type: Literal["for_loop_end"] = "for_loop_end"
    label: str
    data: Dict[str, Any] = Field(
        default_factory=dict,
    )  # for_loop_id: str (paired For Loop node id); optional exports: list[str] for UI handles
    position: Dict[str, float] = Field(default_factory=dict)


# Discriminated union for all graph node kinds.
GraphNode = Union[
    StringPrimitiveNode,
    ListPrimitiveNode,
    DictionaryPrimitiveNode,
    BooleanPrimitiveNode,
    IntPrimitiveNode,
    DateTimePrimitiveNode,
    StructurePrimitiveNode,
    DocumentPrimitiveNode,
    ImagePrimitiveNode,
    GmailPrimitiveNode,
    SandboxTickPrimitiveNode,
    SimpleLLMCallSkillNode,
    MultimodalLLMCallSkillNode,
    TextToSpeechSkillNode,
    TranscribeAudioSkillNode,
    AudioFileInputSkillNode,
    TranscribeFileSkillNode,
    GmailListMessagesSkillNode,
    CalendarListEventsSkillNode,
    GoogleDocsGetDocumentSkillNode,
    FetchUrlSkillNode,
    CaptureUrlSnapshotSkillNode,
    ListToStringUtilityNode,
    StringToListUtilityNode,
    PrependTextUtilityNode,
    StringTruncUtilityNode,
    MessageUtilityNode,
    LenFromListUtilityNode,
    RandomItemFromListUtilityNode,
    SandboxGetPositionUtilityNode,
    SandboxGetFacingUtilityNode,
    SandboxGetNearbyUtilityNode,
    SandboxMoveForwardUtilityNode,
    SandboxTurnLeftUtilityNode,
    SandboxTurnRightUtilityNode,
    SandboxIdleUtilityNode,
    SandboxPickUpItemUtilityNode,
    SandboxPlaceItemUtilityNode,
    SandboxGetInventoryUtilityNode,
    SandboxPromptUserActionUtilityNode,
    IntToStringUtilityNode,
    ListItemByIndexUtilityNode,
    DictionaryValueByKeyUtilityNode,
    DictionarySetValueByKeyUtilityNode,
    ReadDocumentPropertyUtilityNode,
    LoadDocumentUtilityNode,
    UpsertDocumentUtilityNode,
    ParseDocumentBodyUtilityNode,
    HtmlParseBasicUtilityNode,
    GoogleDocsParseDocumentUtilityNode,
    WriteObjectToDocumentBodyUtilityNode,
    AppendValueToDocumentUtilityNode,
    ValidateAgainstStructureUtilityNode,
    AddToListUtilityNode,
    AddDaysUtilityNode,
    AddIntsUtilityNode,
    SubtractIntsUtilityNode,
    MultiplyIntsUtilityNode,
    DivideIntsUtilityNode,
    ModuloIntsUtilityNode,
    MinIntsUtilityNode,
    MaxIntsUtilityNode,
    BasicConditionalControlNode,
    IsControlNode,
    IsEmptyControlNode,
    GtControlNode,
    LtControlNode,
    GteControlNode,
    LteControlNode,
    AndControlNode,
    OrControlNode,
    XorControlNode,
    NotControlNode,
    BetweenControlNode,
    ForLoopControlNode,
    ForLoopEndControlNode,
    TryCatchControlNode,
    StartGraphNode,
    StopGraphNode,
    WorkflowRefNode,
]


class GraphEdge(BaseModel):
    """A directed edge between two graph nodes."""

    source: str  # ID of the source node
    target: str  # ID of the target node
    source_handle: Optional[str] = None  # required for multi-output nodes (Start)
    target_handle: Optional[str] = None  # for future multi-input nodes
