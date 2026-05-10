"""Validate persisted workflow palette JSON (`Palette.colors`)."""

from __future__ import annotations

import re
from typing import Dict, Mapping, MutableMapping

from app.domain.workflow_palette_manifest import allowed_workflow_palette_color_keys

_RE_HEX = re.compile(r"^#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})$")


def normalize_css_compatible_color(candidate: object) -> str:
    """Return stripped color string or raise ValueError with a concise reason."""

    if not isinstance(candidate, str):
        raise ValueError(f"palette color must be a string, got {type(candidate).__name__}")
    s = candidate.strip()
    if not s:
        raise ValueError("palette color must not be empty")
    if _RE_HEX.match(s):
        return s
    low = s.lower()
    if low.startswith(("rgb(", "rgba(", "hsl(", "hsla(")) and low.endswith(")"):
        inner = s[s.index("(") + 1 : -1].strip()
        if not inner:
            raise ValueError("palette color parentheses must contain values")
        return s

    named = {"transparent", "currentcolor"}
    if low in named:
        return low
    raise ValueError(f"palette color is not recognized as a safe CSS fragment: {s!r}")


def normalize_strict_write(colors: Mapping[str, object]) -> dict[str, str]:
    """Require every persisted key appear in SSOT and normalize CSS tokens."""

    allowed = allowed_workflow_palette_color_keys()
    out: dict[str, str] = {}
    for raw_k, raw_val in colors.items():
        if not isinstance(raw_k, str) or not raw_k.strip():
            raise ValueError("palette colors keys must be non-empty strings")
        key = raw_k.strip()
        if key not in allowed:
            raise ValueError(f"unknown palette colors key {key!r}")
        out[key] = normalize_css_compatible_color(raw_val)
    return out


def coerce_validate_palette_import(
    colors: Mapping[str, object],
) -> tuple[dict[str, str], list[str]]:
    """
    Import / preview path: normalize known keys (strict CSS), strip unknown keys with warnings.

    Unknown keys emit `stripped_unknown_palette_color_key:<key>`; invalid colors raise ValueError.
    """

    allowed = allowed_workflow_palette_color_keys()
    sanitized: MutableMapping[str, str] = {}
    warns: list[str] = []
    for raw_k, raw_val in colors.items():
        if not isinstance(raw_k, str) or not raw_k.strip():
            continue
        key = raw_k.strip()
        if key not in allowed:
            warns.append(f"stripped_unknown_palette_color_key:{key}")
            continue
        sanitized[key] = normalize_css_compatible_color(raw_val)

    return dict(sorted(sanitized.items())), sorted(warns)
