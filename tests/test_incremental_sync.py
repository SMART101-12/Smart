from datetime import date

from smart.incremental import IncrementalHistorySync, expected_market_dates
from smart.snapshot_store import SnapshotStore


class FakeAdapter:
    def __init__(self):
        self.full_calls = 0
        self.daily_calls = []

    def resolve_symbol(self, symbol):
        return {"insCode": "123", "lVal18AFC": symbol}

    def instrument_calendar(self, ins_code):
        return []

    def daily_history(self, ins_code, top):
        self.full_calls += 1
        return [
            {
                "dEven": 20260815,
                "pFirst": 98,
                "pMax": 105,
                "pMin": 95,
                "pClosing": 100,
                "qTotTran5J": 10,
            }
        ]

    def daily_history_incremental(self, ins_code, dates):
        self.daily_calls.append(list(dates))
        return (
            [
                {
                    "dEven": int(dates[0]),
                    "pFirst": 99,
                    "pMax": 106,
                    "pMin": 96,
                    "pClosing": 101,
                    "qTotTran5J": 11,
                }
            ],
            [],
        )


def test_expected_iran_dates_exclude_thursday_friday():
    assert expected_market_dates(date(2026, 8, 13), date(2026, 8, 16)) == [
        date(2026, 8, 15),
        date(2026, 8, 16),
    ]


def test_first_sync_uses_full_endpoint_once(tmp_path):
    adapter = FakeAdapter()
    sync = IncrementalHistorySync(
        adapter,
        store=SnapshotStore(tmp_path / "db.sqlite"),
        history_root=tmp_path / "history",
        quality_root=tmp_path / "quality",
        canonical_root=tmp_path / "canonical",
    )
    result = sync.sync("X", start_date="20260815", end_date="20260816")
    assert result["status"] == "COMPLETE"
    assert adapter.full_calls == 1
    assert adapter.daily_calls == []
    assert result["canonical_archive"]["quality"]["status"] == "PASS"


def test_existing_archive_only_requests_missing_dates(tmp_path):
    adapter = FakeAdapter()
    sync = IncrementalHistorySync(
        adapter,
        store=SnapshotStore(tmp_path / "db.sqlite"),
        history_root=tmp_path / "history",
        quality_root=tmp_path / "quality",
        canonical_root=tmp_path / "canonical",
    )
    first = sync.sync("X", start_date="20260815", end_date="20260816")
    second = sync.sync("X", start_date="20260815", end_date="20260818")
    assert first["status"] == "COMPLETE"
    assert second["missing_before_fetch"] >= 1
    assert adapter.full_calls == 1
    assert len(adapter.daily_calls) == 1
