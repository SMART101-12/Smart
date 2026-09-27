# Historical financial layer

## Existing architecture and integration

SMART uses Python, FastAPI and a browser dashboard rendered by `smart.webapp`.
Charts use the existing Chart.js integration. `SnapshotStore` persists market
snapshots and `daily_history` in SQLite; the existing incremental sync and
monthly archive tools remain available. Symbols are resolved to TSETMC InsCode.
The live scanner combines money flow, technical analysis and data quality.

`HistoricalDataRepository` extends `SnapshotStore`, using the same database by
default. It adds financial documents, financial metrics, instrument mappings,
sync state and append-only sync logs. `market_history` is a view over the existing
market table, avoiding duplicate storage. Financial data is never stored in the
market table. Existing symbol-keyed market rows are reused through InsCode mapping.

The live history endpoint now reads the repository before fetching TSETMC. An
initial download fetches full history once; later downloads request new dates
and previously unresolved dates. Financial synchronization discovers Codal
announcements and downloads unknown document IDs. Publication dates, rather
than fiscal periods, drive amendment discovery. Insufficient year coverage or
rejected documents cause metadata rediscovery without downloading known reports.

## Data integrity

SMART DATA INTEGRITY RULE

No financial number may enter the analysis engine unless it has a traceable
source record. No missing financial value may be fabricated, estimated, assumed,
interpolated or replaced with zero. KODAL is the source of truth for financial
reports. TSETMC / approved market-data source is the source of truth for historical
market data. Previously downloaded verified data must be reused locally. Only
new or missing data may be synchronized.

The financial storage boundary re-parses raw evidence and compares extracted
fields with the submitted report. Documents retain raw text, SHA-256 digest,
publication time, retrieval time, source URL and per-cell locations. There is no
public numerical import endpoint and no LLM-to-database path. This is a trusted
provider boundary, not cryptographic certification of arbitrary caller input.

Missing metrics remain null. Non-finite numbers, ambiguous period columns,
unknown units and inconsistent balance-sheet totals are rejected. Revisions
are retained. Selection prefers audited reports, then publication date,
restatement and retrieval time; it selects whole reports, never fills holes
from superseded versions. Standalone and consolidated statements are separate.
Annual reports require explicit 12-month periods. Changed year ends and missing
years prevent a full score. TTM is not inferred from interim reports.

## Scoring and presentation

`FinancialScoringEngine` consumes repository reports only. Six configured
categories use explicit rules exposed in API output: growth, profitability,
cash flow, capital structure, earnings quality and stability. Every active
category requires all its inputs across the configured window (at least five
years). Unavailable categories are null; their weights are not redistributed.
Consequently, a partial dataset can have useful charts but no overall score.

Ratios retain formulas and source references. ROE/ROA explicitly use closing
equity/assets, not an assumed opening balance. Data-quality scores describe
coverage, completeness, source evidence, period compatibility and sync freshness;
they are not investment scores or a claim of complete source coverage.

The live scanner blends the historical financial score with its existing score
only when both are available. Other technical/research scores retain their own
meaning. The Persian narrative uses deterministic evidence templates, not a
free-form model. The dashboard provides eight trend charts, a revenue Tube/bar
chart, all-metric comparison table, source links, scoring rules and audit history.

## Configuration and operation

Default database: `data/smart.db`, shared with the existing snapshot store.

- `SMART_DATA_ROOT`: parent directory of the default database.
- `SMART_SNAPSHOT_DB`: explicit shared SQLite path.
- `SMART_HISTORICAL_DB`: optional separate historical database. Using it creates
  a separate cache; existing market data must be intentionally made available there.
- `SMART_FINANCIAL_CONFIG`: JSON configuration path; see
  `config/financial_history.json` for all category weights, minimum years,
  sync TTL and SMART contribution weight.

Read-only HTTP interfaces:

- `GET /api/financial-history?symbol=...` checks local state and syncs when due.
- `GET /api/financial-history?symbol=...&sync=false` reads local data only.
- `GET /api/financial-history?symbol=...&basis=consolidated` selects consolidated data.
- `GET /api/financial-history/audit?symbol=...` returns sync logs and report versions.

The existing dashboard has a financial button for each symbol and a financial
analysis button independent of the market scan. Source outages preserve local
evidence and expose a warning. With no evidence the UI displays N/A.

## Validation and remaining acceptance work

Unit/integration fixtures are explicitly synthetic and never represent actual
Codal company figures. Run `python -m pytest -q`. The opt-in real-source test is
`tests/test_codal_live.py`; enable `SMART_LIVE_CODAL=1` and optionally set
`SMART_LIVE_CODAL_SYMBOL`, then run that file. It requires actual five-year
coverage and cannot pass using mocked data.

Live Codal acquisition has not yet passed acceptance: connection attempts in
this environment timed out or disconnected. The conservative parser supports
explicit HTML tables and embedded JSON cell grids; actual layout coverage must
be tested against reachable official reports before production acceptance.
PDF-only documents, ambiguous units, quantity/segment disclosures and statement
layouts without explicit column dates are not synthesized. They remain missing
or are rejected. A default report page may expose only part of a multi-sheet
statement; full statement-sheet discovery remains acceptance work.

The new annual financial path does not claim global removal of every historical
fallback in unrelated research scripts. The live market path rejects incomplete
OHLCV for dependent engines and keeps missing flow values null. Market candidate
dates are weekday-based, not an authoritative holiday/listing calendar; unresolved
dates are recorded, and no percentage of complete market coverage is claimed.

No Git metadata exists in the supplied workspace, so no commit or Git diff was
available. No branch, commit, push or remote change was made.
