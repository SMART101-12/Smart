# SMART Model Comparison — 2026-08-17

## New research-driven Market Intelligence v1

OOS on 221 observations:
- MAE / mean absolute move error: 1.8915%
- Direction Accuracy: 67.8733%
- Winner: HGB-conservative
- No-lookahead: true
- Layers: price/trend, volume, trade value, trade count, liquidity/illiquidity, volatility, empirical limit proximity, regime.

## Historical benchmarks

### E080 — Ensemble v2.0
- MAE: 1.3775%
- Direction Accuracy: 53.52%
- OOS: 213

### E00280 — Ensemble v2.1 full pairwise
- MAE: 1.5722%
- Direction Accuracy: 64.06%
- OOS: 256
- Features: OBV(20), OBV(90), EMA(5), OBV(60)

## Interpretation

Market Intelligence v1 currently has the best Direction Accuracy among the compared candidates, but its price/magnitude error is worse than E080 and E00280. Therefore it is not a replacement for the ensemble yet.

The result is promising because the new model uses economically distinct feature families rather than only technical variants. The next test should combine Market Intelligence features with the strongest technical candidates, while keeping a completely frozen OOS and adding transaction-cost-aware trading evaluation.

Important: OOS sample sizes and split construction are not identical across historical experiments, so rankings are directional evidence, not a formal statistical league table yet.

## Missing data layer

Historical Git data does not contain point-in-time order-book depth/queue, حقیقی/حقوقی flow, or Persian news/social sentiment across the full sample. These must be ingested historically before being tested; no proxy is being treated as real LOB/flow/sentiment data.
