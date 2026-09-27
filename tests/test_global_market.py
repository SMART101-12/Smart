from datetime import date

from smart.global_market import FREDClient, GlobalMarketArchive


class FakeResponse:
    content = (
        b"observation_date,TEST\n"
        b"2026-08-20,10.5\n"
        b"2026-08-21,11.0\n"
    )

    def raise_for_status(self):
        return None


class FakeSession:
    def __init__(self):
        self.calls = []
        self.headers = {}

    def get(self, url, params=None, timeout=None):
        self.calls.append((url, params, timeout))
        return FakeResponse()


def test_fred_client_parses_csv_and_bounds_request():
    session = FakeSession()
    client = FREDClient(session=session, series_map={"test": "TEST"})
    observations = client.fetch_missing(
        "test", [date(2026, 8, 20), date(2026, 8, 21)]
    )
    assert [item.value for item in observations] == [10.5, 11.0]
    assert session.calls[0][1]["cosd"] == "2026-08-20"
    assert session.calls[0][1]["coed"] == "2026-08-21"


def test_global_archive_marks_provider_gaps_without_forward_fill(tmp_path):
    session = FakeSession()
    archive = GlobalMarketArchive(
        tmp_path, client=FREDClient(session=session, series_map={"test": "TEST"})
    )
    result = archive.sync(
        "test",
        start_date=date(2026, 8, 20),
        end_date=date(2026, 8, 24),
    )
    assert result["fetched_dates"] == 2
    assert "2026-08-24" in result["provider_unavailable_dates"]
    payload = archive.load("test")
    assert "2026-08-24" in payload["unavailable_dates"]
    assert payload["observations"]["2026-08-20"]["value"] == 10.5
