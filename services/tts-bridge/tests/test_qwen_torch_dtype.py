"""Regression: per-device weight dtype for qwen_torch (MPS float32 vs CUDA bf16)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest
import torch
import torch.nn as nn

from tts_bridge.config import settings
from tts_bridge.engines import qwen_torch
from tts_bridge.engines.qwen_torch import (
    QwenTorchEngine,
    TTS_QWEN_LOAD_CACHE_REVISION,
    _any_meta_tensor,
    _load_qwen3_from_pretrained,
    _qwen3_from_pretrained_load_kwargs,
    _resolve_device,
    _sync_speech_tokenizer_device,
    _weight_dtype_for_device,
)


def test_weight_dtype_cpu_is_float32():
    assert _weight_dtype_for_device("cpu") is torch.float32


def test_weight_dtype_mps_is_float32():
    assert _weight_dtype_for_device("mps") is torch.float32


def test_weight_dtype_cuda_is_bfloat16():
    assert _weight_dtype_for_device("cuda:0") is torch.bfloat16


def test_qwen3_load_kwargs_disable_meta_tensor_path():
    """CPU full load (no device_map) + post ``.to()`` avoids HuggingFace meta / accelerate meta-tensor errors."""
    kw = _qwen3_from_pretrained_load_kwargs(torch.float32)
    assert kw.get("low_cpu_mem_usage") is False
    assert kw.get("device_map") is None
    assert kw.get("local_files_only") is True
    assert kw.get("dtype") is torch.float32


def test_cache_revision_busts_in_process_models():
    assert "st_mat" in TTS_QWEN_LOAD_CACHE_REVISION or "v4" in TTS_QWEN_LOAD_CACHE_REVISION
    assert qwen_torch.TTS_QWEN_LOAD_CACHE_REVISION == TTS_QWEN_LOAD_CACHE_REVISION


def test_any_meta_none_safe():
    assert _any_meta_tensor(None) is False


def test_any_meta_detects_meta_parameter():
    m = nn.Linear(2, 2, device="meta", dtype=torch.float32)
    assert _any_meta_tensor(m) is True


def test_sync_speech_tokenizer_device_updates_inner_model():
    inner = nn.Linear(1, 1)
    st = type("St", (), {"model": inner, "device": None})()
    q = type("Q", (), {"speech_tokenizer": st})()
    dev = torch.device("cpu")
    _sync_speech_tokenizer_device(q, dev)
    assert st.device is not None
    assert next(inner.parameters()).device.type == "cpu"


def test_integration_speech_tokenizer_subdir_exists_for_smoke_path():
    """When a local snapshot exists, speech_tokenizer/ is the path the bridge re-loads. Skip if no weights."""
    root = Path(settings.TTS_MODEL_ROOT)
    cfg = list(root.glob("qwen_torch/**/speech_tokenizer/config.json"))
    if not cfg:
        pytest.skip("No local qwen_torch snapshot under TTS_MODEL_ROOT (optional integration)")
    assert cfg[0].parent.is_dir()


def test_synthesize_base_text_only_raises_without_reference():
    """Base checkpoints are voice-clone: text-only must error (regression: do not call generate_voice_design)."""
    root = Path(settings.TTS_MODEL_ROOT) / "qwen_torch" / "d8488443-1a2b-41d4-8ea1-66700e2d2e98"
    if not (root / "config.json").is_file():
        pytest.skip("No local Base qwen snapshot at expected path (optional)")

    path = root.resolve()
    dev = _resolve_device()
    dt = _weight_dtype_for_device(dev)
    cache_key = f"{path}|{dev}|{dt}|{TTS_QWEN_LOAD_CACHE_REVISION}"

    fake = MagicMock()
    fake.model.tts_model_type = "base"
    QwenTorchEngine._model = fake
    QwenTorchEngine._loaded_key = cache_key
    try:
        eng = QwenTorchEngine()
        with pytest.raises(ValueError, match="Base"):
            eng.synthesize("qwen_torch/d8488443-1a2b-41d4-8ea1-66700e2d2e98", "hi", {"language": "English"})
    finally:
        QwenTorchEngine._model = None
        QwenTorchEngine._loaded_key = None


def test_integration_base_checkpoint_loads_without_meta():
    """
    If a **Base** checkpoint (voice clone) is present, full bridge load must not leave meta tensors
    (regression for d848 / tts_model_type=base + 12Hz speech_tokenizer).
    """
    import json

    import torch

    root = Path(settings.TTS_MODEL_ROOT)
    g = sorted((root / "qwen_torch").glob("*/config.json")) if (root / "qwen_torch").is_dir() else []
    base_path: Path | None = None
    for c in g:
        p = c.parent
        if not (p / "speech_tokenizer" / "config.json").is_file():
            continue
        with open(p / "config.json", encoding="utf-8") as f:
            meta = json.load(f)
        if str(meta.get("tts_model_type") or "").lower() == "base":
            base_path = p
            break
    if base_path is None:
        pytest.skip("No local Base (tts_model_type=base) qwen_torch snapshot (optional)")

    m = _load_qwen3_from_pretrained(base_path, "cpu", torch.float32)
    assert m is not None
    assert not _any_meta_tensor(m.model.speech_tokenizer.model)
