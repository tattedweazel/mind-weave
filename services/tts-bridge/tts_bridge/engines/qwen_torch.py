"""Official qwen-tts + PyTorch (optional dependency)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from tts_bridge.config import settings
from tts_bridge.wav_util import float_samples_to_wav_bytes, minimal_silent_wav, ref_audio_base64_to_float_wav

logger = logging.getLogger(__name__)


def _resolve_device() -> str:
    d = settings.TTS_BRIDGE_DEVICE
    if d != "auto":
        return d
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda:0"
        if getattr(torch.backends, "mps", None) and torch.backends.mps.is_available():
            return "mps"
    except Exception:
        pass
    return "cpu"


def _weight_dtype_for_device(device: str) -> Any:
    """Per-device dtype for weights and inference.

    **MPS** has spotty support for reduced precision: both **bfloat16** and **float16** can surface
    PyTorch \"unsupported scalarType\" in Qwen3-TTS-style models. Use **float32** on MPS for
    compatibility (more VRAM unified memory). CUDA keeps **bfloat16**; CPU uses **float32**.
    """
    import torch

    if device == "cpu":
        return torch.float32
    if device == "mps":
        return torch.float32
    return torch.bfloat16


def _qwen3_from_pretrained_load_kwargs(dtype: Any) -> dict[str, Any]:
    """
    Kwargs for ``Qwen3TTSModel.from_pretrained`` (HuggingFace ``AutoModel``).

    - Current Transformers uses **`dtype`**; **`torch_dtype`** is deprecated. In some versions, the
      deprecated key is *not* forwarded consistently to nested loads (e.g. speech_tokenizer
      inside ``Qwen3TTSForConditionalGeneration``), which can leave submodules on **meta** and
      later break with *"Cannot copy out of meta tensor"*.
    - **low_cpu_mem_usage=False** with **device_map=None** and **local_files_only=True** (for local
      snapshot dirs) avoids accelerate empty-weight / cache paths that show up as meta tensors.
    - Callers that hit ``TypeError`` (older stacks) can retry with ``torch_dtype`` only.
    """
    return {
        "dtype": dtype,
        "low_cpu_mem_usage": False,
        "device_map": None,
        "local_files_only": True,
    }


# Bumps QwenTorchEngine cache when load logic changes; long-running workers must not keep stale models.
TTS_QWEN_LOAD_CACHE_REVISION = "st_mat_v4"


def _any_meta_tensor(module: Any) -> bool:
    """True if any parameter or buffer is on the PyTorch meta device (empty init)."""
    if module is None:
        return False
    try:
        for t in list(module.parameters()) + list(module.buffers()):
            if getattr(t, "is_meta", False):
                return True
    except Exception:
        return False
    return False


def _ensure_qwen_speech_tokenizer_automodel_registry() -> None:
    """Register Qwen speech-tokenizer config/model classes with HuggingFace Auto* (same as Qwen3TTSTokenizer)."""
    from transformers import AutoConfig, AutoModel

    from qwen_tts.core import (
        Qwen3TTSTokenizerV1Config,
        Qwen3TTSTokenizerV1Model,
        Qwen3TTSTokenizerV2Config,
        Qwen3TTSTokenizerV2Model,
    )

    AutoConfig.register("qwen3_tts_tokenizer_25hz", Qwen3TTSTokenizerV1Config)
    AutoModel.register(Qwen3TTSTokenizerV1Config, Qwen3TTSTokenizerV1Model)
    AutoConfig.register("qwen3_tts_tokenizer_12hz", Qwen3TTSTokenizerV2Config)
    AutoModel.register(Qwen3TTSTokenizerV2Config, Qwen3TTSTokenizerV2Model)


def _load_state_dict_flexible(model: Any, state: Any, *, strict: bool) -> None:
    """``load_state_dict`` with ``assign=`` on newer PyTorch (helps some meta edge cases)."""
    import inspect

    sig = inspect.signature(model.load_state_dict)
    if "assign" in sig.parameters:
        model.load_state_dict(state, strict=strict, assign=True)
    else:
        model.load_state_dict(state, strict=strict)


def _speech_tokenizer_inner_materialize_last_resort(speech_dir: Path) -> Any:
    """
    Last-resort materialization of the inner speech-tokenizer ``AutoModel`` on CPU, when
    ``Qwen3TTSTokenizer.from_pretrained`` still leaves **meta** tensors. Tries several strategies so
    different torch/transformers versions and sharded / single safetensors layouts work.
    """
    import torch
    from safetensors.torch import load_file
    from transformers import AutoConfig, AutoModel
    from transformers.modeling_utils import load_sharded_checkpoint
    from transformers.utils import SAFE_WEIGHTS_INDEX_NAME, WEIGHTS_INDEX_NAME

    _ensure_qwen_speech_tokenizer_automodel_registry()
    sp = str(speech_dir)
    err_chain: list[str] = []

    def _ok(name: str, model: Any) -> Any:
        if _any_meta_tensor(model):
            raise RuntimeError(f"inner model still has meta after {name}")
        return model

    # 1) PreTrainedModel standard load (streamed; often survives when raw load_file OOMs).
    try:
        m = AutoModel.from_pretrained(
            sp,
            dtype=torch.float32,
            low_cpu_mem_usage=False,
            device_map=None,
            local_files_only=True,
        )
        return _ok("AutoModel.from_pretrained(float32,local_files_only=True)", m)
    except Exception as e:
        err_chain.append(f"from_pretrained: {type(e).__name__}: {e}")

    # 2) from_config + single file safetensors
    try:
        cfg = AutoConfig.from_pretrained(sp, local_files_only=True)
        model = AutoModel.from_config(cfg)
        w = speech_dir / "model.safetensors"
        if w.is_file():
            state = load_file(str(w))
            _load_state_dict_flexible(model, state, strict=False)
        else:
            raise FileNotFoundError(f"no model.safetensors in {speech_dir}")
        model = model.to(dtype=torch.float32)
        return _ok("from_config+load_file(model.safetensors)", model)
    except Exception as e:
        err_chain.append(f"from_config+load_file: {type(e).__name__}: {e}")

    # 3) sharded safetensors (index + model-*.safetensors) — more RAM-friendly per shard
    if (speech_dir / SAFE_WEIGHTS_INDEX_NAME).is_file() or (speech_dir / WEIGHTS_INDEX_NAME).is_file():
        try:
            cfg = AutoConfig.from_pretrained(sp, local_files_only=True)
            model = AutoModel.from_config(cfg)
            load_sharded_checkpoint(model, sp, strict=False, prefer_safe=True)
            model = model.to(dtype=torch.float32)
            return _ok("load_sharded_checkpoint", model)
        except Exception as e:
            err_chain.append(f"sharded: {type(e).__name__}: {e}")
    # 4) pytorch_model.bin
    pbin = speech_dir / "pytorch_model.bin"
    if pbin.is_file():
        try:
            cfg = AutoConfig.from_pretrained(sp, local_files_only=True)
            model = AutoModel.from_config(cfg)
            try:
                blob = torch.load(str(pbin), map_location="cpu", weights_only=True)
            except TypeError:
                blob = torch.load(str(pbin), map_location="cpu")
            if isinstance(blob, dict):
                _load_state_dict_flexible(model, blob, strict=False)
            model = model.to(dtype=torch.float32)
            return _ok("from_config+torch.load(pytorch_model.bin)", model)
        except Exception as e:
            err_chain.append(f"pytorch_model.bin: {type(e).__name__}: {e}")

    # 5) allow Hub/cache resolution (broken partial local trees)
    try:
        m = AutoModel.from_pretrained(
            sp,
            dtype=torch.float32,
            low_cpu_mem_usage=False,
            device_map=None,
            local_files_only=False,
        )
        return _ok("from_pretrained(float32,local_files_only=False)", m)
    except Exception as e:
        err_chain.append(f"from_pretrained_lfo_off: {type(e).__name__}: {e}")

    msg = " | ".join(err_chain) if err_chain else "unknown"
    raise RuntimeError(f"All inner speech_tokenizer materialization strategies failed. Details: {msg}")


# Back-compat name for tests / logs
_speech_tokenizer_inner_from_safetensors_cpu = _speech_tokenizer_inner_materialize_last_resort


def _build_qwen3_tts_tokenizer_with_inner(
    speech_dir: Path,
    inner_model: Any,
) -> Any:
    """Assemble ``Qwen3TTSTokenizer`` with a pre-built inner ``AutoModel`` (avoids broken from_pretrained)."""
    import torch
    from transformers import AutoFeatureExtractor

    from qwen_tts.inference.qwen3_tts_tokenizer import Qwen3TTSTokenizer

    st = Qwen3TTSTokenizer()
    sp = str(speech_dir)
    try:
        st.feature_extractor = AutoFeatureExtractor.from_pretrained(sp, local_files_only=True)
    except Exception as e1:
        logger.warning("Feature extractor local_files_only load failed; retrying without: %s", e1)
        st.feature_extractor = AutoFeatureExtractor.from_pretrained(sp, local_files_only=False)
    st.model = inner_model
    st.config = st.model.config
    try:
        st.device = next(st.model.parameters()).device
    except StopIteration:
        st.device = torch.device("cpu")
    return st


def _sync_speech_tokenizer_device(qwen_for_cond: Any, dev: Any) -> None:
    """
    ``Qwen3TTSTokenizer`` is not an ``nn.Module``; it is not moved by ``Qwen3TTSForConditionalGeneration.to()``.
    Move the inner HF model explicitly to match ``dev``.
    """
    st = getattr(qwen_for_cond, "speech_tokenizer", None)
    if st is None or getattr(st, "model", None) is None:
        return
    st.model.to(dev)
    try:
        st.device = next(st.model.parameters()).device
    except StopIteration:
        st.device = dev


def _reload_speech_tokenizer_from_disk(path: Path, dtype: Any, m: Any) -> None:
    """
    Re-load ``speech_tokenizer`` with explicit anti-meta kwargs.

    Upstream ``Qwen3TTSForConditionalGeneration.from_pretrained`` passes a depleted ``**kwargs`` into
    ``Qwen3TTSTokenizer.from_pretrained``, so the inner ``AutoModel`` can load with different defaults
    and leave **meta** tensors. Parent ``.to(device)`` then fails. We replace the attached tokenizer
    with one loaded using the same policy as the main module.
    """
    speech_dir = (path / "speech_tokenizer").resolve()
    if not speech_dir.is_dir():
        raise FileNotFoundError(
            f"Qwen3 TTS requires a `speech_tokenizer` directory next to the checkpoint: {speech_dir}. "
            "Re-pull the model snapshot or fix the on-disk layout."
        )

    from qwen_tts.inference.qwen3_tts_tokenizer import Qwen3TTSTokenizer

    import torch

    def _st_from_kw(lkw: dict[str, Any]) -> Any:
        try:
            return Qwen3TTSTokenizer.from_pretrained(str(speech_dir), **lkw)
        except TypeError:
            l2 = {k: v for k, v in lkw.items() if k != "dtype"}
            l2["torch_dtype"] = lkw.get("dtype", dtype)
            return Qwen3TTSTokenizer.from_pretrained(str(speech_dir), **l2)

    def _st_inner() -> Any:
        return getattr(m.model.speech_tokenizer, "model", None)

    # Ordered attempts: normal dtype → float32 → allow HF cache (not local_files_only) → materialize from safetensors.
    attempts: list[tuple[str, dict[str, Any]]] = [
        ("primary", _qwen3_from_pretrained_load_kwargs(dtype)),
    ]
    if dtype != torch.float32:
        attempts.append(("float32", _qwen3_from_pretrained_load_kwargs(torch.float32)))
    lfo_off = {**_qwen3_from_pretrained_load_kwargs(torch.float32), "local_files_only": False}
    attempts.append(("float32_lfo_off", lfo_off))

    for name, lkw in attempts:
        st = _st_from_kw(lkw)
        m.model.load_speech_tokenizer(st)
        inn = _st_inner()
        if inn is not None and not _any_meta_tensor(inn):
            logger.info("Speech tokenizer inner model materialized (strategy=%s, path=%s)", name, path)
            return
        logger.warning(
            "Speech tokenizer inner still has meta after strategy=%s; next fallback (path=%s)", name, path
        )

    # Last resort: direct AutoModel / from_config+weights / sharded (see _speech_tokenizer_inner_materialize_last_resort).
    try:
        inner = _speech_tokenizer_inner_materialize_last_resort(speech_dir)
    except Exception as e:
        logger.exception("Speech tokenizer last-resort materialization failed for %s", path)
        raise RuntimeError(
            f"Speech tokenizer could not be materialized (path={path}). "
            f"Root cause: {type(e).__name__}: {e} "
            "(If this is a RAM/OOM, close other processes or set TTS_BRIDGE_DEVICE=cpu; "
            "if deserialization or key mismatch, re-download the snapshot or remove a corrupted .cache under the model directory.)"
        ) from e
    st = _build_qwen3_tts_tokenizer_with_inner(speech_dir, inner)
    m.model.load_speech_tokenizer(st)
    inn = _st_inner()
    if inn is None or _any_meta_tensor(inn):
        raise RuntimeError(
            f"Speech tokenizer AutoModel is still on meta after safetensors re-load (path={path})."
        )


def _load_qwen3_from_pretrained(path: Path, device: str, dtype: Any) -> Any:
    """Load on CPU (real weights), re-materialize speech_tokenizer, then move to target device."""
    import torch
    from qwen_tts import Qwen3TTSModel

    def _main_from_kw(lkw: dict[str, Any]) -> Any:
        try:
            return Qwen3TTSModel.from_pretrained(str(path), **lkw)
        except TypeError:
            l2 = {k: v for k, v in lkw.items() if k != "dtype"}
            l2["torch_dtype"] = lkw.get("dtype", dtype)
            l2["low_cpu_mem_usage"] = False
            l2["device_map"] = None
            if "local_files_only" not in l2:
                l2["local_files_only"] = True
            return Qwen3TTSModel.from_pretrained(str(path), **l2)

    load_kw = _qwen3_from_pretrained_load_kwargs(dtype)
    m = _main_from_kw(load_kw)

    _reload_speech_tokenizer_from_disk(path, dtype, m)

    if _any_meta_tensor(m.model):
        logger.warning(
            "Qwen3 TTS has meta tensors with dtype=%s; retrying full load in float32 (path=%s)", dtype, path
        )
        f32kw = _qwen3_from_pretrained_load_kwargs(torch.float32)
        m = _main_from_kw(f32kw)
        _reload_speech_tokenizer_from_disk(path, torch.float32, m)

    if _any_meta_tensor(m.model):
        raise RuntimeError(
            f"Qwen3 TTS still has meta tensors after float32 retry (path={path}). "
            "The checkpoint may be incomplete; re-download or set TTS_BRIDGE_DEVICE=cpu and restart."
        )

    dev = torch.device(device)
    try:
        m.model.to(dev)
    except NotImplementedError as e:
        if "meta tensor" in str(e).lower() or "to_empty" in str(e).lower():
            raise RuntimeError(
                f"Failed to move Qwen3 TTS to {device} (meta tensor / materialization). "
                f"Try TTS_BRIDGE_DEVICE=cpu. Original: {e}"
            ) from e
        raise
    # Qwen3TTSTokenizer is a plain object; not moved by the parent .to() above.
    try:
        _sync_speech_tokenizer_device(m.model, dev)
    except NotImplementedError as e:
        if "meta tensor" in str(e).lower() or "to_empty" in str(e).lower():
            raise RuntimeError(
                f"Failed to move speech_tokenizer.model to {device}. Try TTS_BRIDGE_DEVICE=cpu. Original: {e}"
            ) from e
        raise
    m.device = dev
    return m


class QwenTorchEngine:
    engine_key = "qwen_torch"
    _model = None
    _loaded_key: str | None = None

    def _dest_dir(self, artifact_id: str) -> Path:
        root = Path(settings.TTS_MODEL_ROOT)
        return root / self.engine_key / artifact_id

    def pull(self, artifact_id: str, source: dict[str, Any]) -> str:
        kind = source.get("kind")
        dest = self._dest_dir(artifact_id)
        dest.mkdir(parents=True, exist_ok=True)
        if kind == "huggingface_repo":
            try:
                from huggingface_hub import snapshot_download
            except ImportError as e:
                raise ImportError(
                    "huggingface_hub is required for qwen_torch pulls. "
                    "Install bridge deps: cd services/tts-bridge && uv pip install -r requirements.txt"
                ) from e
            repo_id = source.get("repo_id")
            if not repo_id or not isinstance(repo_id, str):
                raise ValueError("source.repo_id required for huggingface_repo")
            revision = source.get("revision")
            snapshot_download(
                repo_id=repo_id,
                revision=revision if isinstance(revision, str) else None,
                local_dir=str(dest),
                local_dir_use_symlinks=False,
            )
        elif kind == "url":
            raise NotImplementedError("url pull not implemented for qwen_torch; use huggingface_repo")
        else:
            raise ValueError(f"Unknown source.kind: {kind!r}")
        return f"{self.engine_key}/{artifact_id}"

    def synthesize(self, model_local_key: str, text: str, options: dict[str, Any]) -> bytes:
        if settings.TTS_BRIDGE_MOCK:
            return minimal_silent_wav()

        root = Path(settings.TTS_MODEL_ROOT).resolve()
        path = (root / model_local_key).resolve()
        try:
            path.relative_to(root)
        except ValueError as e:
            raise ValueError("model_local_key escapes TTS_MODEL_ROOT") from e
        if not path.exists():
            raise FileNotFoundError(f"Model path not found: {path}")

        try:
            import torch
            from qwen_tts import Qwen3TTSModel
        except ImportError as e:
            logger.warning("qwen-tts stack not installed; returning mock WAV (%s)", e)
            return minimal_silent_wav()

        device = _resolve_device()
        dtype = _weight_dtype_for_device(device)

        # Include device, dtype, and load revision so deploys bust stale in-process cached models.
        cache_key = f"{path}|{device}|{dtype}|{TTS_QWEN_LOAD_CACHE_REVISION}"
        if QwenTorchEngine._loaded_key != cache_key or QwenTorchEngine._model is None:
            logger.info("Loading Qwen3 TTS from %s (target device=%s, dtype=%s)", path, device, dtype)
            QwenTorchEngine._model = _load_qwen3_from_pretrained(path, device, dtype)
            QwenTorchEngine._loaded_key = cache_key

        model = QwenTorchEngine._model
        language = str(options.get("language") or "English")
        instruct = str(options.get("instruct") or options.get("voice_prompt") or "")

        ref_b64 = options.get("ref_audio_base64")
        ref_txt = options.get("ref_text")
        use_clone = (
            ref_b64 is not None
            and str(ref_b64).strip() != ""
            and ref_txt is not None
            and str(ref_txt).strip() != ""
        )

        m_inner = getattr(model, "model", None)
        tts_type = str(getattr(m_inner, "tts_model_type", "") or "")

        if use_clone:
            if not hasattr(model, "generate_voice_clone"):
                raise ValueError(
                    "Voice clone requires a Qwen3-TTS Base checkpoint (e.g. *-Base). "
                    "This model does not support generate_voice_clone."
                )
            try:
                ref_wav, ref_sr = ref_audio_base64_to_float_wav(str(ref_b64))
            except ValueError as e:
                raise ValueError(
                    "Invalid reference audio in options.ref_audio_base64 "
                    "(expected base64-encoded RIFF/WAV from Voice Sample Manager)."
                ) from e
            wavs, sr = model.generate_voice_clone(
                text=text,
                language=language,
                ref_audio=(ref_wav, ref_sr),
                ref_text=str(ref_txt).strip(),
            )
        elif tts_type == "base":
            raise ValueError(
                "This checkpoint is Qwen3-TTS **Base** (voice clone only for non-mock use). "
                "For text-only TTS, register a **Voice Design** model, or supply "
                "ref_audio_base64 and ref_text (e.g. via a voice sample on the node)."
            )
        elif tts_type == "voice_design":
            wavs, sr = model.generate_voice_design(
                text=text,
                language=language,
                instruct=instruct or "Speak clearly.",
            )
        elif tts_type == "custom_voice":
            speaker = str(options.get("speaker") or "Vivian")
            wavs, sr = model.generate_custom_voice(
                text=text,
                language=language,
                speaker=speaker,
                instruct=instruct or "Speak naturally.",
            )
        else:
            raise RuntimeError(
                f"Unknown Qwen3 tts_model_type {tts_type!r}; expected base | voice_design | custom_voice"
            )

        arr = wavs[0] if isinstance(wavs, (list, tuple)) else wavs
        if hasattr(arr, "detach") and callable(getattr(arr, "detach", None)):
            arr = arr.detach().cpu().numpy()
        # Stdlib RIFF PCM16 — best browser <audio> compatibility (soundfile layouts can break WebKit).
        return float_samples_to_wav_bytes(arr, int(sr))
