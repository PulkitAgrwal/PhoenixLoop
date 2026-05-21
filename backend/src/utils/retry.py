"""Retry decorator with exponential backoff for external calls."""

import asyncio
import functools
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable:
    """Decorator that retries async functions with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts before giving up.
        backoff_base: Base delay in seconds for first retry.
        backoff_factor: Multiplier applied to delay after each retry.
        retryable_exceptions: Tuple of exception types that trigger a retry.
    """
    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exception: Exception | None = None
            for attempt in range(1, max_attempts + 1):
                try:
                    return await func(*args, **kwargs)
                except retryable_exceptions as e:
                    last_exception = e
                    if attempt < max_attempts:
                        delay = backoff_base * (backoff_factor ** (attempt - 1))
                        logger.warning(
                            "Retry %d/%d for %s: %s. Retrying in %.1fs",
                            attempt,
                            max_attempts,
                            func.__name__,
                            str(e),
                            delay,
                        )
                        await asyncio.sleep(delay)
                    else:
                        logger.error(
                            "Final attempt %d/%d for %s failed: %s",
                            attempt,
                            max_attempts,
                            func.__name__,
                            str(e),
                            exc_info=True,
                        )
            raise last_exception  # type: ignore[misc] -- last_exception is always set after the loop
        return wrapper
    return decorator
