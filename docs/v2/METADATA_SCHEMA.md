# SMART V2 Metadata Schema

Metadata is the audit and lineage index for one instrument. It must never replace market records.

## Required groups

- `instrument`: Persian/English symbol, `ins_code`, instrument type, market type.
- `status`: lifecycle state of the dataset.
- `source`: provider, acquisition module and source family.
- `paths`: stable machine-readable paths to every layer.
- `coverage`: observed and certified date range, record counts, gaps and coverage ratio.
- `quality`: validation status, score, suite version and individual check states.
- `lineage`: source snapshot, dataset versions, commits and transformations.
- `processing_history`: every cleaning/normalization/features run.
- `analysis_history`: every analytical run and its input snapshot.
- `strategy_tests`: strategy experiments, parameters, dataset snapshot and result path.
- `backtests`: reproducible backtest runs and metrics.
- `ai_history`: training/inference/evaluation runs, model and feature-set versions.
- `audit`: creation/update timestamps and human/system notes.

## Lifecycle

`DISCOVERED -> ACQUIRED -> VALIDATING -> VERIFIED -> PROCESSED -> ANALYZED`

Failures use explicit states such as `VALIDATION_FAILED` or `ACQUISITION_PARTIAL` and must preserve the report path.

## Rule

A dataset may only move to `VERIFIED` when the validation run is reproducible and its report records the exact input snapshot, suite version, checks, counts, gaps and failures.
