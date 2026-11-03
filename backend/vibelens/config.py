from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Runtime configuration from the environment (prefix ``VIBELENS_``) or ``.env``."""

    model_config = SettingsConfigDict(env_prefix="VIBELENS_", env_file=".env", extra="ignore")

    # "anthropic" uses Claude; "scripted" is a deterministic offline model for tests and demos.
    llm: str = "anthropic"
    model: str = "claude-opus-5-5"
    scripted_delay: float = 0.0
    summary_effort: str = "medium"
    chat_effort: str = "low"
    max_tool_steps: int = 5

    # "fastembed" is a small local model; "hash" is dependency-free and used by the unit tests.
    embedder: str = "fastembed"
    embedding_dim: int = 384
    # faster-whisper model for uploaded audio and video (runs locally on CPU).
    whisper_model: str = "base.en"

    data_dir: Path = ROOT / "data"
    sample_video: Path = ROOT / "samples" / "forward-deployment.mp4"
    sample_transcript: Path = ROOT / "samples" / "forward-deployment.vtt"
    max_upload_mb: int = 300
    max_minutes: int = 180
    # A cited timestamp counts as verified if it falls within this many seconds of text the agent actually read.
    cite_tolerance: float = 5.0
    cors_origins: list[str] = ["http://localhost:5173"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
