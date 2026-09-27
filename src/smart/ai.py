"""OpenAI integration for SMART.

API credentials are read from environment variables and are never hard-coded.
"""

from __future__ import annotations

import os
import json
from typing import Any

from openai import OpenAI
from dotenv import load_dotenv

from .analysis_contract import analysis_json_schema, validate_structured_analysis


# Load only local development variables. Hosted deployments should inject
# OPENAI_API_KEY as a secret environment variable instead.
load_dotenv()


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


def ask_structured_analysis(
    snapshot: dict[str, Any],
    *,
    question: str = "",
    model: str | None = None,
) -> dict[str, Any]:
    """Ask the configured model for the strict SMART analysis contract.

    The prompt contains only a sealed, point-in-time snapshot. Structured
    output is validated locally; malformed or incomplete model output fails
    closed instead of being shown as a trading conclusion.
    """

    client = get_client()
    instructions = (
        "تو لایه توضیح و تحلیل ساختاریافته SMART هستی. فقط از snapshot داده‌شده "
        "تا تاریخ as_of استفاده کن؛ هیچ قیمت، حجم، شاخص، سطح یا نتیجه‌ای را حدس نزن. "
        "داده آینده، future label و توصیه قطعی ممنوع است. شکست بدون حجم تأیید نیست. "
        "خروجی باید دقیقاً JSON مطابق schema باشد و نقش آن تصمیم‌یار پژوهشی است، نه سفارش. "
        f"سؤال کاربر: {question or 'تحلیل ساختاریافته را ارائه کن.'}"
    )
    response = client.responses.create(
        model=model or os.getenv("OPENAI_MODEL", "gpt-5"),
        instructions=instructions,
        input=json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        text={
            "format": {
                "type": "json_schema",
                "name": "smart_symbol_analysis",
                "description": "Point-in-time SMART symbol analysis contract",
                "strict": True,
                "schema": analysis_json_schema(),
            }
        },
    )
    raw = response.output_text
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Structured analysis response was not valid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Structured analysis response must be a JSON object")
    errors = validate_structured_analysis(parsed)
    if errors:
        raise RuntimeError("Structured analysis failed validation: " + ", ".join(errors))
    return parsed


def healthcheck() -> dict[str, Any]:
    """Return configuration status without exposing the API key."""
    return {
        "configured": bool(os.getenv("OPENAI_API_KEY")),
        "model": os.getenv("OPENAI_MODEL", "gpt-5"),
    }
