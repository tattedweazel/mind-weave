# Apple Silicon (M4) and TTS engines

Mind Weave’s **tts-bridge** supports multiple **`TtsEngine`** implementations:

- **`qwen_torch`** — Official [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) via the `qwen-tts` PyTorch stack. On macOS, PyTorch typically uses **`mps`** when **`TTS_BRIDGE_DEVICE=auto`**; set **`TTS_BRIDGE_DEVICE=cpu`** to force CPU. The bridge **loads the main HF model** with **`device_map=None`**, **`low_cpu_mem_usage=False`**, and **`torch_dtype=…`**, then **re-loads `speech_tokenizer` from `\<checkpoint\>/speech_tokenizer` with the same policy**: upstream `Qwen3TTSForConditionalGeneration.from_pretrained` passes a **thinned** `**kwargs` into the tokenizer’s `AutoModel`, which can leave the speech submodule on **meta**; re-loading fixes that. The **`Qwen3TTSTokenizer`** wrapper is **not** an `nn.Module`, so the bridge **explicitly** moves **`speech_tokenizer.model`** to the same device as the talker (parent `.to(mps|cuda:0|…)` does not recurse there). The in-process model cache key includes a **revision** (`TTS_QWEN_LOAD_CACHE_REVISION` in code) so **restarting the bridge** after a bridge upgrade picks up new load logic. Weights use **float32** on **MPS** and **CPU**; **CUDA** uses **bfloat16** for memory. If you still see *“Cannot copy out of meta tensor”* on **`qwen_torch`**, the HTTP status should be **500** (PyTorch raises **`NotImplementedError`** for that case; the bridge maps it to **500**, not **501**). **Restart tts-bridge** first, then set **`TTS_BRIDGE_DEVICE=cpu`**. If synthesis is too heavy on RAM, CPU-only is the slower but predictable fallback.
- **`qwen_mlx`** — Placeholder for an MLX + converted-weights path. It returns **501** until implemented; use **`qwen_torch`** or enable **`TTS_BRIDGE_MOCK=1`** for integration tests without GPU.

## Recommended Phase 0 checks (on target hardware)

1. Install bridge deps: `pip install -r requirements.txt` (from `services/tts-bridge/`).
2. Set `TTS_MODEL_ROOT` to a writable directory (default: repo `.local/tts-models` if unset).
3. Pull a model via Mind Weave admin **TTS models** (or `POST /v1/models/pull` on the bridge).
4. `GET /health` then `POST /v1/tts` with a short string; compare peak RAM and latency for **`qwen_torch`** vs any future **`qwen_mlx`** build.

See [MLX](https://github.com/ml-explore/mlx) and community Qwen3-TTS MLX ports for research only; review licenses and weight provenance before production use.
