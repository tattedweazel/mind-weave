"""Settings for the STT bridge."""

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


def _default_cache_root() -> Path:
    repo_parent = Path(__file__).resolve().parent.parent.parent.parent
    p = repo_parent / ".local" / "stt-models"
    if p.is_dir() or (repo_parent / ".local").is_dir():
        return p
    return Path(__file__).resolve().parent / ".local" / "stt-models"


class Settings(BaseSettings):
    STT_BRIDGE_TOKEN: str = ""
    """If set, require header X-STT-Bridge-Token to match."""
    STT_BRIDGE_MOCK: bool = False
    """If true, return a fixed transcript without loading faster-whisper."""
    STT_MODEL: str = "medium"
    """faster-whisper model name or path (e.g. small, medium, large-v3)."""
    STT_DEVICE: str = "auto"
    """auto | cpu | cuda | int8 | int8_float16 (passed to faster-whisper)."""
    STT_COMPUTE_TYPE: str = "default"
    """default or explicit compute type for faster-whisper (e.g. int8 for CPU)."""
    STT_MAX_AUDIO_BYTES: int = 75 * 1024 * 1024
    """Max uploaded audio size (75 MiB)."""
    STT_CACHE_DIR: Path = _default_cache_root()
    """Download cache for CTranslate2 / model files."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
