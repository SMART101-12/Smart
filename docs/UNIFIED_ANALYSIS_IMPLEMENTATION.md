# Unified analysis implementation — 2026-09-27

## Starting state

The source snapshot had working TSETMC, Codal, technical, strategy, risk and
legacy web/MCP services. `ARCHITECTURE_AUDIT.md` records the overlap and the
missing unified artifact. The initial suite passed: 124 passed, 3 skipped.
The directory has an empty Git repository on `master` with all project files
untracked. An `origin` remote points to the project's GitHub `main` branch,
but this local snapshot has no common commit to publish from safely.

## Added

- `smart.unified_analysis` persists one job per request, with stage durations,
  warnings and immutable analysis, raw, ChatGPT, report and SHA-256 manifest
  files under `runtime/analysis_runs/<symbol>/<analysis_id>/`.
- The existing TSETMC incremental history, Codal repository/scoring and
  200-strategy walk-forward exam are reused. A failed independent source
  becomes a warning; missing metrics remain absent.
- The default web page has a single analysis action and job progress. The old
  dashboard remains at `/legacy`. New HTTP endpoints create and inspect jobs
  and retrieve saved artifacts. MCP `analyze_stock` uses the same service.
- Artifact reads verify the manifest hashes. The ChatGPT context contains
  supplied evidence and an instruction to avoid invented figures; no model
  result is silently represented as an observed fact.
- The unified job now runs the existing per-symbol long-only learner. It selects
  a candidate using validation only, tests on a frozen OOS range, deducts a
  declared 0.35% round-trip execution cost, and records a model card, error
  analysis and a matched buy-and-hold baseline. A gap through a stop exits at
  the opening price. A missing live closing snapshot can be replaced by
  explicitly labeled cached-history technical analysis; live flow remains
  unavailable.
- The model card and its SHA-256 manifest entry are available at the local
  `/api/analysis/{symbol}/{analysis_id}/model-card` endpoint. Analysis output
  supplies relative local URLs. Forecast confidence remains uncalibrated and
  is never copied from the legacy quality-only score.

## Validation and live evidence

- Baseline: `python -m pytest -q`: 124 passed, 3 skipped.
- Focused unified and web checks: 8 passed.
- `python -m compileall -q src tests`: passed.
- Final regression after the OOS, gap-stop, fallback and boundary changes:
  `python -m pytest -q`: 134 passed, 1 skipped. No failures. A validation
  boundary test and a future-price perturbation test confirm that frozen OOS
  prices cannot change the validation-selected candidate.
- A real TSETMC/Codal run for پالایش produced analysis id
  `89b5adf703694f0b886cdc60e0dc21f5` locally. Symbol, market, history,
  Codal sync, fundamentals and historical exam stages completed. The source
  reported Codal `PARTIAL`; five years have reports, but the strict verified
  financial score is unavailable. The first exam had 1456 bars and status
  COMPLETE, but its 30-decision limit covered the oldest decisions. The exam
  now uses the most recent 300 bars and includes the terminal holdout. This is
  a directional strategy exam, not a long-only after-cost NAV.
- A live run (`e5dc2e1d1bc44bc1a92323bb34c1e6bf`) exercised the cached
  technical fallback when the closing endpoint failed. The later boundary-safe
  run (`94b2f9eae49842428f2f5074b84642f0`) completed all local stages with
  live TSETMC data. The selected candidate's validation return was -7.959647%
  over 32 closed trades; the frozen OOS return was +18.951946% over 54 closed
  trades, versus +253.586506% for fixed buy-and-hold in that OOS interval.
  These are results of the stated unadjusted-price simulation, not forward
  performance. The candidate fails validation and baseline checks; self-test
  decision: `REJECT`. Codal evidence remained insufficient for the strict
  five-year score, so the analysis status is `PARTIAL`.

## Remaining work and limits

- A frozen OOS long-entry model, self-test and after-cost trade simulation are
  integrated. The selected model is rejected on the real-source example.
  Corporate-action adjustment remains unverified, and intraday stop/target
  ordering is unknowable from daily OHLC; ambiguous bars use stop first.
- GitHub has a remote, but the local repository has no commit history. The
  analysis is partial, its model is rejected, and the source snapshot cannot
  be pushed as a normal descendant of remote `main`. No public Git/ChatGPT
  URL or final-valid-analysis marker is asserted. Local API URLs are provided.
- A 200-strategy directional exam is reused and reported as such. Its
  historical outcomes are stored in the raw/report artifact, never used as
  current facts in the ChatGPT context.

## Fund and Codal follow-up — 2026-09-27

- The real symbol پالایش is a fund (`صندوق پالایشی یکم`), so company revenue,
  EPS and debt ratios are not an appropriate financial score. The unified
  analysis now branches by the TSETMC instrument name and shows verified fund
  assets/liabilities/net assets with Codal document, sheet, period, unit and
  cell provenance. It never substitutes an equity score for fund evidence.
- The cached audited annual Codal document `1532541` (period 1404/12/29) and
  its net-assets sheet contain total assets 251632625, liabilities 4137466,
  and net assets 247495159, all in million IRR. Its NAV-per-unit cell is `0`,
  which is preserved as an unusable observed value, not presented as a usable
  valuation. The latest local analysis `ec34ad4d238c4484b9b4cc6e68d97fc8`
  consequently flags `verified_fund_nav_per_unit` as missing.
- Three older announcements resolved to auditor narrative pages rather than
  a numerical financial statement. The parser now excludes those pages from
  numerical extraction without misreporting them as failed statements.
- A forced real Codal search on 2026-09-27 received HTTP 429 at page 1 after
  bounded retries. This source-side rate limit prevents a fresh completeness
  check; local verified documents remain available. The sync status stays
  `PARTIAL`, and the actual source error is now included in the warning.
- The entry/exit stage excludes two explicitly invalid zero-OHLC bars from its
  recent window. The latest fund analysis has no confirmed setup (volume ratio
  0.3637); model self-test is `REJECT`. The dashboard displays a conditional
  research scenario with numerical levels labeled as not a trade order. A
  valid executable entry/exit recommendation is intentionally absent while
  the setup and model checks fail. Corporate-action-adjusted price integrity
  and fund NAV-per-unit verification remain outstanding.
- Final full regression after these changes: `python -m pytest -q` yielded
  139 passed, 1 skipped; `python -m compileall -q src tests` passed. The local
  web process was restarted and GET `/` and the latest fund analysis API both
  returned HTTP 200, including the fund and conditional-level fields.

## Legacy entry/exit display follow-up — 2026-09-27

- The legacy dashboard `/legacy` used `StockAnalysisService.to_frame` to
  reject the entire instrument history when any historical row lacked OHLCV.
  The locally stored پالایش history has 1456 dated rows, of which 134 are
  non-trading/incomplete candle rows. The latest row (2026-09-27) is verified;
  an all-history rejection was hiding valid recent entry/exit calculations.
- The V2 service now excludes incomplete or inconsistent observed candles
  individually, publishes every excluded date and its count, and calculates
  its indicators and last-60-day setup from verified bars only. Missing prices
  are never filled. If the latest source bar itself is invalid, it withholds
  both current trade plans and hypothetical levels to prevent stale signals.
- On the local پالایش history this yields 1322 valid bars, ATR 22546.57,
  setup status `no_setup`, and an explicitly hypothetical breakout scenario:
  entry zone 651226.8–656818.8, stop 626622, targets 717212.4 and 747409.2.
  The observed volume ratio is only 0.3637, so these are not an active entry
  recommendation. The old dashboard now shows the conditional levels and
  the excluded-bar count, and labels its previous confidence field as
  evidence quality rather than a forecast probability.
- Focused regression: 45 passed. Final full regression: 141 passed, 1 skipped;
  Python compilation and legacy dashboard JavaScript syntax checks passed.
- The restarted HTTP service returned 200 for `/` and `/legacy`. One real
  `/api/scan?symbols=پالایش` request returned `ANALYZED`, excluded 134 bars,
  `no_setup`, and the conditional levels above; no source error was reported
  by that request.
- Both pages now show the conditional entry, stop and targets in Persian;
  `/legacy` also includes them in its main ATR/entry line with a `مشروط`
  label. The final JavaScript syntax checks and HTTP 200 checks passed after
  the last display changes.

## Ten market methods and web-job reliability — 2026-09-27

- Ten separately reported, parameter-disclosed market lenses were added in
  `smart.market_models`, with methodology and Iranian-site references in
  `docs/TEN_MARKET_MODELS.md`. They appear in their own field on the main
  dashboard and in a separate section per card under `/legacy`. Every result
  records the input date, numeric metrics, vote, reason and required bar count.
  No consensus count is presented as a calibrated forecast or trade order.
- Windows could prevent the atomic `job.json.tmp` replacement when a status
  polling reader briefly held `job.json`. The writer now retries this specific
  transient `PermissionError`. A regression simulates the lock and verifies
  the committed status. Recent partial Codal results with five verified local
  annual years are reused for the ordinary TTL before acquiring the source
  sync lock; `force=True` still retries the source, and its partial warning
  remains visible. Earlier diagnostic jobs interrupted during this work were
  marked `INTERRUPTED`/`FAILED` rather than left indefinitely `RUNNING`.
- A real completed HTTP job `562d85cf09494571a88de5d381c02e69` returned
  `PARTIAL` with `ten_market_models=COMPLETED`, ten reported methods (7 bullish,
  3 neutral, none unavailable) on verified پالایش bars as of 2026-09-27. The
  Codal/fundamental stages remained partial; this does not override the
  previously rejected executable-entry model or missing fund NAV evidence.
- Final complete regression: 145 passed, 1 skipped. Python compilation,
  both dashboards' JavaScript syntax, GET `/` and `/legacy`, and the latest
  analysis API with ten saved model entries all passed.
