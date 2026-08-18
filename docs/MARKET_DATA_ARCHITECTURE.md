# SMART Market Data Architecture

## 1. Layers

### Raw
`runtime/market_raw/`

Purpose: immutable evidence from external sources.

Current TSETMC source:

`runtime/market_raw/marketwatch/YYYY-MM-DD.gz`

Rules:
- Save the exact response bytes.
- Do not normalize or calculate indicators here.
- Keep source date and source URL documented by the downloader.

### Raw symbol snapshots
`runtime/market_raw/stocks/<symbol>/<YYYY-MM>/<YYYY-MM-DD>.json`

Purpose: one symbol's original MarketWatch row, linked back to the raw source file.

### Processed
`runtime/market_processed/<symbol>/<YYYY-MM>/<YYYY-MM-DD>.json`

Purpose: stable machine-readable data derived from the raw row.

The current processor still keeps the complete MarketWatch row. Future normalization should add stable English fields without deleting the original row.

### Monitored
`runtime/market_monitored/<symbol>/<YYYY-MM>/<YYYY-MM-DD>.json`

Purpose: analysis-ready daily observations and validation flags.

This layer is intentionally separate from `market_processed`. It is where SMART may add:
- normalized metrics
- data-quality flags
- market-calendar status
- technical indicators
- volume/value comparisons
- order-book metrics
- signal components
- score inputs

### Signals and learning
Recommended future layers:

```text
runtime/signals/
runtime/validation/
runtime/learning/
```

Signals must reference the source date and symbol snapshot used to create them. Learning records must reference the original signal and its future outcome.

## 2. Identity model

Current identity:

```text
symbol -> folder_symbol
```

`InsCode` is currently unavailable in the MarketWatch Excel export. It must be enriched later from a dedicated identity endpoint/source.

Required future identity record:

```json
{
  "symbol": "...",
  "ins_code": "...",
  "isin": "...",
  "name": "...",
  "market": "...",
  "instrument_type": "stock|gold_fund|other",
  "valid_from": "YYYY-MM-DD",
  "source": "TSETMC"
}
```

Identity mapping must not be guessed from a name alone when multiple instruments share similar names.

## 3. Daily monitored record

Target structure:

```json
{
  "source_date": "YYYY-MM-DD",
  "symbol": "...",
  "ins_code": null,
  "instrument_type": "stock",
  "market_status": "open",
  "source_quality": {
    "raw_available": true,
    "required_fields_complete": true,
    "duplicate_symbol": false
  },
  "market": {
    "last_price": null,
    "close_price": null,
    "first_price": null,
    "yesterday_price": null,
    "volume": null,
    "value": null,
    "trades": null
  },
  "order_book": {},
  "indicators": {},
  "score": null,
  "signal": null,
  "source_file": "..."
}
```

The null fields are placeholders, not fabricated values.

## 4. Trading calendar

SMART must distinguish:

- Tehran Stock Exchange / equity market hours
- Gold-fund hours
- official Iranian holidays
- Thursday/Friday closures
- exceptional closures

A closed day must not be interpreted as zero volume or a failed data feed.

## 5. Analysis pipeline

```text
raw source
  -> parsing
  -> identity enrichment
  -> normalization
  -> data-quality validation
  -> monitored daily record
  -> indicators
  -> score
  -> signal
  -> 1/3/5 trading-day outcome
  -> learning dataset
```

## 6. Indicator policy

The technical engine is expected to support multiple configurable indicators rather than one fixed formula. Candidate groups include:

- trend / moving averages
- momentum
- volatility
- volume and value
- money-flow / smart-money proxies
- support/resistance
- market breadth where data permits

Weights must be configurable and versioned. A score must record the indicator configuration used to produce it.

## 7. Signal policy

A recommendation should contain at minimum:

- symbol
- date/time
- score
- reasons
- entry zone
- invalidation/stop condition
- target/exit logic
- risk/reward estimate
- confidence
- data-quality status
- model/weight version

The engine must never output a high-confidence recommendation when required source data is missing or stale.

## 8. Historical validation

For every signal, SMART should later record outcomes at:

- 1 trading day
- 3 trading days
- 5 trading days

The outcome record must account for market closures and instrument trading hours. This historical dataset becomes the input for weight adjustment and learning.

## 9. Reproducibility

Every derived file should be traceable to:

```text
source file
source date
symbol
processing version
indicator configuration
model/weight version
```

This allows an old analysis to be reproduced instead of silently changing when the code changes.
