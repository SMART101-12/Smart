from datetime import date, datetime, timezone

from smart.snapshot_store import SnapshotStore


def test_snapshot_is_saved_and_today_is_fresh(tmp_path):
    store = SnapshotStore(tmp_path / "smart.db")
    observed = datetime(2026, 8, 15, 10, 0, tzinfo=timezone.utc)
    store.save("SHL1", "test", observed, {"price": 123})

    latest = store.latest("SHL1", "test")
    assert latest["payload"]["price"] == 123
    assert store.is_fresh_for_today("SHL1", "test", date(2026, 8, 15)) is True
    assert store.is_fresh_for_today("SHL1", "test", date(2026, 8, 16)) is False
