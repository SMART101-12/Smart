"""OpenAI integration for SMART.

API credentials are read from environment variables and are never hard-coded.
"""

from __future__ import annotations

import os
from typing import Any

from openai import OpenAI


def get_client() -> OpenAI:
    """Create an OpenAI client from OPENAI_API_KEY."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return OpenAI(api_key=api_key)


def ask_model(prompt: str, *, model: str | None = None) -> str:
    """Send a simple request through the Responses API."""
    client = get_client()
    response = client.responses.create(
        model=model or os.getenv("OPENAI_MODEL", "gpt-5"),
        input=prompt,
    )
    return response.output_text


def healthcheck() -> dict[str, Any]:
    """Return configuration status without exposing the API key."""
    return {
        "configured": bool(os.getenv("OPENAI_API_KEY")),
        "model": os.getenv("OPENAI_MODEL", "gpt-5"),
    }
