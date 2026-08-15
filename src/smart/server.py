"""SMART MCP server.

Exposes a small, read-only tool surface for ChatGPT/App integrations.
"""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .ai import ask_model, healthcheck
from .scanner import Candidate, initial_analysis
from .sources import source_status

mcp = FastMCP("SMART Market Intelligence")


@mcp.tool()
def smart_health() -> dict[str, Any]:
    """Check SMART/OpenAI configuration without exposing secrets."""
    return healthcheck()


@mcp.tool()
def scan_market(symbols: list[str] | None = None) -> dict[str, Any]:
    """Run the first-pass SMART scanner.

    This MVP accepts normalized candidates and is intentionally conservative:
    it never claims that a trade is executable without live-source validation.
    """
    symbols = symbols or ["SHLDR", "PALAYESH", "AYAR"]
    candidates = [
        Candidate(symbol=s, data_quality_score=50.0)
        for s in symbols
    ]
    return initial_analysis(candidates)


@mcp.tool()
async def source_check(url: str, name: str = "custom") -> dict[str, Any]:
    """Register/check a web source endpoint without treating it as trusted."""
    # Connectivity is deliberately not performed here yet; deployment will
    # supply an HTTP egress policy and source-specific adapters.
    return source_status(name, url=url, available=False, detail="adapter pending")


@mcp.tool()
def analyze_snapshot(snapshot: dict[str, Any]) -> str:
    """Ask the configured OpenAI model to explain a normalized market snapshot."""
    prompt = (
        "You are SMART, an explainable Iran capital-market decision-support system. "
        "Analyze the supplied normalized snapshot. Separate facts, signals, risks, "
        "missing data, and confidence. Do not invent prices or claim certainty.\n\n"
        + json.dumps(snapshot, ensure_ascii=False, indent=2)
    )
    return ask_model(prompt)


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))
