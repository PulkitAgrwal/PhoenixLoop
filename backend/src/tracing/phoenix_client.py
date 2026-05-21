"""Phoenix client singleton for PhoenixLoop."""

import logging
from functools import lru_cache
from typing import Optional

from phoenix.client import Client

logger = logging.getLogger(__name__)


@lru_cache
def get_phoenix_client() -> Optional[Client]:
    """Get cached Phoenix client singleton.

    Returns:
        Phoenix Client instance connected to Phoenix Cloud, or None if
        the API key is not configured or the client cannot be initialised.
    """
    from src.config import get_settings

    settings = get_settings()

    if not settings.phoenix_api_key:
        logger.warning("PHOENIX_API_KEY not set, Phoenix client will be unavailable")
        return None

    try:
        client = Client(
            endpoint=settings.phoenix_base_url,
            api_key=settings.phoenix_api_key,
        )
        logger.info("Phoenix client initialized for %s", settings.phoenix_base_url)
        return client
    except ImportError:
        logger.warning("arize-phoenix-client not installed, Phoenix unavailable")
        return None
    except Exception as exc:
        logger.error("Failed to initialize Phoenix client: %s", exc)
        return None
