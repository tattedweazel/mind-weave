"""Unit tests for Stop output coercion and multi-upstream resolution (list + Gmail envelope)."""

import json
import uuid
from unittest.mock import MagicMock

from app.domain.schemas.graph_nodes import StopGraphNode
from app.domain.schemas.outputs import AudioNodeOutput, DictionaryNodeOutput, ListNodeOutput, StopNodeOutput
from app.domain.workflow_executor.executor import WorkflowExecutor, coerce_stop_output


def test_coerce_stop_list_unwraps_gmail_dictionary_envelope():
    a = {"id": "1"}
    b = {"id": "2"}
    out = coerce_stop_output(
        "stop-1",
        "list",
        DictionaryNodeOutput(
            node_id="gmail",
            data={"messages": [a, b], "resultSizeEstimate": 2},
        ),
    )
    assert isinstance(out, ListNodeOutput)
    assert out.node_id == "stop-1"
    assert out.data == [a, b]


def test_coerce_stop_list_plain_list_unchanged():
    data = [{"x": 1}, {"x": 2}]
    raw = ListNodeOutput(node_id="list-prim", data=data)
    out = coerce_stop_output("stop-1", "list", raw)
    assert isinstance(out, ListNodeOutput)
    assert out.data == data


def test_coerce_stop_list_unwraps_envelope_from_json_string():
    payload = {"messages": [{"id": "a"}], "resultSizeEstimate": 1}
    out = coerce_stop_output(
        "stop-1",
        "list",
        StopNodeOutput(node_id="x", text=json.dumps(payload)),
    )
    assert isinstance(out, ListNodeOutput)
    assert out.data == [{"id": "a"}]


def test_coerce_stop_audio_passthrough():
    a = AudioNodeOutput(node_id="tts", mime_type="audio/wav", audio_base64="YWI=")
    out = coerce_stop_output("stop-1", "audio", a)
    assert isinstance(out, AudioNodeOutput)
    assert out.node_id == "stop-1"
    assert out.mime_type == "audio/wav"
    assert out.audio_base64 == "YWI="


def test_resolve_stop_prefers_gmail_dict_over_string_when_expected_list():
    node = StopGraphNode(
        id="stop-1",
        label="Stop",
        data={"required_outputs": [{"key": "output", "type": "list"}]},
    )
    upstream = [
        StopNodeOutput(node_id="str", text="not a list wire"),
        DictionaryNodeOutput(
            node_id="gmail",
            data={"messages": [{"id": "m1"}], "resultSizeEstimate": 1},
        ),
    ]
    ex = WorkflowExecutor(MagicMock(), uuid.uuid4())
    result = ex._resolve_stop_node(node, upstream)
    assert result["status"] == "ok"
    out = result["output"]
    assert isinstance(out, ListNodeOutput)
    assert out.data == [{"id": "m1"}]
