from smart.signals import smart_money_phase


def test_smart_money_requires_confirmations():
    result = smart_money_phase(
        price_change_pct=3,
        volume_ratio=2,
        money_flow_score=80,
        retail_buy_power=2,
    )
    assert result.score >= 75
    assert result.phase == "accumulation_or_trend_initiation"
