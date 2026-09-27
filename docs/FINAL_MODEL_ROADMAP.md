# SMART Final Model Roadmap and Audit Trail

## User acceptance criterion
نتیجه نهایی باید عملکرد واقعی پیش‌بینی و معامله باشد، نه صرفاً یک امتیاز تکنیکال. تمام مراحل توسعه، آزمون، شکست، اصلاح و انتخاب مدل باید در Git قابل ردیابی باشد.

## Pipeline
1. Git market history is the only historical price input for the experiment.
2. Data quality and market-calendar validation.
3. Earliest valid trading date becomes the walk-forward starting point.
4. Point-in-time feature calculation only from rows available at date T.
5. Generate T+1 price, return, direction and 5-session path forecasts.
6. Persist prediction before using T+1 outcome.
7. Compare actual T+1 against model and naive baseline.
8. Classify the error and update expert weights only after realization.
9. Repeat through the full available history.
10. Freeze an out-of-sample period and do not tune against it.
11. Compare candidate engines by MAE, direction accuracy, improvement over naive, profit factor, expectancy and drawdown.
12. Promote a model only if it survives the acceptance gates.

## Current candidate engine
`daily-prediction-v1.0`

Experts:
- Naive
- SMA20
- EMA20
- Momentum5
- Trend20

Learning:
- Online exponential penalty based on realized percentage error.
- Weights are normalized after every realized next-day close.

## Required next model stages
- Add explicit price-action / support-resistance features.
- Add robust volatility-aware range forecasting.
- Add volume/money-flow features available in the stored data.
- Add trade-entry/stop/target simulation after forecast validation.
- Add regime-specific expert weights using walk-forward training only.
- Add frozen out-of-sample evaluation.
- Add model-vs-model leaderboard.

## Rules against false performance
- No future rows in feature calculation.
- No tuning on the final test window.
- No 99% accuracy claim without untouched out-of-sample evidence.
- A complex model must beat the naive baseline to justify its complexity.
- Every promoted version must have a reproducible report committed to `runtime/experiments/`.

## Git trace
- Specification: `4400a79`
- Calendar foundation: `be25170`
- Prediction engine: `a31e6b1`
- Experiment runner: `f042434`
- Prediction unit tests: `dcc973f`
- CI/experiment pipeline: `5badd842`
- TSETMC test repair: `c5164a1`

## Final deliverable
`runtime/experiments/پالایش/daily_prediction_report.json` is the canonical experiment result. It must identify the engine version, date coverage, prediction count, metrics, final weights, every daily prediction and every learning update.
