"""Shared constructor for the google-genai Client.

The SDK's ``genai.Client(api_key=...)`` constructor routes through the
Gemini Developer (AI Studio) endpoints. When this codebase is deployed
with ``GOOGLE_GENAI_USE_VERTEXAI=true`` the same call still attaches the
``?key=`` query param on aiplatform.googleapis.com requests, which
Google rejects with ``API_KEY_SERVICE_BLOCKED``. The right path is
``genai.Client(vertexai=True)`` (no api_key), which falls back to
Application Default Credentials.

Centralizing this avoids drift across the five call sites that
construct a Client directly.
"""

import google.genai as genai

from src.config import get_settings


def make_genai_client() -> genai.Client:
    """Return a Client wired for Vertex AI or AI Studio per config.

    With ``GOOGLE_GENAI_USE_VERTEXAI=true`` (and ADC available via the
    mounted ``~/.config/gcloud`` volume), the Client uses
    ``aiplatform.googleapis.com`` with OAuth bearer tokens. Otherwise it
    falls back to AI Studio + ``GOOGLE_API_KEY``.
    """
    settings = get_settings()
    if settings.google_genai_use_vertexai:
        return genai.Client(vertexai=True)
    return genai.Client(api_key=settings.google_api_key)
