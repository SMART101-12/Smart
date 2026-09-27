# SMART architecture audit — 2026-09-26

Baseline: Python 3.12; `python -m pytest -q`: **126 passed, 1 skipped in 35.30s**.
The skipped test requires opt-in live Codal access. This directory is a source
snapshot, not a Git checkout; no local commit/remote metadata is available.

## Existing — preserve and extend

* `smart.tsetmc`, `market_history`, `incremental`, `snapshot_store`: symbol
  resolution, SQLite raw history, local-first incremental refresh.
* `archive`: canonical normalization, deterministic deduplication, validation.
* `codal`, `codal_operations`, `financial_history`, `company_financials`,
  `financial_scoring`: verified source documents, versions, monthly/quarterly
  extraction and five-year financial scoring. Missing periods remain absent.
* `technical_analysis`, `strategy_lab`: causal indicators and 200 strategies.
* `symbol_learning`: adaptive profiles, temporal validation and trading costs.
* `smart_v2.analysis.trade_plan`: multi-factor conditional long setups.
* `risk`, `daily_cycle`, `decision_memory`: sizing, durable runs, outcomes.
* `webapp`, `server`: established HTTP APIs and read-only MCP tools.

## Incomplete / incorrect assumptions

* No single audited artifact unifies acquisition, analysis, exam and export.
* The existing strategy exam measures directional forecasts, including a
  hypothetical inverse return for DOWN. It is not a long-only after-cost NAV.
* The V2 Smart Money factor is an OHLCV proxy, not measured client-type flows.
* A missing NAV becomes a neutral value score in the legacy factor engine;
  do not use that composite as a complete equity fundamental assessment.
* Existing report quality misses some discarded input rows and staleness.
* Legacy UI exposes many separate workflows; keep its capabilities accessible
  while making the default workflow a single analysis action.
* Report selection currently has no publication-time cutoff for replay.
* Industry, market-wide point-in-time series and adjusted corporate actions
  are not guaranteed by daily stock OHLCV. Never infer these as verified facts.
* GitHub export, immutable manifest and artifact-reading MCP tools are missing.

## Duplication / cleanup policy

There are legacy and V2 adapters, quality helpers and analysis entrypoints.
They have callers and regression tests: no bulk deletion or rewrite. New
orchestration reuses their stable boundaries. Exclude environment/cache/runtime
artifacts; preserve local market archives and user data. No artifact deletion
is required to implement this sprint.

## Ordered implementation

1. Baseline and audit (above).
2. Unified service and honest quality/availability contract.
3. Causal indicators, actual flows, publication-time selection and exams.
4. Immutable local artifacts, integrity checks, optional GitHub publication.
5. Read-only artifact API/MCP, one-button UI and stage progress.
6. Regression tests and real-source run; record external blockers explicitly.

This audit is not a certification that every legacy algorithm or external
provider is correct. Completion evidence and remaining limits are recorded in
`docs/UNIFIED_ANALYSIS.md`.
