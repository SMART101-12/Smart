import asyncio
from datetime import date, timedelta

from smart.index_context_source import INDEX_IDS, fetch_index_context
from smart.market_regime import analyze_market_regime


def test_official_identity_dated_history_and_cache_are_required(tmp_path):
    calls = []
    names = {code: title for code, title in INDEX_IDS.values()}
    async def get(path):
        calls.append(path)
        code = path.rsplit("/", 1)[1]
        if "GetInstrumentInfo" in path:
            return {"instrumentInfo": {"insCode": code, "yVal": "68", "lVal30": names[code]}}
        return {"indexB2": [{"insCode": int(code),
                             "dEven": int((date(2026, 8, 30) + timedelta(days=i)).strftime("%Y%m%d")),
                             "xNivInuClMresIbs": 100 + i} for i in range(30)]}
    kwargs = {"symbol": "TEST", "ins_code": "123", "is_fund": True,
              "as_of": date(2026, 9, 28), "last_completed_date": "2026-09-27",
              "getter": get, "cache_root": tmp_path}
    bundle = asyncio.run(fetch_index_context(**kwargs))
    result = analyze_market_regime(bundle, as_of=date(2026, 9, 28))
    assert result["regime"] == "BULL"
    assert result["source_validation"] == "VERIFIED"
    assert bundle["major_index"][-1]["date"] == "2026-09-27"
    count = len(calls)
    assert asyncio.run(fetch_index_context(**kwargs)) == bundle
    assert len(calls) == count
