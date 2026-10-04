import asyncio
from datetime import date, timedelta

from smart.client_type_source import fetch_client_type_evidence
from smart.index_context_source import fetch_index_context, INDEX_IDS
from smart.market_regime import analyze_industry_regime
from smart.flow_analysis import analyze_flow


def test_client_type_is_exactly_price_dated_and_cached(tmp_path):
    calls = []
    async def get(path):
        calls.append(path)
        return {"clientType": [
            {"insCode": "123", "recDate": 20260928, "buy_I_Volume": 999, "sell_I_Volume": 1},
            {"insCode": "123", "recDate": 20260927, "buy_I_Volume": 40.5, "sell_I_Volume": 60.5,
             "buy_I_Count": 5, "sell_I_Count": 10, "buy_N_Volume": 60.5, "sell_N_Volume": 40.5}]}
    kwargs = {"ins_code": "123", "price_date": "2026-09-27", "as_of": date(2026, 9, 28),
              "getter": get, "cache_root": tmp_path}
    observation = asyncio.run(fetch_client_type_evidence(**kwargs))
    assert observation["date"] == "2026-09-27" and observation["buy_individual_volume"] == 40.5
    assert observation["buy_individual_count"] == 5
    assert asyncio.run(fetch_client_type_evidence(**kwargs)) == observation
    assert len(calls) == 1


def test_conflicting_or_missing_price_session_is_not_replaced_by_latest(tmp_path):
    async def get(path):
        return {"clientType": [{"insCode": "123", "recDate": 20260928}]}
    result = asyncio.run(fetch_client_type_evidence(ins_code="123", price_date="2026-09-27",
                        as_of=date(2026, 9, 28), getter=get, cache_root=tmp_path))
    assert result["status"] == "UNAVAILABLE"
    assert "date" not in result


def test_industry_uses_official_catalog_code_name_and_dated_membership(tmp_path):
    names = {code: title for code, title in INDEX_IDS.values()}
    names["999"] = "27-فلزات اساسي"
    async def get(path):
        if "AllIndexes" in path:
            return {"indexB1": [{"insCode": "999", "lVal30": names["999"]}]}
        code = path.rsplit("/", 1)[1]
        if "GetInstrumentInfo" in path:
            if code == "123":
                return {"instrumentInfo": {"dEven": 20260928,
                        "sector": {"cSecVal": "27", "lSecVal": "فلزات اساسی"}}}
            return {"instrumentInfo": {"insCode": code, "yVal": "68", "lVal30": names[code]}}
        return {"indexB2": [{"insCode": code, "dEven": int((date(2026, 8, 29)+timedelta(days=i)).strftime("%Y%m%d")),
                             "xNivInuClMresIbs": 100+i} for i in range(30)]}
    bundle = asyncio.run(fetch_index_context(symbol="TEST", ins_code="123", is_fund=False,
                         as_of=date(2026, 9, 28), last_completed_date="2026-09-27", getter=get, cache_root=tmp_path))
    result = analyze_industry_regime(bundle, symbol="TEST", as_of=date(2026, 9, 28))
    assert result["status"] == "SUCCESS" and result["source_validation"] == "VERIFIED"
    assert bundle["industry_identity"]["ins_code"] == "999"
    assert analyze_industry_regime(bundle, symbol="TEST", as_of=date(2026, 9, 27))["regime"] == "UNKNOWN"


def test_observed_flow_volume_mismatch_remains_visible():
    history = [{"date": "20260927", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 200}]
    observation = {"source": "TSETMC ClientType", "date": "2026-09-27",
                   "buy_individual_volume": 80, "sell_individual_volume": 70,
                   "buy_corporate_volume": 20, "sell_corporate_volume": 30}
    result = analyze_flow(history, symbol="TEST", as_of=date(2026, 9, 28), client_type=observation)
    assert result["observed_client_type"]["net_individual_volume"] == 10
    assert result["status"] == "CONFLICTING"
    assert "client_type_and_OHLCV_volume_mismatch" in result["conflicts"]
