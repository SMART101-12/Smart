from datetime import date

from smart.financial_history import HistoricalDataRepository
from smart.financial_scoring import FinancialScoringEngine
from test_financial_history import fixture_report


def test_restatement_published_after_cutoff_does_not_replace_original(tmp_path):
    repo = HistoricalDataRepository(tmp_path / "financial.db")
    report, raw = fixture_report(1404, revenue=100)
    report["source_date"] = "1405/06/20"
    repo.save_report(report, raw)
    revision, revised_raw = fixture_report(1404, revision=True, revenue=200)
    revision["source_date"] = "1405/07/07"
    repo.save_report(revision, revised_raw)
    before = FinancialScoringEngine(repo).analyze("TEST", as_of=date(2026, 9, 27))
    after = FinancialScoringEngine(repo).analyze("TEST", as_of=date(2026, 10, 1))
    assert before["annual"][-1]["cells"]["revenue"]["value"] == 100
    assert after["annual"][-1]["cells"]["revenue"]["value"] == 200
