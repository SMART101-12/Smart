"""Browser-facing SMART dashboard with charts, walk-forward exam and AI explainer."""
from __future__ import annotations

import json
import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from .ai import ask_model, healthcheck
from .decision_memory import DecisionMemory
from .strategy_lab import strategy_catalog
from .strategy_lab import strategy_definitions
from .tsetmc import historical_exam, live_initial_analysis

app = FastAPI(title="SMART Market Intelligence", version="0.5.0")


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


@app.get("/health")
def health():
    return {"service": "SMART", **healthcheck()}


@app.get("/api/scan")
async def scan(symbols: str = Query("فولاد,پالایش,عیار")):
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    return await live_initial_analysis(requested[:20])


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
    return DecisionMemory().summary(symbol.strip(), limit=limit)


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
        prompt = (
            "You are SMART's explanation layer. Explain the supplied result in "
            "Persian, separating facts, indicators, strategy consensus, historical "
            "walk-forward performance and risks. Use no data outside the payload; "
            "do not promise profit or issue an execution order.\n"
            f"Question: {request.question or 'نتیجه را برای من توضیح بده.'}\n"
            + json.dumps(payload, ensure_ascii=False)
        )
        return {"status": "ok", "symbol": symbol, "answer": ask_model(prompt)}
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
      <input id="symbols" value="فولاد,پالایش,عیار" aria-label="نمادها">
      <button onclick="runScan()">تحلیل نمادها</button>
      <button class="secondary" onclick="runExam()">آزمون walk-forward</button>
      <button class="secondary" onclick="loadLearning()">حافظه یادگیری</button>
    </div>
    <div class="toolbar" style="margin-top:10px">
      <input id="chatQuestion" placeholder="سؤال درباره‌ی نتیجه‌ی تحلیل">
      <button onclick="askChat()">توضیح با ChatGPT</button>
    </div>
  </div>
  <div id="message" class="card muted">برای شروع، نمادها را وارد و تحلیل را اجرا کن.</div>
  <div id="cards" class="grid"></div>
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
    function renderCards(data){
      destroyCharts();
      const box=document.getElementById('cards');
      const results=data.results||[];
      if(!results.length){box.innerHTML='<div class="card">داده‌ای برای نمایش موجود نیست.</div>';return}
      box.innerHTML=results.map((x,i)=>{
        const a=x.analysis||{},h=a.technical_history||{},rows=h.history||[],l=h.latest||{};
        const f=a.factor_engine||{},q=a.decision_support||{},p=q.trade_plan||{},
          sd=a.strategy_decision||{};
        return `<div class="card">
          <h2>${esc(x.symbol)} <span class="pill">${esc(f.decision||'N/A')}</span></h2>
          <div class="score">${esc(x.overall_score)}</div>
          <p>قیمت: ${esc(x.price)} | تغییر: ${esc(x.change_pct)}%
            | Smart Money: ${esc(x.smart_money?.phase)}</p>
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
    async function loadLearning(){
      const symbol=document.getElementById('symbols').value.split(',')[0].trim();
      const msg=document.getElementById('message');
      msg.textContent='در حال خواندن حافظه‌ی تصمیم‌های '+symbol+'...';
      try{
        const r=await fetch('/api/learning/'+encodeURIComponent(symbol));
        const d=await r.json(); if(!r.ok)throw new Error(d.detail||'learning failed');
        const reasons=Object.entries(d.outcomes_by_reason||{})
          .map(([k,v])=>'<li>'+esc(k)+': '+esc(v)+'</li>').join('');
        msg.innerHTML=`<h3>حافظه‌ی یادگیری ${esc(symbol)}</h3>
          <p>تصمیم‌ها: ${esc(d.decision_count)} |
          نتیجه‌دار: ${esc(d.outcome_count)} |
          برد: ${esc(d.wins)} |
          باخت: ${esc(d.losses)} |
          نرخ برد: ${esc(d.win_rate_pct)}%</p>
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
          body:JSON.stringify({symbol,question,include_exam:true})});
        const d=await r.json();out.textContent=d.answer||d.detail||'پاسخی دریافت نشد.';
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
</body></html>"""
