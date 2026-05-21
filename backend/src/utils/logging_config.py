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
