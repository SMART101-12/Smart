"""Browser-facing SMART dashboard for the first live test."""

from __future__ import annotations

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

from .ai import healthcheck
from .tsetmc import live_initial_analysis

app = FastAPI(title="SMART Market Intelligence", version="0.2.0")


@app.get("/health")
def health():
    return {"service": "SMART", **healthcheck()}


@app.get("/api/scan")
async def scan(symbols: str = Query("شلرد,پالایش,عیار")):
    requested = [item.strip() for item in symbols.split(",") if item.strip()]
    return await live_initial_analysis(requested[:20])


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!doctype html><html lang='fa' dir='rtl'><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>SMART</title>
    <style>
      body{font-family:Arial,sans-serif;max-width:1100px;margin:30px auto;padding:0 20px;background:#fafafa}
      .card{background:white;border:1px solid #ddd;border-radius:12px;padding:20px;margin-bottom:18px}
      input,button{padding:11px;border-radius:8px;border:1px solid #bbb;font-size:15px}
      button{cursor:pointer}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:14px}
      .score{font-size:28px;font-weight:bold}.muted{color:#666}pre{white-space:pre-wrap;background:#f5f5f5;padding:14px;border-radius:8px;overflow:auto}
    </style></head><body>
      <div class='card'><h1>SMART — تحلیل اولیه بازار</h1>
      <p class='muted'>منبع فعلی: TSETMC | خروجی تصمیم‌یار، نه توصیه قطعی معامله.</p>
      <input id='symbols' value='شلرد,پالایش,عیار' style='width:65%'>
      <button onclick='run()'>اجرای تحلیل زنده</button>
      </div>
      <div id='cards' class='grid'></div><div class='card'><pre id='raw'>آماده...</pre></div>
      <script>
      async function run(){
        document.getElementById('raw').textContent='در حال دریافت و تحلیل...';
        const r=await fetch('/api/scan?symbols='+encodeURIComponent(document.getElementById('symbols').value));
        const data=await r.json();
        document.getElementById('raw').textContent=JSON.stringify(data,null,2);
        document.getElementById('cards').innerHTML=(data.results||[]).map(x=>`<div class='card'><h2>${x.symbol}</h2><div class='score'>${x.overall_score}</div><p>قیمت: ${x.price ?? '-'} | تغییر: ${x.change_pct ?? '-'}%</p><p>پول هوشمند: ${x.smart_money.phase} (${x.smart_money.score})</p><p>RSI14: ${x.technical.rsi14 ?? '-'} | نسبت حجم: ${x.volume_ratio ?? '-'}</p><p>تأییدها: ${(x.smart_money.confirmations||[]).join('، ')||'ندارد'}</p></div>`).join('');
      }
      </script>
    </body></html>
    """
