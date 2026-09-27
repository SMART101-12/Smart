from smart.setup_state import assess_setup


def _inputs():
    levels = {"status": "ready", "evidence": {"as_of": "20260927", "atr": 2},
              "plan": {"entry": 105, "stop": 99, "tp1": 117, "tp2": 123}}
    kwargs = {"gate": {"blockers": [], "freshness": "FRESH"},
              "market": {"status": "SUCCESS", "regime": "BULL"},
              "industry": {"status": "SUCCESS", "regime": "NEUTRAL"},
              "flow": {"observed_client_type": {"signal": "BULLISH"}, "conflicts": []},
              "technical": {}, "model_decision": "PAPER_WATCH_CANDIDATE",
              "last_close": 106}
    return levels, kwargs


def test_confirmed_setup_requires_all_context_and_reports_math():
    levels, kwargs = _inputs()
    result = assess_setup(levels, **kwargs)
    assert result["state"] == "CONFIRMED"
    assert result["confirmed_plan"]["entry"] == 105
    assert result["reward_risk_1"] == 2
    assert result["expires_on"] == "2026-10-04"
    kwargs["market"] = {"status": "UNAVAILABLE", "regime": "UNKNOWN"}
    watch = assess_setup(levels, **kwargs)
    assert watch["state"] == "WATCH"
    assert watch["confirmed_plan"] is None
    assert watch["hypothetical"] is not None


def test_missing_current_bar_or_invalidation_never_confirms():
    levels, kwargs = _inputs()
    kwargs["gate"] = {"blockers": ["source_stale_or_unavailable"], "freshness": "STALE"}
    assert assess_setup(levels, **kwargs)["state"] == "NO_SETUP"
    kwargs["gate"] = {"blockers": [], "freshness": "FRESH"}
    kwargs["last_close"] = 98
    assert assess_setup(levels, **kwargs)["state"] == "INVALIDATED"
