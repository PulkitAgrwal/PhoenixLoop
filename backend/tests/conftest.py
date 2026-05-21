"""Shared test fixtures for PhoenixLoop backend tests."""

import os

# Set test environment before importing anything else
os.environ["APP_ENV"] = "test"
os.environ["GOOGLE_API_KEY"] = "test-google-key"
os.environ["PHOENIX_API_KEY"] = "test-phoenix-key"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
