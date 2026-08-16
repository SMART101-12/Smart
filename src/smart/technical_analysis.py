from __future__ import annotations

"""Historical technical analysis using TSETMC daily history only.

No web-search price source is used. Signals are evaluated without look-ahead:
the signal is formed from data available through day t and the return is measured
over subsequent trading rows.
"""

import argparse
import csv
import json
import math
from pathlib import Path
from typing import Any

from .tsetmc_adapter import TsetmcAdapter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "runtime" / "analysis"


def _num(row: dict[str, Any], *keys: str) -> float | None:
    for key in keys:
        value = row.get(key)
        try:
            if value is not None and value != "":
                return float(value)
        except (TypeError, ValueError):
            pass
    return None


def _date(row: dict[str, Any]) -> str:
    return str(row.get("dEven", ""))


def _sma(values: list[float | None], n: int, i: int) -> float | None:
    if i + 1 < n: return None
    x = values[i + 1 - n:i + 1]
    if any(v is None for v in x): return None
    return sum(x) / n


def _ema(values: list[float | None], n: int) -> list[float | None]:
    out: list[float | None] = [None] * len(values)
    valid = [i for i, v in enumerate(values) if v is not None]
    if len(valid) < n: return out
    start = valid[n - 1]
    seed = sum(values[i] for i in valid[:n]) / n
    out[start] = seed
    alpha = 2 / (n + 1)
    for i in range(start + 1, len(values)):
        if values[i] is None or out[i - 1] is None: continue
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(close: list[float | None], n: int = 14) -> list[float | None]:
    out: list[float | None] = [None] * len(close)
    gains: list[float] = []; losses: list[float] = []
    for i in range(1, len(close)):
        if close[i] is None or close[i - 1] is None: continue
        change = close[i] - close[i - 1]
        gains.append(max(change, 0)); losses.append(max(-change, 0))
        if len(gains) >= n:
            if len(gains) == n:
                ag, al = sum(gains) / n, sum(losses) / n
            else:
                ag = (ag * (n - 1) + gains[-1]) / n
                al = (al * (n - 1) + losses[-1]) / n
            out[i] = 100 if al == 0 else 100 - 100 / (1 + ag / al)
    return out


def _atr(rows: list[dict[str, Any]], n: int = 14) -> list[float | None]:
    tr: list[float | None] = []
    for i, r in enumerate(rows):
        h, l, cprev = _num(r, "pMax", "maxPrice"), _num(r, "pMin", "minPrice"), _num(rows[i - 1], "pClosing", "close") if i else None
        if h is None or l is None: tr.append(None); continue
        tr.append(max(h - l, abs(h - cprev), abs(l - cprev)) if cprev is not None else h - l)
    return [_sma(tr, n, i) for i in range(len(rows))]


def enrich(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = sorted(rows, key=lambda r: int(_date(r) or 0))
    close = [_num(r, "pClosing", "close", "closingPrice") for r in rows]
    high = [_num(r, "pMax", "maxPrice") for r in rows]
    low = [_num(r, "pMin", "minPrice") for r in rows]
    volume = [_num(r, "qTotTran5J", "volume") for r in rows]
    ema12, ema26 = _ema(close, 12), _ema(close, 26)
    macd_raw = [a - b if a is not None and b is not None else None for a, b in zip(ema12, ema26)]
    macd_signal = _ema(macd_raw, 9)
    rsi = _rsi(close); atr = _atr(rows)
    out = []
    for i, r in enumerate(rows):
        item = dict(r)
        item.update({
            "sma20": _sma(close, 20, i), "sma50": _sma(close, 50, i), "sma200": _sma(close, 200, i),
            "ema12": ema12[i], "ema26": ema26[i], "macd": macd_raw[i], "macd_signal": macd_signal[i],
            "rsi14": rsi[i], "atr14": atr[i], "volume_sma20": _sma(volume, 20, i),
        })
        c = close[i]
        v = volume[i]
        signals: list[str] = []
        if c is not None and item["sma20"] is not None and item["sma50"] is not None:
            if c > item["sma20"] > item["sma50"]: signals.append("trend_up")
            if c < item["sma20"] < item["sma50"]: signals.append("trend_down")
        if rsi[i] is not None:
            if rsi[i] < 30: signals.append("rsi_oversold")
            elif rsi[i] > 70: signals.append("rsi_overbought")
        if macd_raw[i] is not None and macd_signal[i] is not None:
            if macd_raw[i] > macd_signal[i]: signals.append("macd_bullish")
            elif macd_raw[i] < macd_signal[i]: signals.append("macd_bearish")
        if v is not None and item["volume_sma20"] not in (None, 0) and v >= 2 * item["volume_sma20"]: signals.append("volume_spike")
        item["signals"] = signals
        out.append(item)
    return out


def backtest(rows: list[dict[str, Any]], horizon: int = 5) -> dict[str, Any]:
    close = [_num(r, "pClosing", "close", "closingPrice") for r in rows]
    rules = {
        "trend_up": lambda r: "trend_up" in r["signals"],
        "rsi_oversold": lambda r: "rsi_oversold" in r["signals"],
        "macd_bullish": lambda r: "macd_bullish" in r["signals"],
        "volume_spike": lambda r: "volume_spike" in r["signals"],
        "trend_down": lambda r: "trend_down" in r["signals"],
        "rsi_overbought": lambda r: "rsi_overbought" in r["signals"],
        "macd_bearish": lambda r: "macd_bearish" in r["signals"],
    }
    result: dict[str, Any] = {}
    for name, rule in rules.items():
        rets = []
        for i in range(len(rows) - horizon):
            if not rule(rows[i]) or close[i] in (None, 0) or close[i + horizon] is None: continue
            rets.append((close[i + horizon] / close[i] - 1) * 100)
        wins = sum(x > 0 for x in rets)
        result[name] = {"signals": len(rets), "win_rate_pct": round(100 * wins / len(rets), 2) if rets else None, "avg_forward_return_pct": round(sum(rets) / len(rets), 2) if rets else None, "median_forward_return_pct": round(sorted(rets)[len(rets)//2], 2) if rets else None}
    return result


def sensitive_points(rows: list[dict[str, Any]], window: int = 10) -> list[dict[str, Any]]:
    close = [_num(r, "pClosing", "close", "closingPrice") for r in rows]; points = []
    for i in range(window, len(rows) - window):
        c = close[i]
        if c is None: continue
        left = [x for x in close[i-window:i] if x is not None]; right = [x for x in close[i+1:i+1+window] if x is not None]
        if left and right and (c >= max(left) and c >= max(right) or c <= min(left) and c <= min(right)):
            points.append({"date": _date(rows[i]), "price": c, "type": "resistance" if c >= max(left + right) else "support", "signals": rows[i]["signals"]})
    return points


def analyze_symbol(symbol: str, horizon: int = 5) -> dict[str, Any]:
    adapter = TsetmcAdapter(); instrument = adapter.resolve_symbol(symbol); ins_code = str(instrument["insCode"])
    raw = adapter.daily_history(ins_code, 0)
    rows = enrich(raw)
    result = {"symbol": symbol, "source": "TSETMC", "ins_code": ins_code, "history_rows": len(rows), "range_start": _date(rows[0]) if rows else None, "range_end": _date(rows[-1]) if rows else None, "backtest_horizon_days": horizon, "indicator_backtest": backtest(rows, horizon), "sensitive_points": sensitive_points(rows), "latest": rows[-1] if rows else None}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / f"{symbol}.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default), encoding="utf-8")
    if rows:
        fields = ["dEven", "pOpening", "pMax", "pMin", "pClosing", "pDrCotVal", "qTotTran5J", "qTotCap", "zTotTran", "sma20", "sma50", "sma200", "ema12", "ema26", "macd", "macd_signal", "rsi14", "atr14", "volume_sma20", "signals"]
        with (OUT / f"{symbol}.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore"); w.writeheader()
            for r in rows:
                x = dict(r); x["signals"] = ",".join(x.get("signals", [])); w.writerow(x)
    return result


def _json_default(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)): return None
    raise TypeError(f"not JSON serializable: {type(value).__name__}")


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("symbol"); p.add_argument("--horizon", type=int, default=5); args = p.parse_args()
    result = analyze_symbol(args.symbol, args.horizon)
    print(json.dumps(result, ensure_ascii=False, indent=2, default=_json_default))


if __name__ == "__main__": main()
