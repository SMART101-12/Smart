"""Ten transparent research lenses over verified, completed TSETMC daily bars.

These rules are SMART's explicit interpretations of commonly used Iranian
charting criteria, not copied recommendations or calibrated forecasts.
"""
from __future__ import annotations

from math import isfinite
from statistics import pstdev
from typing import Any

import pandas as pd

from smart_v2.analysis.stock_service import StockAnalysisService


SPECS = (
    ("sma_trend", "روند میانگین‌های ۲۰ و ۵۰ روزه", 50),
    ("macd", "همگرایی میانگین‌ها (MACD)", 35),
    ("rsi", "قدرت نسبی (RSI 14)", 15),
    ("bollinger", "باند بولینگر (۲۰، ۲)", 20),
    ("ichimoku", "ابر ایچیموکو (۹، ۲۶، ۵۲)", 78),
    ("adx", "قدرت روند و جهت (ADX 14)", 30),
    ("mfi", "جریان پول حجمی (MFI 14)", 15),
    ("obv", "حجم تجمعی (OBV 20)", 21),
    ("volume_breakout", "شکست ۲۰ روزه با تأیید حجم", 21),
    ("atr_regime", "ریسک نوسان (ATR 14)", 35),
)


def _model(spec: tuple[str, str, int], signal: str = "unavailable", *,
           reason: str = "دادهٔ معتبر کافی نیست", metrics: dict | None = None) -> dict[str, Any]:
    ident, title, bars = spec
    return {"id": ident, "title": title, "required_bars": bars,
            "status": "available" if signal != "unavailable" else "unavailable",
            "signal": signal, "reason": reason, "metrics": metrics or {}}


def _last(value: Any) -> float | None:
    try:
        number = float(value)
        return round(number, 6) if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _direction(up: bool, down: bool) -> str:
    return "bullish" if up else "bearish" if down else "neutral"


def analyze_market_models(history: list[dict[str, Any]], *, symbol: str) -> dict[str, Any]:
    """Use no fabricated candles, same-day future data or source-side signals."""
    try:
        frame, bars, quality = StockAnalysisService.to_frame(
            history, symbol=symbol, include_quality=True)
    except (ValueError, TypeError, KeyError) as exc:
        return {"status": "unavailable", "symbol": symbol, "as_of": None,
                "data_quality": {"error": str(exc)},
                "models": [_model(spec, reason=str(exc)) for spec in SPECS]}
    latest = bars[-1]["source_date"]
    if not quality["latest_bar_verified"]:
        return {"status": "unavailable", "symbol": symbol, "as_of": latest,
                "data_quality": quality,
                "models": [_model(spec, reason="آخرین کندل منبع معتبر نیست؛ خروجی قدیمی ارائه نمی‌شود")
                           for spec in SPECS]}

    n = len(bars)
    close, high, low, volume = (frame[key].astype(float).reset_index(drop=True)
                                for key in ("close", "high", "low", "volume"))
    c = float(close.iloc[-1])
    out: list[dict[str, Any]] = []
    for spec in SPECS:
        ident, _, required = spec
        if n < required:
            out.append(_model(spec, reason=f"حداقل {required} کندل معتبر لازم است؛ {n} موجود است"))
            continue
        signal = "neutral"
        reason = "شرط صعودی یا نزولی تأیید نشده است"
        metrics: dict[str, Any] = {}
        if ident == "sma_trend":
            s20, s50 = float(close.iloc[-20:].mean()), float(close.iloc[-50:].mean())
            signal = _direction(c > s20 > s50, c < s20 < s50)
            metrics = {"close": c, "sma20": s20, "sma50": s50}
            reason = "ترتیب قیمت و میانگین‌های ۲۰/۵۰ روزه"
        elif ident == "macd":
            fast = close.ewm(span=12, adjust=False, min_periods=12).mean()
            slow = close.ewm(span=26, adjust=False, min_periods=26).mean()
            line = fast - slow
            sig = line.ewm(span=9, adjust=False, min_periods=9).mean()
            m, s = _last(line.iloc[-1]), _last(sig.iloc[-1])
            signal = _direction(m > s and m > 0, m < s and m < 0)
            metrics = {"macd": m, "signal_line": s, "histogram": m - s}
            reason = "مقایسهٔ خط MACD با خط سیگنال و صفر"
        elif ident == "rsi":
            from .technical_analysis import rsi
            value = rsi(close.tolist(), 14)[-1]
            signal = _direction(50 < value < 70, 30 < value < 50)
            metrics = {"rsi14": value}
            reason = "بازهٔ ۳۰/۵۰/۷۰؛ نواحی اشباع جهت مستقل نمی‌دهند"
        elif ident == "bollinger":
            center = float(close.iloc[-20:].mean())
            deviation = pstdev(close.iloc[-20:].tolist())
            bottom, top = center - 2 * deviation, center + 2 * deviation
            signal = _direction(center < c < top, bottom < c < center)
            metrics = {"lower": bottom, "middle": center, "upper": top, "close": c}
            reason = "جایگاه قیمت در باند؛ بیرون باند به‌تنهایی سیگنال نیست"
        elif ident == "ichimoku":
            tenkan = (max(high.iloc[-9:]) + min(low.iloc[-9:])) / 2
            kijun = (max(high.iloc[-26:]) + min(low.iloc[-26:])) / 2
            # The cloud visible at t comes from observations at t-26.
            old_tenkan = (max(high.iloc[-35:-26]) + min(low.iloc[-35:-26])) / 2
            old_kijun = (max(high.iloc[-52:-26]) + min(low.iloc[-52:-26])) / 2
            span_a = (old_tenkan + old_kijun) / 2
            span_b = (max(high.iloc[-78:-26]) + min(low.iloc[-78:-26])) / 2
            signal = _direction(c > max(span_a, span_b) and tenkan > kijun,
                                c < min(span_a, span_b) and tenkan < kijun)
            metrics = {"tenkan": tenkan, "kijun": kijun, "cloud_a": span_a,
                       "cloud_b": span_b, "close": c}
            reason = "ابر جابه‌جا شدهٔ ۲۶ روز قبل و ترتیب تنکان/کیجون؛ بدون آینده‌نگری"
        elif ident == "adx":
            up, down = high.diff(), -low.diff()
            plus_dm = up.where((up > down) & (up > 0), 0.0)
            minus_dm = down.where((down > up) & (down > 0), 0.0)
            tr = pd.concat((high - low, (high - close.shift()).abs(),
                            (low - close.shift()).abs()), axis=1).max(axis=1)
            smooth = lambda x: x.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
            atr = smooth(tr)
            plus, minus = 100 * smooth(plus_dm) / atr, 100 * smooth(minus_dm) / atr
            dx = 100 * (plus - minus).abs() / (plus + minus).replace(0, float("nan"))
            adx, p, m = _last(smooth(dx).iloc[-1]), _last(plus.iloc[-1]), _last(minus.iloc[-1])
            if adx is None or p is None or m is None:
                out.append(_model(spec, reason="دامنهٔ واقعی یا جهت حرکت قابل محاسبه نیست"))
                continue
            signal = _direction(adx >= 25 and p > m, adx >= 25 and m > p)
            metrics = {"adx14": adx, "plus_di": p, "minus_di": m}
            reason = "قدرت روند ۲۵ و مقایسهٔ DI مثبت/منفی"
        elif ident == "mfi":
            typical = (high + low + close) / 3
            flow = typical * volume
            delta = typical.diff()
            positive = float(flow.where(delta > 0, 0).iloc[-14:].sum())
            negative = float(flow.where(delta < 0, 0).iloc[-14:].sum())
            if positive + negative <= 0:
                out.append(_model(spec, reason="حجم یا جریان پول معتبر برای این بازه موجود نیست"))
                continue
            value = 100 * positive / (positive + negative)
            signal = _direction(50 < value < 80, 20 < value < 50)
            metrics = {"mfi14": value}
            reason = "قیمت نمونه و حجم؛ نواحی اشباع به‌تنهایی جهت نمی‌دهند"
        elif ident == "obv":
            signed = close.diff().fillna(0).apply(lambda x: 1 if x > 0 else -1 if x < 0 else 0)
            obv = (signed * volume).cumsum()
            change = float(obv.iloc[-1] - obv.iloc[-21])
            signal = _direction(change > 0, change < 0)
            metrics = {"obv_change_20": change, "obv": float(obv.iloc[-1])}
            reason = "جهت تغییر حجم تجمعی در ۲۰ کندل"
        elif ident == "volume_breakout":
            ceiling = float(high.iloc[-21:-1].max())
            floor = float(low.iloc[-21:-1].min())
            baseline = float(volume.iloc[-21:-1].mean())
            if baseline <= 0:
                out.append(_model(spec, reason="میانگین حجم ۲۰ کندل مثبت نیست"))
                continue
            ratio = float(volume.iloc[-1] / baseline)
            signal = _direction(c > ceiling and ratio >= 1.2,
                                c < floor and ratio >= 1.2)
            metrics = {"prior_high": ceiling, "prior_low": floor, "volume_ratio": ratio}
            reason = "عبور قیمت از محدودهٔ ۲۰ روز قبل با حجم دست‌کم ۱٫۲ برابر"
        elif ident == "atr_regime":
            previous = close.shift()
            tr = pd.concat((high - low, (high - previous).abs(),
                            (low - previous).abs()), axis=1).max(axis=1)
            current = float(tr.iloc[-14:].mean())
            baseline = float(tr.iloc[-34:-14].mean())
            if baseline <= 0:
                out.append(_model(spec, reason="خط مبنای نوسان مثبت نیست"))
                continue
            ratio = current / baseline
            # Volatility is a risk condition, never a directional vote.
            metrics = {"atr14": current, "atr_baseline20": baseline,
                       "atr_ratio": ratio, "risk_regime": "elevated" if ratio >= 1.5 else "ordinary"}
            reason = "نوسان جاری نسبت به ۲۰ کندل پیشین؛ این مدل جهت خرید/فروش نمی‌دهد"
        out.append(_model(spec, signal, reason=reason,
                          metrics={key: _last(value) if isinstance(value, (int, float)) else value
                                   for key, value in metrics.items()}))
    counts = {signal: sum(m["signal"] == signal for m in out)
              for signal in ("bullish", "bearish", "neutral", "unavailable")}
    return {"status": "available", "symbol": symbol, "as_of": latest,
            "timeframe": "1d", "source": "TSETMC verified daily OHLCV",
            "data_quality": quality, "models": out, "counts": counts,
            "interpretation": "۱۰ دیدگاه پژوهشی مستقل؛ شمارش آنها احتمال موفقیت یا مجوز معامله نیست."
                              " قیمت‌ها از نظر رویدادهای شرکتی تعدیل‌سنجی نشده‌اند."}
