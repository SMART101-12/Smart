import asyncio
import os

from smart import unified_analysis as ua


def test_recovery_marks_orphans_but_preserves_owned_jobs_and_evidence(monkeypatch, tmp_path):
    monkeypatch.setattr(ua, "_root", lambda: tmp_path)
    dead = ua.create_job("OLD")
    live = ua.create_job("LIVE")
    path = ua._directory("OLD", dead["analysis_id"])
    path.joinpath("raw.json").write_text('{"original": true}', encoding="utf-8")
    dead.update(status="RUNNING", owner_pid=None)
    ua._write(path / "job.json", dead)
    assert ua.recover_interrupted_jobs() == [dead["analysis_id"]]
    assert ua.find_job(dead["analysis_id"])["status"] == "INTERRUPTED"
    assert path.joinpath("raw.json").read_text() == '{"original": true}'
    assert ua.find_job(live["analysis_id"])["status"] == "QUEUED"
    assert ua._process_alive(os.getpid()) is True


def test_duplicate_symbol_request_reuses_active_analysis(monkeypatch, tmp_path):
    monkeypatch.setattr(ua, "_root", lambda: tmp_path)
    first = ua.create_job("عيار")
    second = ua.create_job("عیار")
    assert first["analysis_id"] == second["analysis_id"]
    assert second["reused_active"] is True
    first.update(status="INTERRUPTED")
    ua._write(ua._directory(first["symbol"], first["analysis_id"]) / "job.json", first)
    assert ua.create_job("عیار")["analysis_id"] != first["analysis_id"]


def test_unexpected_worker_failure_and_timeout_are_persisted(monkeypatch, tmp_path):
    monkeypatch.setattr(ua, "_root", lambda: tmp_path)
    async def fail(job):
        raise RuntimeError("fixture failure outside stage")
    monkeypatch.setattr(ua, "_run_job", fail)
    first = ua.create_job("FAIL")
    asyncio.run(ua.run_job(first))
    assert ua.find_job(first["analysis_id"])["status"] == "FAILED"
    async def slow(job):
        await asyncio.Event().wait()
    monkeypatch.setattr(ua, "_run_job", slow)
    monkeypatch.setattr(ua, "JOB_TIMEOUT_SECONDS", .01)
    second = ua.create_job("SLOW")
    asyncio.run(ua.run_job(second))
    assert ua.find_job(second["analysis_id"])["status"] == "TIMED_OUT"
    assert not ua._active_jobs


def test_concurrent_duplicate_worker_only_executes_once(monkeypatch, tmp_path):
    monkeypatch.setattr(ua, "_root", lambda: tmp_path)
    calls = []
    async def worker(job):
        calls.append(job["analysis_id"])
        await asyncio.sleep(.02)
    monkeypatch.setattr(ua, "_run_job", worker)
    job = ua.create_job("TEST")
    async def run():
        await asyncio.gather(ua.run_job(job), ua.run_job(dict(job)))
    asyncio.run(run())
    assert calls == [job["analysis_id"]]
