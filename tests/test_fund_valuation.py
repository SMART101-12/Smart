from datetime import date

from smart.fund_financial import fund_valuation


def test_nav_discount_requires_positive_same_session_observed_unit_and_publication():
    nav = {"value": 10000, "unit": "IRR/unit", "as_of": "2026-09-27",
           "published_at": "1405/07/05", "document_id": "official-cell-1"}
    result = fund_valuation(nav, price=9000, price_date="2026-09-27", as_of=date(2026, 9, 28))
    assert result["premium_discount_pct"] == -10
    assert result["valuation_score"] == 70
    assert fund_valuation({**nav, "value": 0}, price=9000,
                          price_date="2026-09-27", as_of=date(2026, 9, 28))["valuation_score"] is None
    assert fund_valuation(nav, price=9000, price_date="2026-09-28",
                          as_of=date(2026, 9, 28))["valuation_score"] is None
    assert fund_valuation({**nav, "published_at": "1405/07/10"}, price=9000,
                          price_date="2026-09-27", as_of=date(2026, 9, 28))["valuation_score"] is None
