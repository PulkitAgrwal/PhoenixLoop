"""Defensive JSON parser for LLM responses.

Even with ``response_mime_type="application/json"`` set, Gemini occasionally
returns: markdown-fenced JSON, prose before/after the object, or a single-key
wrapper with the real JSON encoded as a string inside it. This module strips
those wrappers and validates the result against a Pydantic schema before the
caller gets to see it.
"""

import json
import logging
import re
from typing import Type, TypeVar

from pydantic import BaseModel, ValidationError

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_FENCE_PATTERN = re.compile(r"^```(?:json)?\s*\n?(.*?)\n?```$", re.DOTALL)
_OBJECT_PATTERN = re.compile(r"\{.*\}", re.DOTALL)


class LLMJsonParseError(ValueError):
    """Raised when an LLM response cannot be coerced into the target schema."""


def parse_llm_json(raw: str, schema: Type[T]) -> T:
    """Parse and validate an LLM response into ``schema``.

    Repair steps, applied in order until one succeeds:

    1. Strip ``` or ```json fences around the entire text.
    2. ``schema.model_validate_json(...)`` on the candidate string.
    3. Extract the first balanced ``{...}`` block via regex and revalidate.
    4. If the extracted block is a one-key dict whose value is itself a JSON
       string, unwrap one level and revalidate (handles double-encoding).

    Raises ``LLMJsonParseError`` if every attempt fails.
    """
    if not raw or not raw.strip():
        raise LLMJsonParseError("Empty LLM response")

    candidate = _strip_fences(raw.strip())

    try:
        return schema.model_validate_json(candidate)
    except ValidationError:
        pass

    extracted = _extract_first_object(candidate)
    if extracted is not None:
        try:
            return schema.model_validate_json(extracted)
        except ValidationError:
            unwrapped = _unwrap_string_encoded(extracted)
            if unwrapped is not None:
                try:
                    return schema.model_validate_json(unwrapped)
                except ValidationError as exc:
                    logger.debug("Final repair attempt failed: %s", exc)

    snippet = candidate[:200].replace("\n", " ")
    raise LLMJsonParseError(
        f"Could not coerce LLM output into {schema.__name__}: {snippet!r}"
    )


def _strip_fences(text: str) -> str:
    match = _FENCE_PATTERN.match(text)
    if match is not None:
        return match.group(1).strip()
    return text


def _extract_first_object(text: str) -> str | None:
    match = _OBJECT_PATTERN.search(text)
    return match.group(0) if match is not None else None


def _unwrap_string_encoded(text: str) -> str | None:
    """If ``text`` parses as a one-key dict whose value is a JSON string, return that string."""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and len(parsed) == 1:
        only_value = next(iter(parsed.values()))
        if isinstance(only_value, str) and only_value.lstrip().startswith("{"):
            return only_value
    return None
