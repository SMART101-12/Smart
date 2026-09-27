"""Deterministic daily long-only breakout/retest plans from observed OHLCV."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from statistics import mean
from typing import Any, Literal


@dataclass(frozen=True)
class TradePlan:
    symbol: str
    tf: str
    entry_zone: tuple[float, float]
    sl: float
    tp1: float
    tp2: float
    risk_reward: tuple[float, float]
    invalidation_condition: str

    def as_dict(self) -> dict[str, Any]:
        result = asdict(self)
        # Compatibility with the existing dashboard and analysis contract.
        result.update(entry=self.entry_zone[1], stop=self.sl, target=self.tp1)
        return result


@dataclass(frozen=True)
class TradePlanResult:
    status: Literal["ready", "no_setup", "insufficient_data"]
    reason: str
    plan: TradePlan | None = None
    evidence: dict[str, float | str] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reason": self.reason,
                "plan": self.plan.as_dict() if self.plan else None,
                "evidence": self.evidence or {}}


class EntryExitEngine:
    def generate(self, rows: list[dict[str, Any]], symbol: str, tf: str = "1d") -> TradePlanResult:
        if tf != "1d":
            return TradePlanResult("insufficient_data", "Only daily bars are supported; no implicit resampling")
        if len(rows) < 22:
            return TradePlanResult("insufficient_data", "At least 22 completed daily bars required")
        aliases = {"open": ("open", "pFirst", "priceFirst"), "high": ("high", "pMax", "priceMax"),
                   "low": ("low", "pMin", "priceMin"), "close": ("close", "pClosing"),
                   "volume": ("volume", "qTotTran5J")}
        bars: list[tuple[str, dict[str, float]]] = []
        try:
            for row in rows:
                day = str(row.get("source_date") or row.get("date") or row.get("dEven") or "").replace("-", "").replace("/", "")
                from datetime import datetime
                datetime.strptime(day, "%Y%m%d")
                values: dict[str, float] = {}
                for field, keys in aliases.items():
                    raw = next((row[k] for k in keys if row.get(k) is not None), None)
                    if raw is None or isinstance(raw, bool):
                        raise ValueError("Missing OHLCV")
                    value = float(raw)
                    if not isfinite(value) or value < 0 or field != "volume" and value == 0:
                        raise ValueError("Invalid OHLCV")
                    values[field] = value
                if not values["low"] <= min(values["open"], values["close"]) <= max(values["open"], values["close"]) <= values["high"]:
                    raise ValueError("Inconsistent OHLC")
                bars.append((day, values))
            if len({d for d, _ in bars}) != len(bars):
                raise ValueError("Duplicate dates")
        except (ValueError, TypeError, KeyError):
            return TradePlanResult("insufficient_data", "Missing, duplicate or invalid dated OHLCV bars")
        bars.sort(key=lambda item: item[0])
        data = [b for _, b in bars]
        last, previous = data[-1], data[-2]
        history = data[-22:-2]
        resistance = max(b["high"] for b in history)
        support = min(b["low"] for b in history)
        ranges = [max(b["high"] - b["low"], abs(b["high"] - a["close"]), abs(b["low"] - a["close"]))
                  for a, b in zip(data[:-2], data[1:-1])]
        atr = mean(ranges[-14:])
        volume = mean(b["volume"] for b in history)
        if atr <= 0 or volume <= 0:
            return TradePlanResult("insufficient_data", "Positive historical ATR and volume baseline required")
        breakout = previous["close"] <= resistance and last["close"] > resistance + .1 * atr
        retest = (previous["close"] > resistance + .1 * atr and previous["volume"] >= 1.2 * volume
                  and resistance - .25 * atr <= last["low"] <= resistance + .25 * atr
                  and last["close"] > resistance and last["close"] > last["open"])
        confirmed = last["volume"] >= 1.2 * volume
        evidence: dict[str, float | str] = {"support": support, "resistance": resistance, "atr": atr,
            "volume_ratio": last["volume"] / volume, "as_of": bars[-1][0]}
        if not (breakout or retest) or not confirmed:
            return TradePlanResult("no_setup", "Breakout/retest and volume confirmation must agree", evidence=evidence)
        if last["close"] > resistance + 2 * atr:
            return TradePlanResult("no_setup", "Price is extended beyond the entry zone", evidence=evidence)
        low, high = max(resistance, last["close"] - .25 * atr), last["close"] + .25 * atr
        stop = resistance - atr
        risk = high - stop
        if stop <= 0 or risk <= 0:
            return TradePlanResult("no_setup", "No valid positive stop distance", evidence=evidence)
        plan = TradePlan(symbol, tf, (low, high), stop, high + 2 * risk, high + 3 * risk,
                         (2., 3.), f"Daily close below {stop:g}; setup expires when price exceeds entry zone")
        evidence["setup"] = "retest" if retest else "breakout"
        return TradePlanResult("ready", "Structure, ATR risk and volume confirmed", plan, evidence)
