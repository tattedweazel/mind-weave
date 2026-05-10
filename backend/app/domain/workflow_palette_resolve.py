"""Resolve workflow palette overrides + shipped defaults → effective colors."""

from __future__ import annotations

from typing import Mapping, MutableMapping

from app.domain.palette_defaults import DEFAULT_PALETTE_COLORS
from app.domain.workflow_palette_manifest import (
    PALETTE_HANDLE_TO_FAMILY_FALLBACK,
    WORKFLOW_PALETTE_FAMILY_KEYS,
    allowed_workflow_palette_color_keys,
    palette_handle_ordered_labels,
    palette_handle_to_manifest_kind,
)


def _strip_optional(value: object) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def warn_unknown_palette_color_keys(colors: Mapping[str, str]) -> list[str]:
    allowed = allowed_workflow_palette_color_keys()
    return [str(k) for k in sorted(colors.keys()) if k not in allowed]


def resolve_effective_color(colors: Mapping[str, str], palette_handle: str) -> str:
    """
    Match SPA `resolveWorkflowPaletteColor`:
    persisted handle → stepped family fallback → shipped default → `any` persisted → shipped `any`.
    """

    raw_spec = colors.get(palette_handle)
    spec = _strip_optional(raw_spec)
    if spec:
        return spec

    family = PALETTE_HANDLE_TO_FAMILY_FALLBACK.get(palette_handle)
    if family is not None and family in WORKFLOW_PALETTE_FAMILY_KEYS:
        fam_hex = _strip_optional(colors.get(family))
        if fam_hex:
            return fam_hex

    def_hex = DEFAULT_PALETTE_COLORS.get(palette_handle)
    if isinstance(def_hex, str) and def_hex.strip():
        return def_hex.strip()

    any_hex = _strip_optional(colors.get("any"))
    if any_hex:
        return any_hex

    return DEFAULT_PALETTE_COLORS["any"]


def workflow_palette_computed_payload(
    colors: Mapping[str, str],
) -> tuple[list[dict[str, str]], dict[str, str], list[str]]:
    """
    API payload helpers:
      - `entries`: ordered manifest rows `{ key, label, kind, effective_color }`.
      - `effective_colors`: every manifest handle plus step-family keys (resolved).
      - `warnings`: persisted keys absent from SSOT (+ family keys).
    """

    warns = [f"unknown_palette_color_key:{k}" for k in warn_unknown_palette_color_keys(colors)]

    kinds = palette_handle_to_manifest_kind()
    effective_colors: MutableMapping[str, str] = {}

    entries: list[dict[str, str]] = []
    for handle_key, editor_label in palette_handle_ordered_labels():
        ec = resolve_effective_color(colors, handle_key)
        entries.append(
            {
                "key": handle_key,
                "label": editor_label,
                "kind": kinds.get(handle_key, "pseudo"),
                "effective_color": ec,
            },
        )
        effective_colors[handle_key] = ec

    for fam in WORKFLOW_PALETTE_FAMILY_KEYS:
        effective_colors[fam] = resolve_effective_color(colors, fam)

    return entries, dict(sorted(effective_colors.items())), warns
