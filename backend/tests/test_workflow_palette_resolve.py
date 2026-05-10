"""Unit tests for workflow palette resolution (+ validate import coercion)."""

import pytest

from app.domain.palette_defaults import DEFAULT_PALETTE_COLORS
from app.domain.workflow_palette_resolve import resolve_effective_color, workflow_palette_computed_payload
from app.domain.workflow_palette_validate import coerce_validate_palette_import


def test_resolve_matches_family_fallback():
    colors = {"utility": "#111111"}
    eff = resolve_effective_color(colors, "list_to_string")
    assert eff == "#111111"


def test_resolve_falls_through_to_shipped_default():
    colors: dict[str, str] = {}
    assert resolve_effective_color(colors, "string") == DEFAULT_PALETTE_COLORS["string"]


def test_computed_payload_warnings_unknown_keys():
    _entries, _ecs, warns = workflow_palette_computed_payload({"not_a_real_key": "#ffffff"})
    assert any(w.startswith("unknown_palette_color_key:") for w in warns)


def test_coerce_import_strips_unknown():
    sanitized, warns = coerce_validate_palette_import({"string": "#ff00ff", "bogus_key_xyz": "#000000"})
    assert "string" in sanitized
    assert "bogus_key_xyz" not in sanitized
    assert any("stripped_unknown_palette_color_key:bogus_key_xyz" in w for w in warns)


def test_coerce_import_rejects_bad_hex():
    with pytest.raises(ValueError):
        coerce_validate_palette_import({"string": "not-a-color"})
