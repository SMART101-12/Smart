# SMART Experiment Results

## Palayesh — daily-prediction-v1.0

Run date: 2026-08-16

Data source: Git history under `runtime/history/پالایش/`

Coverage: 20200826 → 20260815
Rows: 1,425
Walk-forward predictions: 1,394
No look-ahead: true

### Results
- Direction accuracy: 50.7174%
- Model MAE: 1.8333%
- Naive next-close MAE: 1.8115%
- Mean improvement vs naive: -39.4886%
- Share of predictions beating naive: 49.5349%
- Final weights: naive 69.7773%, momentum5 8.0923%, trend20 22.1304%; SMA20 and EMA20 were effectively eliminated by the online learner.

### Decision
**REJECT as final model.** The engine is not yet better than the naive baseline and therefore must not be used as the production prediction engine.

### What this test proved
1. The Git history can be consumed end-to-end from the earliest valid Palayesh record.
2. The walk-forward runner completes without look-ahead.
3. Every daily forecast and learning update can be persisted.
4. Online learning alone is insufficient; the current expert set does not add predictive value.

### Next experiment gates
- Add point-in-time price-action and support/resistance features.
- Add volatility/range forecasting.
- Add stored volume/money-flow features.
- Test regime-specific experts.
- Separate development, validation and frozen out-of-sample windows.
- Re-run against the naive baseline after each change.
- Do not promote any version unless it improves out-of-sample performance without leakage.

## CI status for this stage
- Linux unit tests + experiment: PASS.
- Windows installer + unit tests: PASS after fixing a floating-point assertion in the new test.
- The Windows failure and its correction are part of the Git history.
