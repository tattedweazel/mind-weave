"""Unit tests for deterministic JSON helpers used by document merge and utilities."""

import pytest

from app.domain.document_json import (
    deterministic_json_dumps,
    merge_json_objects,
    parse_json_object_strict,
)


def test_deterministic_json_dumps_sorts_keys():
    assert deterministic_json_dumps({"b": 1, "a": 2}) == '{"a":2,"b":1}'


def test_parse_json_object_strict_accepts_object():
    assert parse_json_object_strict('  {"x": 1}  ', what="t") == {"x": 1}


def test_parse_json_object_strict_rejects_array():
    with pytest.raises(ValueError, match="object"):
        parse_json_object_strict("[1]", what="t")


def test_parse_json_object_strict_rejects_invalid_json():
    with pytest.raises(ValueError, match="invalid JSON"):
        parse_json_object_strict("{", what="t")


def test_merge_json_objects_incoming_wins_leaf():
    assert merge_json_objects({"a": 1}, {"a": 2}) == {"a": 2}


def test_merge_json_objects_recursive_dicts():
    base = {"a": {"x": 1, "y": 2}, "b": 3}
    inc = {"a": {"y": 9, "z": 4}}
    assert merge_json_objects(base, inc) == {"a": {"x": 1, "y": 9, "z": 4}, "b": 3}


def test_merge_json_objects_incoming_replaces_non_dict_leaf():
    assert merge_json_objects({"a": {"x": 1}}, {"a": "str"}) == {"a": "str"}
