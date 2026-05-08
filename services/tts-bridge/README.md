# TTS bridge

Local HTTP service for workflow **Text-to-Speech**. Mind Weave calls it with `httpx`; this process may load PyTorch / MLX and model weights.

## Install

**Recommended (same Python for installs and for the server):** from **`services/tts-bridge/`**:

```bash
cd services/tts-bridge
uv sync
```

That creates/uses **`.venv/`** in this directory and installs **`huggingface_hub`** and the rest of the bridge deps there.

**Why `uv pip install -r requirements.txt` can look like it “did nothing”:** that command installs into **whatever interpreter `uv` picks** (often a tool or global env). If you then start the app with plain **`uvicorn`** on your **`PATH`**, that binary may belong to **another** Python (Homebrew, pyenv, a different venv) that never got those packages—so **`pull`** still fails with **`No module named 'huggingface_hub'`**. Fix: either use **`uv run`** (below) or install with **`uv pip install -r requirements.txt --python $(which python3)`** after **`source .venv/bin/activate`**, and run **`python -m uvicorn ...`** from that same venv.

For **real** PyTorch synthesis, also install **`torch`** and **`qwen-tts`** per [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS) (they stay optional / commented in `requirements.txt`). **`qwen_torch`** writes **RIFF PCM16** with the stdlib **`wave`** module (same family as the mock clip) so browser **`<audio>`** matches desktop players—some **`soundfile`** WAV layouts decode in apps but show **0:00** / disabled controls in WebKit.

Legacy: **`requirements.txt`** is kept in sync with **`pyproject.toml`** for **`pip install -r`** workflows.

## Run

From **`services/tts-bridge/`**, use **`uv run`** so the server uses the project **`.venv`** from **`uv sync`**:

```bash
export TTS_MODEL_ROOT="${PWD}/../../.local/tts-models"
export TTS_BRIDGE_MOCK=1   # optional: return tiny WAV without qwen-tts
uv run uvicorn tts_bridge.main:app --host 127.0.0.1 --port 8765
```

If you activated **`.venv`** manually, **`python -m uvicorn tts_bridge.main:app --host 127.0.0.1 --port 8765`** is equivalent.

**Sanity check** (should print a path, not an error):

```bash
uv run python -c "import huggingface_hub; print(huggingface_hub.__file__)"
```

Point Mind Weave at `TTS_BRIDGE_URL=http://127.0.0.1:8765`.

## Tests

```bash
uv sync --group dev
uv run python -m pytest tests/ -q
```

## `POST /v1/tts` request body

JSON fields:

- **`engine`** — e.g. `qwen_torch`.
- **`model_local_key`** — Path key returned from **`/v1/models/pull`** (under **`TTS_MODEL_ROOT`**).
- **`text`** — Text to speak.
- **`options`** — Engine-specific options (defaults to `{}`). For **`qwen_torch`**:
  - **Voice Design** (no clone): **`language`**, **`instruct`** (or **`voice_prompt`**) when the loaded model exposes **`generate_voice_design`**.
  - **Custom voice preset** (no clone): **`speaker`**, **`language`**, **`instruct`** when the model exposes **`generate_custom_voice`** and clone fields are absent.
  - **Voice clone:** non-empty **`ref_audio_base64`** (standard base64 of a **RIFF WAV**) and non-empty **`ref_text`** (transcript of the reference audio). The bridge **decodes** the WAV and passes **`(waveform, sample_rate)`** into Qwen’s API. Passing the base64 string through unchanged is unsafe: standard base64 often contains **`/`**, and **`qwen_tts`** would treat the string as a **filesystem path** (then **`[Errno 63] File name too long`**). The checkpoint must support **`generate_voice_clone`** (typically a **Base** Qwen3-TTS build). If clone is requested but the model has no **`generate_voice_clone`**, the bridge returns **400** with an explanatory message.
- **`response_format`** — `wav` (raw bytes) or `base64_json`.

Mind Weave’s main API forwards **`options`** from workflow **`tts_options`** and, when **`voice_sample_id`** is set, adds **`ref_audio_base64`** and **`ref_text`** from **`voice_samples`**.

## Environment


| Variable              | Description                                                                                                                   |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `TTS_MODEL_ROOT`      | Root directory for downloaded weights (default: `.local/tts-models` under repo parent if exists, else `./.local/tts-models`). |
| `TTS_BRIDGE_TOKEN`    | If set, require header `X-TTS-Bridge-Token` to match.                                                                         |
| `TTS_BRIDGE_MOCK`     | If `1`, `true`, or `yes`, synthesize returns a minimal silent WAV without loading Qwen.                                       |
| `TTS_BRIDGE_DEVICE`   | For `qwen_torch`: `auto` (cuda > mps > cpu), `mps`, `cuda`, `cpu`.                                                            |
| `TTS_MAX_TEXT_CHARS`  | Max input characters (default 10000).                                                                                         |
| `TTS_MAX_AUDIO_BYTES` | Max response bytes (default 50MB).                                                                                            |


See [docs/APPLE_SILICON.md](docs/APPLE_SILICON.md) for M-series notes.