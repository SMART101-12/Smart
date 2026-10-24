"""Deterministic daily long-only breakout/retest plans from observed OHLCV."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from math import isfinite
from statistics import mean
from typing import Any, Literal

from smart.technical_analysis import ema
from .trade_policy import TradePolicy


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
    target_method: str = "risk_projection"
    overhead_resistances: tuple[float, ...] = ()
    exit_rules: dict[str, Any] | None = None

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
    def __init__(self, policy: TradePolicy | None = None) -> None:
        self.policy = policy or TradePolicy()

    def build_plan(self, symbol: str, tf: str, low: float, high: float, stop: float,
                   as_of: str, overhead: list[float] | None = None) -> TradePlan | None:
        """Require room to the nearest known resistance after disclosed costs."""
        if not all(isfinite(v) and v > 0 for v in (low, high, stop)) or not stop < low <= high:
            return None
        risk = high - stop
        if risk / high * 100 > self.policy.max_stop_distance_pct:
            return None
        cost = high * self.policy.cost_rate
        total_risk = risk + cost
        targets = [high + cost + multiple * total_risk for multiple in
                   (self.policy.min_net_reward_risk, self.policy.second_net_reward_risk)]
        ceilings = sorted({v for v in (overhead or []) if isfinite(v) and v > high})
        if ceilings:
            targets[0] = min(targets[0], ceilings[0])
            if len(ceilings) > 1:
                targets[1] = min(targets[1], ceilings[1])
        net = tuple((target - high - cost) / total_risk for target in targets)
        if (not all(isfinite(v) for v in (*targets, *net)) or
                net[0] + 1e-10 < self.policy.min_net_reward_risk or targets[1] <= targets[0]):
            return None
        day = datetime.strptime(as_of, "%Y%m%d").date()
        return TradePlan(symbol, tf, (low, high), stop, targets[0], targets[1],
                         ((targets[0] - high) / risk, (targets[1] - high) / risk),
                         "Price touches stop, setup expires, or entry exceeds the upper zone; reassess before entry",
                         day.isoformat(), (day + timedelta(days=self.policy.entry_validity_days)).isoformat(),
                         (net[0], net[1]), "risk_projection_capped_by_observed_pivot_resistance" if ceilings else "risk_projection_no_observed_overhead",
                         tuple(ceilings), self.policy.exit_rules())

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
        evidence: dict[str, float | str] = {"support": support, "resistance": resistance, "atr": atr,
            "volume_ratio": last["volume"] / volume, "as_of": bars[-1][0]}
        if not (breakout or retest or pullback) or not confirmed:
            return TradePlanResult("no_setup", "Breakout/retest or trend pullback must agree with volume confirmation", evidence=evidence)
        setup = "retest" if retest else "breakout" if breakout else "trend_pullback"
        anchor = resistance if setup != "trend_pullback" else min(b["low"] for b in data[-6:-1])
        if setup != "trend_pullback" and last["close"] > resistance + 2 * atr:
            return TradePlanResult("no_setup", "Price is extended beyond the entry zone", evidence=evidence)
        low, high = max(anchor, last["close"] - .25 * atr), last["close"] + .25 * atr
        stop = anchor - self.policy.stop_atr_buffer * atr
        # Only confirmed historical pivots; the newest two bars cannot confirm themselves.
        overhead = [data[i]["high"] for i in range(2, len(data) - 2)
                    if data[i]["high"] == max(b["high"] for b in data[i - 2:i + 3])
                    and data[i]["high"] > high]
        plan = self.build_plan(symbol, tf, low, high, stop, bars[-1][0], overhead)
        evidence.update(setup=setup, stop_anchor=anchor,
                        cost_pct=self.policy.round_trip_cost_pct + self.policy.slippage_pct)
        if plan is None:
            return TradePlanResult("no_setup", "Stop distance or net reward/risk to overhead resistance fails policy", evidence=evidence)
        return TradePlanResult("ready", "Structure, ATR risk and volume confirmed", plan, evidence)
