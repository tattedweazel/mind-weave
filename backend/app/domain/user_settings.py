"""User.settings JSON: shared limits and resolution for keys used by API and runtime."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, cast

from pydantic import ValidationError

if TYPE_CHECKING:
    from app.domain.execution_limits import ExecutionLimitsOverrides

MAX_CONCURRENT_LM_STUDIO_CALLS_MIN = 1
MAX_CONCURRENT_LM_STUDIO_CALLS_MAX = 32
MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT = 3

MAX_SANDBOX_FAVORITE_COLORS = 16

_TTS_PLAYBACK_WHEN_VALUES = frozenset({"inline", "manual", "after_workflow"})


def normalize_sandbox_favorite_colors(raw: Any) -> list[str]:
    """Validate and normalize user favorite hex colors for Sandbox regions."""
    from app.domain.schemas.sandbox import normalize_hex_color

    if not isinstance(raw, list):
        raise ValueError("settings.sandbox_favorite_colors must be a list")
    if len(raw) > MAX_SANDBOX_FAVORITE_COLORS:
        raise ValueError(
            f"settings.sandbox_favorite_colors must have at most {MAX_SANDBOX_FAVORITE_COLORS} entries",
        )
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            raise ValueError("settings.sandbox_favorite_colors must be a list of strings")
        try:
            normalized = normalize_hex_color(item)
        except ValueError as exc:
            raise ValueError(f"settings.sandbox_favorite_colors invalid color: {item!r}") from exc
        if normalized not in seen:
            seen.add(normalized)
            out.append(normalized)
    return out


def resolve_sandbox_favorite_colors(settings: Any) -> list[str]:
    if not isinstance(settings, dict):
        return []
    raw = settings.get("sandbox_favorite_colors")
    if not isinstance(raw, list):
        return []
    try:
        return normalize_sandbox_favorite_colors(raw)
    except ValueError:
        return []


def resolve_tts_playback_when(settings: Any) -> str:
    """Workflow editor TTS timing during Build runs (`GET …/events`): inline | manual | after_workflow. Default inline."""
    if not isinstance(settings, dict):
        return "inline"
    w = settings.get("tts_playback_when")
    if isinstance(w, str) and w in _TTS_PLAYBACK_WHEN_VALUES:
        return w
    return "inline" if _legacy_auto_play_bool(settings) else "manual"


def _legacy_auto_play_bool(settings: dict) -> bool:
    raw = settings.get("auto_play_tts_on_node_end")
    if raw is None:
        return True
    if isinstance(raw, bool):
        return raw
    return True


def resolve_auto_play_tts_on_node_end(settings: Any) -> bool:
    """When True (default), workflow editor may inline auto-play TTS on node completion during Build runs (`GET …/events`).

    Equivalent to resolve_tts_playback_when(settings) == \"inline\".
    """
    return resolve_tts_playback_when(settings) == "inline"


def parse_execution_limits_prefs_from_settings(settings: Any) -> Optional["ExecutionLimitsOverrides"]:
    """Optional overlays from ``User.settings['workflow_execution_limits_prefs']``. None if absent or invalid."""

    from app.domain.execution_limits import ExecutionLimitsOverrides

    if not isinstance(settings, dict):
        return None
    raw = settings.get("workflow_execution_limits_prefs")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    try:
        return ExecutionLimitsOverrides.model_validate(raw)
    except ValidationError:
        return None


def resolve_max_concurrent_lm_studio_calls(settings: Any) -> int:
    """Clamp to allowed range; default when missing or invalid."""
    if not isinstance(settings, dict):
        return MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT
    raw = settings.get("max_concurrent_lm_studio_calls")
    if raw is None:
        return MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT
    if isinstance(raw, bool) or not isinstance(raw, int):
        return MAX_CONCURRENT_LM_STUDIO_CALLS_DEFAULT
    return cast(
        int,
        max(
            MAX_CONCURRENT_LM_STUDIO_CALLS_MIN,
            min(MAX_CONCURRENT_LM_STUDIO_CALLS_MAX, raw),
        ),
    )
