"""Editor-only annotation nodes are excluded from workflow execution parsing."""

import logging

from app.domain.workflow_executor.parsing import _parse_node


def test_parse_annotation_note_returns_none_no_warning(caplog):
    raw = {
        "id": "ann1",
        "kind": "annotation",
        "annotation_type": "note",
        "label": "Note",
        "data": {"text": "Hello"},
        "position": {"x": 0.0, "y": 0.0},
    }
    with caplog.at_level(logging.WARNING):
        assert _parse_node(raw) is None
    assert not any("unrecognised node kind" in r.message for r in caplog.records)


def test_parse_annotation_region_returns_none_no_warning(caplog):
    raw = {
        "id": "ann2",
        "kind": "annotation",
        "annotation_type": "region",
        "label": "Group",
        "data": {"width": 400, "height": 280},
        "position": {"x": 10.0, "y": 20.0},
    }
    with caplog.at_level(logging.WARNING):
        assert _parse_node(raw) is None
    assert not any("unrecognised node kind" in r.message for r in caplog.records)
