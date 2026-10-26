"""Deterministic daily long-only breakout/retest plans from observed OHLCV."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from math import isfinite
from statistics import mean
from typing import Any, Literal

from smart.technical_analysis import ema
from .trade_policy import TradePolicy
from .price_levels import confirmed_price_levels

ENGINE_VERSION = "STRUCTURAL-ENTRY-1"


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
    as_of: str = ""
    expires_on: str = ""
    net_risk_reward: tuple[float, float] | None = None
    target_method: str = "observed_pivot_resistance"
    overhead_resistances: tuple[float, ...] = ()
    exit_rules: dict[str, Any] | None = None
    level_evidence: dict[str, Any] | None = None

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
    evidence: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {"status": self.status, "reason": self.reason,
                "plan": self.plan.as_dict() if self.plan else None,
                "evidence": self.evidence or {}, "engine_version": ENGINE_VERSION}


class EntryExitEngine:
    def __init__(self, policy: TradePolicy | None = None) -> None:
        self.policy = policy or TradePolicy()

    def build_plan(self, symbol: str, tf: str, low: float, high: float, stop: float,
                   as_of: str, overhead: list[float] | None = None,
                   level_evidence: dict[str, Any] | None = None) -> TradePlan | None:
        """Evaluate observed exit levels; reward/risk filters never create them."""
        if not all(isfinite(v) and v > 0 for v in (low, high, stop)) or not stop < low <= high:
            return None
        risk = high - stop
        if risk / high * 100 > self.policy.max_stop_distance_pct:
            return None
        cost = high * self.policy.cost_rate
        total_risk = risk + cost
        ceilings = sorted({v for v in (overhead or []) if isfinite(v) and v > high})
        if len(ceilings) < 2:
            return None
        targets = ceilings[:2]
        net = tuple((target - high - cost) / total_risk for target in targets)
        if (not all(isfinite(v) for v in (*targets, *net)) or
                net[0] + 1e-10 < self.policy.min_net_reward_risk or
                net[1] + 1e-10 < self.policy.second_net_reward_risk or targets[1] <= targets[0]):
            return None
        day = datetime.strptime(as_of, "%Y%m%d").date()
        return TradePlan(symbol, tf, (low, high), stop, targets[0], targets[1],
                         ((targets[0] - high) / risk, (targets[1] - high) / risk),
                         "Price touches stop, setup expires, or entry exceeds the upper zone; reassess before entry",
                         day.isoformat(), (day + timedelta(days=self.policy.entry_validity_days)).isoformat(),
                         (net[0], net[1]), "observed_pivot_resistance",
                         tuple(ceilings), self.policy.exit_rules(), level_evidence)

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
        except (ValueError, TypeError, KeyError, AttributeError, OverflowError):
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
        if not isfinite(atr) or not isfinite(volume) or atr <= 0 or volume <= 0:
            return TradePlanResult("insufficient_data", "Positive historical ATR and volume baseline required")
        breakout = previous["close"] <= resistance and last["close"] > resistance + .1 * atr
        retest = (previous["close"] > resistance + .1 * atr and previous["volume"] >= self.policy.volume_confirmation * volume
                  and resistance - .25 * atr <= last["low"] <= resistance + .25 * atr
                  and last["close"] > resistance and last["close"] > last["open"])
        confirmed = last["volume"] >= self.policy.volume_confirmation * volume
        pullback = False
        if len(data) >= 60:
            closes = [b["close"] for b in data]
            fast, slow = ema(closes, 20), ema(closes, 50)
            pullback = (slow[-6] is not None and fast[-1] > slow[-1] > slow[-6]
                        and fast[-2] - .5 * atr <= previous["low"] <= fast[-2] + .5 * atr
                        and last["close"] > fast[-1] and last["close"] > previous["high"]
                        and last["close"] > last["open"])
        structure = confirmed_price_levels(bars)
        evidence: dict[str, Any] = {"support": support, "resistance": resistance, "atr": atr,
            "volume_ratio": last["volume"] / volume, "as_of": bars[-1][0],
            "last_close": last["close"], "structural_levels": structure,
            "confirmation": {"breakout": breakout, "retest": retest,
                             "trend_pullback": pullback, "volume": confirmed}}
        if not (breakout or retest or pullback) or not confirmed:
            return TradePlanResult("no_setup", "Breakout/retest or trend pullback must agree with volume confirmation", evidence=evidence)
        setup = "retest" if retest else "breakout" if breakout else "trend_pullback"
        anchor = resistance
        anchor_evidence: dict[str, Any] = {"kind": "broken_range_resistance", "price": resistance,
            "source_dates": [day for day, b in bars[-22:-2] if b["high"] == resistance]}
        if setup == "trend_pullback":
            supports = [v for v in structure["supports"]
                        if v["pivot_dates"][-1] >= datetime.strptime(
                            bars[max(0, len(bars) - 20)][0], "%Y%m%d").date().isoformat()]
            if not supports:
                return TradePlanResult("no_setup", "Trend pullback lacks a confirmed swing support", evidence=evidence)
            anchor_evidence = max(supports, key=lambda v: v["pivot_dates"][-1])
            anchor = anchor_evidence["price"]
        if setup != "trend_pullback" and last["close"] > resistance + 2 * atr:
            return TradePlanResult("no_setup", "Price is extended beyond the entry zone", evidence=evidence)
        low, high = max(anchor, last["close"] - .25 * atr), last["close"] + .25 * atr
        stop = anchor - self.policy.stop_atr_buffer * atr
        if any(level["price"] <= high for level in structure["resistances"]):
            return TradePlanResult("no_setup", "Entry zone overlaps an observed overhead resistance", evidence=evidence)
        # Only confirmed historical pivots; the newest two bars cannot confirm themselves.
        targets = [v for v in structure["resistances"] if v["price"] > high]
        overhead = [v["price"] for v in targets]
        level_evidence = {"entry": anchor_evidence,
                          "stop": {"anchor": anchor_evidence, "atr": atr,
                                   "atr_buffer": self.policy.stop_atr_buffer},
                          **({"target_1": targets[0], "target_2": targets[1]} if len(targets) >= 2 else {})}
        plan = self.build_plan(symbol, tf, low, high, stop, bars[-1][0], overhead, level_evidence)
        evidence.update(setup=setup, stop_anchor=anchor,
                        cost_pct=self.policy.round_trip_cost_pct + self.policy.slippage_pct)
        if plan is None:
            reason = ("Two confirmed overhead resistances required; no projected targets" if len(targets) < 2
                      else "Stop distance or net reward/risk to observed resistances fails policy")
            return TradePlanResult("no_setup", reason, evidence=evidence)
        return TradePlanResult("ready", "Structure, ATR risk and volume confirmed", plan, evidence)
