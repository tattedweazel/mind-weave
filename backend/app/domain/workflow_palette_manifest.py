"""Load workflow step manifest palette metadata (`shared/workflow_graph_step_kinds.json`)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, FrozenSet, List, Mapping, TypedDict


class ManifestStepPalette(TypedDict, total=False):
    kind: str
    primitive_type: str
    utility_type: str
    skill_type: str
    control_type: str
    react_flow_type: str
    pydantic_model: str
    palette_handle: str
    editor_label: str


class ManifestExtraPalette(TypedDict):
    palette_handle: str
    editor_label: str
    kind: str


_REPO_ROOT_FOR_DOMAIN = Path(__file__).resolve().parents[3]
_MANIFEST_PATH = _REPO_ROOT_FOR_DOMAIN / "shared" / "workflow_graph_step_kinds.json"

WORKFLOW_PALETTE_FAMILY_KEYS: FrozenSet[str] = frozenset({"primitive", "skill", "utility", "control"})

# Mirrors `PALETTE_KEY_TO_FAMILY` in `frontend/src/domain/paletteDefaults.ts` (family fallback when palette is sparse).
PALETTE_HANDLE_TO_FAMILY_FALLBACK: dict[str, str] = {
    "string": "primitive",
    "list": "primitive",
    "dictionary": "primitive",
    "structure": "primitive",
    "document": "primitive",
    "image": "primitive",
    "gmail": "primitive",
    "sandbox_tick": "utility",
    "sandbox_get_position": "utility",
    "sandbox_get_facing": "utility",
    "sandbox_get_nearby": "utility",
    "sandbox_move_forward": "utility",
    "sandbox_turn_left": "utility",
    "sandbox_turn_right": "utility",
    "sandbox_idle": "utility",
    "boolean": "primitive",
    "int": "primitive",
    "datetime": "primitive",
    "simple_llm_call": "skill",
    "multimodal_llm": "skill",
    "text_to_speech": "skill",
    "transcribe_audio": "skill",
    "audio_file_input": "skill",
    "transcribe_file": "skill",
    "audio": "skill",
    "gmail_list_messages": "skill",
    "calendar_list_events": "skill",
    "google_docs_get_document": "skill",
    "fetch_url": "skill",
    "capture_url_snapshot": "skill",
    "list_to_string": "utility",
    "string_to_list": "utility",
    "prepend_text": "utility",
    "string_trunc": "utility",
    "message": "utility",
    "len_from_list": "utility",
    "random_item_from_list": "utility",
    "int_to_string": "utility",
    "list_item_by_index": "utility",
    "dictionary_value_by_key": "utility",
    "dictionary_set_value_by_key": "utility",
    "read_document_property": "utility",
    "load_document": "utility",
    "upsert_document": "utility",
    "parse_document_body": "utility",
    "html_parse_basic": "utility",
    "google_docs_parse_document": "utility",
    "write_object_to_document_body": "utility",
    "append_value_to_document": "utility",
    "validate_against_structure": "utility",
    "add_to_list": "utility",
    "add_ints": "utility",
    "add_days": "utility",
    "subtract_ints": "utility",
    "multiply_ints": "utility",
    "divide_ints": "utility",
    "modulo_ints": "utility",
    "min_ints": "utility",
    "max_ints": "utility",
    "basic_conditional": "control",
    "is_control": "control",
    "is_empty": "control",
    "gt_control": "control",
    "lt_control": "control",
    "gte_control": "control",
    "lte_control": "control",
    "and_control": "control",
    "or_control": "control",
    "xor_control": "control",
    "not_control": "control",
    "between_control": "control",
    "try_catch_control": "control",
    "for_loop_control": "control",
    "for_loop_end_control": "control",
}


@lru_cache(maxsize=1)
def workflow_graph_step_kinds_manifest() -> Mapping[str, Any]:
    raw = json.loads(_MANIFEST_PATH.read_text(encoding="utf-8"))
    if int(raw.get("manifest_version") or 0) < 2:
        raise ValueError(f"{_MANIFEST_PATH}: manifest_version must be >= 2 for palette SSOT.")
    return raw


def manifest_steps_palettes() -> List[ManifestStepPalette]:
    return list(workflow_graph_step_kinds_manifest()["steps"])


def manifest_palette_extras() -> List[ManifestExtraPalette]:
    return list(workflow_graph_step_kinds_manifest().get("palette_extras") or [])


@lru_cache(maxsize=1)
@lru_cache(maxsize=1)
def palette_handle_to_manifest_kind() -> dict[str, str]:
    """Map palette_handle → manifest row `kind` (start/stop/workflow/pseudo/…)."""

    out: dict[str, str] = {}
    for row in manifest_steps_palettes():
        out[row["palette_handle"]] = row["kind"]
    for row in manifest_palette_extras():
        out[row["palette_handle"]] = row["kind"]
    return out


@lru_cache(maxsize=1)
def palette_handle_ordered_labels() -> list[tuple[str, str]]:
    """Stable `(palette_handle, editor_label)` for manifest rows then extras."""

    tuples: List[tuple[str, str]] = [(r["palette_handle"], r["editor_label"]) for r in manifest_steps_palettes()]
    tuples.extend((r["palette_handle"], r["editor_label"]) for r in manifest_palette_extras())
    return tuples


@lru_cache(maxsize=1)
def allowed_workflow_palette_color_keys() -> FrozenSet[str]:
    names = frozenset(h for h, _ in palette_handle_ordered_labels())
    return names | WORKFLOW_PALETTE_FAMILY_KEYS


def manifest_palette_path_for_tests() -> Path:
    """Exposed for tests that snapshot manifest IO."""

    return _MANIFEST_PATH
