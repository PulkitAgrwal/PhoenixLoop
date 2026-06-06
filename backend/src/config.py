"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

_PROJECT_ROOT_ENV = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT_ENV),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google / Gemini
    google_api_key: str = ""
    google_genai_use_vertexai: bool = False
    gemini_model: str = "gemini-2.5-flash"

    # Arize Phoenix Cloud
    phoenix_api_key: str = ""
    phoenix_base_url: str = "https://app.phoenix.arize.com"
    phoenix_collector_endpoint: str = "https://app.phoenix.arize.com"
    phoenix_project_name: str = "phoenixloop"

    # Application
    app_env: str = "development"
    app_port: int = 8000
    database_url: str = "sqlite:///phoenixloop.db"
    frontend_url: str = "http://localhost:3000"

    # Thresholds (hackathon defaults from PRD Section 7.2)
    repeated_failure_count: int = 2
    repeated_failure_rate: float = 0.30
    critical_failure_immediate: bool = True
    cooldown_minutes: int = 30
    release_score_threshold: float = 0.75
    latency_budget_ms: int = 10000


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
