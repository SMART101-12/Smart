"""Small browser-facing SMART dashboard for the first live test."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from .ai import healthcheck
from .scanner import Candidate, initial_analysis

app = FastAPI(title="SMART Market Intelligence", version="0.1.0")


@app.get("/health")
def health():
    return {"service": "SMART", **healthcheck()}


@app.get("/api/scan")
def scan():
    # Safe smoke-test payload until live market adapters are enabled.
    candidates = [
        Candidate("SHLDR", smart_money_score=0, technical_score=0, liquidity_score=0, data_quality_score=50),
        Candidate("PALAYESH", smart_money_score=0, technical_score=0, liquidity_score=0, data_quality_score=50),
        Candidate("AYAR", smart_money_score=0, technical_score=0, liquidity_score=0, data_quality_score=50),
    ]
    return initial_analysis(candidates)


@app.get("/", response_class=HTMLResponse)
def home():
    return """
    <!doctype html><html lang='fa' dir='rtl'><head><meta charset='utf-8'>
    <meta name='viewport' content='width=device-width,initial-scale=1'>
    <title>SMART</title>
    <style>body{font-family:Arial,sans-serif;max-width:1000px;margin:40px auto;padding:0 20px}button{padding:12px 20px;font-size:16px}pre{white-space:pre-wrap;background:#f5f5f5;padding:16px;border-radius:8px}</style>
    </head><body><h1>SMART — Market Intelligence</h1>
    <p>نسخه MVP برای تست اولیه موتور اسکن و تحلیل.</p>
    <button onclick='run()'>اجرای اسکن اولیه</button><pre id='out'>آماده...</pre>
    <script>async function run(){document.getElementById('out').textContent='در حال اجرا...';const r=await fetch('/api/scan');document.getElementById('out').textContent=JSON.stringify(await r.json(),null,2)}</script>
    </body></html>
    """
