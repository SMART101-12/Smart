# SMART Project Status

## Current state

Branch: `agent/data-gap-recovery`

The TSETMC raw MarketWatch pipeline is operational:

```text
TSETMC MarketWatchPlus
        |
        v
runtime/market_raw/marketwatch/YYYY-MM-DD.gz
        |
        v
scripts/process_marketwatch.py
        |
        +--> runtime/market_raw/universe/YYYY-MM-DD.json
        |
        +--> runtime/market_raw/stocks/<symbol>/<YYYY-MM>/<YYYY-MM-DD>.json
        |
        +--> runtime/market_processed/<symbol>/<YYYY-MM>/<YYYY-MM-DD>.json
```

## Important design decisions

1. The raw TSETMC response is preserved unchanged.
2. Raw data and derived data are kept in separate layers.
3. MarketWatchPlus does not provide `InsCode` in the export used by SMART. The processor therefore does not invent one; `ins_code` is currently `null`.
4. Symbol is the current identity for the first processing layer. Later enrichment must map symbol to `InsCode`/ISIN using a dedicated TSETMC identity source.
5. Duplicate symbols are not silently merged; duplicate folders receive `__2`, `__3`, etc.
6. Dates are stored as Gregorian ISO dates (`YYYY-MM-DD`) in the data layer. Persian calendar presentation belongs to the reporting layer.
7. The raw layer must never be overwritten by indicator calculations or model outputs.

## Current commands

Download and commit the latest raw MarketWatch file:

```powershell
.\update-file.ps1
```

Process the latest raw MarketWatch file:

```powershell
.\process-market.ps1
```

## Next implementation stages

1. Build the monitored layer from processed symbol snapshots.
2. Add market-calendar rules: Thursday/Friday closures, official holidays, and instrument-specific trading hours.
3. Add identity enrichment (`symbol -> InsCode/ISIN`).
4. Normalize prices, volume, value, orders, and other MarketWatch fields into stable English field names while retaining the original row.
5. Add technical indicators and market microstructure metrics.
6. Add fundamental-data ingestion as a separate source; do not infer fundamentals from MarketWatch.
7. Build scoring and ranking: Top 10 candidates, then Top 3 with entry/exit/risk fields.
8. Record every signal and evaluate it after 1, 3, and 5 trading days.
9. Build the learning engine only after enough validated historical outcomes exist.
10. Add cross-source validation before using live data for decisions.

## Validation requirements

Every new stage must report:

- source file and source date
- row/instrument counts
- missing critical fields
- duplicate symbols
- malformed values
- processing timestamp
- output path
- failure reason without modifying Git when processing fails

## AI handoff rule

Before changing the pipeline, read this file and `docs/MARKET_DATA_ARCHITECTURE.md`. Do not redesign an existing working stage without first checking its current Git implementation and recorded assumptions.
