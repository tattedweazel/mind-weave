"""Tests for workflow input resolution (e.g. multimodal ``images`` from dictionary outputs)."""

from __future__ import annotations

import json

from app.domain.schemas import (
    DictionaryNodeOutput,
    DocumentNodeOutput,
    GraphEdge,
    ListNodeOutput,
    NodeOutputUnion,
    StringNodeOutput,
)
from app.domain.workflow_executor.inputs import (
    _dict_is_multimodal_images_upstream,
    _plain_upstream_from_slot,
    _resolve_inputs_by_target_handle,
)
from app.domain.workflow_executor.parsing import _parse_node


def test_dict_is_multimodal_images_upstream_flat_ref():
    d = {
        "artifact_id": "00000000-0000-0000-0000-000000000001",
        "mime_type": "image/png",
        "width": 1,
        "height": 1,
    }
    assert _dict_is_multimodal_images_upstream(d) is True


def test_dict_is_multimodal_images_upstream_snapshot_shaped():
    d = {
        "image": {
            "artifact_id": "00000000-0000-0000-0000-000000000002",
            "mime_type": "image/png",
            "width": 1,
            "height": 1,
        },
        "final_url": "https://example.com/",
    }
    assert _dict_is_multimodal_images_upstream(d) is True


def test_dict_is_multimodal_images_upstream_random_dict_false():
    assert _dict_is_multimodal_images_upstream({"foo": 1}) is False


def test_plain_upstream_from_slot_images_passes_flat_dictionary_output():
    slot = DictionaryNodeOutput(
        node_id="n_img",
        data={
            "artifact_id": "00000000-0000-0000-0000-000000000003",
            "mime_type": "image/png",
            "width": 2,
            "height": 3,
        },
    )
    out = _plain_upstream_from_slot(slot, "list", input_key="images")
    assert isinstance(out, dict)
    assert out["artifact_id"] == "00000000-0000-0000-0000-000000000003"
    # Must not be JSON string (old bug)
    assert not isinstance(out, str)


def test_plain_upstream_from_slot_images_passes_full_snapshot_dict():
    slot = DictionaryNodeOutput(
        node_id="n_cap",
        data={
            "image": {
                "artifact_id": "00000000-0000-0000-0000-000000000004",
                "mime_type": "image/png",
                "width": 1,
                "height": 1,
            },
            "final_url": "https://x.com/",
        },
    )
    out = _plain_upstream_from_slot(slot, "list", input_key="images")
    assert out["image"]["artifact_id"] == "00000000-0000-0000-0000-000000000004"


def test_plain_upstream_from_slot_list_slot_still_works_for_images_list():
    slot = ListNodeOutput(
        node_id="n_l",
        data=[{"artifact_id": "00000000-0000-0000-0000-000000000005"}],
    )
    out = _plain_upstream_from_slot(slot, "list", input_key="images")
    assert out == [{"artifact_id": "00000000-0000-0000-0000-000000000005"}]


def test_plain_upstream_from_slot_unrelated_dict_with_list_expected_still_stringifies():
    """Non-image dicts to a generic list-typed input keep legacy JSON behavior."""
    slot = DictionaryNodeOutput(node_id="x", data={"not_image": 1})
    out = _plain_upstream_from_slot(slot, "list", input_key="images")
    # Does not match multimodal heuristics -> falls through to json.dumps
    assert out == json.dumps({"not_image": 1}, indent=2)


def test_plain_upstream_from_slot_document_string_is_body_markdown():
    doc_id = "550e8400-e29b-41d4-a716-446655440099"
    slot = DocumentNodeOutput(
        node_id="n_doc",
        document_id=doc_id,
        name="N",
        description="D",
        markdown="# Hi\n",
    )
    assert _plain_upstream_from_slot(slot, "string") == "# Hi\n"
    assert _plain_upstream_from_slot(slot, "string", input_key="user_prompt") == "# Hi\n"


def test_plain_upstream_from_slot_document_non_string_stays_dict_shape():
    doc_id = "550e8400-e29b-41d4-a716-4466554400aa"
    slot = DocumentNodeOutput(
        node_id="n_doc2",
        document_id=doc_id,
        name="Title",
        description="Desc",
        markdown="body md",
    )
    expected = {
        "id": doc_id,
        "name": "Title",
        "description": "Desc",
        "body": "body md",
    }
    assert _plain_upstream_from_slot(slot, "dictionary") == expected
    assert _plain_upstream_from_slot(slot, None) == expected


def test_plain_upstream_from_slot_document_any_returns_full_dict_like_override():
    doc_id = "550e8400-e29b-41d4-a716-4466554400bb"
    slot = DocumentNodeOutput(
        node_id="n_doc3",
        document_id=doc_id,
        name="T",
        description="",
        markdown="md",
    )
    out_any = _plain_upstream_from_slot(slot, "any")
    assert out_any == {
        "id": doc_id,
        "name": "T",
        "description": "",
        "body": "md",
    }


def test_resolve_images_input_from_dictionary_node_output():
    """End-to-end: multimodal required_inputs ``images`` (type list) + upstream dict output."""
    node_mm = "n_mm"
    node_src = "n_src"
    raw_mm = {
        "id": node_mm,
        "kind": "skill",
        "skill_type": "multimodal_llm",
        "label": "MM",
        "data": {
            "persona_id": "00000000-0000-0000-0000-0000000000aa",
            "required_inputs": [
                {"key": "user_prompt", "type": "string", "value": "hi"},
                {"key": "images", "type": "list", "value": None},
            ],
        },
        "position": {},
    }
    mm = _parse_node(raw_mm)
    assert mm is not None
    out_src = DictionaryNodeOutput(
        node_id=node_src,
        data={
            "artifact_id": "00000000-0000-0000-0000-0000000000ab",
            "mime_type": "image/png",
            "width": 1,
            "height": 1,
        },
    )
    outputs: dict[str, NodeOutputUnion] = {node_src: out_src}
    edges: list[GraphEdge] = [
        GraphEdge(source=node_src, target=node_mm, target_handle="images", source_handle="output")
    ]
    res = _resolve_inputs_by_target_handle(
        node_mm,
        ["user_prompt", "images"],
        edges,
        outputs,
        {},
        (mm.data or {}).get("required_inputs") or [],
    )
    assert isinstance(res.get("images"), dict)
    assert res["images"]["artifact_id"] == "00000000-0000-0000-0000-0000000000ab"


_UPSERT_LIKE_KEYS = ["name", "content", "existing_document_id", "write_mode"]

_UPSERT_LIKE_REQUIRED_INPUTS: list[dict] = [
    {"key": "name", "type": "string", "value": "My Doc"},
    {"key": "content", "type": "string", "value": ""},
    {"key": "existing_document_id", "type": "string", "value": None},
    {"key": "write_mode", "type": "string", "value": "replace"},
]


def test_resolve_upsert_content_implicit_null_target_handle_when_allow_listed():
    """Legacy edge without ``target_handle`` still fills ``content`` when allow-listed (upsert)."""
    nid_up = "n_up"
    nid_src = "n_l2s"
    edges = [GraphEdge(source=nid_src, target=nid_up, target_handle=None)]
    outputs: dict[str, NodeOutputUnion] = {nid_src: StringNodeOutput(node_id=nid_src, text="hello from wire")}
    res = _resolve_inputs_by_target_handle(
        nid_up,
        _UPSERT_LIKE_KEYS,
        edges,
        outputs,
        {},
        _UPSERT_LIKE_REQUIRED_INPUTS,
        implicit_null_target_wire_string_keys=frozenset({"name", "content"}),
    )
    assert res["name"] == "My Doc"
    assert res["content"] == "hello from wire"


def test_normalize_upsert_edges_maps_content_aliases():
    """Executor maps wrong-but-non-null body handles onto ``content`` before resolution."""
    from app.domain.workflow_executor.executor import _normalize_edges_for_upsert_document

    nid = "n_u"
    edges = [
        GraphEdge(source="a", target=nid, target_handle="markdown"),
        GraphEdge(source="b", target=nid, target_handle=""),
        GraphEdge(source="c", target=nid, target_handle="trigger"),
        GraphEdge(source="d", target="other_node", target_handle="x"),
        GraphEdge(source="e", target=nid, target_handle="name"),
    ]
    norm = _normalize_edges_for_upsert_document(nid, edges)
    assert norm[0].target_handle == "content"
    assert norm[1].target_handle == ""
    assert norm[2].target_handle == "trigger"
    assert norm[3].target_handle == "x"
    assert norm[4].target_handle == "name"


def test_resolve_upsert_with_normalized_markdown_alias_fills_content():
    from app.domain.workflow_executor.executor import _normalize_edges_for_upsert_document

    nid_up = "n_up"
    nid_src = "n_src"
    raw_edges = [GraphEdge(source=nid_src, target=nid_up, target_handle="markdown")]
    edges = _normalize_edges_for_upsert_document(nid_up, raw_edges)
    outputs: dict[str, NodeOutputUnion] = {nid_src: StringNodeOutput(node_id=nid_src, text="body text")}
    res = _resolve_inputs_by_target_handle(
        nid_up,
        _UPSERT_LIKE_KEYS,
        edges,
        outputs,
        {},
        _UPSERT_LIKE_REQUIRED_INPUTS,
        implicit_null_target_wire_string_keys=frozenset({"name", "content"}),
    )
    assert res["name"] == "My Doc"
    assert res["content"] == "body text"


def test_resolve_no_implicit_string_wire_without_allow_list():
    """Default resolver does not attach null-target edges to plain string ports."""
    nid_up = "n_up"
    nid_src = "n_l2s"
    edges = [GraphEdge(source=nid_src, target=nid_up, target_handle=None)]
    outputs: dict[str, NodeOutputUnion] = {
        nid_src: StringNodeOutput(node_id=nid_src, text="ignored unless explicit handle")
    }
    res = _resolve_inputs_by_target_handle(
        nid_up,
        _UPSERT_LIKE_KEYS,
        edges,
        outputs,
        {},
        _UPSERT_LIKE_REQUIRED_INPUTS,
    )
    assert res["name"] == "My Doc"
    assert res["content"] == ""
