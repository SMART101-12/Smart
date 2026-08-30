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
from .tsetmc import historical_exam, live_initial_analysis
from .strategy_lab import latest_strategy_decision, strategy_catalog, strategy_definitions

mcp = FastMCP("SMART Market Intelligence")


@mcp.tool()
def smart_health() -> dict[str, Any]:
    """Check SMART/OpenAI configuration without exposing secrets."""
    return healthcheck()


@mcp.tool()
async def scan_market(symbols: list[str] | None = None) -> dict[str, Any]:
    """Run a live first-pass analysis from TSETMC for the requested symbols."""
    symbols = symbols or ["شلرد", "پالایش", "عیار"]
    return await live_initial_analysis(symbols)


@mcp.tool()
async def walk_forward_exam(
    symbol: str,
    initial_history: int = 20,
    evaluation_window: int = 30,
) -> dict[str, Any]:
    """Run the 200-strategy, no-look-ahead historical examination."""
    return await historical_exam(
        symbol,
        initial_history=max(10, min(initial_history, 250)),
        evaluation_window=max(5, min(evaluation_window, 250)),
    )


@mcp.tool()
async def current_strategy_decision(symbol: str) -> dict[str, Any]:
    """Return today's point-in-time 200-strategy decision for one symbol."""
    from .tsetmc import daily_history, search_symbol

    found = await search_symbol(symbol)
    rows = await daily_history(
        str(found.get("insCode")),
        top=int(os.getenv("TSETMC_HISTORY_TOP", "0")),
    )
    result = latest_strategy_decision(rows, symbol=symbol, initial_history=20, horizon=5)
    result["source"] = "TSETMC"
    result["ins_code"] = str(found.get("insCode"))
    return result


@mcp.tool()
def list_strategies() -> dict[str, Any]:
    """List the 200 auditable research strategy variants."""
    catalog = strategy_catalog()
    return {
        "count": len(catalog),
        "families": sorted({item.family for item in catalog}),
        "strategies": [
            {
                "id": item.strategy_id,
                "name": item.name,
                "family": item.family,
                "parameters": item.parameters,
                "description": item.description,
            }
            for item in catalog
        ],
    }


@mcp.tool()
def chat_explain(snapshot: dict[str, Any], question: str = "") -> dict[str, Any]:
    """Ask the configured OpenAI model to explain SMART's structured result."""
    enriched = dict(snapshot)
    leaderboard = enriched.get("leaderboard") or (
        enriched.get("walk_forward_exam", {}) if isinstance(enriched.get("walk_forward_exam"), dict) else {}
    ).get("leaderboard", [])
    ids = [item.get("strategy_id") for item in leaderboard if isinstance(item, dict)]
    enriched["strategy_logic"] = strategy_definitions(ids[:20])
    prompt = (
        "You are the explanation layer of SMART, an Iran-market decision-support "
        "system. Use only the supplied structured facts. Explain indicators, "
        "strategy consensus, walk-forward performance and risks. Never invent "
        "prices, future data, trades or certainty. This is research, not advice.\n"
        f"User question: {question or 'Explain the result clearly.'}\n"
        + json.dumps(enriched, ensure_ascii=False, indent=2)
    )
    try:
        return {"status": "ok", "answer": ask_model(prompt)}
    except RuntimeError as exc:
        return {"status": "unavailable", "error": str(exc)}


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
