# SMART TSETMC Historical Data

## Purpose

`MarketWatchPlus` is a point-in-time market snapshot. It is useful for daily monitoring, but it is **not** the historical price database.

SMART therefore has a separate historical ingestion stage based directly on TSETMC historical endpoints.

## Data flow

```text
TSETMC historical endpoint
        |
        v
runtime/market_raw/history/<symbol>/raw/<retrieval-date>.txt
        |
        v
runtime/market_raw/history/<symbol>/<retrieval-date>.json
        |
        v
future monitoring / indicators / learning engine
```

The raw response is preserved before parsing so the historical dataset can be audited and reparsed later.

## Historical source

Primary endpoint:

`InstTradeHistory.aspx?i=<InsCode>&Top=99999&A=0`

Fallback:

`Financial.aspx?i=<InsCode>&t=ph&a=0`

The ingestion code first resolves the symbol to its TSETMC `insCode`, then requests the historical series. TSETMC's daily-history endpoint is documented as returning multiple daily records, with `Top=0` conventionally meaning all available records; the implementation uses a high `Top` value and a chart-history fallback for resilience.

## Stored fields

Where supplied by the primary endpoint:

- `date`
- `open`
- `high`
- `low`
- `close`
- `last`
- `previous_close`
- `volume`
- `value`
- `trades`
- `ins_code`

The fallback chart endpoint supplies its available OHLCV fields and does not invent unavailable values.

## One-command update

From the repository root:

```powershell
.\history-market.ps1
```

This command:

1. Fetches historical data for every symbol in `config/tsetmc_symbols.txt`.
2. Saves the raw TSETMC response.
3. Saves a parsed JSON history with first/last date and record count.
4. Writes a retrieval universe/status file.
5. Commits the historical data.
6. Pushes it to `agent/data-gap-recovery`.

## Important distinction

- `runtime/market_raw/marketwatch/` = daily point-in-time market snapshots.
- `runtime/market_raw/history/` = historical daily trading records.
- `runtime/market_processed/` = processed data derived from MarketWatch and later processing stages.

A historical price answer must use `history/`, not the MarketWatch snapshot.

## Validation rule

Before using a symbol's history for analysis, check:

- `status == ok`
- `record_count > 0`
- `first_date` and `last_date`
- the requested trading date exists in `records`
- no duplicate dates
- price/volume fields are numeric

The system must report missing trading dates rather than silently filling them.
