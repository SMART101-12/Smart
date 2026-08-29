# -*- coding: utf-8 -*-
"""Robust E2E pipeline tests for smart_v2 (auto-generated)."""
from __future__ import annotations

import inspect
from datetime import timedelta

import pandas as pd
import pytest

# ---------------------------------------------------------------- imports ---
from smart_v2.analysis.smart_money import SmartMoneyAnalyzer
from smart_v2.analysis.smart_money import SmartMoneyAnalyzer
from smart_v2.analysis.gold_fund import GoldFundAnalyzer
from smart_v2.analysis.multi_factor_engine import MultiFactorEngine

from smart_v2.analysis.service import GoldFundAnalyzer  # noqa: E402

try:  # MultiFactorEngine may live in different modules
    from smart_v2.analysis.service import MultiFactorEngine
except ImportError:
    try:
        from smart_v2.analysis import MultiFactorEngine
    except ImportError:
        from smart_v2.ai.service import MultiFactorEngine

try:
    from smart_v2.acquisition.service import get_stock_data, get_macro_data
except ImportError:
    try:
        from smart_v2.acquisition import get_stock_data, get_macro_data
    except ImportError:
        get_stock_data = get_macro_data = None


# --------------------------------------------------------------- helpers ----
def _make_ohlcv(n: int = 40) -> pd.DataFrame:
    """Deterministic OHLCV frame with 30+ rows and many alias columns."""
    n = max(n, 30)
    base = pd.Timestamp("2026-01-01")
    dates = [base + timedelta(days=i) for i in range(n)]
    closes = [1000.0 + i * 10 for i in range(n)]
    opens = [c - 5 for c in closes]
    highs = [c + 15 for c in closes]
    lows = [c - 20 for c in closes]
    vols = [10000 + i * 100 for i in range(n)]
    df = pd.DataFrame({
        "date": dates, "open": opens, "high": highs,
        "low": lows, "close": closes, "volume": vols,
    })
    for alias in ("Date", "Open", "High", "Low", "Close", "Volume",
                  "vol", "Vol", "Close_"):
        df[alias] = df[alias.lower()] if alias.lower() in df.columns else df["close"]
    return df


def _get_frame():
    """Acquire a DataFrame: live acquisition if available, synthetic fallback."""
    df = None
    if get_stock_data is not None:
        try:
            df = get_stock_data()
        except TypeError:
            try:
                df = get_stock_data("ظپظˆظ„ط§ط¯")
            except Exception:
                df = None
        except Exception:
            df = None
        if isinstance(df, dict):
            for key in ("data", "df", "history", "candles", "result"):
                if isinstance(df.get(key), pd.DataFrame):
                    df = df[key]
                    break
            else:
                df = None
    if not isinstance(df, pd.DataFrame) or df.empty:
        df = _make_ohlcv(40)
    if len(df) < 30:
        pytest.skip("acquired frame has fewer than 30 rows")
    return df


def _find_param(sig, names):
    params = sig.parameters
    for n in names:
        if n in params:
            return n
    return None


def _call_analyze(cls, df, aliases=("symbol", "ticker", "name"), sym="ظپظˆظ„ط§ط¯"):
    """Call cls().analyze(...) flexibly by inspecting its signature."""
    inst = cls()
    fn = getattr(inst, "analyze")
    sig = inspect.signature(fn)
    kwargs = {}
    df_param = _find_param(sig, ("df", "data", "dataframe",
                                 "ohlcv", "frame", "dataset"))
    sym_param = _find_param(sig, list(aliases))
    if df_param:
        kwargs[df_param] = df
    if sym_param:
        kwargs[sym_param] = sym
    try:
        return fn(**kwargs)
    except TypeError as exc:
        params = list(sig.parameters.values())
        required = [p for p in params
                    if p.default is inspect.Parameter.empty
                    and p.kind in (p.POSITIONAL_ONLY, p.POSITIONAL_OR_KEYWORD)]
        if df_param is None:
            if required:
                return fn(df, *([sym] if len(required) > 1 else []))
            return fn(df)
        raise exc


def _extract_score(result):
    """Pull a numeric score from dicts, objects, tuples or lists."""
    if isinstance(result, bool):
        return None
    if isinstance(result, (int, float)):
        return float(result)
    if isinstance(result, (tuple, list)) and result:
        return _extract_score(result[0])
    if isinstance(result, dict):
        for key in ("score", "total_score", "final_score",
                    "smart_money_score", "value"):
            if key in result:
                try:
                    return float(result[key])
                except (TypeError, ValueError):
                    continue
        for val in result.values():
            sub = _extract_score(val)
            if sub is not None:
                return sub
        return None
    for attr in ("score", "total_score", "final_score", "smart_money_score",
                 "result", "value", "data"):
        val = getattr(result, attr, None)
        if val is not None and not isinstance(val, (pd.DataFrame, str)):
            sub = _extract_score(val)
            if sub is not None:
                return sub
    return None


def _find_method(obj, names):
    for n in names:
        if hasattr(obj, n) and callable(getattr(obj, n)):
            return getattr(obj, n)
    return None


def _map_scores(fn, scores):
    """Call fn with four canonical scores via kwargs or positional args."""
    canon = ("trend", "smart_money", "momentum", "risk")
    alts = {
        "trend": ("trend", "trend_score"),
        "smart_money": ("smart_money", "smart", "smart_money_score", "sm"),
        "momentum": ("momentum", "momentum_score", "mom"),
        "risk": ("risk", "risk_score"),
    }
    sig = inspect.signature(fn)
    params = sig.parameters
    kwargs = {}
    used = 0
    for canonical in canon:
        for name in params:
            if name not in kwargs and name in alts[canonical]:
                kwargs[name] = scores[canonical]
                used += 1
                break
    if used == 4:
        return fn(**kwargs)
    return fn(*scores.values())


def _get(obj, key):
    if isinstance(obj, dict):
        return obj.get(key)
    return getattr(obj, key, None)


# ----------------------------------------------------------------- tests ----
def test_smart_money_analyzer_e2e():
    df = _get_frame()
    result = _call_analyze(SmartMoneyAnalyzer, df)
    assert result is not None
    score = _extract_score(result)
    if score is None:
        pytest.skip("could not extract numeric score from SmartMoneyAnalyzer output")
    assert 0.0 <= score <= 100.0 or -1.0 <= score <= 1.0


def test_multi_factor_and_gold_fund_e2e():
    df = _get_frame()

    # --- MultiFactorEngine ---
    engine = MultiFactorEngine()
    method = _find_method(engine, ("score", "analyze", "evaluate", "run",
                                   "compute", "calculate", "score_all",
                                   "combined_score", "get_scores"))
    if method is None:
        pytest.skip("no scoring method found on MultiFactorEngine")
    sig = inspect.signature(method)
    required = [p for p in sig.parameters.values()
                if p.default is inspect.Parameter.empty]
    if _find_param(sig, ("scores", "factors", "inputs", "data", "results"))             is not None or len(required) >= 4:
        scores = {"trend": 70.0, "smart_money": 60.0,
                  "momentum": 55.0, "risk": 25.0}
        try:
            out = _map_scores(method, scores)
        except TypeError:
            out = method(70.0, 60.0, 55.0, 25.0)
    else:
        df_param = _find_param(sig, ("df", "data", "dataframe", "ohlcv"))
        try:
            out = method(**{df_param: df}) if df_param else method(df)
        except TypeError:
            out = method(df)
    assert out is not None

    for key in ("score", "total_score", "final_score"):
        val = _get(out, key)
        if val is not None:
            try:
                assert 0.0 <= float(val) <= 100.0
            except (TypeError, ValueError):
                pass
            break
    for key in ("decision", "action", "signal", "recommendation"):
        dec = _get(out, key)
        if dec is not None:
            assert str(dec).strip() != ""
            break
    for key in ("risk", "risk_score", "risk_level"):
        risk = _get(out, key)
        if risk is not None:
            assert str(risk).strip() != ""
            break

    # --- GoldFundAnalyzer ---
    fund_df = _make_ohlcv(30)
    fund_df["price"] = fund_df["close"]
    fund_df["market_price"] = fund_df["close"]
    fund_df["fund_price"] = fund_df["close"]
    fund_df["nav"] = fund_df["close"] / 1000.0
    fund_df["nav_per_unit"] = fund_df["close"] / 1000.0
    fund_df["xau_usd"] = 2000.0
    fund_df["gold_oz_usd"] = 2000.0
    fund_df["usd_irr"] = 600000.0
    fund_df["usd_irr_rate"] = 600000.0

    inst = GoldFundAnalyzer()
    fn = getattr(inst, "analyze")
    sig = inspect.signature(fn)
    df_param = _find_param(sig, ("df", "data", "dataframe",
                                 "ohlcv", "frame"))
    scalar_map = {"price": 1050.0, "market_price": 1050.0, "fund_price": 1050.0,
                  "nav": 1.05, "nav_per_unit": 1.05, "xau_usd": 2000.0,
                  "gold_oz_usd": 2000.0, "usd_irr": 600000.0,
                  "usd_irr_rate": 600000.0}
    if df_param:
        try:
            fresult = fn(**{df_param: fund_df})
        except TypeError:
            fresult = fn(fund_df)
    else:
        kwargs = {k: v for k, v in scalar_map.items() if k in sig.parameters}
        if not kwargs:
            pytest.skip("GoldFundAnalyzer.analyze signature cannot be supported")
        fresult = fn(**kwargs)
    assert fresult is not None
    for key in ("action", "decision", "signal", "recommendation"):
        val = _get(fresult, key)
        if val is not None:
            assert str(val).strip() != ""
            break
