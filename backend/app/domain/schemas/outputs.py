"""Workflow node output models."""

from typing import Any, Dict, List, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field


class NodeOutput(BaseModel):
    """Base type for all workflow node outputs."""

    node_id: str  # ID of the graph node that produced this output


class StringNodeOutput(NodeOutput):
    """Output from a String Value node."""

    kind: Literal["string"] = "string"
    text: str


class ResponseNodeOutput(NodeOutput):
    """Output from Simple LLM Call skill node."""

    kind: Literal["response"] = "response"
    text: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class ListNodeOutput(NodeOutput):
    """Output from a List Value node."""

    kind: Literal["list"] = "list"
    data: List[Any] = Field(default_factory=list)


class DictionaryNodeOutput(NodeOutput):
    """Output from a Dictionary Value node."""

    kind: Literal["dictionary"] = "dictionary"
    data: Dict[str, Any] = Field(default_factory=dict)


class StartNodeOutput(NodeOutput):
    """Output from a Start node. outputs keyed by input key; text for backward compat."""

    kind: Literal["start"] = "start"
    outputs: Dict[str, Any] = Field(default_factory=dict)  # key -> value per slot
    text: str = ""  # concatenation of string outputs for Steps that expect .text


class StopNodeOutput(NodeOutput):
    """Output from a Stop node — wraps all final upstream outputs."""

    kind: Literal["stop"] = "stop"
    text: str


class StructureNodeOutput(NodeOutput):
    """Output from a Structure primitive — carries parsed JSON schema for structured outputs."""

    kind: Literal["structure"] = "structure"
    schema_dict: Dict[str, Any] = Field(default_factory=dict)  # avoids shadowing NodeOutput.schema


class DocumentNodeOutput(NodeOutput):
    """Output from a Document primitive — carries stored body text (`markdown` wire field) and metadata."""

    kind: Literal["document"] = "document"
    document_id: str
    name: str
    description: str
    markdown: str


class ConditionalNodeOutput(NodeOutput):
    """Output from a Basic Conditional control node — indicates which branch was taken."""

    kind: Literal["conditional"] = "conditional"
    branch: Literal["true", "false"]


class BooleanNodeOutput(NodeOutput):
    """Output from a Boolean Value node."""

    kind: Literal["boolean"] = "boolean"
    value: bool


class IntNodeOutput(NodeOutput):
    """Output from an Int Value node or Len from List utility."""

    kind: Literal["int"] = "int"
    value: int


class DateTimeNodeOutput(NodeOutput):
    """Output from a DateTime primitive — RFC3339 instant string."""

    kind: Literal["datetime"] = "datetime"
    iso: str


class AudioNodeOutput(NodeOutput):
    """Output from Text-to-Speech — WAV (or compatible) as base64 for JSON/stream transport."""

    kind: Literal["audio"] = "audio"
    mime_type: str = "audio/wav"
    audio_base64: str


class GmailNodeOutput(NodeOutput):
    """Output from a Gmail primitive or typed Gmail message — curated fields only (no raw HTML)."""

    model_config = ConfigDict(extra="ignore", populate_by_name=True)

    kind: Literal["gmail"] = "gmail"
    id: Optional[str] = None
    threadId: Optional[str] = None
    internalDate: Optional[str] = None
    snippet: Optional[str] = None
    labelIds: List[str] = Field(default_factory=list)
    subject: Optional[str] = None
    from_: Optional[str] = Field(default=None, alias="from")
    to: Optional[str] = None
    date: Optional[str] = None
    body_text: Optional[str] = None
    body_truncated: Optional[bool] = None
    fetch_error: Optional[str] = None


def gmail_dict_to_node_output(node_id: str, data: dict[str, Any]) -> GmailNodeOutput:
    """Build GmailNodeOutput from a workflow-facing message dict (e.g. curated list item)."""
    merged: dict[str, Any] = {"node_id": node_id, **dict(data)}
    return GmailNodeOutput.model_validate(merged)


# Discriminated union — use this type anywhere a node output is consumed.
NodeOutputUnion = Union[
    StringNodeOutput,
    ResponseNodeOutput,
    ListNodeOutput,
    DictionaryNodeOutput,
    StructureNodeOutput,
    DocumentNodeOutput,
    AudioNodeOutput,
    GmailNodeOutput,
    StartNodeOutput,
    StopNodeOutput,
    ConditionalNodeOutput,
    BooleanNodeOutput,
    IntNodeOutput,
    DateTimeNodeOutput,
]
