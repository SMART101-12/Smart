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
from .analysis_contract import build_structured_analysis
from .scanner import Candidate, initial_analysis
from .sources import source_status
from .symbol_learning import FOCUS_SYMBOLS, summarize_profile
from .tsetmc import (
    historical_exam,
    live_initial_analysis,
    symbol_entry_profile as build_symbol_entry_profile,
)
from .strategy_lab import latest_strategy_decision, strategy_catalog, strategy_definitions

mcp = FastMCP("SMART Market Intelligence")


@mcp.tool()
def smart_health() -> dict[str, Any]:
    """Check SMART/OpenAI configuration without exposing secrets."""
    return healthcheck()


@mcp.tool()
async def scan_market(symbols: list[str] | None = None) -> dict[str, Any]:
    """Run a live first-pass analysis from TSETMC for the requested symbols."""
    symbols = symbols or list(FOCUS_SYMBOLS)
    return await live_initial_analysis(symbols)


@mcp.tool()
async def structured_symbol_analysis(symbol: str) -> dict[str, Any]:
    """Return one deterministic JSON analysis without calling an LLM."""

    cleaned = str(symbol or "").strip()
    if not cleaned:
        return {"status": "error", "error": "symbol is required"}
    scan = await live_initial_analysis([cleaned])
    results = scan.get("results") or []
    if not results:
        return {
            "status": "error",
            "symbol": cleaned,
            "errors": scan.get("errors", []),
        }
    row = results[0]
    return {
        "status": "ok",
        "symbol": cleaned,
        "source": scan.get("source", "TSETMC"),
        "analysis": row.get("structured_analysis") or build_structured_analysis(row),
        "warnings": scan.get("errors", []),
    }


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
async def symbol_entry_profile(
    symbol: str,
    years: int = 10,
    initial_history: int = 20,
    evaluation_window: int = 30,
    transaction_cost_pct: float = 0.35,
) -> dict[str, Any]:
    """Train one symbol-specific, long-only adaptive entry profile.

    The returned summary contains the validation-selected configuration,
    dynamic Ichimoku/MACD/RSI/EMA/SMA weights by timeframe, current entry
    state, fixed validation/test evidence gates and the persisted audit path.
    """

    profile = await build_symbol_entry_profile(
        symbol,
        years=max(1, min(int(years), 15)),
        initial_history=max(10, min(int(initial_history), 500)),
        evaluation_window=max(5, min(int(evaluation_window), 250)),
        transaction_cost_pct=max(0.0, min(float(transaction_cost_pct), 5.0)),
    )
    return summarize_profile(profile) or profile


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
    """Explain a sealed SMART snapshot and return its deterministic contract."""
    enriched = dict(snapshot)
    enriched["structured_analysis"] = build_structured_analysis(snapshot)
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
        return {
            "status": "ok",
            "answer": ask_model(prompt),
            "structured_analysis": enriched["structured_analysis"],
        }
    except RuntimeError as exc:
        return {
            "status": "unavailable",
            "error": str(exc),
            "structured_analysis": enriched["structured_analysis"],
        }


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
    """Ask the configured model to explain the sealed SMART snapshot."""
    structured = build_structured_analysis(snapshot)
    prompt = (
        "You are SMART, an explainable Iran capital-market decision-support system. "
        "Analyze the supplied normalized snapshot. Separate facts, signals, risks, "
        "missing data, and confidence. Do not invent prices or claim certainty.\n\n"
        + json.dumps(structured, ensure_ascii=False, indent=2)
    )
    return ask_model(prompt)


if __name__ == "__main__":
    mcp.run(transport=os.getenv("MCP_TRANSPORT", "stdio"))
