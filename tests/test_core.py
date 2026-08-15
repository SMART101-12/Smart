from datetime import date, datetime, timezone

from smart.snapshot_store import SnapshotStore
from smart.tsetmc_adapter import TsetmcAdapter


def test_snapshot_store_freshness(tmp_path):
    store = SnapshotStore(tmp_path / "smart.db")
    now = datetime(2026, 8, 15, 12, 0, tzinfo=timezone.utc)
    store.save("عیار", "tsetmc", now, {"price": 518201})
    assert store.is_fresh_for_today("عیار", "tsetmc", date(2026, 8, 15))
    assert not store.is_fresh_for_today("عیار", "tsetmc", date(2026, 8, 16))
    latest = store.latest("عیار", "tsetmc")
    assert latest["payload"]["price"] == 518201


def test_tsetmc_adapter_collection_contract(monkeypatch, tmp_path):
    responses = {
        "Instrument/GetInstrumentSearch/%D8%B9%DB%8C%D8%A7%D8%B1": {
            "instrumentSearch": [{"lVal18AFC": "عیار", "insCode": "123"}]
        },
        "ClosingPrice/GetClosingPriceInfo/123": {"closingPriceInfo": {"pClosing": 517080}},
        "ClientType/GetClientType/123/1/0": {"clientType": {"buy_I_Volume": 10}},
        "ClosingPrice/GetClosingPriceDailyList/123/0": {
            "closingPriceDaily": [{"dEven": 20260815, "pClosing": 517080}, {"dEven": 20260814, "pClosing": 509267}]
        },
    }

    class FakeResponse:
        headers = {"content-type": "application/json"}

        def __init__(self, payload):
            self.payload = payload

        def raise_for_status(self):
            return None

        def json(self):
            return self.payload

    class FakeSession:
        def __init__(self):
            self.headers = {}

        def get(self, url, timeout):
            path = url.split("/api/", 1)[1]
            return FakeResponse(responses[path])

    adapter = TsetmcAdapter(store=SnapshotStore(tmp_path / "smart.db"))
    monkeypatch.setattr(adapter, "session", FakeSession())
    result = adapter.collect_symbol("عیار")

    assert result["symbol"] == "عیار"
    assert result["ins_code"] == "123"
    assert result["source"] == "tsetmc"
    assert result["history_rows"] == 2
    assert result["latest_history"]["dEven"] == 20260815
    assert adapter.store.latest("عیار", "tsetmc") is not None
