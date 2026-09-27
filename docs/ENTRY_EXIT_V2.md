# Deterministic entry/exit service

`AnalysisService.trade_plan(records, symbol, tf="1d")` and
`POST /api/trade-plan` return `ready`, `no_setup`, or `insufficient_data`.
The request body contains `symbol`, `tf`, and dated OHLCV `records`.
Only completed daily bars are supported; callers must exclude an in-progress
session. No implicit timeframe conversion is performed.

The engine uses a prior 20-bar resistance/support window, historical 14-bar
mean true range, and a prior volume baseline. A breakout must close above
resistance plus 0.1 ATR. A retest requires a prior confirmed breakout and a
reclaim of resistance within 0.25 ATR. Current volume must be at least 1.2
times baseline. Prices more than 2 ATR above resistance are not chased.
The stop is one ATR below broken resistance; targets use 2R and 3R measured
from the upper entry-zone boundary. These are calculated conditional levels,
not source prices or predictions. The engine is long-only and does not execute.

Missing/invalid OHLCV, duplicate dates, unsupported timeframes and unavailable
ATR/volume return no plan. Unconfirmed conditions return `no_setup`, not an
invented neutral plan. The dashboard displays the reason and second target.

`AnalysisService.report` uses `AnalysisOutputFormatter` to produce versioned
summary, data-quality, technical, entry/exit, risk, source and warning sections.
Existing stock-analysis keys remain available to existing consumers.

`smart_v2.acquisition.codal.CodalClient` is the typed notice facade over the
existing endpoint and source policy. Inject an `httpx.Client` with MockTransport
for tests and an injectable wait function for deterministic retry tests.
Notices retain title/date/report ID and official PDF/attachment links; summaries
remain empty when absent from the source. Failed discovery raises an explicit
error, never fake notices. Attachment downloads validate every redirect.

Run the application from PowerShell:

```powershell
Set-Location D:\samrt
$env:PYTHONPATH = 'src'
python -m uvicorn smart.webapp:app --host 127.0.0.1 --port 8000 --reload
```

Open `http://127.0.0.1:8000`. Run regressions with:

```powershell
python -m pytest tests/v2/test_trade_plan_regression.py tests/v2/test_codal_client.py -q
```
