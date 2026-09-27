# Acquisition layer

Acquisition is the only V2 layer allowed to contact market-data providers.

## Sources

- `smart.tsetmc_adapter.TsetmcAdapter`: instrument-specific TSETMC history and market data.
- `marketwatch_splitter.MarketWatchSplitter`: converts a raw gzip-wrapped TSETMC MarketWatch XLSX snapshot into symbol-level raw JSON records.

## Contract

1. Preserve provider responses before validation.
2. Use English filesystem identifiers: `<SYMBOL_EN>_<INS_CODE>`.
3. Keep Persian labels in JSON metadata only.
4. Never write to `runtime/validated_market`.
5. Never normalize or score data in acquisition.
6. Downstream validation is responsible for deciding whether a raw record is trusted.
