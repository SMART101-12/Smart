# Gold Learning Dataset v1

The SMART learning engine must treat each gold analysis as a permanent training example rather than a disposable chat answer.

## Record lifecycle

`FORECAST_CREATED -> HORIZON_OPEN -> OUTCOME_REALIZED -> EVALUATED -> TRAINING_ELIGIBLE`

A forecast record is immutable after creation. Outcome fields are appended only after the corresponding horizon closes.

## Required fields

- `run_id`
- `model_version`
- `feature_set_version`
- `generated_at`
- `input_snapshot`
- `source_manifest`
- `feature_vector`
- `factor_contributions`
- `composite_score`
- `regime`
- `confidence`
- `forecast_horizon_days`
- `forecast_direction`
- `forecast_range`
- `realized_return`
- `direction_hit`
- `max_favorable_excursion`
- `max_adverse_excursion`
- `data_quality`

## Anti-leakage rules

1. No future price or future macro information may enter the feature vector.
2. The feature timestamp must be <= forecast timestamp.
3. Outcome fields are never used when generating the original forecast.
4. Model evaluation uses chronological/out-of-sample splits.
5. Every training/evaluation run stores its input snapshot and model version.

## Daily learning loop

For each trading day:

1. collect and validate global gold/macro inputs;
2. create a frozen input snapshot;
3. calculate the factor vector and score;
4. generate 1D/3D/5D/20D forecasts;
5. store the forecast immediately;
6. on later days, attach realized outcomes for horizons that have closed;
7. calculate hit rate, MAE, MFE, calibration and regime accuracy;
8. compare against the previous model version;
9. promote a new model only when out-of-sample metrics improve without violating data-quality thresholds.

## Training labels

Primary labels:

- direction: up/down/flat using a configurable dead-band;
- forward return for 1D, 3D, 5D and 20D;
- maximum favorable excursion;
- maximum adverse excursion.

Secondary labels:

- whether support/resistance range was reached;
- regime transition;
- volatility expansion/contraction.

This dataset is the durable memory for the gold component of SMART. Model memory must never be the only place where a learned rule or historical result exists.
