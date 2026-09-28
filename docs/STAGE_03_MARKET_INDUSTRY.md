# Stage 3: market and industry regime

The optional `SMART_REGIME_SNAPSHOT` environment variable names an imported JSON bundle. Its schema has `source`, `major_index`, `equal_weight_index`, `memberships`, and `industry_indices`. Index series contain at least 22 objects with ISO `date` and positive `close`. Memberships contain `symbol`, `industry`, `effective_from`, and optional `effective_to`. The parser rejects stale, future, malformed, duplicate, and misaligned observations. It reports 20 session returns, divergence, and source attribution. Historical membership must be effective on the analysis date.

At the initial stage 3 commit the repository did not have official historical Iranian index series or industry membership history, so production returned `UNAVAILABLE/UNKNOWN`. Stage 10 added an official TSETMC index provider with identity checks and raw response hashes; see `STAGE_10_DELIVERY.md`. An operator imported snapshot still only declares its source and cannot mark itself as a verified official fetch. Price of the analyzed symbol and US FRED macro series never stand in for the Iranian broad market. Missing evidence is listed in `missing_data`, and the versioned layer contract remains additive to old artifacts.

Example structure (illustrative; do not treat as real observations):

```json
{"source":"TSETMC imported snapshot", "major_index":[{"date":"2026-09-26","close":100}], "equal_weight_index":[{"date":"2026-09-26","close":100}], "memberships":[{"symbol":"EXAMPLE","industry":"EXAMPLE_SECTOR","effective_from":"2026-01-01","effective_to":null}], "industry_indices":{"EXAMPLE_SECTOR":[{"date":"2026-09-26","close":100}]}}
```

The example is intentionally insufficient for a classification. Imported series must contain enough dated observations and source provenance. Historical industry membership and a verified industry index remain unavailable when they cannot be resolved from a dated official source.
