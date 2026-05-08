"""Engine registry."""

from __future__ import annotations

from typing import Any

from tts_bridge.engines.qwen_mlx import QwenMlxEngine
from tts_bridge.engines.qwen_torch import QwenTorchEngine

_ENGINES: dict[str, Any] = {
    "qwen_torch": QwenTorchEngine(),
    "qwen_mlx": QwenMlxEngine(),
}


def get_engine(key: str):
    e = _ENGINES.get(key)
    if e is None:
        raise ValueError(f"Unknown engine: {key!r}")
    return e
