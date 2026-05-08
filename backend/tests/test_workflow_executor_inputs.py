"""Tests for workflow executor input wiring helpers."""

from app.domain.schemas import (
    BooleanNodeOutput,
    DictionaryNodeOutput,
    DocumentNodeOutput,
    GmailNodeOutput,
    IntNodeOutput,
    ListNodeOutput,
    ResponseNodeOutput,
    StopNodeOutput,
    StringNodeOutput,
    StructureNodeOutput,
)
from app.domain.workflow_executor.inputs import node_output_to_input_override_value


def test_node_output_to_input_override_value_preserves_list_and_dict():
    assert node_output_to_input_override_value(ListNodeOutput(node_id="a", data=[1, 2, {"x": 3}])) == [
        1,
        2,
        {"x": 3},
    ]
    assert node_output_to_input_override_value(DictionaryNodeOutput(node_id="b", data={"k": [1, 2]})) == {"k": [1, 2]}


def test_node_output_to_input_override_value_primitives():
    assert node_output_to_input_override_value(StringNodeOutput(node_id="s", text="hi")) == "hi"
    assert node_output_to_input_override_value(ResponseNodeOutput(node_id="r", text="x")) == "x"
    assert node_output_to_input_override_value(StopNodeOutput(node_id="t", text="y")) == "y"
    assert node_output_to_input_override_value(IntNodeOutput(node_id="i", value=7)) == 7
    assert node_output_to_input_override_value(BooleanNodeOutput(node_id="b", value=True)) is True


def test_node_output_to_input_override_value_structure():
    assert node_output_to_input_override_value(StructureNodeOutput(node_id="st", schema_dict={"a": 1})) == {"a": 1}


def test_node_output_to_input_override_value_document():
    assert node_output_to_input_override_value(
        DocumentNodeOutput(
            node_id="d1",
            document_id="550e8400-e29b-41d4-a716-446655440000",
            name="N",
            description="D",
            markdown="# Hi",
        )
    ) == {
        "id": "550e8400-e29b-41d4-a716-446655440000",
        "name": "N",
        "description": "D",
        "body": "# Hi",
    }


def test_node_output_to_input_override_value_gmail():
    out = GmailNodeOutput(
        node_id="g1",
        id="msg-123",
        threadId="thread-456",
        subject="Hello",
        snippet="Preview text",
    )
    result = node_output_to_input_override_value(out)
    assert isinstance(result, dict)
    assert result["id"] == "msg-123"
    assert result["threadId"] == "thread-456"
    assert result["subject"] == "Hello"
    assert result["snippet"] == "Preview text"


def test_node_output_to_input_override_value_gmail_minimal():
    out = GmailNodeOutput(node_id="g2")
    result = node_output_to_input_override_value(out)
    assert isinstance(result, dict)
    assert result["kind"] == "gmail"
