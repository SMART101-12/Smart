from smart.scanner import Candidate, rank_candidates


def test_ranking_is_descending():
    rows = rank_candidates([
        Candidate("A", smart_money_score=90, technical_score=90, liquidity_score=90, data_quality_score=90),
        Candidate("B", smart_money_score=50, technical_score=50, liquidity_score=50, data_quality_score=50),
    ])
    assert rows[0]["symbol"] == "A"
    assert rows[0]["score"] > rows[1]["score"]
