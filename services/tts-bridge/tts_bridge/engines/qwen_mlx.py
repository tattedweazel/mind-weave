"""MLX-based Qwen TTS (placeholder — implement when Phase 0 selects MLX weights)."""

from __future__ import annotations

from typing import Any


class QwenMlxEngine:
    engine_key = "qwen_mlx"

    def pull(self, artifact_id: str, source: dict[str, Any]) -> str:
        raise NotImplementedError(
            "qwen_mlx engine is not implemented yet. Use qwen_torch or set TTS_BRIDGE_MOCK=1 for tests."
        )

    def synthesize(self, model_local_key: str, text: str, options: dict[str, Any]) -> bytes:
        raise NotImplementedError(
            "qwen_mlx engine is not implemented yet. Use qwen_torch or set TTS_BRIDGE_MOCK=1 for tests."
        )
