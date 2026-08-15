"""SMART MCP server.

Read-only tools for the first ChatGPT/App test. Live market data comes from
isolated source adapters and is returned with source/error metadata.
"""

from __future__ import annotations

import json
import os
from typing import Any

from mcp.server.fastmcp import FastMCP

from .ai import ask_model, healthcheck
from .scanner import Candidate, initial_analysis
from .sources import source_status
from .tsetmc import live_initial_analysis

mcp = FastMCP("SMART Market Intelligence")


@mcp.tool()
def smart_health() -> dict[str, Any]:
    """Check SMART/OpenAI configuration without exposing secrets."""
    return healthcheck()


@mcp.tool()
def scan_market(symbols: list[str] | None = None) -> dict[str, Any]:
    """Run a live first-pass analysis from TSETMC for the requested symbols."""
    symbols = symbols or ["شلرد", "پالایش", "عیار"]
    import asyncio
    return asyncio.run(live_initial_analysis(symbols))


@mcp.tool()
def scan_smoke(symbols: list[str] | None = None) -> dict[str, Any]:
    """Run deterministic scanner smoke test without external market data."""
    symbols = symbols or ["SHLDR", "PALAYESH", "AYAR"]
    candidates = [Candidate(symbol=s, data_quality_score=50.0) for s in symbols]
    return initial_analysis(candidates)


@mcp.tool()
async def source_check(url: str, name: str = "custom") -> dict[str, Any]:
    """Describe a web source without treating it as trusted market data."""
    return source_status(name, url=url, available=False, detail="use a source adapter for production ingestion")


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
