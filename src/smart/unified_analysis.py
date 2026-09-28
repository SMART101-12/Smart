"""One auditable stock-analysis job built on SMART's existing engines."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
import uuid
import contextlib
from threading import RLock
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .archive import safe_symbol, deduplicate_rows
from zoneinfo import ZoneInfo

VERSION = "SMART-ANALYSIS-2.2"
ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")
JOB_TIMEOUT_SECONDS = 1200
STAGE_TIMEOUT_SECONDS = 180
_job_lock = RLock()
_active_jobs: set[str] = set()


def _process_alive(pid: int | None) -> bool:
    if not isinstance(pid, int) or pid <= 0:
        return False
    if pid == os.getpid():
        return True
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        kernel.OpenProcess.restype = wintypes.HANDLE
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5  # Access denied is not proof of death.
        try:
            exit_code = wintypes.DWORD()
            kernel.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code))) and exit_code.value == 259
        finally:
            kernel.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except PermissionError:
        return True
    except ProcessLookupError:
        return False


def recover_interrupted_jobs() -> list[str]:
    """Repair mutable job state only; completed evidence is never rewritten."""
    recovered = []
    for path in _root().glob("*/*/job.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8-sig"))
            if job.get("status") not in {"QUEUED", "RUNNING"} or _process_alive(job.get("owner_pid")):
                continue
            if path.with_name("manifest.json").exists():
                report = get_artifact(job["symbol"], job["analysis_id"], "analysis.json")
                job.update(status=report["status"], stage="finished", finished_at=_now())
            else:
                job.update(status="INTERRUPTED", finished_at=_now(),
                           recovery_reason="analysis_worker_stopped", retryable=True)
            _write(path, job)
            recovered.append(job["analysis_id"])
        except (ValueError, KeyError, OSError):
            # Preserve damaged files for diagnosis rather than replacing evidence.
            continue
    return recovered


def _root() -> Path:
    return Path(os.getenv("SMART_ANALYSIS_ROOT", "runtime/analysis_runs"))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False).encode("utf-8")
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_bytes(encoded)
    # Windows readers can briefly hold a handle on job.json while the
    # dashboard polls it. Keep the atomic replacement and retry that race.
    for attempt in range(10):
        try:
            temporary.replace(path)
            break
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(.03)


def _directory(symbol: str, analysis_id: str) -> Path:
    if not ID_PATTERN.fullmatch(analysis_id):
        raise FileNotFoundError("invalid analysis id")
    return _root() / safe_symbol(symbol) / analysis_id


def create_job(symbol: str) -> dict[str, Any]:
    symbol = str(symbol or "").strip()
    if not symbol or len(symbol) > 80 or any(ch in symbol for ch in "/\\\x00"):
        raise ValueError("invalid symbol")
    from .persian_text import normalize_persian_text
    with _job_lock:
        for path in _root().glob("*/*/job.json"):
            try:
                existing = json.loads(path.read_text(encoding="utf-8-sig"))
                if (existing.get("status") in {"QUEUED", "RUNNING"}
                        and normalize_persian_text(existing.get("symbol")) == normalize_persian_text(symbol)
                        and _process_alive(existing.get("owner_pid"))):
                    return {**existing, "reused_active": True}
            except (ValueError, OSError):
                continue
        job = {"analysis_id": uuid.uuid4().hex, "symbol": symbol, "status": "QUEUED",
               "stage": "queued", "stages": [], "warnings": [], "created_at": _now(),
               "engine_version": VERSION, "owner_pid": os.getpid(), "heartbeat_at": _now()}
        _write(_directory(symbol, job["analysis_id"]) / "job.json", job)
        return job


def get_job(symbol: str, analysis_id: str) -> dict[str, Any]:
    return json.loads((_directory(symbol, analysis_id) / "job.json").read_text(encoding="utf-8"))


def find_job(analysis_id: str) -> dict[str, Any]:
    if not ID_PATTERN.fullmatch(analysis_id):
        raise FileNotFoundError("invalid analysis id")
    for path in _root().glob(f"*/{analysis_id}/job.json"):
        return json.loads(path.read_text(encoding="utf-8"))
    raise FileNotFoundError(analysis_id)


def get_artifact(symbol: str, analysis_id: str, name: str) -> Any:
    if name not in {"analysis.json", "raw.json", "chatgpt.json", "report.json", "model_card.json"}:
        raise FileNotFoundError(name)
    directory = _directory(symbol, analysis_id)
    manifest = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
    contents = (directory / name).read_bytes()
    if hashlib.sha256(contents).hexdigest() != manifest["sha256"][name]:
        raise ValueError("artifact integrity check failed")
    return json.loads(contents)


def latest(symbol: str) -> dict[str, Any]:
    from .persian_text import normalize_persian_text
    jobs = sorted(_root().glob("*/*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in jobs:
        job = json.loads(path.read_text(encoding="utf-8"))
        if (normalize_persian_text(job["symbol"]) == normalize_persian_text(symbol)
                and job["status"] in {"COMPLETED", "PARTIAL"}):
            return get_artifact(job["symbol"], job["analysis_id"], "analysis.json")
    raise FileNotFoundError(symbol)


async def run_job(job: dict[str, Any]) -> None:
    """Own the job lifecycle, including unexpected errors and interrupted runs."""
    analysis_id = job["analysis_id"]
    directory = _directory(job["symbol"], analysis_id)
    with _job_lock:
        if analysis_id in _active_jobs or (directory / "manifest.json").exists():
            return
        _active_jobs.add(analysis_id)
    job.update(owner_pid=os.getpid(), heartbeat_at=_now())

    async def heartbeat():
        while True:
            await asyncio.sleep(5)
            job["heartbeat_at"] = _now()
            _write(directory / "job.json", job)

    def fail(state, error):
        job.update(status=state, finished_at=_now(), retryable=True)
        job.setdefault("warnings", []).append({"stage": job.get("stage"), "error": error})
        _write(directory / "job.json", job)

    monitor = asyncio.create_task(heartbeat())
    try:
        await asyncio.wait_for(_run_job(job), timeout=JOB_TIMEOUT_SECONDS)
    except asyncio.CancelledError:
        if not (directory / "manifest.json").exists():
            fail("INTERRUPTED", "Analysis worker cancelled; retry creates a new analysis.")
        raise
    except TimeoutError:
        fail("TIMED_OUT", "Analysis exceeded its execution budget.")
    except Exception as exc:
        fail("FAILED", str(exc))
    finally:
        monitor.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await monitor
        with _job_lock:
            _active_jobs.discard(analysis_id)


async def _run_job(job: dict[str, Any]) -> None:
    """Keep independent source failures visible without inventing substitute facts."""
    from . import tsetmc
    from .financial_history import HistoricalDataRepository
    from .financial_scoring import FinancialScoringEngine
    from .fund_financial import fund_financial_evidence, fund_valuation, is_fund_instrument
    from .conditional_levels import conditional_levels
    from .analysis_layers import from_legacy_summary
    from .data_quality_gate import financial_gate, market_gate
    from .market_models import analyze_market_models
    from .market_regime import analyze_market_regime, analyze_industry_regime, load_regime_snapshot
    from .index_context_source import fetch_index_context
    from .technical_structure import analyze_technical_structure
    from .flow_analysis import analyze_flow
    from .setup_state import assess_setup
    from .backtest_audit import audit_backtest
    from .final_decision import decide
    from .analysis_settings import load_analysis_configuration
    from .strategy_lab import bars_from_rows, walk_forward_exam
    from .symbol_learning import build_symbol_profile
    from .unified_evaluation import evaluate_profile
    from .research_cache import cached_research
    from dataclasses import asdict

    symbol, analysis_id = job["symbol"], job["analysis_id"]
    directory = _directory(symbol, analysis_id)
    if (directory / "manifest.json").exists():
        # A completed analysis is an immutable snapshot. Refresh creates a
        # new analysis_id; subsequent outcomes live in a separate subfolder.
        return
    job["status"] = "RUNNING"
    _write(directory / "job.json", job)
    started = time.monotonic()

    async def stage(name, action):
        start = time.monotonic()
        job["stage"] = name
        _write(directory / "job.json", job)
        try:
            value = await asyncio.wait_for(action(), timeout=STAGE_TIMEOUT_SECONDS)
            reported = value.get("status") if isinstance(value, dict) else None
            state = "PARTIAL" if reported in {"PARTIAL", "RATE_LIMITED", "SOURCE_UNAVAILABLE", "INSUFFICIENT_HISTORY", "INSUFFICIENT_DATA", "DEGRADED", "INVALID", "UNAVAILABLE", "NOT_AVAILABLE", "CONFLICTING", "unavailable"} else "COMPLETED"
        except Exception as exc:
            value = None
            state = "NOT_AVAILABLE"
            job["warnings"].append({"stage": name, "error":
                                   "Stage execution budget exceeded" if isinstance(exc, TimeoutError) else str(exc)})
        job["stages"].append({"name": name, "status": state,
                              "seconds": round(time.monotonic() - start, 3)})
        with (directory / "analysis.log").open("a", encoding="utf-8") as log:
            log.write(json.dumps({"timestamp": _now(), "symbol": symbol, "stage": name,
                                  "duration": job["stages"][-1]["seconds"],
                                  "source": "TSETMC" if name in {"symbol", "market_and_technical", "historical_data"}
                                            else "KODAL" if name in {"codal_sync", "fundamental"}
                                            else "local", "status": state,
                                  "error": job["warnings"][-1]["error"] if state == "NOT_AVAILABLE" else None},
                                 ensure_ascii=False) + "\n")
        _write(directory / "job.json", job)
        return value

    configuration = await stage("configuration", lambda: asyncio.to_thread(load_analysis_configuration))
    if not configuration:
        job.update(status="FAILED", stage="finished", finished_at=_now())
        _write(directory / "job.json", job)
        return
    found = await stage("symbol", lambda: tsetmc.search_symbol(symbol))
    if not found or not found.get("insCode"):
        job.update(status="SYMBOL_NOT_FOUND", stage="finished", finished_at=_now())
        _write(directory / "job.json", job)
        return
    canonical = found.get("lVal18AFC") or symbol
    ins_code = str(found["insCode"])
    is_fund = is_fund_instrument(found)
    async def fetch_history():
        return await tsetmc.daily_history(ins_code)

    history = await stage("historical_data", fetch_history)
    quality_gate = await stage("data_quality_gate", lambda: asyncio.to_thread(
        market_gate, history or [], symbol=symbol,
        as_of=datetime.now(ZoneInfo("Asia/Tehran")).date(),
        completed_before=datetime.now(ZoneInfo("Asia/Tehran")).date()))
    canonical_history, _ = deduplicate_rows(history or [], symbol=symbol)
    excluded_dates = set((quality_gate or {}).get("invalid_ohlc_dates", []) +
                         (quality_gate or {}).get("missing_volume_dates", []) +
                         (quality_gate or {}).get("future_dates", []) +
                         (quality_gate or {}).get("incomplete_session_dates", []))
    analysis_history = [r for r in canonical_history if r["source_date"] not in excluded_dates]
    async def outcome_review():
        from .analysis_outcomes import record_forward_outcomes
        root = _root() / safe_symbol(symbol)
        prior = sorted(root.glob("*/manifest.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:20]
        recorded = 0
        for manifest_path in prior:
            previous = get_artifact(symbol, manifest_path.parent.name, "analysis.json")
            recorded += len(record_forward_outcomes(previous, analysis_history,
                            manifest_path.parent / "outcomes",
                            as_of=date.fromisoformat(quality_gate["as_of"])))
        return {"status": "COMPLETED", "observed_horizons": recorded,
                "outcomes_used_for_current_decision": False}

    await stage("outcome_review", outcome_review)
    async def regimes():
        snapshot = await asyncio.to_thread(load_regime_snapshot)
        cutoff = date.fromisoformat(quality_gate["as_of"])
        if not snapshot:
            snapshot = await fetch_index_context(symbol=canonical, ins_code=ins_code,
                is_fund=is_fund, as_of=cutoff, last_completed_date=quality_gate.get("latest_valid_date"))
        snapshot["stock_series"] = [{"date": r["source_date"], "close": r["close"]}
                                    for r in analysis_history]
        market = analyze_market_regime(snapshot, as_of=cutoff)
        industry = analyze_industry_regime(snapshot, symbol=canonical, as_of=cutoff)
        market["errors"].extend(e for e in snapshot.get("source_errors", []) if not e.startswith("industry:"))
        industry["errors"].extend(e for e in snapshot.get("source_errors", []) if e.startswith("industry:"))
        return {"status": "SUCCESS" if market["status"] == industry["status"] == "SUCCESS" else "PARTIAL",
                "market": market, "industry": industry, "source_errors": snapshot.get("source_errors", [])}

    regime = await stage("market_industry_regime", regimes)
    critical_market = bool(quality_gate and any(issue in quality_gate["blockers"]
                           for issue in ("latest_bar_invalid_or_future", "future_dated_source_rows")))
    # The existing adapter uses the same local incremental history cache.
    row = None if critical_market else await stage(
        "market_and_technical", lambda: tsetmc.analyze_symbol(symbol))
    live_snapshot_available = row is not None
    if row is None and history and not critical_market:
        async def cached_technical():
            from .analysis_contract import build_structured_analysis
            technical_history = tsetmc._technical_history(analysis_history)
            snapshot = {"symbol": symbol, "source": "TSETMC cached daily history",
                        "technical_history": technical_history,
                        "analysis": {"technical_history": technical_history}}
            snapshot["structured_analysis"] = build_structured_analysis(snapshot)
            return snapshot

        row = await stage("cached_technical", cached_technical)

    async def financial():
        repository = HistoricalDataRepository()
        if is_fund:
            return await asyncio.to_thread(fund_financial_evidence, repository, symbol,
                                           as_of=date.fromisoformat(quality_gate["as_of"]))
        return await asyncio.to_thread(FinancialScoringEngine(repository).analyze, symbol,
                                       as_of=date.fromisoformat(quality_gate["as_of"]))

    async def financial_sync():
        from .codal import HistoricalDataSyncManager
        repository = HistoricalDataRepository()
        return await asyncio.to_thread(HistoricalDataSyncManager(repository).sync_financial, symbol)

    sync = await stage("codal_sync", financial_sync)
    if sync and sync.get("status") in {"PARTIAL", "SOURCE_UNAVAILABLE"}:
        job["warnings"].append({"stage": "codal_sync", "error": sync.get("error") or sync["status"]})
    async def verify_financial_source():
        repository = HistoricalDataRepository()
        return await asyncio.to_thread(financial_gate, repository.reports(symbol), sync,
                                       instrument_type="FUND" if is_fund else "EQUITY",
                                       as_of=date.fromisoformat(quality_gate["as_of"]))

    fundamental_quality = await stage("fundamental_quality_gate", verify_financial_source)
    fundamental = None if fundamental_quality and fundamental_quality["status"] == "INVALID" else await stage(
        "fundamental", financial)
    if is_fund and fundamental:
        last_bar = analysis_history[-1] if analysis_history else {}
        valuation = fund_valuation(fundamental.get("net_asset_value_per_unit"),
                    price=last_bar.get("close"), price_date=last_bar.get("source_date"),
                    as_of=date.fromisoformat(quality_gate["as_of"]))
        fundamental.update(valuation=valuation, valuation_score=valuation["valuation_score"])
    if fundamental and fundamental.get("source_error"):
        job["warnings"].append({"stage": "fundamental", "error": fundamental["source_error"]})
        _write(directory / "job.json", job)

    async def exam():
        if not analysis_history:
            raise ValueError("no historical bars")
        # Bound research to recent observations while retaining the terminal
        # holdout. Capping decisions would instead examine only the oldest days.
        recent = [asdict(bar) for bar in bars_from_rows(analysis_history)[-300:]]
        value, cache = await cached_research("historical_exam", {
            "symbol": symbol, "history": recent, "engine_version": VERSION,
            "configuration": configuration,
            "parameters": {"initial_history": 20, "evaluation_window": 30, "horizon": 5}},
            lambda: asyncio.to_thread(walk_forward_exam, recent, symbol=symbol))
        research_cache["historical_exam"] = cache
        return value

    research_cache = {}
    backtest = await stage("historical_exam", exam)

    async def long_only():
        if not analysis_history:
            raise ValueError("no historical bars")
        metadata = {"source": "TSETMC", "ins_code": ins_code}
        value, cache = await cached_research("long_only_oos", {
            "symbol": symbol, "history": analysis_history, "engine_version": VERSION,
            "configuration": configuration, "transaction_cost_pct": 0.35, "source_metadata": metadata},
            lambda: asyncio.to_thread(build_symbol_profile, analysis_history, symbol=symbol,
                                      transaction_cost_pct=0.35, persist=False, source_metadata=metadata))
        research_cache["long_only_oos"] = cache
        return value

    profile = await stage("long_only_oos", long_only)

    async def self_evaluation():
        if not profile or not analysis_history:
            raise ValueError("long-only profile unavailable")
        return await asyncio.to_thread(evaluate_profile, profile, analysis_history)

    evaluation = await stage("model_self_test", self_evaluation)
    backtest_audit = await stage("backtest_audit", lambda: asyncio.to_thread(
        audit_backtest, profile, evaluation))
    model_backtest = (evaluation or {}).get("backtest")
    self_test = (evaluation or {}).get("self_test")

    async def entry_exit():
        if not quality_gate or quality_gate["blockers"]:
            return {"status": "INSUFFICIENT_DATA", "signal_status": "NOT_AVAILABLE",
                    "reason": "Market data quality gate: " + ", ".join(
                        (quality_gate or {}).get("blockers", ["source_unavailable"])),
                    "plan": None, "conditional": None}
        if not history:
            raise ValueError("no historical bars")
        recent = [asdict(bar) for bar in bars_from_rows(analysis_history)[-60:]]
        return await asyncio.to_thread(conditional_levels, recent, symbol,
                                       model_decision=(self_test or {}).get("decision"))

    levels = await stage("entry_exit", entry_exit)
    async def ten_models():
        return await asyncio.to_thread(analyze_market_models, analysis_history, symbol=symbol)

    models = await stage("ten_market_models", ten_models)
    structure = await stage("technical_structure", lambda: asyncio.to_thread(
        analyze_technical_structure, analysis_history, symbol=symbol,
        as_of=date.fromisoformat(quality_gate["as_of"]), weights=configuration["technical_weights"]))
    flow_analysis = await stage("money_flow", lambda: asyncio.to_thread(
        analyze_flow, analysis_history, symbol=symbol,
        as_of=date.fromisoformat(quality_gate["as_of"]),
        client_type=(row or {}).get("client_type_observation")))
    setup_state = await stage("setup_state", lambda: asyncio.to_thread(
        assess_setup, levels, gate=quality_gate,
        market=(regime or {}).get("market"), industry=(regime or {}).get("industry"),
        flow=flow_analysis, technical=structure,
        model_decision=(self_test or {}).get("decision"),
        last_close=(structure or {}).get("timeframes", {}).get("daily", {}).get("last_close")))
    structured = (row or {}).get("structured_analysis") or {}
    quality = structured.get("data_quality", {"status": "poor", "issues": ["market_unavailable"]})
    if row and not live_snapshot_available:
        quality = dict(quality)
        quality["issues"] = [*quality.get("issues", []), "live_snapshot_unavailable"]
        if quality.get("status") == "good":
            quality["status"] = "medium"
    missing = [key for key, value in (("market", row), ("fundamental", fundamental),
                                      ("backtest", backtest)) if value is None]
    if not live_snapshot_available:
        missing.extend(("live_market_snapshot", "client_type_flow"))
    if not quality_gate or quality_gate["blockers"]:
        missing.append("verified_current_market_data")
    if fundamental_quality and fundamental_quality["status"] == "INVALID":
        missing.append("verified_financial_publication")
    if is_fund:
        if not fundamental or fundamental.get("net_asset_value_per_unit") is None:
            missing.append("verified_fund_nav_per_unit")
    elif fundamental and fundamental.get("financial_score") is None:
        missing.append("verified_five_year_fundamentals")
    if backtest and backtest.get("status") != "COMPLETE":
        missing.append("historical_exam_metrics")
    if not evaluation or evaluation.get("status") != "COMPLETE":
        missing.extend(("long_only_after_cost_backtest", "frozen_oos_model", "model_self_test"))
    if not models or models.get("status") != "available":
        missing.append("ten_market_models")
    if not regime or regime["market"]["status"] != "SUCCESS":
        missing.append("verified_broad_market_regime")
    if not regime or regime["industry"]["status"] != "SUCCESS":
        missing.append("verified_historical_industry_regime")
    status = "COMPLETED" if not missing and quality.get("status") == "good" else "PARTIAL"
    evidence_missing = [item for item in missing if item != "git_publication"]
    model_rejected = self_test is not None and self_test.get("decision") != "PAPER_WATCH_CANDIDATE"
    base_path = f"/api/analysis/{quote(symbol, safe='')}/{analysis_id}"
    summary = {
        "status": status, "symbol": canonical, "requested_symbol": symbol,
        "instrument_type": "FUND" if is_fund else "EQUITY",
        "tsetmc_id": ins_code, "analysis_id": analysis_id, "engine_version": VERSION,
        "configuration": configuration,
        "as_of": (quality_gate or {}).get("latest_valid_date"), "data_quality": quality,
        "quality_gate": quality_gate,
        "market": (regime or {}).get("market"),
        "industry": (regime or {}).get("industry"),
        "regime_source_errors": (regime or {}).get("source_errors", []),
        "fundamental_quality_gate": fundamental_quality,
        "technical": structure,
        "legacy_technical": {key: value for key, value in structured.items()
                             if key not in {"final_assessment", "scenarios"}} if row else None,
        "smart_money": (row or {}).get("smart_money"),
        "fundamental": fundamental,
        "backtest": {"directional_exam": backtest, "long_only": model_backtest,
                     "audit": backtest_audit},
        "prediction": (profile or {}).get("current_entry") if profile and profile.get("status") == "COMPLETE" else None,
        "entry_exit": levels,
        "market_models": models,
        "technical_structure": structure,
        "flow": flow_analysis,
        "setup": setup_state,
        "self_test": self_test,
        "risk": {"level": (setup_state or {}).get("risk"),
                 "stop_distance_pct": (setup_state or {}).get("risk_pct"),
                 "reward_risk_1": (setup_state or {}).get("reward_risk_1"),
                 "liquidity": (setup_state or {}).get("liquidity"),
                 "gap_execution_risk": (setup_state or {}).get("gap_execution_risk")},
        "legacy_risk": structured.get("risk"),
        # The legacy contract's quality-only number is not a calibrated
        # probability of future success. No forecast confidence is inferred.
        "confidence": None,
        "model_policy": {"approved": False, "state": "RESEARCH_CANDIDATE",
                         "automatic_promotion": False},
        "confidence_status": "INSUFFICIENT_DATA" if evidence_missing else "MODEL_REJECTED" if model_rejected else "NOT_CALIBRATED",
        "final_engine_output": {
            "trend": structured.get("trend") if row else None,
            "market_phase": structured.get("market_phase") if row else None,
            "financial_score": fundamental.get("financial_score") if fundamental else None,
            "exam_status": backtest.get("status") if backtest else None,
            "model_decision": self_test.get("decision") if self_test else None,
            "assessment": "INSUFFICIENT_DATA" if evidence_missing else
                          self_test.get("decision") if model_rejected else structured.get("final_assessment", {}).get("label"),
        },
        "warnings": job["warnings"], "missing_data": missing,
        "provenance": {"market": "TSETMC live" if live_snapshot_available else
                       "TSETMC cached history" if row else None,
                       "fundamental": "KODAL" if fundamental and (
                           fundamental.get("coverage", {}).get("available") or
                           fundamental.get("coverage", {}).get("observed_cells")) else None,
                       "retrieved_at": _now(), "point_in_time": bool(row)},
        "seconds": round(time.monotonic() - started, 3),
        "github": {"analysis_url": None, "chatgpt_context_url": None},
        "local_urls": {"analysis": base_path, "chatgpt_context": base_path + "/chatgpt",
                       "raw": base_path + "/raw", "report": base_path + "/report",
                       "model_card": base_path + "/model-card"},
    }
    summary["decision"] = decide(summary, weights=configuration["decision_weights"])
    summary["confidence_evidence"] = summary["decision"]["confidence"]
    summary["research_cache"] = research_cache
    summary["final_engine_output"]["assessment"] = summary["decision"]["state"]
    summary.update(from_legacy_summary(summary, job["stages"]))
    context = {"instruction": "Use only supplied validated data. Separate observed facts, calculated metrics and uncertainty. Never invent numbers.",
               "analysis_id": analysis_id, "symbol": canonical, "status": status,
               "as_of": summary["as_of"], "data_quality": quality,
               "quality_gate": quality_gate,
               "market": summary["market"], "industry": summary["industry"],
               "fundamental_quality_gate": fundamental_quality,
               "technical": summary["technical"], "fundamental": fundamental,
               "backtest_status": (backtest or {}).get("status"),
               "backtest_audit": backtest_audit,
               "long_only_oos": {"metrics": (model_backtest or {}).get("metrics"),
                                 "baseline": (model_backtest or {}).get("baseline")},
               "self_test": self_test,
               "entry_exit": levels,
               "market_models": models,
               "technical_structure": structure,
               "flow": flow_analysis,
               "setup": setup_state,
               "decision": summary["decision"],
               "confidence_evidence": summary["confidence_evidence"],
               "layers": summary["layers"], "contract_version": summary["contract_version"],
               "risk": summary["risk"], "research_cache": research_cache,
               "missing_data": missing, "warnings": job["warnings"]}
    raw = {"symbol_resolution": found, "market_analysis": row, "history": history,
           "symbol_profile": profile, "regime_source_errors": (regime or {}).get("source_errors", [])}
    model_card = {"engine_version": (profile or {}).get("engine_version"),
                  "selected_model": (profile or {}).get("selected_model"),
                  "coverage": (profile or {}).get("coverage"),
                  "protocol": (profile or {}).get("protocol"),
                  "validation": (model_backtest or {}).get("metrics", {}).get("validation"),
                  "frozen_oos": (model_backtest or {}).get("metrics", {}).get("test"),
                  "self_test": self_test, "data_quality": quality,
                  "decision_version": summary["decision"]["version"],
                  "decision_weights": summary["decision"]["weights"],
                  "technical_version": (structure or {}).get("version"),
                  "technical_weights": (structure or {}).get("weights"),
                  "model_policy": summary["model_policy"],
                  "configuration": configuration,
                  "limitations": missing}
    report = {"title": "SMART stock analysis", "summary": summary,
              "limitations": missing, "stages": job["stages"]}
    for name, value in (("analysis.json", summary), ("chatgpt.json", context),
                        ("raw.json", raw), ("report.json", report),
                        ("model_card.json", model_card)):
        _write(directory / name, value)
    hashes = {name: hashlib.sha256((directory / name).read_bytes()).hexdigest()
              for name in ("analysis.json", "chatgpt.json", "raw.json", "report.json", "model_card.json")}
    manifest = {"analysis_id": analysis_id, "symbol": symbol, "status": status,
                "engine_version": VERSION, "created_at": job["created_at"], "sha256": hashes}
    # Manifest cannot hash itself; its integrity is anchored by the local filesystem.
    _write(directory / "manifest.json", manifest)
    job.update(status=status, stage="finished", finished_at=_now())
    _write(directory / "job.json", job)
