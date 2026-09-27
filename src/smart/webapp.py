"""Browser-facing SMART dashboard with charts, walk-forward exam and AI explainer."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .ai import ask_model, ask_structured_analysis, healthcheck
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

app = FastAPI(title="SMART Market Intelligence", version="0.5.0")


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
        HistoricalDataSyncManager(repository).sync_financial(symbol)
    return FinancialScoringEngine(repository).analyze(symbol, basis)


@app.get("/api/financial-history/audit")
def financial_history_audit(symbol: str = Query(min_length=1, max_length=80)):
    from .financial_history import HistoricalDataRepository
    repo = HistoricalDataRepository()
    return {"symbol": symbol, "sync_log": repo.audit(symbol),
            "versions": [r for basis in ("standalone", "consolidated")
                         for r in repo.reports(symbol, basis, selected=False)]}


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


class PositionSizeRequest(BaseModel):
    account_equity: float
    risk_percent: float = 1.0
    entry: float
    stop: float
    target: float | None = None
    max_allocation_percent: float = 25.0
    fee_percent: float = 0.0
    slippage_percent: float = 0.0


class PortfolioRequest(BaseModel):
    positions: list[dict]


class TradePlanRequest(BaseModel):
    symbol: str
    tf: str = "1d"
    records: list[dict]


@app.post("/api/trade-plan")
def calculate_trade_plan(request: TradePlanRequest) -> dict:
    from smart_v2.analysis.service import AnalysisService
    return AnalysisService().trade_plan(request.records, request.symbol, request.tf)


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
    """Explain structured SMART output with the configured OpenAI model."""
    try:
        symbol = request.symbol.strip()
        scan_result = await live_initial_analysis([symbol])
        compact_scan = dict(scan_result)
        compact_results = []
        for item in scan_result.get("results", []):
            row = dict(item)
            analysis = dict(row.get("analysis") or {})
            technical = dict(analysis.get("technical_history") or {})
            technical["history"] = (technical.get("history") or [])[-10:]
            analysis["technical_history"] = technical
            row["analysis"] = analysis
            compact_results.append(row)
        compact_scan["results"] = compact_results
        payload: dict = {"scan": compact_scan}
        saved_profile = load_latest_symbol_profile(symbol)
        if saved_profile:
            payload["symbol_specific_entry_model"] = summarize_profile(saved_profile)
        if request.include_exam:
            exam_result = await historical_exam(symbol)
            payload["walk_forward_exam"] = {
                key: exam_result.get(key)
                for key in (
                    "status", "symbol", "protocol", "bars", "range",
                    "strategy_count", "metrics", "segments", "leaderboard",
                    "learning",
                )
            }
            leaderboard_ids = [
                item.get("strategy_id")
                for item in exam_result.get("leaderboard", [])
                if item.get("strategy_id")
            ]
            payload["strategy_logic"] = {
                "families": sorted({item["family"] for item in strategy_definitions()}),
                "top_definitions": strategy_definitions(leaderboard_ids[:20]),
            }
        # Always expose the deterministic contract.  Only an explicit
        # structured request calls the optional OpenAI endpoint.
        first_result = (compact_scan.get("results") or [{}])[0]
        payload["structured_analysis"] = build_structured_analysis(first_result)
        if request.structured:
            try:
                payload["structured_analysis_ai"] = ask_structured_analysis(
                    payload["structured_analysis"],
                    question=request.question,
                )
            except RuntimeError as exc:
                payload["structured_analysis_ai_error"] = str(exc)
        prompt = (
            "You are SMART's explanation layer. Explain the supplied result in "
            "Persian, separating facts, indicators, strategy consensus, historical "
            "walk-forward performance and risks. Use no data outside the payload; "
            "do not promise profit or issue an execution order.\n"
            f"Question: {request.question or 'نتیجه را برای من توضیح بده.'}\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        return {
            "status": "ok",
            "symbol": symbol,
            "answer": ask_model(prompt),
            "structured_analysis": payload["structured_analysis"],
            "structured_analysis_ai": payload.get("structured_analysis_ai"),
            "structured_analysis_ai_error": payload.get("structured_analysis_ai_error"),
        }
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.get("/", response_class=HTMLResponse)
def home():
    return """<!doctype html>
<html lang="fa" dir="rtl">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>SMART | تحلیل و یادگیری</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
  <style>
    :root{--ink:#16233b;--muted:#64748b;--line:#dce3ef;--bg:#f4f7fb;
      --blue:#2563eb;--green:#15803d;--amber:#d97706;--red:#dc2626}
    *{box-sizing:border-box}
    body{font-family:Tahoma,Arial,sans-serif;max-width:1420px;margin:0 auto;
      padding:22px;background:var(--bg);color:var(--ink)}
    .card{background:#fff;border:1px solid var(--line);border-radius:16px;
      padding:18px;margin:12px 0;box-shadow:0 5px 20px #1e3a5f0b}
    .toolbar{display:flex;gap:9px;align-items:center;flex-wrap:wrap}
    .toolbar input{flex:1;min-width:260px}
    input,button{padding:11px;border:1px solid #bdc9dc;border-radius:9px;
      font-size:14px;font-family:inherit}
    button{cursor:pointer;background:var(--blue);color:#fff;border:0}
    button.secondary{background:#475569}
    .grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(500px,1fr));gap:16px}
    .score{font-size:32px;font-weight:800;color:var(--green)}
    .muted{color:var(--muted);font-size:13px}
    .metric{display:inline-block;background:#eff4fb;padding:8px 10px;margin:3px;
      border-radius:8px;font-size:13px}
    .chart-wrap{height:250px;margin-top:12px}.chart-wrap.small{height:190px}
    .pill{padding:4px 9px;border-radius:999px;background:#e8eefc;font-size:12px}
    .error{color:var(--red)}.success{color:var(--green)}
    table{width:100%;border-collapse:collapse;font-size:12px}
    td,th{border-bottom:1px solid var(--line);padding:7px;text-align:right}
    .exam-chart{height:250px}.hidden{display:none}
  </style>
</head>
<body>
  <div class="card">
    <h1>SMART — تحلیل و یادگیری بازار</h1>
    <p class="muted">محاسبه‌ی اندیکاتورها روی تاریخچه‌ی نماد، تصمیم نقطه‌ای،
      آزمون ۲۰ روز آموزش و ۳۰ روز ارزیابی، و ثبت نتیجه‌ی واقعی.</p>
    <div class="toolbar">
      <input id="symbols" value="فولاد,پالایش,فملی,فجر" aria-label="نمادها">
      <button onclick="runScan()">تحلیل نمادها</button>
      <button class="secondary" onclick="loadFinancial(document.getElementById('symbols').value.split(',')[0].trim(),'financialPanel')">تحلیل مالی ۵ ساله</button>
      <button class="secondary" onclick="runDailyRun()">گزارش روزانه</button>
      <button class="secondary" onclick="loadDailyRuns()">سوابق گزارش‌ها</button>
      <button class="secondary" onclick="runExam()">آزمون walk-forward</button>
      <button class="secondary" onclick="runProfiles()">آموزش اختصاصی نمادها</button>
      <button class="secondary" onclick="loadLearning()">حافظه یادگیری</button>
    </div>
    <div class="toolbar" style="margin-top:10px">
      <input id="chatQuestion" placeholder="سؤال درباره‌ی نتیجه‌ی تحلیل">
      <button onclick="askChat()">توضیح با ChatGPT</button>
    </div>
  </div>
  <div id="message" class="card muted">برای شروع، نمادها را وارد و تحلیل را اجرا کن.</div>
  <div class="card">
    <h2>Risk calculator</h2>
    <p class="muted">Calculate a long-only position size from equity, entry and stop. This is advisory and does not place an order.</p>
    <div class="toolbar">
      <input id="riskEquity" type="number" min="0" step="any" placeholder="Account equity">
      <input id="riskPct" type="number" min="0" step="any" value="1" placeholder="Risk %">
      <input id="riskEntry" type="number" min="0" step="any" placeholder="Entry">
      <input id="riskStop" type="number" min="0" step="any" placeholder="Stop">
      <input id="riskTarget" type="number" min="0" step="any" placeholder="Target (optional)">
      <button onclick="calculateRisk()">Calculate</button>
    </div>
    <div id="riskResult" class="muted" style="margin-top:10px"></div>
  </div>
  <div id="cards" class="grid"></div>
  <div id="financialPanel"></div>
  <div id="chatCard" class="card hidden"><h2>توضیح هوش مصنوعی</h2><div id="chatAnswer"></div></div>
  <script>
    let charts=[];
    const esc=v=>String(v??'-').replace(/[&<>"']/g,m=>({'&':'&amp;','<':'&lt;',
      '>':'&gt;','"':'&quot;',"'":'&#039;'}[m]));
    function destroyCharts(){charts.forEach(c=>c.destroy());charts=[]}
    function lineChart(id,labels,datasets){
      const el=document.getElementById(id); if(!el||!window.Chart)return;
      charts.push(new Chart(el,{type:'line',data:{labels,datasets},
        options:{responsive:true,maintainAspectRatio:false,interaction:{mode:'index',intersect:false},
          scales:{x:{ticks:{maxTicksLimit:9}},y:{beginAtZero:false}},
          plugins:{legend:{display:true}}}}));
    }
    async function runDailyRun(){
      const msg=document.getElementById('message');
      const symbols=document.getElementById('symbols').value.split(',').map(x=>x.trim()).filter(Boolean);
      msg.textContent='در حال اجرای گزارش روزانه؛ پیشرفت هر نماد ذخیره می‌شود...';
      try{
        const r=await fetch('/api/daily-runs',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({symbols,max_age_days:3})});
        const d=await r.json(); if(!r.ok)throw new Error(d.detail?.message||d.detail||'daily run failed');
        await pollDailyRun(d.run.run_id);
      }catch(e){msg.innerHTML='<span class="error">گزارش روزانه اجرا نشد: '+esc(e)+'</span>'}
    }
    async function pollDailyRun(runId){
      const msg=document.getElementById('message');
      for(let attempt=0;attempt<180;attempt++){
        const r=await fetch('/api/daily-runs/'+encodeURIComponent(runId)); const d=await r.json();
        if(!r.ok)throw new Error(d.detail||'report unavailable');
        const x=d.run; msg.textContent='وضعیت: '+x.status+' | '+x.processed_count+'/'+x.counts.requested+' نماد';
        if(!['queued','running'].includes(x.status)){
          msg.innerHTML='<h3>گزارش روزانه '+esc(x.status)+'</h3><p>موفق: '+esc(x.counts.eligible)+' | حذف‌شده: '+esc(x.counts.excluded)+' | خطا: '+esc(x.errors.length)+'</p><p>Top 10: '+esc((x.top_10||[]).map(y=>y.symbol).join('، ')||'موردی ندارد')+'</p>';
          return;
        }
        await new Promise(resolve=>setTimeout(resolve,1000));
      }
      throw new Error('daily report polling timeout');
    }
    async function loadDailyRuns(){
      const msg=document.getElementById('message');
      try{const r=await fetch('/api/daily-runs?limit=10');const d=await r.json();
        msg.innerHTML='<h3>سوابق گزارش‌های روزانه</h3><table><thead><tr><th>شناسه</th><th>وضعیت</th><th>تاریخ</th><th>نمادهای موفق</th><th>خطا</th></tr></thead><tbody>'+d.runs.map(x=>'<tr><td>'+esc(x.run_id.slice(0,10))+'</td><td>'+esc(x.status)+'</td><td>'+esc(x.report_date)+'</td><td>'+esc(x.counts?.eligible)+'</td><td>'+esc(x.errors?.length||0)+'</td></tr>').join('')+'</tbody></table>';
      }catch(e){msg.innerHTML='<span class="error">خواندن سوابق ناموفق: '+esc(e)+'</span>'}
    }
    function renderCards(data){
      destroyCharts();
      const box=document.getElementById('cards');
      const results=data.results||[];
      if(!results.length){box.innerHTML='<div class="card">داده‌ای برای نمایش موجود نیست.</div>';return}
      box.innerHTML=results.map((x,i)=>{
        const a=x.analysis||{},h=a.technical_history||{},rows=h.history||[],l=h.latest||{};
        const f=a.factor_engine||{},q=a.decision_support||{},p=q.trade_plan||{},
          sd=a.strategy_decision||{}, sa=x.structured_analysis||{};
        const fa=sa.final_assessment||{}, tr=sa.trend||{}, risk=sa.risk||{};
        return `<div class="card">
          <h2>${esc(x.symbol)} <span class="pill">${esc(f.decision||'N/A')}</span></h2>
          <button class="secondary" onclick="loadFinancial(decodeURIComponent('${encodeURIComponent(x.symbol)}'),'finance-${i}')">📊 تحلیل مالی</button>
          <div id="finance-${i}"></div>
          <div class="score">${esc(x.overall_score)}</div>
          <p>قیمت: ${esc(x.price)} | تغییر: ${esc(x.change_pct)}%
            | Smart Money: ${esc(x.smart_money?.phase)}</p>
          <p><b>قرارداد تصمیم‌یار:</b> ${esc(fa.label||'watchlist')} |
            امتیاز ${esc(fa.score_0_100)} | اطمینان ${esc(fa.confidence_0_100)} |
            ریسک ${esc(risk.level)} | فاز ${esc(sa.market_phase)}<br>
            روند کوتاه/میان/بلند: ${esc(tr.short_term)} / ${esc(tr.mid_term)} / ${esc(tr.long_term)}</p>
          <div class="metric">RSI14: ${esc(l.rsi14)}</div>
          <div class="metric">MACD: ${esc(l.macd)}</div>
          <div class="metric">Signal: ${esc(l.macd_signal)}</div>
          <div class="metric">MA5: ${esc(l.sma5)}</div>
          <div class="metric">MA20: ${esc(l.sma20)}</div>
          <div class="metric">MA50: ${esc(l.sma50)}</div>
          <div class="metric">EMA12: ${esc(l.ema12)}</div>
          <div class="metric">EMA26: ${esc(l.ema26)}</div>
          <p><b>تصمیم چندعاملی:</b> ${esc(f.decision)} | امتیاز ${esc(f.composite)}
            | ریسک ${esc(f.risk_level)}</p>
          <p><b>رأی ۲۰۰ استراتژی:</b> ${esc(sd.decision)} |
            اطمینان ${esc(sd.confidence)} |
            استراتژی‌های فعال ${esc((sd.selected_strategies||[]).length)}</p>
          <p>ATR: ${esc(q.atr)} | ورود: ${esc(p.entry)}
            | حد ضرر: ${esc(p.stop)} | هدف: ${esc(p.target)}</p>
          <p>وضعیت ورود/خروج: ${esc(q.entry_exit?.status)} | ${esc(q.reason)}<br>
            هدف دوم: ${esc(p.tp2)} | ابطال: ${esc(p.invalidation_condition)}</p>
          <div class="chart-wrap"><canvas id="price-${i}"></canvas></div>
          <div class="chart-wrap small"><canvas id="vol-${i}"></canvas></div>
          <div class="chart-wrap small"><canvas id="osc-${i}"></canvas></div>
          <p class="muted">کل تاریخچه: ${rows.length} روز |
            آخرین تصمیم: ${esc(l.date)}</p>
          <button class="secondary" onclick="runExam('${encodeURIComponent(x.symbol)}')">
            آزمون این نماد</button>
          <div class="toolbar" style="margin-top:9px">
            <input id="ret-${i}" type="number" step="0.001" placeholder="بازده واقعی، مثلاً -0.03">
            <button onclick="recordOutcome(${i},'${esc(x.symbol)}','${esc(x.decision_record?.decision_id||'')}')">
              ثبت نتیجه</button>
          </div>
        </div>`;
      }).join('');
      results.forEach((x,i)=>{
        const rows=x.analysis?.technical_history?.history||[];
        const labels=rows.map(r=>r.date);
        lineChart('price-'+i,labels,[
          {label:'قیمت',data:rows.map(r=>r.close),borderColor:'#2563eb',
            backgroundColor:'#2563eb22',pointRadius:0,tension:.2},
          {label:'MA20',data:rows.map(r=>r.sma20),borderColor:'#16a34a',pointRadius:0,tension:.2},
          {label:'MA50',data:rows.map(r=>r.sma50),borderColor:'#f97316',pointRadius:0,tension:.2},
          {label:'EMA12',data:rows.map(r=>r.ema12),borderColor:'#7c3aed',pointRadius:0,tension:.2},
          {label:'EMA26',data:rows.map(r=>r.ema26),borderColor:'#db2777',pointRadius:0,tension:.2}
        ]);
        lineChart('vol-'+i,labels,[
          {label:'حجم',data:rows.map(r=>r.volume),borderColor:'#64748b',
            backgroundColor:'#64748b55',pointRadius:0,fill:true}
        ]);
        lineChart('osc-'+i,labels,[
          {label:'RSI14',data:rows.map(r=>r.rsi14),borderColor:'#d97706',pointRadius:0},
          {label:'MACD',data:rows.map(r=>r.macd),borderColor:'#7c3aed',pointRadius:0},
          {label:'Signal',data:rows.map(r=>r.macd_signal),borderColor:'#dc2626',pointRadius:0}
        ]);
      });
    }
    async function runScan(){
      const msg=document.getElementById('message');
      msg.textContent='در حال دریافت تاریخچه و محاسبه‌ی اندیکاتورها...';
      try{
        const r=await fetch('/api/scan?symbols='+encodeURIComponent(document.getElementById('symbols').value));
        const data=await r.json(); renderCards(data);
        msg.textContent=data.errors?.length?'تحلیل انجام شد؛ برخی منابع خطا داشتند.':'تحلیل کامل انجام شد.';
      }catch(e){msg.innerHTML='<span class="error">خطا: '+esc(e)+'</span>'}
    }
    async function calculateRisk(){
      const payload={account_equity:Number(document.getElementById('riskEquity').value),
        risk_percent:Number(document.getElementById('riskPct').value),
        entry:Number(document.getElementById('riskEntry').value),
        stop:Number(document.getElementById('riskStop').value)};
      const target=Number(document.getElementById('riskTarget').value);
      if(Number.isFinite(target)&&target>0)payload.target=target;
      const out=document.getElementById('riskResult'); out.textContent='Calculating...';
      try{
        const r=await fetch('/api/risk/position-size',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});
        const d=await r.json(); if(!r.ok)throw new Error(d.detail||'risk calculation failed');
        const x=d.result; out.innerHTML=`<b>Units:</b> ${esc(x.units)} &nbsp; <b>Notional:</b> ${esc(x.notional)} &nbsp; <b>Max loss:</b> ${esc(x.estimated_max_loss)} &nbsp; <b>Allocation:</b> ${esc(x.allocation_percent)}%`;
      }catch(e){out.innerHTML='<span class="error">'+esc(e)+'</span>'}
    }
    async function runExam(sym){
      const symbol=decodeURIComponent(sym||document.getElementById('symbols').value.split(',')[0].trim());
      const msg=document.getElementById('message');
      msg.textContent='در حال اجرای آزمون ۲۰ روز آموزش و ۳۰ روز ارزیابی برای '+symbol+'...';
      try{
        const r=await fetch('/api/exam?symbol='+encodeURIComponent(symbol));
        const d=await r.json(); if(!r.ok)throw new Error(d.detail||'exam failed');
        const segments=d.segments||[];
        msg.innerHTML=`<h3>نتیجه آزمون ${esc(symbol)}</h3>
          <p>تعداد استراتژی‌ها: ${esc(d.strategy_count)} |
          تصمیم‌ها: ${esc(d.metrics?.decisions)} |
          نرخ موفقیت: ${esc(d.metrics?.win_rate_pct)}% |
          جمع بازده علامت‌دار: ${esc(d.metrics?.cumulative_return_pct)}% |
          ترکیب‌شده‌ی هم‌پوشان: ${esc(d.metrics?.overlapping_compounded_return_pct)}%</p>
          <p class="muted">تاریخچه: ${esc(d.bars)} روز |
          آموزش اولیه: ${esc(d.protocol?.initial_history_bars)} روز |
          پنجره ارزیابی: ${esc(d.protocol?.evaluation_window_bars)} روز</p>
          <div class="exam-chart"><canvas id="examSegments"></canvas></div>
          <table><thead><tr><th>بخش</th><th>از</th><th>تا</th><th>تصمیم</th><th>موفقیت</th><th>بازده</th></tr></thead>
          <tbody>${segments.map(s=>`<tr><td>${esc(s.segment)}</td><td>${esc(s.from)}</td><td>${esc(s.to)}</td>
          <td>${esc(s.metrics?.decisions)}</td><td>${esc(s.metrics?.win_rate_pct)}%</td>
          <td>${esc(s.metrics?.overlapping_compounded_return_pct ??
                    s.metrics?.cumulative_return_pct)}%</td></tr>`).join('')}</tbody></table>`;
        const labels=segments.map(s=>'بخش '+s.segment);
        lineChart('examSegments',labels,[{label:'نرخ موفقیت %',
          data:segments.map(s=>s.metrics?.win_rate_pct),borderColor:'#15803d',
          backgroundColor:'#15803d22',fill:true,pointRadius:4}]);
      }catch(e){msg.innerHTML='<span class="error">آزمون انجام نشد: '+esc(e)+'</span>'}
    }
    async function runProfiles(){
      const raw=document.getElementById('symbols').value;
      const msg=document.getElementById('message');
      msg.textContent='در حال آموزش مستقل هر نماد با تاریخچه حداکثر ۱۰ سال، وزن‌های پویا و آزمون خارج از نمونه...';
      try{
        const r=await fetch('/api/symbol-profiles?symbols='+encodeURIComponent(raw)+'&years=10&initial_history=20&evaluation_window=30');
        const d=await r.json(); if(!r.ok)throw new Error(d.detail||'profile training failed');
        const rows=d.results||[];
        const errors=(d.errors||[]).map(x=>'<li>'+esc(x.symbol)+': '+esc(x.error)+'</li>').join('');
        if(!rows.length){msg.innerHTML='<span class="error">برای هیچ نمادی پروفایل ساخته نشد.</span><ul>'+errors+'</ul>';return}
        msg.innerHTML=`<h3>آموزش اختصاصی هر نماد</h3>
          <p class="muted">فقط ورود خرید بررسی شده است. مدل فقط با validation انتخاب می‌شود؛ test فریز است و test خوب، validation ضعیف را تأیید نمی‌کند.</p>
          <table><thead><tr><th>نماد</th><th>مدل / داده</th><th>اعتبارسنجی</th><th>آزمون فریز</th><th>نتیجه پژوهش</th><th>وضعیت امروز</th><th>دلایل باخت</th></tr></thead>
          <tbody>${rows.map(p=>{
            const selected=p.selected_model||{}, validation=selected.range_metrics?.validation||{}, metrics=selected.range_metrics?.test||{};
            const current=p.current_entry||{}, errors=Object.entries(p.failure_diagnostics?.losses_by_reason||{})
              .map(([k,v])=>k+': '+v).join('، ');
            const validationGate=selected.validation_gate||{}, testGate=selected.test_gate||{};
            const validationState=validationGate.passed?'کافی':('ناکافی: '+(validationGate.failed_checks||[]).join('، '));
            const testState=testGate.passed?'کافی':('ناکافی: '+(testGate.failed_checks||[]).join('، '));
            const promotion=p.promotion||{};
            const technical=current.technical_signal_status?' | سیگنال تکنیکی: '+current.technical_signal_status:'';
            return `<tr><td>${esc(p.symbol)}</td><td>${esc(selected.config?.label||selected.config?.config_id)}<br><span class="muted">${esc(p.coverage?.bars_used)} روز | ${esc(selected.selection_status)}</span></td>
              <td>${esc(validationState)}<br><span class="muted">${esc(validation.cumulative_return_pct)}% | PF ${esc(validation.profit_factor)}</span></td>
              <td>${esc(testState)}<br><span class="muted">${esc(metrics.cumulative_return_pct)}% | برد ${esc(metrics.win_rate_pct)}%</span></td>
              <td>${esc(promotion.decision)}<br><span class="muted">${esc(promotion.reason)}</span></td>
              <td>${esc(current.status)}<br><span class="muted">${esc(current.reason)}${esc(technical)}</span></td>
              <td>${esc(errors||'-')}</td></tr>`;
          }).join('')}</tbody></table>
          ${errors?'<p class="error">خطاهای منبع:</p><ul>'+errors+'</ul>':''}`;
      }catch(e){msg.innerHTML='<span class="error">آموزش اختصاصی ناموفق: '+esc(e)+'</span>'}
    }
    async function loadLearning(){
      const symbol=document.getElementById('symbols').value.split(',')[0].trim();
      const msg=document.getElementById('message');
      msg.textContent='در حال خواندن حافظه‌ی تصمیم‌های '+symbol+'...';
      try{
        const r=await fetch('/api/learning/'+encodeURIComponent(symbol));
        const d=await r.json(); if(!r.ok)throw new Error(d.detail||'learning failed');
        const reasons=Object.entries(d.outcomes_by_reason||{})
          .map(([k,v])=>'<li>'+esc(k)+': '+esc(v)+'</li>').join('');
        const profile=d.adaptive_entry_profile||{};
        const selected=profile.selected_model||{}, test=selected.test_metrics||{};
        const profileInfo=profile.status?`<p><b>پروفایل اختصاصی:</b> ${esc(profile.status)} |
          مدل ${esc(selected.config?.label||selected.config?.config_id)} |
          ورود فعلی ${esc(profile.current_entry?.status)} |
          بازده test ${esc(test.cumulative_return_pct)}%</p>`:'';
        msg.innerHTML=`<h3>حافظه‌ی یادگیری ${esc(symbol)}</h3>
          <p>تصمیم‌ها: ${esc(d.decision_count)} |
          نتیجه‌دار: ${esc(d.outcome_count)} |
          برد: ${esc(d.wins)} |
          باخت: ${esc(d.losses)} |
          نرخ برد: ${esc(d.win_rate_pct)}%</p>${profileInfo}
          <p><b>دلایل ثبت‌شده:</b></p><ul>${reasons||'<li>هنوز نتیجه‌ای ثبت نشده است.</li>'}</ul>`;
      }catch(e){msg.innerHTML='<span class="error">خواندن حافظه ناموفق: '+esc(e)+'</span>'}
    }
    async function askChat(){
      const symbol=document.getElementById('symbols').value.split(',')[0].trim();
      const question=document.getElementById('chatQuestion').value;
      const card=document.getElementById('chatCard'),out=document.getElementById('chatAnswer');
      card.classList.remove('hidden');out.textContent='در حال پرسش از مدل...';
      try{
        const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({symbol,question,include_exam:true,structured:true})});
        const d=await r.json();
        const structured=d.structured_analysis_ai||d.structured_analysis;
        out.textContent=(d.answer||d.detail||'پاسخی دریافت نشد.')+
          (structured?'\\n\\nتحلیل ساختاریافته:\\n'+JSON.stringify(structured,null,2):'');
      }catch(e){out.textContent='خطا: '+e}
    }
    async function recordOutcome(index,symbol,decisionId){
      const value=Number(document.getElementById('ret-'+index).value);
      if(!decisionId||!Number.isFinite(value)){alert('شناسه تصمیم یا بازده واقعی نامعتبر است.');return}
      const response=await fetch('/api/outcome',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({symbol,decision_id:decisionId,realized_return:value,notes:'ثبت‌شده از داشبورد'})});
      const data=await response.json();
      document.getElementById('message').textContent=response.ok
        ? 'نتیجه تصمیم '+decisionId+' ثبت شد: '+(data.outcome?.result||'-')
        : 'ثبت نتیجه ناموفق: '+(data.detail||'خطا');
    }
  </script>
  <script src="/financial-history.js"></script>
</body></html>"""
