"""Unit tests for DateTime primitive graph normalization in workflow parsing."""

from app.domain.workflow_executor.parsing import (
    _coerce_use_now_flag,
    _normalize_raw_datetime_primitive,
)


def test_coerce_use_now_flag_bools_and_strings():
    assert _coerce_use_now_flag(True) is True
    assert _coerce_use_now_flag(False) is False
    assert _coerce_use_now_flag(None) is False
    assert _coerce_use_now_flag("true") is True
    assert _coerce_use_now_flag("FALSE") is False
    assert _coerce_use_now_flag("1") is True
    assert _coerce_use_now_flag("0") is False
    assert _coerce_use_now_flag(1) is True
    assert _coerce_use_now_flag(0) is False


def test_normalize_datetime_primitive_root_use_now_into_data():
    raw = {
        "id": "n1",
        "kind": "primitive",
        "primitive_type": "datetime",
        "label": "D",
        "use_now": True,
        "data": {"iso": None},
        "position": {},
    }
    n = _normalize_raw_datetime_primitive(raw)
    assert n["data"]["use_now"] is True
    assert "useNow" not in n["data"]
    assert n["data"]["iso"] is None


def test_normalize_datetime_primitive_data_use_now_camel():
    raw = {
        "id": "n1",
        "kind": "primitive",
        "primitive_type": "datetime",
        "label": "D",
        "data": {"iso": None, "useNow": True},
        "position": {},
    }
    n = _normalize_raw_datetime_primitive(raw)
    assert n["data"]["use_now"] is True
    assert "useNow" not in n["data"]


def test_normalize_datetime_primitive_non_dict_data_becomes_dict_with_flag():
    raw = {
        "id": "n1",
        "kind": "primitive",
        "primitive_type": "datetime",
        "label": "D",
        "use_now": True,
        "data": [],
        "position": {},
    }
    n = _normalize_raw_datetime_primitive(raw)
    assert isinstance(n["data"], dict)
    assert n["data"]["use_now"] is True
