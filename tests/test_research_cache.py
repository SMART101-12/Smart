import asyncio
import json

from smart import research_cache as cache


def test_research_reuses_only_matching_data_cost_configuration_and_implementation(monkeypatch, tmp_path):
    monkeypatch.setenv("SMART_RESEARCH_CACHE", str(tmp_path))
    monkeypatch.setattr(cache, "implementation_fingerprint", lambda: "source-v1")
    calls = []
    async def compute():
        calls.append(1)
        return {"status": "COMPLETE", "return_pct": 1.25}
    original = {"history": [100.1], "cost": .35, "config": "a"}
    first, meta = asyncio.run(cache.cached_research("historical_exam", original, compute))
    assert meta["reused"] is False
    second, meta = asyncio.run(cache.cached_research("historical_exam", original, compute))
    assert meta["reused"] is True and second == first
    for changed in ({**original, "history": [100.2]}, {**original, "cost": .4},
                    {**original, "config": "b"}):
        assert asyncio.run(cache.cached_research("historical_exam", changed, compute))[1]["reused"] is False
    monkeypatch.setattr(cache, "implementation_fingerprint", lambda: "source-v2")
    assert asyncio.run(cache.cached_research("historical_exam", original, compute))[1]["reused"] is False
    assert len(calls) == 5


def test_corrupt_cache_is_recomputed_and_failed_research_is_not_reused(monkeypatch, tmp_path):
    monkeypatch.setenv("SMART_RESEARCH_CACHE", str(tmp_path))
    monkeypatch.setattr(cache, "implementation_fingerprint", lambda: "fixture")
    async def compute():
        return {"value": 3.75}
    asyncio.run(cache.cached_research("long_only_oos", {}, compute))
    path = next(tmp_path.rglob("*.json"))
    payload = json.loads(path.read_text(encoding="utf-8"))
    payload["result"]["value"] = 999
    path.write_text(json.dumps(payload), encoding="utf-8")
    result, meta = asyncio.run(cache.cached_research("long_only_oos", {}, compute))
    assert result["value"] == 3.75 and meta["state"] == "INVALIDATED"
    async def fail():
        return {"status": "FAILED"}
    assert asyncio.run(cache.cached_research("historical_exam", {}, fail))[1]["state"] == "NOT_CACHED"
    assert not (tmp_path / "historical_exam").exists()
