from smart.gold_model import classify, score_factors


def test_classification_boundaries():
    assert classify(0.60) == "BULLISH_STRONG"
    assert classify(0.25) == "BULLISH"
    assert classify(0.0) == "NEUTRAL"
    assert classify(-0.25) == "BEARISH"
    assert classify(-0.60) == "BEARISH_STRONG"


def test_full_score_is_weighted_and_covered():
    result = score_factors({name: 1.0 for name in [
        "xau_momentum", "dxy", "us10y", "real_yield",
        "fed_expectations", "geopolitics", "central_banks",
        "etf_flows", "oil_inflation"
    ]})
    assert result.score == 1.0
    assert result.regime == "BULLISH_STRONG"
    assert result.coverage == 1.0


def test_missing_factors_are_renormalized_and_coverage_is_exposed():
    result = score_factors({"xau_momentum": 1.0, "dxy": -1.0})
    assert result.score == 0.25
    assert result.coverage == 0.40
