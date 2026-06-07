"""Application configuration loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
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

    # Demo / auto-seed
    # ``lightweight_demo`` makes the lifespan auto-seed read pre-recorded
    # JSON fixtures from ``backend/tests/fixtures/seed/`` instead of making
    # any Gemini calls. Used for UI iteration without burning the token
    # budget. Live mode (default) goes through the full pipeline.
    lightweight_demo: bool = False
    enable_llm_tool_evals: bool = False

    # When true, the lifespan skips the background full_loop_seed task so the
    # DB stays empty after a fresh `docker compose up -v` reset.
    skip_autoseed: bool = False

    demo_force_pending_review: bool = Field(
        default=False,
        description=(
            "When true, the live healing seed coerces the release-gate verdict "
            "to PENDING_HUMAN_REVIEW so demo viewers always see the human-approval "
            "step. Has no effect on production agent runs."
        ),
    )

    demo_force_failure: bool = Field(
        default=False,
        description=(
            "When true, the live SSE healing loop strips the citations field "
            "from the 2nd and 4th tickets' agent responses BEFORE evals run, "
            "so the citation_presence evaluator deterministically fails twice. "
            "This is what produces the cluster threshold + healing trigger for "
            "the 'Watch it heal' demo. The agent's actual Gemini calls and "
            "Phoenix traces are untouched."
        ),
    )


@lru_cache
def get_settings() -> Settings:
    """Get cached application settings singleton."""
    return Settings()
