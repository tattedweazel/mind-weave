"""
Built-in app-wide system color themes (light + dark token maps).

Must stay aligned with `frontend/src/theme/defaults.ts` token keys.
Names/slugs match workflow palette built-ins in `palette_defaults.py`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Mapping

# Mirrors SystemColorToken in the SPA (keep keys in sync).
DEFAULT_SYSTEM_THEME_NAME = "Default"
DEFAULT_SYSTEM_THEME_SLUG = "default"

_DEFAULT_LIGHT: Dict[str, str] = {
    "page_bg": "#f9fafb",
    "sidebar_bg": "#ffffff",
    "card_bg": "#ffffff",
    "card_bg_alt": "#f3f4f6",
    "text_primary": "#111827",
    "text_secondary": "#4b5563",
    "border": "#e5e7eb",
    "primary": "#2563eb",
    "primary_hover": "#1d4ed8",
    "primary_muted": "#eff6ff",
    "success": "#16a34a",
    "success_muted": "#dcfce7",
    "error": "#dc2626",
    "error_muted": "#fee2e2",
}

_DEFAULT_DARK: Dict[str, str] = {
    "page_bg": "#030712",
    "sidebar_bg": "#111827",
    "card_bg": "#111827",
    "card_bg_alt": "#1f2937",
    "text_primary": "#f9fafb",
    "text_secondary": "#9ca3af",
    "border": "#1f2937",
    "primary": "#60a5fa",
    "primary_hover": "#93c5fd",
    "primary_muted": "#1e293b",
    "success": "#4ade80",
    "success_muted": "#14532d",
    "error": "#f87171",
    "error_muted": "#7f1d1d",
}

SYSTEM_COLOR_TOKEN_KEYS = frozenset(_DEFAULT_LIGHT.keys())


def _pair(light: Mapping[str, str], dark: Mapping[str, str]) -> Dict[str, Dict[str, str]]:
    return {"light": dict(light), "dark": dict(dark)}


@dataclass(frozen=True)
class BuiltinSystemPalette:
    name: str
    slug: str
    colors: Dict[str, Dict[str, str]]


BUILTIN_SYSTEM_PALETTES: List[BuiltinSystemPalette] = [
    BuiltinSystemPalette(DEFAULT_SYSTEM_THEME_NAME, DEFAULT_SYSTEM_THEME_SLUG, _pair(_DEFAULT_LIGHT, _DEFAULT_DARK)),
    BuiltinSystemPalette(
        "Slate",
        "slate",
        _pair(
            {
                **_DEFAULT_LIGHT,
                "page_bg": "#f1f5f9",
                "sidebar_bg": "#f8fafc",
                "card_bg": "#ffffff",
                "card_bg_alt": "#e2e8f0",
                "text_primary": "#0f172a",
                "text_secondary": "#64748b",
                "border": "#cbd5e1",
                "primary": "#3b82f6",
                "primary_hover": "#2563eb",
                "primary_muted": "#dbeafe",
            },
            {
                **_DEFAULT_DARK,
                "page_bg": "#0f172a",
                "sidebar_bg": "#1e293b",
                "card_bg": "#1e293b",
                "card_bg_alt": "#334155",
                "text_primary": "#f1f5f9",
                "text_secondary": "#94a3b8",
                "border": "#334155",
                "primary": "#38bdf8",
                "primary_hover": "#7dd3fc",
                "primary_muted": "#164e63",
            },
        ),
    ),
    BuiltinSystemPalette(
        "Paper",
        "paper",
        _pair(
            {
                **_DEFAULT_LIGHT,
                "page_bg": "#fafaf9",
                "sidebar_bg": "#fafaf9",
                "card_bg": "#ffffff",
                "card_bg_alt": "#f5f5f4",
                "text_primary": "#292524",
                "text_secondary": "#78716c",
                "border": "#e7e5e4",
                "primary": "#b45309",
                "primary_hover": "#92400e",
                "primary_muted": "#ffedd5",
                "success": "#15803d",
                "success_muted": "#dcfce7",
            },
            {
                **_DEFAULT_DARK,
                "page_bg": "#1c1917",
                "sidebar_bg": "#292524",
                "card_bg": "#292524",
                "card_bg_alt": "#44403c",
                "text_primary": "#fafaf9",
                "text_secondary": "#a8a29e",
                "border": "#44403c",
                "primary": "#fbbf24",
                "primary_hover": "#fcd34d",
                "primary_muted": "#713f12",
            },
        ),
    ),
    BuiltinSystemPalette(
        "Maritime",
        "maritime",
        _pair(
            {
                **_DEFAULT_LIGHT,
                "primary": "#0284c7",
                "primary_hover": "#0369a1",
                "primary_muted": "#e0f2fe",
                "sidebar_bg": "#f0f9ff",
                "page_bg": "#f8fafc",
                "border": "#bae6fd",
            },
            {
                **_DEFAULT_DARK,
                "primary": "#22d3ee",
                "primary_hover": "#67e8f9",
                "primary_muted": "#164e63",
                "sidebar_bg": "#0c4a6e",
                "page_bg": "#082f49",
                "border": "#155e75",
            },
        ),
    ),
    BuiltinSystemPalette(
        "Aurora",
        "aurora",
        _pair(
            {
                **_DEFAULT_LIGHT,
                "page_bg": "#fdf4ff",
                "sidebar_bg": "#faf5ff",
                "card_bg": "#ffffff",
                "card_bg_alt": "#f3e8ff",
                "primary": "#9333ea",
                "primary_hover": "#7c3aed",
                "primary_muted": "#f3e8ff",
                "border": "#e9d5ff",
            },
            {
                **_DEFAULT_DARK,
                "page_bg": "#1e1b4b",
                "sidebar_bg": "#312e81",
                "card_bg": "#312e81",
                "card_bg_alt": "#3730a3",
                "primary": "#c084fc",
                "primary_hover": "#d8b4fe",
                "primary_muted": "#4c1d95",
                "border": "#5b21b6",
            },
        ),
    ),
    BuiltinSystemPalette(
        "Meadow",
        "meadow",
        _pair(
            {
                **_DEFAULT_LIGHT,
                "page_bg": "#f7fee7",
                "sidebar_bg": "#ecfccb",
                "card_bg": "#ffffff",
                "card_bg_alt": "#d9f99d",
                "primary": "#16a34a",
                "primary_hover": "#15803d",
                "primary_muted": "#dcfce7",
                "border": "#bbf7d0",
                "success": "#15803d",
                "success_muted": "#bbf7d0",
            },
            {
                **_DEFAULT_DARK,
                "page_bg": "#052e16",
                "sidebar_bg": "#14532d",
                "card_bg": "#14532d",
                "card_bg_alt": "#166534",
                "primary": "#4ade80",
                "primary_hover": "#86efac",
                "primary_muted": "#14532d",
                "border": "#166534",
                "success_muted": "#052e16",
            },
        ),
    ),
    BuiltinSystemPalette(
        "Arcade",
        "arcade",
        _pair(
            {
                **_DEFAULT_LIGHT,
                "page_bg": "#fefce8",
                "sidebar_bg": "#fff7ed",
                "card_bg": "#ffffff",
                "card_bg_alt": "#fef3c7",
                "primary": "#db2777",
                "primary_hover": "#be185d",
                "primary_muted": "#fce7f3",
                "border": "#fbcfe8",
                "text_primary": "#0f172a",
            },
            {
                **_DEFAULT_DARK,
                "page_bg": "#18181b",
                "sidebar_bg": "#27272a",
                "card_bg": "#27272a",
                "card_bg_alt": "#3f3f46",
                "primary": "#f472b6",
                "primary_hover": "#f9a8d4",
                "primary_muted": "#831843",
                "border": "#52525b",
                "text_primary": "#fafafa",
            },
        ),
    ),
]


def default_system_theme_colors_copy() -> Dict[str, Dict[str, str]]:
    """Default `{light, dark}` token maps for new user-owned system palettes."""
    return _pair(_DEFAULT_LIGHT, _DEFAULT_DARK)


for _b in BUILTIN_SYSTEM_PALETTES:
    for _mode in ("light", "dark"):
        for _k in _b.colors[_mode]:
            if _k not in SYSTEM_COLOR_TOKEN_KEYS:
                raise ValueError(f"Builtin system palette {_b.slug!r}: invalid token {_k!r} in {_mode}.")
