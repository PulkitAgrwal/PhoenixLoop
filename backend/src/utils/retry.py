"""Retry decorator with exponential backoff for external calls.

Supports an optional ``delay_resolver`` callback that lets a caller honor
server-suggested retry delays (e.g. Gemini's ``RetryInfo.retryDelay`` on 429
responses) instead of fixed exponential backoff.
"""

import asyncio
import functools
import logging
import re
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

_RATE_LIMIT_DELAY_CAP_SECONDS = 30.0


def retry(
    max_attempts: int = 3,
    backoff_base: float = 1.0,
    backoff_factor: float = 2.0,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
    delay_resolver: Optional[Callable[[Exception], Optional[float]]] = None,
) -> Callable:
    """Decorator that retries async functions with exponential backoff.

    Args:
        max_attempts: Maximum number of attempts before giving up.
        backoff_base: Base delay in seconds for the first retry.
        backoff_factor: Multiplier applied to delay after each retry.
        retryable_exceptions: Tuple of exception types that trigger a retry.
        delay_resolver: Optional callback ``(exc) -> seconds | None``. When it
            returns a non-None value, that value is used in place of the
            exponential backoff for the next sleep. The value is capped at
            ``_RATE_LIMIT_DELAY_CAP_SECONDS`` so a misbehaving server cannot
            stall the caller indefinitely.
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
                        if delay_resolver is not None:
                            suggested = delay_resolver(e)
                            if suggested is not None:
                                delay = min(suggested, _RATE_LIMIT_DELAY_CAP_SECONDS)
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


_RETRY_DELAY_REGEX = re.compile(r"['\"]retryDelay['\"]\s*:\s*['\"](\d+(?:\.\d+)?)s['\"]")


def extract_gemini_retry_delay(exc: Exception) -> Optional[float]:
    """Return the server-suggested retry delay (seconds) from a Gemini 429.

    The Gemini SDK raises ``google.genai.errors.ClientError`` whose string form
    embeds the original error JSON, including a ``RetryInfo`` block with a
    ``retryDelay`` field like ``"12s"``. We parse it out so the retry decorator
    can wait exactly as long as Google asks.

    Returns None if the exception isn't a Gemini rate-limit error.
    """
    text = str(exc)
    if "RESOURCE_EXHAUSTED" not in text and "429" not in text:
        return None
    match = _RETRY_DELAY_REGEX.search(text)
    if match is None:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def retry_on_rate_limit(max_attempts: int = 3) -> Callable:
    """Retry decorator pre-wired for Gemini 429 responses.

    Catches any exception (so the SDK's typed errors and bare ``Exception`` both
    work), reads ``retryDelay`` from the error body, and sleeps for exactly that
    long before retrying. Falls back to exponential backoff when the delay
    can't be parsed.
    """
    return retry(
        max_attempts=max_attempts,
        backoff_base=2.0,
        retryable_exceptions=(Exception,),
        delay_resolver=extract_gemini_retry_delay,
    )
