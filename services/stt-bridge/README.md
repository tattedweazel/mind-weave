# STT bridge

Local HTTP service for workflow **transcribe_audio** (faster-whisper). Mind Weave’s API calls it with `httpx`; this process may download and load CTranslate2 / Whisper models.

## Install

From `**services/stt-bridge/`**:

```bash
cd services/stt-bridge
uv sync
```

## Run

```bash
export STT_CACHE_DIR="${PWD}/../../.local/stt-models"   # optional; default is repo .local/stt-models
export STT_BRIDGE_MOCK=1   # optional: return a fixed transcript without loading models
uv run uvicorn stt_bridge.main:app --host 127.0.0.1 --port 8766
```

Point Mind Weave at `STT_BRIDGE_URL=http://127.0.0.1:8766` (see main app settings).

## Tests

```bash
uv sync --group dev
uv run python -m pytest tests/ -q
```

## Integration (Mind Weave API + in-process)

From the `**backend/**` app tree, the script `**scripts/run_voice_input_workflow_e2e.py**` creates a **Start → Voice input → Stop** graph, runs `**run_stream`**, and uploads bytes to the in-process transcribe path. Use `**--real-stt --audio tts`** to hit this service with TTS-synthesized speech (see the script’s docstring).

This bridge is also the **`local_whisper`** provider for the provider-abstracted **`transcribe_file`** skill (see [docs/WORKFLOW_SKILLS.md](../../docs/WORKFLOW_SKILLS.md#transcribe-file-provider-abstracted--skill-transcribe_file)). When `transcribe_file` runs against `local_whisper`, the API process calls the same `POST /v1/transcribe` endpoint. The script `**scripts/run_transcribe_file_workflow_e2e.py**` exercises this path (defaults mock the bridge; pass `--real-stt --audio-file …` to hit it for real).

## `POST /v1/transcribe`

- **Auth:** if `STT_BRIDGE_TOKEN` is set, send header `X-STT-Bridge-Token`.
- **Body:** `multipart/form-data` with:
  - `**file`** — audio (browser `MediaRecorder` often produces `webm`; ffmpeg-backed decoding).
  - `**task`** — optional, `transcribe` (default) or `translate`.
  - `**language**` — optional BCP-47 code; omit for auto-detect.

**Response JSON:** `text`, `segments` (list of `{start, end, text}`), `language`, `duration_seconds`, `model`.

## Environment


| Variable              | Description                                       |
| --------------------- | ------------------------------------------------- |
| `STT_BRIDGE_TOKEN`    | If set, require `X-STT-Bridge-Token`.             |
| `STT_BRIDGE_MOCK`     | `1` / `true` — no model load; fixed transcript.   |
| `STT_MODEL`           | Model size or path (default `medium`).            |
| `STT_DEVICE`          | `auto` (default), `cpu`, or `cuda`.               |
| `STT_COMPUTE_TYPE`    | Override (e.g. `int8` on CPU) when not `default`. |
| `STT_MAX_AUDIO_BYTES` | Max upload (default 75 MiB). Keep aligned with backend `STT_MAX_AUDIO_UPLOAD_BYTES`, frontend `VITE_STT_MAX_AUDIO_UPLOAD_BYTES`, and proxy `client_max_body_size`. |
| `STT_CACHE_DIR`       | Model download cache.                             |


Model weights are **not** in git; first run downloads from Hugging Face (cached under `STT_CACHE_DIR`).