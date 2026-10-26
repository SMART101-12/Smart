"""Browser-facing SMART dashboard with charts, walk-forward exam and AI explainer."""
from __future__ import annotations

import json
import os
from typing import Any, Callable
from contextlib import asynccontextmanager
from datetime import date, datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field, FiniteFloat, StrictBool

from .ai import ask_structured_analysis, healthcheck
from .analysis_contract import build_structured_analysis
from .decision_memory import DecisionMemory
from .daily_cycle import (
    ActiveRunError,
    DailyRunStore,
    default_store_path,
    execute_daily_run,
    normalize_symbols,
)
from .risk import portfolio_summary, position_size
from .strategy_lab import strategy_catalog
from .strategy_lab import strategy_definitions
from .symbol_learning import FOCUS_SYMBOLS, load_latest_symbol_profile, summarize_profile
from .tsetmc import (
    focus_symbol_profiles,
    historical_exam,
    live_initial_analysis,
    symbol_entry_profile,
)

@asynccontextmanager
async def analysis_lifespan(app):
    from .unified_analysis import recover_interrupted_jobs
    recover_interrupted_jobs()
    yield


app = FastAPI(title="SMART Market Intelligence", version="0.5.0", lifespan=analysis_lifespan)


@app.get("/positions", response_class=HTMLResponse)
def positions_page() -> str:
    from .positions_ui import HTML
    return HTML


@app.get("/positions.js")
def positions_script():
    from pathlib import Path
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).with_name("positions.js"), media_type="text/javascript")


class UnifiedAnalysisRequest(BaseModel):
    symbol: str


@app.post("/api/analyze", status_code=202)
async def start_unified_analysis(request: UnifiedAnalysisRequest, background_tasks: BackgroundTasks):
    from .unified_analysis import create_job, run_job
    try:
        job = create_job(request.symbol)
    except ValueError as exc:
        raise HTTPException(422, detail=str(exc)) from exc
    if not job.get("reused_active"):
        background_tasks.add_task(run_job, job)
    return job


@app.get("/api/analyze/{job_id}")
def unified_analysis_job(job_id: str):
    from .unified_analysis import find_job
    try:
        return find_job(job_id)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail="analysis job not found") from exc


@app.get("/api/analysis/{symbol}/latest")
def latest_unified_analysis(symbol: str):
    from .unified_analysis import latest
    try:
        return latest(symbol)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail="analysis not found") from exc


@app.get("/api/analysis/{symbol}/history")
def unified_analysis_history(symbol: str, limit: int = Query(20, ge=1, le=100)):
    from .unified_analysis import _root, get_artifact
    from .persian_text import normalize_persian_text
    items = []
    for path in _root().glob("*/*/job.json"):
        try:
            job = json.loads(path.read_text(encoding="utf-8-sig"))
            if normalize_persian_text(job["symbol"]) != normalize_persian_text(symbol):
                continue
            item = {key: job.get(key) for key in
                    ("analysis_id", "symbol", "status", "created_at", "engine_version", "stage")}
            if path.with_name("manifest.json").exists():
                try:
                    report = get_artifact(job["symbol"], job["analysis_id"], "analysis.json")
                    item.update(as_of=report.get("as_of"), decision=(report.get("decision") or {}).get("state"),
                                failed_gates=(report.get("decision") or {}).get("failed_gates", []),
                                self_test=(report.get("self_test") or {}).get("decision"))
                except (ValueError, KeyError, OSError):
                    item.update(status="INTEGRITY_ERROR")
            items.append(item)
        except (ValueError, KeyError, OSError):
            continue
    return {"symbol": symbol, "items": sorted(items, key=lambda item: item.get("created_at") or "", reverse=True)[:limit]}


def _read_unified_artifact(symbol: str, analysis_id: str, name: str):
    from .unified_analysis import get_artifact
    try:
        return get_artifact(symbol, analysis_id, name)
    except FileNotFoundError as exc:
        raise HTTPException(404, detail="analysis artifact not found") from exc
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@app.get("/api/analysis/{symbol}/{analysis_id}")
def unified_analysis_artifact(symbol: str, analysis_id: str):
    return _read_unified_artifact(symbol, analysis_id, "analysis.json")


@app.get("/api/analysis/{symbol}/{analysis_id}/chatgpt")
def unified_analysis_chatgpt(symbol: str, analysis_id: str):
    return _read_unified_artifact(symbol, analysis_id, "chatgpt.json")


@app.get("/api/analysis/{symbol}/{analysis_id}/raw")
def unified_analysis_raw(symbol: str, analysis_id: str):
    return _read_unified_artifact(symbol, analysis_id, "raw.json")


@app.get("/api/analysis/{symbol}/{analysis_id}/analysts")
def unified_analysis_analysts(symbol: str, analysis_id: str):
    from fastapi.responses import JSONResponse
    payload = _read_unified_artifact(symbol, analysis_id, "analysts.json")
    return JSONResponse(payload, headers={"Content-Disposition": f'attachment; filename="smart-evidence-{analysis_id}.json"'})


@app.get("/api/analysis/{symbol}/{analysis_id}/chart")
def unified_analysis_chart(symbol: str, analysis_id: str):
    from .archive import deduplicate_rows
    import math
    summary = _read_unified_artifact(symbol, analysis_id, "analysis.json")
    raw = _read_unified_artifact(symbol, analysis_id, "raw.json")
    gate = summary.get("quality_gate") or {}
    excluded = {day for key in ("invalid_ohlc_dates", "missing_volume_dates",
                                "future_dates", "incomplete_session_dates", "conflicting_duplicate_dates")
                for day in gate.get(key, [])}
    cutoff = gate.get("latest_valid_date") or summary.get("as_of")
    history = raw.get("verified_analysis_history")
    if history is None:
        history = raw.get("history") or []
    rows, _ = deduplicate_rows(history, symbol=symbol)
    bars = [{key: row[key] for key in ("source_date", "open", "high", "low", "close", "volume")}
            for row in rows if cutoff and row["source_date"] <= cutoff
            and row["source_date"] not in excluded
            and all(isinstance(row.get(key), (int, float)) and math.isfinite(row[key])
                    for key in ("open", "high", "low", "close", "volume"))
            and 0 < row["low"] <= min(row["open"], row["close"])
            and row["high"] >= max(row["open"], row["close"]) and row["volume"] >= 0]
    return {"symbol": symbol, "as_of": cutoff, "source": gate.get("source"),
            "adjustment": gate.get("corporate_action_adjustment", "UNVERIFIED"),
            "bars": sorted(bars, key=lambda row: row["source_date"])}


@app.get("/api/analysis/{symbol}/{analysis_id}/insights")
def unified_analysis_insights(symbol: str, analysis_id: str):
    from .analysis_insights import explain_gates, report_source_health
    from .financial_history import HistoricalDataRepository
    from .unified_analysis import _now
    summary = _read_unified_artifact(symbol, analysis_id, "analysis.json")
    cooldown = HistoricalDataRepository().state("__SOURCE__", "KODAL_HTTP")
    return {"analysis_id": analysis_id, "report_as_of": summary.get("as_of"),
            "gates": explain_gates(summary), "sources": report_source_health(summary),
            "codal_cooldown": cooldown if cooldown.get("retry_at", "") > _now() else None,
            "sources_scope": "saved_report", "checked_at": _now()}


@app.get("/dashboard.js")
@app.get("/dashboard.css")
def dashboard_asset(request: Request):
    from pathlib import Path
    from fastapi.responses import FileResponse
    filename = request.url.path.rsplit("/", 1)[-1]
    return FileResponse(Path(__file__).with_name(filename),
                        media_type="text/javascript" if filename.endswith(".js") else "text/css")


@app.get("/api/analysis/{symbol}/{analysis_id}/report")
def unified_analysis_report(symbol: str, analysis_id: str):
    return _read_unified_artifact(symbol, analysis_id, "report.json")


@app.get("/api/analysis/{symbol}/{analysis_id}/manifest")
def unified_analysis_manifest(symbol: str, analysis_id: str):
    from .unified_analysis import _directory
    try:
        path = _directory(symbol, analysis_id) / "manifest.json"
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise HTTPException(404, detail="manifest not found") from exc


@app.get("/api/analysis/{symbol}/{analysis_id}/model-card")
def unified_analysis_model_card(symbol: str, analysis_id: str):
    return _read_unified_artifact(symbol, analysis_id, "model_card.json")


@app.get("/", response_class=HTMLResponse)
def unified_dashboard():
    from .unified_dashboard import HTML
    return HTML


@app.get("/api/analysis/{symbol}/{analysis_id}/replay")
def unified_analysis_replay(symbol: str, analysis_id: str):
    from .analysis_outcomes import replay_decision
    summary = _read_unified_artifact(symbol, analysis_id, "analysis.json")
    try:
        return replay_decision(summary)
    except ValueError as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@app.get("/api/analysis/{symbol}/{analysis_id}/outcomes")
def unified_analysis_outcomes(symbol: str, analysis_id: str):
    from .unified_analysis import _directory
    _read_unified_artifact(symbol, analysis_id, "analysis.json")
    root = _directory(symbol, analysis_id) / "outcomes"
    return {"analysis_id": analysis_id, "outcomes": [json.loads(p.read_text(encoding="utf-8"))
            for p in sorted(root.glob("*.json"))], "used_for_original_decision": False}


@app.post("/api/analysis/{symbol}/{analysis_id}/outcomes/refresh")
async def unified_analysis_outcomes_refresh(symbol: str, analysis_id: str):
    from datetime import timedelta
    from zoneinfo import ZoneInfo
    from . import tsetmc
    from .analysis_outcomes import record_forward_outcomes
    from .unified_analysis import _directory
    summary = _read_unified_artifact(symbol, analysis_id, "analysis.json")
    try:
        history = await tsetmc.daily_history(summary["tsetmc_id"])
        outcomes = record_forward_outcomes(summary, history,
                    _directory(symbol, analysis_id) / "outcomes",
                    as_of=datetime.now(ZoneInfo("Asia/Tehran")).date() - timedelta(days=1))
        return {"analysis_id": analysis_id, "outcomes": outcomes,
                "used_for_original_decision": False}
    except (ValueError, RuntimeError) as exc:
        raise HTTPException(409, detail=str(exc)) from exc


@app.get("/api/analysis-learning/{symbol}/candidate")
def unified_learning_candidate(symbol: str):
    from .analysis_outcomes import learning_candidate
    from .archive import safe_symbol
    from .unified_analysis import _root
    rows = []
    for path in sorted((_root() / safe_symbol(symbol)).glob("*/outcomes/*.json")):
        rows.append(json.loads(path.read_text(encoding="utf-8")))
    return learning_candidate(rows)


@app.get("/api/financial-history")
def financial_history(symbol: str = Query(min_length=1, max_length=80),
                      sync: bool = True, basis: str = "standalone"):
    from .financial_history import HistoricalDataRepository
    from .financial_scoring import FinancialScoringEngine
    from .codal import HistoricalDataSyncManager
    if basis not in {"standalone", "consolidated"}:
        raise HTTPException(400, "Invalid consolidation basis")
    repository = HistoricalDataRepository()
    if sync:
        HistoricalDataSyncManager(repository).sync_company(symbol)
    from .company_financials import company_dataset
    return dict(FinancialScoringEngine(repository).analyze(symbol, basis),
                company_reports=company_dataset(repository, symbol))


@app.get("/api/financial-history/audit")
def financial_history_audit(symbol: str = Query(min_length=1, max_length=80)):
    from .financial_history import HistoricalDataRepository
    repo = HistoricalDataRepository()
    return {"symbol": symbol, "sync_log": repo.audit(symbol),
            "versions": [r for basis in ("standalone", "consolidated")
                         for r in repo.reports(symbol, basis, selected=False)]}


@app.get("/financial-reports", response_class=HTMLResponse)
def codal_reports_page() -> str:
    from .codal_reports_ui import HTML
    return HTML


@app.get("/codal-reports.js")
def codal_reports_script():
    from pathlib import Path
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).with_name("codal-reports.js"), media_type="text/javascript")


@app.get("/api/company-reports")
def company_reports(symbol: str = Query(min_length=1, max_length=80), sync: bool = False) -> dict:
    from .financial_history import HistoricalDataRepository
    from .codal import HistoricalDataSyncManager
    from .company_financials import company_dataset
    from .codal_access import assistance_info
    repo = HistoricalDataRepository()
    state = (HistoricalDataSyncManager(repo).sync_company(symbol, force=True) if sync
             else repo.state(symbol, "KODAL_COMPANY"))
    return dict(company_dataset(repo, symbol), sync=state, assistance=assistance_info(repo, symbol))


class CodalAssistanceRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=80)
    session_id: str = Field(min_length=16, max_length=128)


class CodalVerificationRequest(CodalAssistanceRequest):
    code: str = Field(min_length=1, max_length=10)


def _codal_assist(request: CodalAssistanceRequest, code: str | None = None) -> dict:
    import httpx
    from .codal import _sync_lock
    from .codal_access import access_session
    from .financial_history import HistoricalDataRepository, normalize
    repo = HistoricalDataRepository()
    try:
        with _sync_lock(str(repo.path.resolve()), normalize(request.symbol)):
            with access_session(repo, request.symbol, create=False) as access:
                if access is None:
                    raise ValueError("Verification session expired; press resume to obtain a new challenge")
                if code is None:
                    return access.image(request.session_id)
                return {"verified": access.verify(request.session_id, code)}
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    except httpx.HTTPError as exc:
        raise HTTPException(502, "Codal verification service unavailable; saved reports are preserved") from exc


@app.post("/api/codal-assistance/image")
def codal_assistance_image(request: CodalAssistanceRequest) -> dict:
    return _codal_assist(request)


@app.post("/api/codal-assistance/verify")
def codal_assistance_verify(request: CodalVerificationRequest) -> dict:
    result = _codal_assist(request, request.code)
    if not result["verified"]:
        return result
    # Continue with the same HTTP client and checkpointed reports after user verification.
    return dict(result, reports=company_reports(request.symbol, sync=True))


@app.get("/financial-history.js")
def financial_history_script():
    from pathlib import Path
    from fastapi.responses import FileResponse
    return FileResponse(Path(__file__).with_name("financial-history.js"), media_type="text/javascript")


class OutcomeRequest(BaseModel):
    symbol: str
    decision_id: str
    realized_return: float | None = None
    reason: str = ""
    notes: str = ""


class SettleRequest(BaseModel):
    symbol: str
    decision_id: str
    horizon: int = 5
    notes: str = ""


class ChatRequest(BaseModel):
    symbol: str
    question: str = ""
    include_exam: bool = True
    structured: bool = False
    analysis_id: str | None = None


class PositionSizeRequest(BaseModel):
    account_equity: float
    risk_percent: float = 1.0
    entry: float
    stop: float
    target: float | None = None
    max_allocation_percent: float = 25.0
    fee_percent: float = 0.0
    slippage_percent: float = 0.0
    lot_size: int = Field(default=1, ge=1, strict=True)


class PortfolioRequest(BaseModel):
    positions: list[dict]


class TradePlanRequest(BaseModel):
    symbol: str
    tf: str = "1d"
    records: list[dict]


@app.post("/api/trade-plan")
def calculate_trade_plan(request: TradePlanRequest) -> dict:
    from smart_v2.analysis.service import AnalysisService
    from smart_v2.analysis.trade_policy import TradePolicy
    from .analysis_settings import load_analysis_configuration
    policy = TradePolicy(**load_analysis_configuration()["trade_policy"])
    return AnalysisService().trade_plan(request.records, request.symbol, request.tf, policy=policy)


class PositionReviewRequest(BaseModel):
    entry_price: FiniteFloat = Field(gt=0)
    stop: FiniteFloat = Field(gt=0)
    tp1: FiniteFloat = Field(gt=0)
    tp2: FiniteFloat = Field(gt=0)
    bar: dict
    as_of: date
    holding_sessions: int = Field(ge=1, strict=True)
    tp1_taken: StrictBool = False


class OpenPositionRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    symbol: str = Field(min_length=1, max_length=80)
    mode: str
    entry_date: date
    entry_price: FiniteFloat = Field(gt=0)
    quantity: int = Field(gt=0, strict=True)
    stop: FiniteFloat = Field(gt=0)
    tp1: FiniteFloat = Field(gt=0)
    tp2: FiniteFloat = Field(gt=0)
    entry_fee: FiniteFloat = Field(default=0, ge=0)


class ExitFillRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    fill_date: date
    price: FiniteFloat = Field(gt=0)
    quantity: int = Field(gt=0, strict=True)
    fee: FiniteFloat = Field(default=0, ge=0)
    reason: str = "MANUAL"


class RaiseStopRequest(BaseModel):
    request_id: str = Field(min_length=8, max_length=128)
    stop: FiniteFloat = Field(gt=0)
    effective_on: date


def _position_action(action: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    try:
        return action()
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc


@app.get("/api/positions")
def list_positions() -> dict:
    from .position_store import PositionStore
    return {"positions": PositionStore().list()}


@app.post("/api/positions", status_code=201)
def open_reported_position(request: OpenPositionRequest) -> dict:
    from .position_store import PositionStore
    from .analysis_settings import load_analysis_configuration
    from smart_v2.analysis.trade_policy import TradePolicy
    return _position_action(lambda: PositionStore().open(**request.model_dump(),
        policy=TradePolicy(**load_analysis_configuration()["trade_policy"])))


@app.get("/api/positions/{position_id}")
def get_position(position_id: str) -> dict:
    from .position_store import PositionStore
    return _position_action(lambda: PositionStore().get(position_id))


@app.post("/api/positions/{position_id}/fills")
def report_exit_fill(position_id: str, request: ExitFillRequest) -> dict:
    from .position_store import PositionStore
    return _position_action(lambda: PositionStore().exit_fill(position_id, **request.model_dump()))


@app.post("/api/positions/{position_id}/stop")
def report_stop_change(position_id: str, request: RaiseStopRequest) -> dict:
    from .position_store import PositionStore
    return _position_action(lambda: PositionStore().raise_stop(position_id, **request.model_dump()))


@app.post("/api/positions/{position_id}/review")
async def refresh_position_review(position_id: str) -> dict:
    """Independent exit review; no Codal or backtest dependency."""
    import asyncio
    from zoneinfo import ZoneInfo
    from . import tsetmc
    from .archive import parse_market_date
    from .position_store import PositionStore
    store = PositionStore()
    position = _position_action(lambda: store.get(position_id))
    today = datetime.now(ZoneInfo("Asia/Tehran")).date()
    try:
        found = await asyncio.wait_for(tsetmc.search_symbol(position["symbol"]), timeout=20)
        rows = await asyncio.wait_for(tsetmc.daily_history(str(found["insCode"])), timeout=60)
        completed = [r for r in rows if (d := parse_market_date(r.get("source_date") or r.get("date") or r.get("dEven"))) and d < today]
        latest = max((parse_market_date(r.get("source_date") or r.get("date") or r.get("dEven")) for r in completed), default=None)
        if latest is None or (today - latest).days > 3:
            return {"status": "insufficient_data", "action": "REVIEW_DATA",
                    "reason": "No recent completed session; position unchanged"}
        return _position_action(lambda: store.review(position_id, completed, as_of=latest))
    except (TimeoutError, tsetmc.TSETMCError, RuntimeError, KeyError, ValueError) as exc:
        return {"status": "source_error", "action": "REVIEW_DATA", "reason": str(exc),
                "position_unchanged": True}


@app.post("/api/risk/review-position")
def review_open_position(request: PositionReviewRequest) -> dict:
    """Review caller-supplied holdings; no order, fill or position is persisted."""
    from .position_review import review_position
    from .analysis_settings import load_analysis_configuration
    from smart_v2.analysis.trade_policy import TradePolicy
    try:
        return review_position(**request.model_dump(),
            policy=TradePolicy(**load_analysis_configuration()["trade_policy"]))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


class DailyRunRequest(BaseModel):
    symbols: list[str]
    max_age_days: int = 3
    symbol_timeout_seconds: float = 120.0


def _run_daily_cycle(run_id: str, timeout: float) -> None:
    """Background worker entrypoint; all progress is persisted locally."""
    import asyncio

    asyncio.run(execute_daily_run(DailyRunStore(default_store_path()), run_id,
                                  live_initial_analysis, symbol_timeout=timeout))


@app.get("/health")
def health():
    return {"service": "SMART", **healthcheck()}


@app.get("/api/status")
def status():
    """Return local readiness information without calling market providers."""
    learning_root = os.getenv("SMART_LEARNING_ROOT", "runtime/learning")
    runtime_root = os.getenv("SMART_RUNTIME_ROOT", "runtime")
    return {
        "service": "SMART",
        "version": app.version,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "openai_configured": bool(os.getenv("OPENAI_API_KEY")),
        "market_source": "TSETMC",
        "paths": {
            "runtime": {"path": runtime_root, "exists": os.path.isdir(runtime_root)},
            "learning": {"path": learning_root, "exists": os.path.isdir(learning_root)},
        },
        "limits": {"max_scan_symbols": 20, "max_profile_symbols": 8},
        "disclaimer": "Readiness only; this endpoint does not verify live source availability.",
    }


@app.post("/api/risk/position-size")
def calculate_position_size(request: PositionSizeRequest):
    """Calculate a long-only position size from the supplied risk constraints."""
    try:
        return {"status": "ok", "result": position_size(**request.model_dump())}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/portfolio/summary")
def summarize_portfolio(request: PortfolioRequest):
    """Summarize positions supplied by the caller; no portfolio is persisted."""
    try:
        return {"status": "ok", "portfolio": portfolio_summary(request.positions)}
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.post("/api/daily-runs", status_code=202)
def create_daily_run(request: DailyRunRequest, background_tasks: BackgroundTasks):
    """Start one checkpointed watchlist scan; only one may run at a time."""
    try:
        symbols = normalize_symbols(request.symbols)
        if not 0 <= request.max_age_days <= 30:
            raise ValueError("max_age_days must be from 0 to 30")
        if not 1 <= request.symbol_timeout_seconds <= 600:
            raise ValueError("symbol_timeout_seconds must be from 1 to 600")
        report = DailyRunStore().create(symbols, max_age_days=request.max_age_days)
    except ActiveRunError as exc:
        raise HTTPException(status_code=409, detail={"message": str(exc), "run_id": exc.run_id}) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    background_tasks.add_task(_run_daily_cycle, report["run_id"], request.symbol_timeout_seconds)
    return {"status": "accepted", "run": DailyRunStore.summary(report)}


@app.get("/api/daily-runs")
def list_daily_runs(limit: int = Query(20, ge=1, le=100)):
    return {"status": "ok", "runs": DailyRunStore().list(limit=limit)}


@app.get("/api/daily-runs/latest")
def latest_daily_run():
    runs = DailyRunStore().list(limit=1)
    if not runs:
        raise HTTPException(status_code=404, detail="no daily reports found")
    try:
        return {"status": "ok", "run": DailyRunStore().get(runs[0]["run_id"])}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/daily-runs/{run_id}")
def get_daily_run(run_id: str):
    try:
        return {"status": "ok", "run": DailyRunStore().get(run_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get("/api/scan")
async def scan(symbols: str = Query(",".join(FOCUS_SYMBOLS))):
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    return await live_initial_analysis(requested[:20])


@app.get("/api/analysis")
async def structured_analysis(symbol: str = Query(..., min_length=1)):
    """Return the deterministic, parseable point-in-time analysis contract.

    This route deliberately has no OpenAI dependency: the local engine owns
    facts, indicators, quality and risk; the optional model is only an
    explanation layer exposed by ``/api/chat`` with ``structured=true``.
    """

    cleaned = symbol.strip()
    try:
        scan_result = await live_initial_analysis([cleaned])
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    results = scan_result.get("results") or []
    if not results:
        errors = scan_result.get("errors") or [{"symbol": cleaned, "error": "no analysis result"}]
        raise HTTPException(status_code=502, detail=errors[0].get("error", "no analysis result"))
    row = results[0]
    return {
        "status": "ok",
        "source": scan_result.get("source", "TSETMC"),
        "symbol": cleaned,
        "analysis": row.get("structured_analysis") or build_structured_analysis(row),
        "warnings": scan_result.get("errors", []),
    }


@app.get("/api/exam")
async def exam(
    symbol: str = Query(..., min_length=1),
    initial_history: int = Query(20, ge=10, le=250),
    evaluation_window: int = Query(30, ge=5, le=250),
):
    try:
        return await historical_exam(
            symbol.strip(),
            initial_history=initial_history,
            evaluation_window=evaluation_window,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/symbol-profile")
async def adaptive_entry_profile(
    symbol: str = Query(..., min_length=1),
    years: int = Query(10, ge=1, le=15),
    initial_history: int = Query(20, ge=10, le=500),
    evaluation_window: int = Query(30, ge=5, le=250),
    transaction_cost_pct: float = Query(0.35, ge=0, le=5),
):
    """Train one independent long-only adaptive profile and persist its audit."""

    try:
        return await symbol_entry_profile(
            symbol.strip(),
            years=years,
            initial_history=initial_history,
            evaluation_window=evaluation_window,
            transaction_cost_pct=transaction_cost_pct,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/api/symbol-profiles")
async def adaptive_entry_profiles(
    symbols: str = Query(",".join(FOCUS_SYMBOLS)),
    years: int = Query(10, ge=1, le=15),
    initial_history: int = Query(20, ge=10, le=500),
    evaluation_window: int = Query(30, ge=5, le=250),
    transaction_cost_pct: float = Query(0.35, ge=0, le=5),
):
    """Train separately for each requested symbol; source errors stay visible."""

    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    return await focus_symbol_profiles(
        requested,
        years=years,
        initial_history=initial_history,
        evaluation_window=evaluation_window,
        transaction_cost_pct=transaction_cost_pct,
    )


@app.get("/api/strategies")
def strategies():
    """Return the auditable 200-variant research catalog."""
    return {
        "count": len(strategy_catalog()),
        "families": sorted({item.family for item in strategy_catalog()}),
        "strategies": [
            {
                "id": item.strategy_id,
                "name": item.name,
                "family": item.family,
                "variant": item.variant,
                "parameters": item.parameters,
                "description": item.description,
            }
            for item in strategy_catalog()
        ],
    }


@app.get("/api/learning/{symbol}")
def learning(symbol: str, limit: int = Query(20, ge=1, le=100)):
    """Inspect persisted wins, losses and failure diagnostics for a symbol."""
    result = DecisionMemory().summary(symbol.strip(), limit=limit)
    result["adaptive_entry_profile"] = summarize_profile(
        load_latest_symbol_profile(symbol.strip())
    )
    return result


@app.post("/api/outcome")
def outcome(request: OutcomeRequest):
    try:
        return DecisionMemory().record_outcome(
            request.symbol,
            request.decision_id,
            realized_return=request.realized_return,
            reason=request.reason,
            notes=request.notes,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post("/api/settle")
async def settle(request: SettleRequest):
    """Settle a stored decision using newly available TSETMC bars."""
    from .tsetmc import daily_history, search_symbol

    try:
        found = await search_symbol(request.symbol.strip())
        try:
            rows = await daily_history(
                str(found.get("insCode")),
                top=int(os.getenv("TSETMC_HISTORY_TOP", "0")),
            )
        except TypeError:
            rows = await daily_history(str(found.get("insCode")))
        return DecisionMemory().settle_from_rows(
            request.symbol.strip(),
            request.decision_id,
            rows,
            horizon=max(1, min(request.horizon, 100)),
            notes=request.notes,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/api/chat")
async def chat(request: ChatRequest):
    """Explain exactly one verified unified analysis, with a local fallback."""
    from . import unified_analysis as ua
    from .analysis_explanation import render_explanation
    from copy import deepcopy
    from .analysis_workers import run_blocking
    symbol = request.symbol.strip()
    if not symbol:
        raise HTTPException(422, detail="symbol is required")
    if request.analysis_id:
        reference = _read_unified_artifact(symbol, request.analysis_id, "analysis.json")
    else:
        try:
            job = ua.create_job(symbol)
        except ValueError as exc:
            raise HTTPException(422, detail=str(exc)) from exc
        if job.get("reused_active"):
            raise HTTPException(409, detail={"message": "analysis is running", "analysis_id": job["analysis_id"]})
        await ua.run_job(job)
        if job.get("status") not in {"COMPLETED", "PARTIAL"}:
            raise HTTPException(503, detail={"message": "analysis unavailable", "analysis_id": job["analysis_id"], "status": job.get("status")})
        reference = _read_unified_artifact(symbol, job["analysis_id"], "analysis.json")
    # Explanation is rendered afresh; a saved narrative cannot override facts.
    facts = {key: value for key, value in reference.items() if key != "explanation"}
    explanation = render_explanation(facts)
    ai_result, ai_error = None, None
    if request.structured:
        try:
            ai_result = await run_blocking(ask_structured_analysis, deepcopy(facts), question=request.question)
            if ai_result.get("reference") != facts:
                raise RuntimeError("Model explanation changed the reference analysis")
            # Render from the original facts again. Never trust returned text.
            explanation = render_explanation(facts, ai_result.get("fact_ids"))
            ai_result = {"reference": facts, **explanation}
        except Exception:
            ai_result = None
            ai_error = "توضیح مدل در دسترس یا معتبر نیست؛ متن محاسباتی گزارش نمایش داده شد."
    return {"status": "ok", "symbol": reference.get("symbol", symbol),
            "analysis_id": reference.get("analysis_id"), "answer": explanation["answer"],
            "explanation": explanation, "structured_analysis": reference,
            "structured_analysis_ai": ai_result, "structured_analysis_ai_error": ai_error,
            "raw_data_url": (reference.get("local_urls") or {}).get("analysts"),
            "include_exam": "Unified analysis includes dated research evidence; no separate computation is used."}


@app.get("/legacy", response_class=HTMLResponse)
def home():
    from pathlib import Path
    return (Path(__file__).parent / "templates" / "legacy.html").read_text(encoding="utf-8")
