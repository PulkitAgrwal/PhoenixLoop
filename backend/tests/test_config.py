"""Tests for configuration module."""

import os
import pytest
from src.config import Settings


class TestSettings:
    def test_default_thresholds(self):
        """Verify hackathon default threshold values."""
        settings = Settings(
            google_api_key="test",
            phoenix_api_key="test",
        )
        assert settings.repeated_failure_count == 2
        assert settings.repeated_failure_rate == 0.30
        assert settings.critical_failure_immediate is True
        assert settings.cooldown_minutes == 30
        assert settings.release_score_threshold == 0.75
        assert settings.latency_budget_ms == 10000

    def test_default_app_settings(self):
        """Verify default application settings."""
        settings = Settings(
            google_api_key="test",
            phoenix_api_key="test",
        )
        assert settings.app_env == "development"
        assert settings.app_port == 8000
        assert settings.frontend_url == "http://localhost:3000"
        assert settings.phoenix_project_name == "phoenixloop"

    def test_env_var_override(self, monkeypatch):
        """Settings should load from environment variables."""
        monkeypatch.setenv("GOOGLE_API_KEY", "my-google-key")
        monkeypatch.setenv("PHOENIX_API_KEY", "my-phoenix-key")
        monkeypatch.setenv("REPEATED_FAILURE_COUNT", "5")
        monkeypatch.setenv("APP_ENV", "production")
        settings = Settings()
        assert settings.google_api_key == "my-google-key"
        assert settings.phoenix_api_key == "my-phoenix-key"
        assert settings.repeated_failure_count == 5
        assert settings.app_env == "production"

    def test_phoenix_defaults(self):
        """Verify Phoenix Cloud default URLs."""
        settings = Settings(
            google_api_key="test",
            phoenix_api_key="test",
        )
        assert settings.phoenix_base_url == "https://app.phoenix.arize.com"
        assert settings.phoenix_collector_endpoint == "https://app.phoenix.arize.com"
