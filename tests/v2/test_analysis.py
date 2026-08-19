from smart_v2.analysis.service import AnalysisService


def test_analysis_service():
    records = [
        {"date": "2026-08-10", "processing": {"derived": {"close": 100}}},
        {"date": "2026-08-11", "processing": {"derived": {"close": 105}}},
    ]

    result = AnalysisService().analyze(records)

    assert len(result) == 2
    assert result[0]["date"] == "2026-08-10"
    assert result[1]["processing"]["derived"]["close"] == 105
