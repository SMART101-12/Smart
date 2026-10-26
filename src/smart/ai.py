"""OpenAI integration for SMART.

API credentials are read from environment variables and are never hard-coded.
"""

from __future__ import annotations

import os
import json
from typing import Any

from openai import OpenAI
from dotenv import load_dotenv



# Load only local development variables. Hosted deployments should inject
# OPENAI_API_KEY as a secret environment variable instead.
load_dotenv()


def get_client() -> OpenAI:
    """Create an OpenAI client from OPENAI_API_KEY."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not configured")
    return OpenAI(api_key=api_key, timeout=30.0, max_retries=0)


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
    """Choose an explanation outline; computed numbers remain server-owned."""
    from copy import deepcopy
    from .analysis_explanation import explanation_facts, render_explanation

    reference = deepcopy(snapshot)
    facts = explanation_facts(reference)
    response = get_client().responses.create(
        model=model or os.getenv("OPENAI_MODEL", "gpt-5"),
        instructions=("Select fact IDs relevant to the question, in a useful reading order. "
                      "Return only IDs from the supplied facts. Do not create claims or numbers."),
        input=json.dumps({"question": question, "facts": facts}, ensure_ascii=False),
        text={"format": {"type": "json_schema", "name": "smart_explanation_outline",
            "strict": True, "schema": {
                "type": "object", "additionalProperties": False,
                "required": ["fact_ids"], "properties": {"fact_ids": {
                    "type": "array", "minItems": 1,
                    "items": {"type": "string", "enum": list(facts)}}}}}},
    )
    try:
        parsed = json.loads(response.output_text)
    except (TypeError, ValueError) as exc:
        raise RuntimeError("Explanation response was not valid JSON") from exc
    if not isinstance(parsed, dict) or set(parsed) != {"fact_ids"}:
        raise RuntimeError("Explanation may only select computed fact IDs")
    explanation = render_explanation(reference, parsed["fact_ids"])
    return {"reference": reference, **explanation}


def healthcheck() -> dict[str, Any]:
    """Return configuration status without exposing the API key."""
    return {
        "configured": bool(os.getenv("OPENAI_API_KEY")),
        "model": os.getenv("OPENAI_MODEL", "gpt-5"),
    }
