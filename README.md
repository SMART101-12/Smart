# SMART

Excel-first, modular, adaptive decision-support system for the Iran capital market.

## Current stage
**Sprint 2 — Full technical dashboard, strategy lab and ChatGPT explanation**

The repository also includes a resumable data/archive/analysis/learning path:

```text
raw TSETMC/FRED -> canonical archive -> validation -> analysis -> OOS learning
```

See [`docs/SMART_COMPLETE_IMPLEMENTATION_2026-08-29.md`](docs/SMART_COMPLETE_IMPLEMENTATION_2026-08-29.md)
for the branch audit, completed work, data counts, paths, tests and next commands.

Workflow:
1. Live data collection
2. Multi-source validation
3. Pre-filter
4. Daily Top 10
5. Operator selects 2–3
6. Analysis modules
7. Risk / trade plan
8. Outcome logging
9. Learning & optimization

## What is live in the codebase now

- TSETMC live adapter for symbol search, instrument info, quote, daily history and حقیقی/حقوقی flow
- Technical primitives: SMA, EMA, RSI and volatility
- Full-history MACD, RSI, SMA/MA, EMA, ATR, breakout and volume series
- Chart.js price/MA/EMA, volume and oscillator charts in the browser dashboard
- 200-strategy research catalog with point-in-time walk-forward exam
- Automatic decision artifacts and `/api/outcome`/`/api/settle` outcome loop
- Optional ChatGPT explanation endpoint (`/api/chat`) and MCP `chat_explain`
- Multi-confirmation Smart Money phase engine
- Explainable ranking/scanner
- Read-only MCP tools
- Streamable HTTP MCP entrypoint
- Browser dashboard for first live analysis
- Docker + Render blueprint
- GitHub Actions test workflow
- Incremental TSETMC sync (`scripts/sync_tsetmc_incremental.py`)
- Canonical archive and safe derived-data audit (`scripts/audit_data_layers.py`)
- FRED global-market archive (`scripts/sync_global_market.py`)
- Integrated stock analysis (`smart_v2.analysis.StockAnalysisService`)
- Leakage-safe local AI training (`scripts/train_smart_ai.py`)
- Walk-forward exam CLI (`scripts/run_walk_forward_exam.py`)

## ChatGPT App path

The MCP server is designed to be hosted at `https://<host>/mcp`. After HTTPS deployment, connect that remote MCP server in the ChatGPT Apps/MCP developer testing flow and call `scan_market`.

See [`docs/CHATGPT_TEST.md`](docs/CHATGPT_TEST.md) for the exact acceptance test.
See [`docs/STRATEGY_RESEARCH_200.md`](docs/STRATEGY_RESEARCH_200.md) for the
200-strategy catalog and no-look-ahead protocol.
For a cross-platform setup guide, see [`SETUP_ANY_SYSTEM.md`](SETUP_ANY_SYSTEM.md).

## Local Windows start

If `conda` or `python` is not on `PATH`, call the Anaconda interpreter directly:

```powershell
$py = "C:\Users\PC101\anaconda3\python.exe"
$env:PYTHONPATH = ".\src"
& $py -m pip install -r requirements.txt
& $py -m pytest -q
& $py -m uvicorn smart.webapp:app --reload
```

Open `http://127.0.0.1:8000/`. Set `OPENAI_API_KEY` in a local `.env` (or the
PowerShell environment) only when the ChatGPT explanation endpoint is needed.

## Data-source note

TSETMC endpoints used by the adapter are community-documented and can change or restrict access. SMART reports source failures explicitly and never fabricates missing market values. Global macro/market proxies are available through the FRED adapter; gold proxy fields are explicitly named and are not silently treated as spot XAU/USD.

## Security

The OpenAI API key is read only from `OPENAI_API_KEY`. It is never stored in source code or committed to GitHub.
