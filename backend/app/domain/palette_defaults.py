"""Canonical default colors for workflow palettes (API + seeding)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List

DEFAULT_PALETTE_NAME = "Default"
DEFAULT_PALETTE_SLUG = "default"

DEFAULT_PALETTE_COLORS: Dict[str, str] = {
    "string": "#38bdf8",
    "list": "#f472b6",
    "dictionary": "#e879f9",
    "structure": "#a78bfa",
    "document": "#2dd4bf",
    "image": "#f43f5e",
    "gmail": "#f97316",
    "sandbox_tick": "#2dd4bf",
    "sandbox_get_position": "#0f766e",
    "sandbox_get_facing": "#14b8a6",
    "sandbox_get_nearby": "#5eead4",
    "sandbox_move_forward": "#10b981",
    "sandbox_turn_left": "#059669",
    "sandbox_turn_right": "#059669",
    "sandbox_idle": "#34d399",
    "sandbox_pick_up_item": "#fbbf24",
    "sandbox_place_item": "#fb923c",
    "sandbox_get_inventory": "#a78bfa",
    "sandbox_prompt_user_action": "#6366f1",
    "read_document_property": "#14b8a6",
    "load_document": "#2dd4bf",
    "upsert_document": "#14b8a6",
    "parse_document_body": "#5eead4",
    "write_object_to_document_body": "#0d9488",
    "append_value_to_document": "#0f766e",
    "validate_against_structure": "#a78bfa",
    "any": "#ffffff",
    "workflow": "#14b8a6",
    "simple_llm_call": "#8b5cf6",
    "multimodal_llm": "#6366f1",
    "text_to_speech": "#c4b5fd",
    "transcribe_audio": "#4ade80",
    "audio_file_input": "#22c55e",
    "transcribe_file": "#16a34a",
    "audio": "#c4b5fd",
    "gmail_list_messages": "#ea4335",
    "calendar_list_events": "#4285f4",
    "google_docs_get_document": "#0ea5e9",
    "google_docs_parse_document": "#65a30d",
    "fetch_url": "#0ea5e9",
    "capture_url_snapshot": "#7c3aed",
    "html_parse_basic": "#65a30d",
    "list_to_string": "#22d3ee",
    "string_to_list": "#67e8f9",
    "prepend_text": "#f59e0b",
    "string_trunc": "#2dd4bf",
    "broadcast_message": "#6366f1",
    "basic_conditional": "#10b981",
    "is_control": "#06b6d4",
    "is_empty": "#06b6d4",
    "gt_control": "#0891b2",
    "lt_control": "#0891b2",
    "gte_control": "#0891b2",
    "lte_control": "#0891b2",
    "and_control": "#0d9488",
    "or_control": "#0d9488",
    "xor_control": "#0d9488",
    "boolean": "#22c55e",
    "int": "#f97316",
    "datetime": "#0ea5e9",
    "len_from_list": "#0ea5e9",
    "random_item_from_list": "#ec4899",
    "int_to_string": "#818cf8",
    "list_item_by_index": "#a855f7",
    "dictionary_value_by_key": "#9333ea",
    "dictionary_set_value_by_key": "#7c3aed",
    "add_to_list": "#d946ef",
    "add_ints": "#2dd4bf",
    "add_days": "#06b6d4",
    "subtract_ints": "#14b8a6",
    "multiply_ints": "#5eead4",
    "divide_ints": "#0d9488",
    "modulo_ints": "#f472b6",
    "min_ints": "#34d399",
    "max_ints": "#eab308",
    "not_control": "#6366f1",
    "between_control": "#c026d3",
    "try_catch_control": "#0369a1",
    "for_loop_control": "#059669",
    "for_loop_end_control": "#047857",
    "annotation_note": "#94a3b8",
    "annotation_region": "#64748b",
    "start": "#6366f1",
    "stop": "#f43f5e",
}

WORKFLOW_PALETTE_FAMILY_KEYS = frozenset({"primitive", "skill", "utility", "control"})


@dataclass(frozen=True)
class BuiltinPalette:
    name: str
    slug: str
    colors: Dict[str, str]


BUILTIN_WORKFLOW_PALETTES: List[BuiltinPalette] = [
    BuiltinPalette(DEFAULT_PALETTE_NAME, DEFAULT_PALETTE_SLUG, dict(DEFAULT_PALETTE_COLORS)),
    BuiltinPalette(
        "Slate",
        "slate",
        {
            "primitive": "#94a3b8",
            "skill": "#6366f1",
            "utility": "#38bdf8",
            "control": "#0e7490",
            "any": "#f1f5f9",
            "workflow": "#3b82f6",
            "int": "#fb923c",
        },
    ),
    BuiltinPalette(
        "Paper",
        "paper",
        {
            "primitive": "#78716c",
            "skill": "#6d28d9",
            "utility": "#0d9488",
            "control": "#115e59",
            "any": "#fafaf9",
            "workflow": "#57534e",
            "int": "#dc2626",
        },
    ),
    BuiltinPalette(
        "Maritime",
        "maritime",
        {
            "primitive": "#38bdf8",
            "skill": "#4f46e5",
            "utility": "#2dd4bf",
            "control": "#164e63",
            "any": "#f0f9ff",
            "workflow": "#0d9488",
            "int": "#fb923c",
        },
    ),
    BuiltinPalette(
        "Aurora",
        "aurora",
        {
            "primitive": "#22d3ee",
            "skill": "#d946ef",
            "utility": "#5eead4",
            "control": "#0891b2",
            "any": "#fae8ff",
            "workflow": "#2dd4bf",
            "int": "#fb7185",
        },
    ),
    BuiltinPalette(
        "Meadow",
        "meadow",
        {
            "primitive": "#4ade80",
            "skill": "#059669",
            "utility": "#2dd4bf",
            "control": "#14532d",
            "any": "#f7fee7",
            "workflow": "#16a34a",
            "int": "#ea580c",
        },
    ),
    BuiltinPalette(
        "Arcade",
        "arcade",
        {
            "primitive": "#22d3ee",
            "skill": "#d946ef",
            "utility": "#2dd4bf",
            "control": "#3b82f6",
            "any": "#fef9c3",
            "workflow": "#34d399",
            "int": "#fbbf24",
        },
    ),
]

_allowed_builtin_color_keys = frozenset(DEFAULT_PALETTE_COLORS.keys()) | WORKFLOW_PALETTE_FAMILY_KEYS
for _b in BUILTIN_WORKFLOW_PALETTES:
    for _k in _b.colors:
        if _k not in _allowed_builtin_color_keys:
            raise ValueError(
                f"Builtin palette {_b.slug!r}: invalid colors key {_k!r}; "
                "must be a per-step key or primitive/skill/utility/control."
            )


def default_palette_colors_copy() -> Dict[str, str]:
    return dict(DEFAULT_PALETTE_COLORS)
