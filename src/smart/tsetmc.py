"""TSETMC live adapter for the first SMART market-analysis test.

The endpoints are community-documented and can change without notice. The
adapter therefore reports source/HTTP errors explicitly and never fabricates
missing values.
"""

from __future__ import annotations

import os
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any
from urllib.parse import quote

import httpx

from .signals import smart_money_phase
from .technical import ema, rsi, sma
from .technical_analysis import build_features
from .strategy_lab import (
    bars_from_rows,
    build_learning_summary,
    latest_strategy_decision,
    walk_forward_exam,
)
from .decision_memory import DecisionMemory
from .archive import safe_symbol
from smart_v2.analysis.stock_service import StockAnalysisService

BASE = "https://cdn.tsetmc.com/api"
HEADERS = {"User-Agent": "Mozilla/5.0 SMART/0.1"}


class TSETMCError(RuntimeError):
    pass


async def _get(path: str) -> Any:
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True, headers=HEADERS) as client:
            response = await client.get(f"{BASE}{path}")
            response.raise_for_status()
            return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        raise TSETMCError(f"TSETMC request failed: {path}") from exc


async def search_symbol(symbol: str) -> dict[str, Any]:
    data = await _get(f"/Instrument/GetInstrumentSearch/{quote(symbol)}")
    rows = data.get("instrumentSearch", [])
    if not rows:
        raise TSETMCError(f"symbol not found: {symbol}")
    return rows[0]


async def instrument_info(ins_code: str) -> dict[str, Any]:
    data = await _get(f"/Instrument/GetInstrumentInfo/{ins_code}")
    return data.get("instrumentInfo", {})


async def closing_info(ins_code: str) -> dict[str, Any]:
    data = await _get(f"/ClosingPrice/GetClosingPriceInfo/{ins_code}")
    return data.get("closingPriceInfo", {})


async def daily_history(ins_code: str, top: int = 0) -> list[dict[str, Any]]:
    data = await _get(f"/ClosingPrice/GetClosingPriceDailyList/{ins_code}/{top}")
    return data.get("closingPriceDaily", [])


async def client_type(ins_code: str) -> dict[str, Any]:
    data = await _get(f"/ClientType/GetClientType/{ins_code}/1/0")
    rows = data.get("clientType", [])
    return rows[0] if isinstance(rows, list) and rows else (rows if isinstance(rows, dict) else {})


def _number(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        if value is None or value == "":
            continue
        try:
            return float(value)
        except (TypeError, ValueError):
            continue
    return None


def _analyze_rows(symbol: str, info: dict[str, Any], current: dict[str, Any], history: list[dict[str, Any]], flow: dict[str, Any]) -> dict[str, Any]:
    closes = [v for v in (_number(r, "pClosing", "pc", "close") for r in reversed(history)) if v is not None]
    volumes = [v for v in (_number(r, "qTotTran5J", "volume", "qTotTran") for r in reversed(history)) if v is not None]
    price = _number(current, "pDrCotVal", "pl", "last") or _number(current, "pClosing", "pc", "close")
    previous = closes[-2] if len(closes) >= 2 else None
    change_pct = ((price - previous) / previous * 100) if price and previous else 0.0
    avg_volume = mean(volumes[-20:]) if len(volumes) >= 20 else (mean(volumes) if volumes else None)
    current_volume = _number(current, "qTotTran5J", "qTotTran", "volume")
    volume_ratio = current_volume / avg_volume if current_volume and avg_volume else 1.0

    buy_i = _number(flow, "buy_I_Volume", "buyIVolume") or 0.0
    sell_i = _number(flow, "sell_I_Volume", "sellIVolume") or 0.0
    buy_n = _number(flow, "buy_N_Volume", "buyNVolume") or 0.0
    sell_n = _number(flow, "sell_N_Volume", "sellNVolume") or 0.0
    retail_power = (buy_i / max(buy_n, 1.0)) / max(sell_i / max(sell_n, 1.0), 1e-9)
    net_retail = buy_i - sell_i
    money_flow_score = max(0.0, min(100.0, 50.0 + (net_retail / max(buy_i + sell_i, 1.0)) * 50.0))
    smart = smart_money_phase(
        price_change_pct=change_pct,
        volume_ratio=volume_ratio,
        money_flow_score=money_flow_score,
        retail_buy_power=retail_power,
    )

    tech_score = 50.0
    if len(closes) >= 20 and price:
        s20 = sma(closes, 20)
        e20 = ema(closes, 20)
        if s20 and price > s20:
            tech_score += 15
        if e20 and price > e20:
            tech_score += 15
    rsi_value = rsi(closes, 14) if len(closes) >= 15 else None
    if rsi_value is not None:
        if 50 <= rsi_value <= 70:
            tech_score += 20
        elif rsi_value > 75 or rsi_value < 30:
            tech_score -= 15

    return {
        "symbol": symbol,
        "ins_code": info.get("insCode") or info.get("insCode"),
        "price": price,
        "change_pct": round(change_pct, 2),
        "volume": current_volume,
        "volume_ratio": round(volume_ratio, 2),
        "retail_net_volume": net_retail,
        "retail_buy_power": round(retail_power, 2),
        "money_flow_score": round(money_flow_score, 2),
        "smart_money": {
            "phase": smart.phase,
            "score": smart.score,
            "confirmations": list(smart.confirmations),
            "warnings": list(smart.warnings),
        },
        "technical": {
            "score": round(max(0.0, min(100.0, tech_score)), 2),
            "rsi14": round(rsi_value, 2) if rsi_value is not None else None,
            "sma20": round(sma(closes, 20), 2) if len(closes) >= 20 else None,
            "ema20": round(ema(closes, 20), 2) if len(closes) >= 20 else None,
        },
        "data_quality": 90.0 if price is not None and len(history) >= 20 else 60.0,
        "source": "TSETMC cdn API",
    }


def _technical_history(history: list[dict[str, Any]]) -> dict[str, Any]:
    bars = bars_from_rows(history)
    features = build_features(bars, horizon=5) if bars else []
    rows = []
    public_fields = (
        "date", "close", "return_1d", "sma5", "sma20", "sma50",
        "ema12", "ema26", "rsi14", "macd", "macd_signal", "atr14",
        "volume", "volume_ratio20", "roc20", "drawdown_60", "breakout_up20",
        "breakout_down20", "composite_score", "prediction",
    )
    for index, item in enumerate(features):
        # Future-return labels are reserved for the exam evaluator and are
        # never exposed as live decision inputs or sent to the LLM.
        row = {
            field: (
                bars[index].volume
                if field == "volume"
                else getattr(item, field)
            )
            for field in public_fields
        }
        rows.append(row)
    latest = rows[-1] if rows else {}
    return {
        "bars": len(bars),
        "latest": latest,
        "history": rows,
        "method": "point-in-time indicators; future_return_5d is evaluation-only",
    }


async def historical_exam(symbol: str, *, initial_history: int = 20, evaluation_window: int = 30) -> dict[str, Any]:
    """Fetch the complete available history and run the offline exam."""
    found = await search_symbol(symbol)
    ins_code = str(found.get("insCode"))
    history = await daily_history(ins_code, top=int(os.getenv("TSETMC_HISTORY_TOP", "0")))
    exam = walk_forward_exam(
        history,
        symbol=symbol,
        initial_history=initial_history,
        evaluation_window=evaluation_window,
    )
    exam["source"] = "TSETMC"
    exam["ins_code"] = ins_code
    run_stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    artifact = (
        Path("runtime/learning")
        / safe_symbol(symbol)
        / "exams"
        / f"{run_stamp}-{uuid.uuid4().hex[:8]}.json"
    )
    artifact.parent.mkdir(parents=True, exist_ok=True)
    exam["artifact_path"] = str(artifact)
    learning_summary = build_learning_summary(exam)
    learning_artifact = artifact.parent.parent / "strategy_memory.json"
    learning_summary["artifact_path"] = str(learning_artifact)
    learning_artifact.write_text(
        json.dumps(learning_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    exam["learning"] = {
        "artifact_path": str(learning_artifact),
        "failure_diagnostics": learning_summary["failure_diagnostics"],
    }
    artifact.write_text(
        json.dumps(exam, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return exam


async def analyze_symbol(symbol: str) -> dict[str, Any]:
    found = await search_symbol(symbol)
    ins_code = str(found.get("insCode"))
    info = await instrument_info(ins_code)
    current = await closing_info(ins_code)
    try:
        history = await daily_history(ins_code, top=int(os.getenv("TSETMC_HISTORY_TOP", "0")))
    except TypeError:
        # Preserve compatibility with injected/test adapters accepting one arg.
        history = await daily_history(ins_code)
    flow = await client_type(ins_code)
    result = _analyze_rows(symbol, info, current, history, flow)
    technical_history = _technical_history(history)
    result["technical_history"] = technical_history
    try:
        strategy_decision = latest_strategy_decision(
            history,
            symbol=symbol,
            initial_history=20,
            horizon=5,
        )
    except (TypeError, ValueError, KeyError) as exc:
        strategy_decision = {
            "status": "UNAVAILABLE",
            "error": f"strategy decision unavailable: {exc}",
        }
    result["strategy_decision"] = strategy_decision
    # The first-pass scanner is intentionally lightweight; enrich it with the
    # downstream, point-in-time analysis service when enough OHLCV rows exist.
    try:
        result["analysis"] = StockAnalysisService().analyze(
            history,
            symbol=symbol,
            ins_code=ins_code,
            include_history_metrics=False,
        )
    except (TypeError, ValueError, KeyError) as exc:
        result["analysis"] = {
            "status": "UNAVAILABLE",
            "error": f"downstream analysis unavailable: {exc}",
        }
    # Persist the exact point-in-time decision context for later outcome review.
    decision = result.get("analysis", {})
    if isinstance(decision, dict):
        # Keep the public analysis contract self-contained for the dashboard,
        # MCP clients and the ChatGPT explanation layer.
        decision["technical_history"] = technical_history
        decision["strategy_decision"] = strategy_decision
    try:
        result["decision_record"] = DecisionMemory().record_decision(
            symbol,
            {
                "as_of": result["technical_history"].get("latest", {}).get("date"),
                "prediction": strategy_decision.get(
                    "decision",
                    result["technical_history"].get("latest", {}).get("prediction"),
                ),
                "indicators": result["technical_history"].get("latest", {}),
                "factor_engine": decision.get("factor_engine", {}),
                "strategy_decision": strategy_decision,
            },
        )
    except OSError:
        result["decision_record"] = None
    return result


async def live_initial_analysis(symbols: list[str]) -> dict[str, Any]:
    # Keep the public pipeline bounded and deterministic for API callers.
    cleaned_symbols = []
    for symbol in symbols or []:
        value = str(symbol).strip()
        if value and value not in cleaned_symbols:
            cleaned_symbols.append(value)
    symbols = cleaned_symbols[:20]
    results: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for symbol in symbols:
        try:
            results.append(await analyze_symbol(symbol))
        except TSETMCError as exc:
            errors.append({"symbol": symbol, "error": str(exc)})
        except Exception as exc:  # source adapter failures must be visible, not 500s
            errors.append({"symbol": symbol, "error": f"unexpected source failure: {exc}"})

    results.sort(key=lambda row: (
        row.get("smart_money", {}).get("score", 0) * 0.4
        + row.get("technical", {}).get("score", 0) * 0.35
        + row.get("data_quality", 0) * 0.25
    ), reverse=True)
    for rank, row in enumerate(results, start=1):
        row["rank"] = rank
        row["overall_score"] = round(
            row["smart_money"]["score"] * 0.4
            + row["technical"]["score"] * 0.35
            + row["data_quality"] * 0.25,
            2,
        )

    return {
        "status": "ok" if results else ("error" if errors else "empty"),
        "stage": "live_initial_analysis",
        "source": "TSETMC",
        "symbols_requested": symbols,
        "results": results,
        "errors": errors,
        "disclaimer": "Decision-support output only; validate live data and execution conditions before trading.",
    }
