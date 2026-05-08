"""
Document Metadata Service
=========================
Pure helpers that compute size statistics for a Document body so the SPA can
surface them in the **Manage Documents → Metadata** tab. Token counts are an
*estimate* against the GPT-4o family encoding (``o200k_base``); local LM Studio
models may use a different tokenizer, so the UI labels this honestly.

The encoding is loaded lazily and cached for the process lifetime via
``functools.lru_cache``. Importing this module does **not** trigger the load,
which keeps app startup fast and lets tests preload only when needed.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import tiktoken

#: Canonical tokenizer name surfaced to the UI alongside the count. Hardcoded
#: today; future work may make this configurable per persisted LLM target.
TOKENIZER_NAME = "o200k_base"


@dataclass(frozen=True)
class DocumentBodyStats:
    """Lightweight stats derived from a Document ``body`` string."""

    token_count: int
    character_count: int
    word_count: int
    line_count: int


@lru_cache(maxsize=1)
def _get_encoding() -> tiktoken.Encoding:
    """Return the cached ``o200k_base`` encoding (loaded on first call)."""
    return tiktoken.get_encoding(TOKENIZER_NAME)


def compute_document_metadata(body: str) -> DocumentBodyStats:
    """
    Compute token / character / word / line counts for ``body``.

    An empty string returns all zeros. ``word_count`` is a whitespace split,
    matching what most users intuitively expect for prose; ``line_count`` is
    the number of ``\\n``-separated segments (so ``"a\\nb"`` is 2 lines).
    """
    if not body:
        return DocumentBodyStats(
            token_count=0,
            character_count=0,
            word_count=0,
            line_count=0,
        )

    encoding = _get_encoding()
    return DocumentBodyStats(
        token_count=len(encoding.encode(body)),
        character_count=len(body),
        word_count=len(body.split()),
        line_count=len(body.splitlines()) or 1,
    )
