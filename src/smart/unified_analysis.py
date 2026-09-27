"""One auditable stock-analysis job built on SMART's existing engines."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from .archive import safe_symbol

VERSION = "SMART-ANALYSIS-1.3"
ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")


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
    job = {"analysis_id": uuid.uuid4().hex, "symbol": symbol, "status": "QUEUED",
           "stage": "queued", "stages": [], "warnings": [], "created_at": _now(),
           "engine_version": VERSION}
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
    root = _root() / safe_symbol(symbol)
    jobs = sorted(root.glob("*/job.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in jobs:
        job = json.loads(path.read_text(encoding="utf-8"))
        if job["symbol"] == symbol and job["status"] in {"COMPLETED", "PARTIAL"}:
            return get_artifact(symbol, job["analysis_id"], "analysis.json")
    raise FileNotFoundError(symbol)


async def run_job(job: dict[str, Any]) -> None:
    """Keep independent source failures visible without inventing substitute facts."""
    from . import tsetmc
    from .financial_history import HistoricalDataRepository
    from .financial_scoring import FinancialScoringEngine
    from .fund_financial import fund_financial_evidence, is_fund_instrument
    from .conditional_levels import conditional_levels
    from .analysis_layers import from_legacy_summary
    from .data_quality_gate import financial_gate, market_gate
    from .market_models import analyze_market_models
    from .market_regime import analyze_market_regime, analyze_industry_regime, load_regime_snapshot
    from .strategy_lab import bars_from_rows, walk_forward_exam
    from .symbol_learning import build_symbol_profile
    from .unified_evaluation import evaluate_profile
    from dataclasses import asdict

    symbol, analysis_id = job["symbol"], job["analysis_id"]
    directory = _directory(symbol, analysis_id)
    job["status"] = "RUNNING"
    _write(directory / "job.json", job)
    started = time.monotonic()

    async def stage(name, action):
        start = time.monotonic()
        job["stage"] = name
        _write(directory / "job.json", job)
        try:
            value = await action()
            reported = value.get("status") if isinstance(value, dict) else None
            state = "PARTIAL" if reported in {"PARTIAL", "SOURCE_UNAVAILABLE", "INSUFFICIENT_HISTORY", "INSUFFICIENT_DATA", "DEGRADED", "INVALID"} else "COMPLETED"
        except Exception as exc:
            value = None
            state = "NOT_AVAILABLE"
            job["warnings"].append({"stage": name, "error": str(exc)})
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
        market_gate, history or [], symbol=symbol))
    async def regimes():
        snapshot = await asyncio.to_thread(load_regime_snapshot)
        cutoff = date.fromisoformat(quality_gate["as_of"])
        return {"market": analyze_market_regime(snapshot, as_of=cutoff),
                "industry": analyze_industry_regime(snapshot, symbol=canonical, as_of=cutoff)}

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
            technical_history = tsetmc._technical_history(history)
            snapshot = {"symbol": symbol, "source": "TSETMC cached daily history",
                        "technical_history": technical_history,
                        "analysis": {"technical_history": technical_history}}
            snapshot["structured_analysis"] = build_structured_analysis(snapshot)
            return snapshot

        row = await stage("cached_technical", cached_technical)

    async def financial():
        repository = HistoricalDataRepository()
        if is_fund:
            return await asyncio.to_thread(fund_financial_evidence, repository, symbol)
        return await asyncio.to_thread(FinancialScoringEngine(repository).analyze, symbol)

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
                                       instrument_type="FUND" if is_fund else "EQUITY")

    fundamental_quality = await stage("fundamental_quality_gate", verify_financial_source)
    fundamental = None if fundamental_quality and fundamental_quality["status"] == "INVALID" else await stage(
        "fundamental", financial)
    if fundamental and fundamental.get("source_error"):
        job["warnings"].append({"stage": "fundamental", "error": fundamental["source_error"]})
        _write(directory / "job.json", job)

    async def exam():
        if not history:
            raise ValueError("no historical bars")
        # Bound research to recent observations while retaining the terminal
        # holdout. Capping decisions would instead examine only the oldest days.
        recent = [asdict(bar) for bar in bars_from_rows(history)[-300:]]
        return await asyncio.to_thread(walk_forward_exam, recent, symbol=symbol)

    backtest = await stage("historical_exam", exam)

    async def long_only():
        if not history:
            raise ValueError("no historical bars")
        return await asyncio.to_thread(build_symbol_profile, history, symbol=symbol,
                                       transaction_cost_pct=0.35, persist=False,
                                       source_metadata={"source": "TSETMC", "ins_code": ins_code})

    profile = await stage("long_only_oos", long_only)

    async def self_evaluation():
        if not profile or not history:
            raise ValueError("long-only profile unavailable")
        return await asyncio.to_thread(evaluate_profile, profile, history)

    evaluation = await stage("model_self_test", self_evaluation)
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
        recent = [asdict(bar) for bar in bars_from_rows(history)[-60:]]
        return await asyncio.to_thread(conditional_levels, recent, symbol,
                                       model_decision=(self_test or {}).get("decision"))

    levels = await stage("entry_exit", entry_exit)
    async def ten_models():
        cached = ((row or {}).get("analysis") or {}).get("market_models")
        return cached if cached else await asyncio.to_thread(
            analyze_market_models, history or [], symbol=symbol)

    models = await stage("ten_market_models", ten_models)
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
    missing.append("git_publication")
    status = "COMPLETED" if not missing and quality.get("status") == "good" else "PARTIAL"
    evidence_missing = [item for item in missing if item != "git_publication"]
    model_rejected = self_test is not None and self_test.get("decision") != "PAPER_WATCH_CANDIDATE"
    base_path = f"/api/analysis/{quote(symbol, safe='')}/{analysis_id}"
    summary = {
        "status": status, "symbol": canonical, "requested_symbol": symbol,
        "instrument_type": "FUND" if is_fund else "EQUITY",
        "tsetmc_id": ins_code, "analysis_id": analysis_id, "engine_version": VERSION,
        "as_of": structured.get("as_of"), "data_quality": quality,
        "quality_gate": quality_gate,
        "market": (regime or {}).get("market"),
        "industry": (regime or {}).get("industry"),
        "fundamental_quality_gate": fundamental_quality,
        "technical": {key: value for key, value in structured.items()
                      if key not in {"final_assessment", "scenarios"}} if row else None,
        "smart_money": (row or {}).get("smart_money"),
        "fundamental": fundamental,
        "backtest": {"directional_exam": backtest, "long_only": model_backtest},
        "prediction": (profile or {}).get("current_entry") if profile and profile.get("status") == "COMPLETE" else None,
        "entry_exit": levels,
        "market_models": models,
        "self_test": self_test,
        "risk": structured.get("risk"),
        # The legacy contract's quality-only number is not a calibrated
        # probability of future success. No forecast confidence is inferred.
        "confidence": None,
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
    summary.update(from_legacy_summary(summary, job["stages"]))
    context = {"instruction": "Use only supplied validated data. Separate observed facts, calculated metrics and uncertainty. Never invent numbers.",
               "analysis_id": analysis_id, "symbol": canonical, "status": status,
               "as_of": summary["as_of"], "data_quality": quality,
               "quality_gate": quality_gate,
               "market": summary["market"], "industry": summary["industry"],
               "fundamental_quality_gate": fundamental_quality,
               "technical": summary["technical"], "fundamental": fundamental,
               "backtest_status": (backtest or {}).get("status"),
               "long_only_oos": {"metrics": (model_backtest or {}).get("metrics"),
                                 "baseline": (model_backtest or {}).get("baseline")},
               "self_test": self_test,
               "entry_exit": levels,
               "market_models": models,
               "layers": summary["layers"], "contract_version": summary["contract_version"],
               "risk": summary["risk"], "missing_data": missing, "warnings": job["warnings"]}
    raw = {"symbol_resolution": found, "market_analysis": row, "history": history,
           "symbol_profile": profile}
    model_card = {"engine_version": (profile or {}).get("engine_version"),
                  "selected_model": (profile or {}).get("selected_model"),
                  "coverage": (profile or {}).get("coverage"),
                  "protocol": (profile or {}).get("protocol"),
                  "validation": (model_backtest or {}).get("metrics", {}).get("validation"),
                  "frozen_oos": (model_backtest or {}).get("metrics", {}).get("test"),
                  "self_test": self_test, "data_quality": quality,
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
