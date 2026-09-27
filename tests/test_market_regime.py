from datetime import date, timedelta

from smart.market_regime import analyze_industry_regime, analyze_market_regime


def _rows(start, slope):
    return [{"date": (date(2026, 8, 26) + timedelta(days=i)).isoformat(),
             "close": round(start * (1 + slope * i), 3)} for i in range(30)]


def test_market_requires_two_current_index_series_and_exposes_divergence():
    cutoff = date(2026, 9, 27)
    bundle = {"source": "TSETMC imported index bundle",
              "major_index": _rows(100, .004),
              "equal_weight_index": _rows(100, -.004)}
    result = analyze_market_regime(bundle, as_of=cutoff)
    assert result["regime"] == "NEUTRAL"
    assert result["conflicts"] == ["major_equal_weight_divergence"]
    assert analyze_market_regime({"source": "TSETMC", "major_index": bundle["major_index"]},
                                 as_of=cutoff)["regime"] == "UNKNOWN"
    bundle["equal_weight_index"].append({"date": "2026-10-01", "close": 200})
    assert "future_observation_excluded" in analyze_market_regime(bundle, as_of=cutoff)["errors"]


def test_industry_membership_does_not_backfill_future_classification():
    bundle = {"source": "TSETMC imported industry bundle",
              "memberships": [{"symbol": "TEST", "industry": "A",
                               "effective_from": "2026-09-01", "effective_to": None}],
              "industry_indices": {"A": _rows(100, .005)}}
    assert analyze_industry_regime(bundle, symbol="TEST", as_of=date(2026, 8, 30))["regime"] == "UNKNOWN"
    result = analyze_industry_regime(bundle, symbol="TEST", as_of=date(2026, 9, 27))
    assert result["regime"] == "BULL"
    assert result["evidence"]["membership_effective_from"] == "2026-09-01"
