"""Structured logging configuration for PhoenixLoop."""

import logging
import sys


def setup_logging(app_env: str = "development") -> None:
    """Configure logging for the application.

    Args:
        app_env: Application environment. "development" uses human-readable format,
                 anything else uses structured JSON-like format.
    """
    level = logging.DEBUG if app_env == "development" else logging.INFO

    if app_env == "development":
        fmt = "%(asctime)s | %(levelname)-7s | %(name)s:%(funcName)s | %(message)s"
    else:
        fmt = '{"timestamp":"%(asctime)s","level":"%(levelname)s","logger":"%(name)s","function":"%(funcName)s","message":"%(message)s"}'

    formatter = logging.Formatter(fmt)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(level)
    if not root.handlers:
        root.addHandler(handler)

    # Silence verbose DEBUG traces from third-party libraries. Each aiosqlite op
    # logs start+complete, and httpcore logs every TCP/TLS lifecycle step — they
    # drown the application's own logs when the root level is DEBUG.
    for noisy in ("aiosqlite", "httpcore", "httpx", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    # Google ADK and google-genai emit the full LLM request + response payload
    # at DEBUG level on every turn. Useful for one-off agent debugging but
    # overwhelming during normal runs — pin them at INFO.
    for verbose_sdk in ("google_adk", "google_genai", "google.adk", "google.genai"):
        logging.getLogger(verbose_sdk).setLevel(logging.INFO)
