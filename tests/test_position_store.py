from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from smart.position_store import PositionStore
from smart_v2.analysis.trade_policy import TradePolicy


def opened(store: PositionStore, **changes: object) -> dict:
    data = dict(request_id="entry-request-1", symbol="TEST", mode="PAPER",
                entry_date=date(2026, 1, 1), entry_price=100, quantity=10,
                stop=95, tp1=110, tp2=120, entry_fee=10)
    data.update(changes)
    return store.open(**data)


def candle(day: str, **changes: float) -> dict:
    return {"date": day, "open": 101, "high": 108, "low": 99,
            "close": 105, "volume": 100, **changes}


def test_persisted_partial_exit_and_idempotency(tmp_path: Path) -> None:
    path = tmp_path / "positions.db"
    store = PositionStore(path)
    p = opened(store)
    assert opened(store)["id"] == p["id"]
    with pytest.raises(ValueError, match="different inputs"):
        opened(store, quantity=20)
    args = dict(request_id="exit-request-1", fill_date=date(2026, 1, 3),
                price=110, quantity=4, fee=2, reason="TP1")
    partial = store.exit_fill(p["id"], **args)
    assert partial["remaining_quantity"] == 6
    assert partial["realized_net_pnl"] == 34  # 40 - sale fee 2 - allocated entry fee 4
    restarted = PositionStore(path)
    assert restarted.exit_fill(p["id"], **args) == partial
    assert restarted.get(p["id"])["remaining_quantity"] == 6
    with pytest.raises(ValueError):
        restarted.exit_fill(p["id"], **{**args, "request_id": "exit-too-many", "quantity": 7})
    closed = restarted.exit_fill(p["id"], **{**args, "request_id": "exit-request-2", "quantity": 6, "price": 120})
    assert closed["status"] == "CLOSED"
    assert closed["realized_net_pnl"] == 146


def test_review_does_not_invent_fill_and_remembers_old_trigger(tmp_path: Path) -> None:
    store = PositionStore(tmp_path / "p.db")
    p = opened(store)
    history = [candle("20260102", high=112), candle("20260103")]
    first = store.review(p["id"], history, as_of=date(2026, 1, 3))
    assert first["latest_action"] == "HOLD" and first["action"] == "TP1_REVIEW"
    assert store.review(p["id"], history, as_of=date(2026, 1, 3)) == first
    persisted = store.get(p["id"])
    assert len(persisted["reviews"]) == 1 and persisted["remaining_quantity"] == 10
    assert persisted["fills"] == []


def test_invalid_or_missing_bar_cannot_silently_disappear(tmp_path: Path) -> None:
    store = PositionStore(tmp_path / "p.db")
    p = opened(store)
    result = store.review(p["id"], [candle("20260102", low=0), candle("20260103")], as_of=date(2026, 1, 3))
    assert result["status"] == "insufficient_data"
    assert store.review(p["id"], [candle("20260102")], as_of=date(2026, 1, 3))["action"] == "REVIEW_DATA"
    assert store.review(p["id"], [candle("20260103")] * 2, as_of=date(2026, 1, 3))["status"] == "insufficient_data"


def test_prior_stop_cannot_be_overridden_by_later_target(tmp_path: Path) -> None:
    store = PositionStore(tmp_path / "p.db")
    p = opened(store)
    result = store.review(p["id"], [candle("20260102", low=90), candle("20260103", high=115)], as_of=date(2026, 1, 3))
    assert result["latest_action"] == "TP1_REVIEW"
    assert result["action"] == "EXIT_REVIEW"


def test_time_exit_uses_frozen_policy_and_future_does_not_leak(tmp_path: Path) -> None:
    store = PositionStore(tmp_path / "p.db")
    p = opened(store, policy=TradePolicy(time_exit_sessions=2))
    rows = [candle("20260102"), candle("20260103")]
    result = store.review(p["id"], rows, as_of=date(2026, 1, 3))
    extended = store.review(p["id"], rows + [candle("20260104", low=1)], as_of=date(2026, 1, 3))
    assert result["observations"] == extended["observations"]
    assert result["action"] == "TIME_EXIT_REVIEW"


def test_stop_changes_never_rewrite_previous_sessions(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import smart.position_store as module
    monkeypatch.setattr(module, "_today", lambda: date(2026, 1, 4))
    store = PositionStore(tmp_path / "p.db")
    p = opened(store)
    with pytest.raises(ValueError):
        store.raise_stop(p["id"], request_id="stop-request-1", stop=99, effective_on=date(2026, 1, 3))
    store.raise_stop(p["id"], request_id="stop-request-1", stop=99, effective_on=date(2026, 1, 5))
    before = store.review(p["id"], [candle("20260103", low=97)], as_of=date(2026, 1, 3))
    assert before["observations"][0]["active_stop"] == 95
    monkeypatch.setattr(module, "_today", lambda: date(2026, 1, 6))
    after = store.review(p["id"], [candle("20260105", low=97)], as_of=date(2026, 1, 5))
    assert after["observations"][0]["active_stop"] == 99
    assert after["action"] == "EXIT_REVIEW"


def test_positions_api_and_source_failure_preserve_holdings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from smart import webapp, tsetmc
    monkeypatch.setenv("SMART_POSITIONS_DB", str(tmp_path / "positions.db"))
    client = TestClient(webapp.app)
    request = dict(request_id="api-entry-1", symbol="TEST", mode="PAPER", entry_date="2026-01-01",
                   entry_price=100, quantity=10, stop=95, tp1=110, tp2=120)
    response = client.post("/api/positions", json=request)
    assert response.status_code == 201
    identity = response.json()["id"]
    assert client.post("/api/positions", json=request).json()["id"] == identity
    assert len(client.get("/api/positions").json()["positions"]) == 1
    async def unavailable(symbol: str) -> dict:
        raise tsetmc.TSETMCError("offline fixture")
    monkeypatch.setattr(tsetmc, "search_symbol", unavailable)
    assert client.post(f"/api/positions/{identity}/review").json()["status"] == "source_error"
    assert client.get(f"/api/positions/{identity}").json()["remaining_quantity"] == 10
    assert client.get("/api/positions/unknown").status_code == 404
    assert client.get("/positions").status_code == 200
    assert client.get("/positions.js").status_code == 200
