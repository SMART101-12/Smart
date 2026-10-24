"""Artificial financial evidence for fiscal-calendar comparison regressions."""
from datetime import date
from typing import Any
from unittest.mock import Mock

import pytest

from smart.company_financials import quarterly_trends
from smart.financial_history import HistoricalDataRepository, METRICS
from smart.financial_scoring import FinancialScoringEngine
from smart.fiscal_calendar import comparable_fiscal_year_ends


@pytest.mark.parametrize("periods, expected", [
    (["1402/12/29", "1403/12/30", "1404/12/29"], True),
    (["1402/12/29", "1403/12/29", "1404/12/29"], True),
    (["1403/06/31", "1404/06/31"], True),
    (["1403/09/30", "1404/09/30"], True),
    (["1403/06/30", "1404/06/31"], False),
    (["1403/12/30", "1404/09/30"], False),
    (["1399/12/29", "1403/12/30"], False),
    (["1404/12/30", "1405/12/30"], False),
    (["1404/07/31"], False),
    (["invalid"], False),
    (["1403/12/30", "1404/13/01"], False),
    ([], False),
])
def test_fiscal_end_equivalence_requires_valid_calendar_dates(
    periods: list[str], expected: bool,
) -> None:
    assert comparable_fiscal_year_ends(periods) is expected


def annual_report(period: str) -> dict[str, Any]:
    values = {metric: 10.0 for metric in METRICS}
    values.update(revenue=100.0, assets=200.0, liabilities=80.0, equity=120.0,
                  net_profit=30.0, operating_profit=40.0, operating_cash_flow=35.0,
                  nonoperating_profit=2.0, finance_cost=3.0)
    return {"report_type": "annual", "months": 12, "period": period, "basis": "standalone",
            "document_id": "synthetic-" + period, "source_url": "https://www.codal.ir/synthetic",
            "source_date": "1405/03/01", "digest": "synthetic", "audited": True, "restated": False,
            "retrieved_at": "2026-10-01T00:00:00+00:00",
            "metrics": {key: {"value": value, "unit": "million_IRR", "locator": "synthetic:" + key}
                        for key, value in values.items()}}


@pytest.mark.parametrize("changed_end", [False, True])
def test_annual_scoring_preserves_source_dates_and_rejects_changed_fiscal_month(
    changed_end: bool,
) -> None:
    periods = ["1400/12/29", "1401/12/29", "1402/12/29", "1403/12/30", "1404/12/29"]
    if changed_end:
        periods[-1] = "1404/09/30"
    repository = Mock(spec=HistoricalDataRepository)
    repository.reports.return_value = [annual_report(period) for period in periods]
    repository.state.return_value = {}
    repository.fresh.return_value = False
    result = FinancialScoringEngine(repository).analyze("SYNTHETIC")
    assert result["comparable"] is not changed_end
    assert (result["financial_score"] is None) is changed_end
    assert [row["period"] for row in result["annual"]] == periods


def quarter(year_end: str, ordinal: int, revenue: float) -> dict[str, Any]:
    return {"fiscal_year_end": year_end, "quarter": ordinal, "basis": "standalone",
            "metrics": {metric: {"value": revenue, "unit": "IRR", "source_records": []}
                        for metric in ("revenue", "net_profit", "eps", "gross_profit", "operating_profit")}}


def test_quarterly_yoy_and_qoq_survive_leap_year_without_rewriting_source_dates() -> None:
    rows = [quarter("1402/12/29", 4, 100.0), quarter("1403/12/30", 4, 120.0),
            quarter("1404/12/29", 1, 60.0), quarter("1404/12/29", 4, 150.0)]
    trends = quarterly_trends(rows)
    assert trends[1]["metrics"]["revenue_yoy"]["value"] == pytest.approx(0.2)
    assert trends[2]["metrics"]["revenue_qoq"]["value"] == pytest.approx(-0.5)
    assert trends[3]["metrics"]["revenue_yoy"]["value"] == pytest.approx(0.25)
    assert [row["fiscal_year_end"] for row in trends] == [row["fiscal_year_end"] for row in rows]


def test_quarterly_trends_reject_actual_fiscal_change_and_ambiguous_prior() -> None:
    previous = quarter("1403/12/30", 4, 100.0)
    changed = quarter("1404/09/30", 4, 150.0)
    assert quarterly_trends([previous, changed])[1]["metrics"]["revenue_yoy"]["value"] is None
    current = quarter("1404/12/29", 4, 150.0)
    assert quarterly_trends([previous, previous, current])[2]["metrics"]["revenue_yoy"]["value"] is None


def test_leap_year_comparability_keeps_point_in_time_restatement_selection() -> None:
    periods = ["1400/12/29", "1401/12/29", "1402/12/29", "1403/12/30", "1404/12/29"]
    original = annual_report(periods[-1])
    original["source_date"] = "1405/06/20"
    revision = annual_report(periods[-1])
    revision.update(source_date="1405/07/07", restated=True, document_id="synthetic-revised")
    revision["metrics"]["revenue"]["value"] = 200.0
    repository = Mock(spec=HistoricalDataRepository)
    repository.reports.return_value = [*(annual_report(period) for period in periods[:-1]), original, revision]
    repository.state.return_value = {}
    repository.fresh.return_value = False
    scorer = FinancialScoringEngine(repository)
    before = scorer.analyze("SYNTHETIC", as_of=date(2026, 9, 27))
    after = scorer.analyze("SYNTHETIC", as_of=date(2026, 10, 1))
    assert before["comparable"] and after["comparable"]
    assert before["annual"][-1]["cells"]["revenue"]["value"] == 100.0
    assert after["annual"][-1]["cells"]["revenue"]["value"] == 200.0
    assert [row["period"] for row in before["annual"]] == periods


def test_quarterly_trends_keep_non_esfand_year_end_and_reporting_basis_separate() -> None:
    previous = quarter("1403/09/30", 4, 100.0)
    next_quarter = quarter("1404/09/30", 1, 150.0)
    consolidated = dict(quarter("1403/09/30", 4, 1000.0), basis="consolidated")
    trends = quarterly_trends([previous, consolidated, next_quarter])
    assert trends[-1]["metrics"]["revenue_qoq"]["value"] == pytest.approx(0.5)
    assert trends[-1]["fiscal_year_end"] == "1404/09/30"
