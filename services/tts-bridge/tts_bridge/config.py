"""Bridge settings (env)."""

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_model_root() -> Path:
    # Prefer monorepo .local/tts-models: services/tts-bridge -> repo root is parent.parent.parent
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    candidate = repo_root / ".local" / "tts-models"
    if candidate.parent.exists():
        return candidate
    return Path.cwd() / ".local" / "tts-models"


class BridgeSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    TTS_MODEL_ROOT: Path = _default_model_root()
    TTS_BRIDGE_TOKEN: str = ""
    TTS_BRIDGE_MOCK: bool = False
    TTS_BRIDGE_DEVICE: Literal["auto", "mps", "cuda", "cpu"] = "auto"
    TTS_MAX_TEXT_CHARS: int = 10_000
    TTS_MAX_AUDIO_BYTES: int = 50 * 1024 * 1024


settings = BridgeSettings()
