"""Tests for workflow executor input wiring helpers."""

from app.domain.schemas import (
    BooleanNodeOutput,
    ConditionalNodeOutput,
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
from app.domain.workflow_executor.inputs import (
    _branch_control_passthrough_slot,
    node_output_to_input_override_value,
    passthrough_value_to_node_output,
)


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


def test_passthrough_value_to_node_output_types():
    assert passthrough_value_to_node_output("n1", [1, 2]).data == [1, 2]
    assert passthrough_value_to_node_output("n2", {"a": 1}).data == {"a": 1}
    assert passthrough_value_to_node_output("n3", True).value is True
    assert passthrough_value_to_node_output("n4", 9).value == 9
    assert passthrough_value_to_node_output("n5", "hi").text == "hi"


def test_branch_control_passthrough_slot_active_branch_data_handle():
    out = ConditionalNodeOutput(node_id="c1", branch="false", passthrough_value=[1, 2, 3])
    slot = _branch_control_passthrough_slot(out, "false", "list")
    assert isinstance(slot, ListNodeOutput)
    assert slot.data == [1, 2, 3]


def test_branch_control_passthrough_slot_skips_trigger_edges():
    out = ConditionalNodeOutput(node_id="c1", branch="false", passthrough_value=[1, 2, 3])
    assert _branch_control_passthrough_slot(out, "false", "trigger") is None
    assert _branch_control_passthrough_slot(out, "false", None) is None
    assert _branch_control_passthrough_slot(out, "true", "list") is None
