# SMART local / in-chat runtime

## Data retention rule

Every market fetch must be persisted **before** analysis. The raw source payload,
source name, observation timestamp, and save timestamp are stored in SQLite.

The scanner must not silently reuse an old record as today's market data.
Before an observation is used as live/current data, `freshness_status()` checks:

1. the source observation timestamp;
2. the calendar date against the current UTC date;
3. the maximum allowed age (default 5 minutes for live observations).

If the check fails, the result is marked stale/previous-day and the scanner must
fetch fresh data or explicitly report that current data is unavailable.

## No-host limitation

The repository can run locally with Python/Docker and persist its SQLite database
without a cloud database. However, a custom ChatGPT App/MCP server still needs a
reachable HTTPS endpoint for ChatGPT to call it. GitHub itself is source control,
not a runtime host.

Until a public endpoint exists, SMART can be exercised in this ChatGPT session by
using the available web/data tools and the same analysis contracts, but that is
not the same as installing the repository as a native custom ChatGPT App.

## Intended flow

```text
fetch source
   -> save raw snapshot
   -> freshness check
   -> compare with prior observations
   -> validate sources
   -> analyze
   -> save analysis/audit record
   -> return result + data timestamp
```
