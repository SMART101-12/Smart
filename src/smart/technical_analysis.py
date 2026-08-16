from __future__ import annotations

import argparse
import csv
import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class Bar:
    date: str
    close: float
    high: float
    low: float
    open: float
    volume: float
    value: float
    trades: float


@dataclass
class Feature:
    date: str
    close: float
    return_1d: float | None
    sma5: float | None
    sma20: float | None
    sma50: float | None
    ema12: float | None
    ema26: float | None
    rsi14: float | None
    macd: float | None
    macd_signal: float | None
    atr14: float | None
    volume_ratio20: float | None
    roc20: float | None
    drawdown_60: float | None
    breakout_up20: bool
    breakout_down20: bool
    composite_score: int
    prediction: str
    future_return_5d: float | None
    prediction_correct: bool | None


def _num(row: dict, *keys: str) -> float:
    for key in keys:
        value = row.get(key)
        if value in (None, "", "-"):
            continue
        try:
            return float(str(value).replace(",", ""))
        except ValueError:
            continue
    return 0.0


def load_bars(history_root: Path, symbol: str) -> list[Bar]:
    root = history_root / symbol
    rows: dict[str, dict] = {}
    if root.exists():
        for path in sorted(root.glob("*.json")):
            if len(path.stem) != 6 or not path.stem.isdigit():
                continue
            payload = json.loads(path.read_text(encoding="utf-8"))
            for row in payload.get("daily_history", []):
                date = str(row.get("dEven", ""))
                if len(date) == 8 and date.isdigit():
                    rows[date] = row
    flat = history_root / f"{symbol}.json"
    if flat.exists():
        payload = json.loads(flat.read_text(encoding="utf-8"))
        for row in payload.get("daily_history", []):
            date = str(row.get("dEven", ""))
            if len(date) == 8 and date.isdigit():
                rows.setdefault(date, row)
    bars: list[Bar] = []
    for date in sorted(rows):
        row = rows[date]
        close = _num(row, "pClosing", "pDrCotVal")
        if close <= 0:
            continue
        bars.append(
            Bar(
                date=date,
                close=close,
                high=_num(row, "pMax", "pClosing", "pDrCotVal"),
                low=_num(row, "pMin", "pClosing", "pDrCotVal"),
                open=_num(row, "pFirst", "pClosing", "pDrCotVal"),
                volume=_num(row, "qTotTran5J"),
                value=_num(row, "qTotCap"),
                trades=_num(row, "zTotTran"),
            )
        )
    if not bars:
        raise RuntimeError(f"No usable TSETMC history found for {symbol}")
    return bars


def sma(values: list[float], period: int) -> list[float | None]:
    out = [None] * len(values)
    total = 0.0
    for i, value in enumerate(values):
        total += value
        if i >= period:
            total -= values[i - period]
        if i >= period - 1:
            out[i] = total / period
    return out


def ema(values: list[float | None], period: int) -> list[float | None]:
    out = [None] * len(values)
    clean = [(i, v) for i, v in enumerate(values) if v is not None]
    if len(clean) < period:
        return out
    seed_i = clean[period - 1][0]
    previous = sum(v for _, v in clean[:period]) / period
    out[seed_i] = previous
    alpha = 2.0 / (period + 1.0)
    for i, value in clean[period:]:
        previous = alpha * value + (1.0 - alpha) * previous
        out[i] = previous
    return out


def rsi(values: list[float], period: int = 14) -> list[float | None]:
    out = [None] * len(values)
    if len(values) <= period:
        return out
    gains = [0.0] * len(values)
    losses = [0.0] * len(values)
    for i in range(1, len(values)):
        delta = values[i] - values[i - 1]
        gains[i] = max(delta, 0.0)
        losses[i] = max(-delta, 0.0)
    avg_gain = sum(gains[1 : period + 1]) / period
    avg_loss = sum(losses[1 : period + 1]) / period
    out[period] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(period + 1, len(values)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def atr(bars: list[Bar], period: int = 14) -> list[float | None]:
    tr = [0.0] * len(bars)
    for i, bar in enumerate(bars):
        if i == 0:
            tr[i] = max(bar.high - bar.low, 0.0)
        else:
            tr[i] = max(bar.high - bar.low, abs(bar.high - bars[i - 1].close), abs(bar.low - bars[i - 1].close))
    out = [None] * len(bars)
    if len(bars) < period:
        return out
    value = sum(tr[:period]) / period
    out[period - 1] = value
    for i in range(period, len(bars)):
        value = ((value * (period - 1)) + tr[i]) / period
        out[i] = value
    return out


def _rolling_max(values: list[float], period: int, index: int) -> float | None:
    return None if index < period else max(values[index - period : index])


def _rolling_min(values: list[float], period: int, index: int) -> float | None:
    return None if index < period else min(values[index - period : index])


def build_features(bars: list[Bar], horizon: int = 5) -> list[Feature]:
    closes = [b.close for b in bars]
    volumes = [b.volume for b in bars]
    sma5, sma20, sma50 = sma(closes, 5), sma(closes, 20), sma(closes, 50)
    ema12, ema26 = ema(closes, 12), ema(closes, 26)
    rsi14 = rsi(closes, 14)
    macd = [None if ema12[i] is None or ema26[i] is None else ema12[i] - ema26[i] for i in range(len(bars))]
    macd_signal = ema(macd, 9)
    atr14 = atr(bars, 14)
    volume_avg20 = sma(volumes, 20)
    features: list[Feature] = []
    for i, bar in enumerate(bars):
        return_1d = None if i == 0 else bar.close / bars[i - 1].close - 1.0
        vr = None if volume_avg20[i] in (None, 0) else bar.volume / volume_avg20[i]
        roc20 = None if i < 20 else bar.close / bars[i - 20].close - 1.0
        peak = max(closes[max(0, i - 59) : i + 1])
        drawdown = None if peak == 0 else bar.close / peak - 1.0
        prior_high = _rolling_max(closes, 20, i)
        prior_low = _rolling_min(closes, 20, i)
        breakout_up = prior_high is not None and bar.close > prior_high
        breakout_down = prior_low is not None and bar.close < prior_low
        score = 0
        if sma20[i] is not None:
            score += 1 if bar.close > sma20[i] else -1
        if sma50[i] is not None:
            score += 1 if bar.close > sma50[i] else -1
        if ema12[i] is not None and ema26[i] is not None:
            score += 1 if ema12[i] > ema26[i] else -1
        if macd[i] is not None and macd_signal[i] is not None:
            score += 1 if macd[i] > macd_signal[i] else -1
        if rsi14[i] is not None:
            if rsi14[i] < 30:
                score += 1
            elif rsi14[i] > 70:
                score -= 1
        if breakout_up:
            score += 1
        elif breakout_down:
            score -= 1
        if vr is not None and vr >= 1.5 and return_1d is not None:
            score += 1 if return_1d > 0 else -1
        prediction = "UP" if score >= 2 else "DOWN" if score <= -2 else "NEUTRAL"
        future = None if i + horizon >= len(bars) else bars[i + horizon].close / bar.close - 1.0
        correct = None
        if prediction != "NEUTRAL" and future is not None:
            correct = (prediction == "UP" and future > 0) or (prediction == "DOWN" and future < 0)
        features.append(Feature(
            date=bar.date, close=bar.close, return_1d=return_1d, sma5=sma5[i], sma20=sma20[i], sma50=sma50[i],
            ema12=ema12[i], ema26=ema26[i], rsi14=rsi14[i], macd=macd[i], macd_signal=macd_signal[i],
            atr14=atr14[i], volume_ratio20=vr, roc20=roc20, drawdown_60=drawdown,
            breakout_up20=breakout_up, breakout_down20=breakout_down, composite_score=score,
            prediction=prediction, future_return_5d=future, prediction_correct=correct,
        ))
    return features


def _indicator_accuracy(features: list[Feature], name: str) -> dict:
    cases: list[bool] = []
    for f in features:
        if f.future_return_5d is None:
            continue
        signal: int | None = None
        if name == "SMA20" and f.sma20 is not None:
            signal = 1 if f.close > f.sma20 else -1
        elif name == "SMA50" and f.sma50 is not None:
            signal = 1 if f.close > f.sma50 else -1
        elif name == "EMA12_26" and f.ema12 is not None and f.ema26 is not None:
            signal = 1 if f.ema12 > f.ema26 else -1
        elif name == "MACD" and f.macd is not None and f.macd_signal is not None:
            signal = 1 if f.macd > f.macd_signal else -1
        elif name == "RSI" and f.rsi14 is not None:
            signal = 1 if f.rsi14 < 30 else -1 if f.rsi14 > 70 else None
        elif name == "BREAKOUT20":
            signal = 1 if f.breakout_up20 else -1 if f.breakout_down20 else None
        elif name == "VOLUME_SPIKE" and f.volume_ratio20 is not None and f.volume_ratio20 >= 1.5:
            signal = 1 if (f.return_1d or 0) > 0 else -1 if (f.return_1d or 0) < 0 else None
        if signal is None:
            continue
        outcome = 1 if f.future_return_5d > 0 else -1 if f.future_return_5d < 0 else 0
        if outcome:
            cases.append(signal == outcome)
    return {"indicator": name, "signals": len(cases), "correct": sum(cases), "accuracy": round(sum(cases) / len(cases), 4) if cases else None}


def sensitive_points(features: list[Feature]) -> list[dict]:
    events: list[dict] = []
    for i, f in enumerate(features):
        if i > 0:
            p = features[i - 1]
            if all(x is not None for x in (p.sma20, p.sma50, f.sma20, f.sma50)):
                if p.sma20 <= p.sma50 and f.sma20 > f.sma50:
                    events.append({"date": f.date, "type": "GOLDEN_CROSS", "close": f.close})
                elif p.sma20 >= p.sma50 and f.sma20 < f.sma50:
                    events.append({"date": f.date, "type": "DEATH_CROSS", "close": f.close})
        if f.rsi14 is not None and f.rsi14 < 30:
            events.append({"date": f.date, "type": "RSI_OVERSOLD", "close": f.close, "rsi14": round(f.rsi14, 2)})
        elif f.rsi14 is not None and f.rsi14 > 70:
            events.append({"date": f.date, "type": "RSI_OVERBOUGHT", "close": f.close, "rsi14": round(f.rsi14, 2)})
        if f.volume_ratio20 is not None and f.volume_ratio20 >= 2:
            events.append({"date": f.date, "type": "VOLUME_SPIKE_2X", "close": f.close, "volume_ratio20": round(f.volume_ratio20, 2)})
        if f.breakout_up20:
            events.append({"date": f.date, "type": "BREAKOUT_UP_20D", "close": f.close})
        elif f.breakout_down20:
            events.append({"date": f.date, "type": "BREAKOUT_DOWN_20D", "close": f.close})
        if f.drawdown_60 is not None and f.drawdown_60 <= -0.15:
            events.append({"date": f.date, "type": "DRAWDOWN_15PCT_60D", "close": f.close, "drawdown_60": round(f.drawdown_60, 4)})
    return events


def analyze(symbol: str, history_root: Path, output_root: Path) -> dict:
    bars = load_bars(history_root, symbol)
    features = build_features(bars)
    names = ["SMA20", "SMA50", "EMA12_26", "MACD", "RSI", "BREAKOUT20", "VOLUME_SPIKE"]
    accuracies = [_indicator_accuracy(features, name) for name in names]
    evaluated = [f for f in features if f.prediction != "NEUTRAL" and f.prediction_correct is not None]
    correct = sum(bool(f.prediction_correct) for f in evaluated)
    report = {
        "symbol": symbol,
        "source": "TSETMC history stored in Git",
        "method": "walk-forward, end-of-day signal; 5-trading-day forward return; no look-ahead",
        "bars": len(bars), "range_start": bars[0].date, "range_end": bars[-1].date,
        "composite": {"signals": len(evaluated), "correct": correct, "accuracy": round(correct / len(evaluated), 4) if evaluated else None},
        "indicators": accuracies,
        "sensitive_points": sensitive_points(features),
    }
    output_root.mkdir(parents=True, exist_ok=True)
    (output_root / f"{symbol}_analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    with (output_root / f"{symbol}_signals.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(asdict(features[0]).keys()))
        writer.writeheader(); writer.writerows(asdict(f) for f in features)
    events = report["sensitive_points"]
    with (output_root / f"{symbol}_sensitive_points.csv").open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=sorted({k for e in events for k in e}) if events else ["date", "type", "close"])
        writer.writeheader(); writer.writerows(events)
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward technical analysis using TSETMC history stored in Git")
    parser.add_argument("symbol")
    parser.add_argument("--history-root", default="runtime/history")
    parser.add_argument("--output-root", default="runtime/analysis")
    args = parser.parse_args()
    report = analyze(args.symbol, Path(args.history_root), Path(args.output_root))
    print(json.dumps({k: v for k, v in report.items() if k != "sensitive_points"}, ensure_ascii=False, indent=2))
    print(f"sensitive_points={len(report['sensitive_points'])}")


if __name__ == "__main__":
    main()
