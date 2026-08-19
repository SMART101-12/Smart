# SMART V2 Instrument Metadata Specification

## Purpose

`metadata.json` is the identity, lineage, quality, coverage and capability registry for one instrument. It is intentionally richer than a simple symbol dictionary.

Metadata must answer:

1. What instrument is this?
2. Where did its data come from?
3. Where is every data layer stored?
4. What dates are covered?
5. How many records have been received, tested, passed and rejected?
6. Which validation rules and test versions were used?
7. Which processing pipelines and indicator versions have been run?
8. Which strategies/backtests have been run, with which data and results?
9. What AI models/features have consumed the data?
10. What is the current quality/status of the instrument?

## Recommended structure

```json
{
  "schema_version": "2.0",
  "instrument": {
    "symbol_fa": "پالایش",
    "symbol_en": "PALAYESH",
    "ins_code": "67675656072510693",
    "instrument_type": "fund",
    "market": "iran_capital_market",
    "board": null,
    "issuer": null,
    "fund_name": null,
    "status": "active"
  },
  "identity_history": [],
  "source": {
    "primary": "tsetmc",
    "source_ids": {
      "tsetmc_ins_code": "67675656072510693"
    },
    "acquisition_module": "smart.acquisition",
    "acquisition_version": null,
    "last_successful_fetch": null
  },
  "storage": {
    "raw_path": "runtime/raw_market/PALAYESH_67675656072510693",
    "validated_path": "runtime/validated_market/PALAYESH_67675656072510693",
    "processed_path": "runtime/processed_market/PALAYESH_67675656072510693",
    "validation_report_path": "runtime/validation_reports/PALAYESH_67675656072510693.json",
    "analysis_path": "runtime/reports/PALAYESH_67675656072510693",
    "ai_path": "runtime/ai/PALAYESH_67675656072510693"
  },
  "coverage": {
    "first_observed_date": null,
    "first_trading_date": null,
    "last_observed_date": null,
    "last_validated_date": null,
    "calendar_version": null,
    "expected_trading_days": null,
    "received_days": 0,
    "validated_days": 0,
    "rejected_days": 0,
    "missing_days": 0,
    "duplicate_days": 0,
    "coverage_ratio": null
  },
  "quality": {
    "status": "unknown",
    "quality_score": null,
    "last_validation_at": null,
    "validation_run_id": null,
    "validation_suite_version": null,
    "rules": [],
    "open_issues": [],
    "resolved_issues": []
  },
  "validation_history": [],
  "processing_history": [],
  "analysis_history": [],
  "strategy_tests": [],
  "backtests": [],
  "ai_history": [],
  "data_lineage": {
    "source_commit": null,
    "raw_snapshot_ids": [],
    "validated_snapshot_ids": [],
    "processing_run_ids": [],
    "analysis_run_ids": [],
    "ai_run_ids": []
  },
  "current_state": {
    "raw_ready": false,
    "validated_ready": false,
    "processed_ready": false,
    "analysis_ready": false,
    "ai_ready": false,
    "last_state_change": null
  },
  "audit": {
    "created_at": null,
    "updated_at": null,
    "created_by": "smart-v2",
    "notes": []
  }
}
```

## Important rules

- Metadata is descriptive; it does not replace the actual market records.
- Raw data is immutable evidence. Validation failures are recorded, not hidden.
- Every validation run should record its suite version and run ID.
- Every processing/analysis/backtest/AI run should record its code/model version, input dataset snapshot, date range and result location.
- Historical symbol/name changes belong in `identity_history` rather than overwriting the past.
- A successful test must not be represented by a boolean alone; retain test name, version, run ID, timestamp, scope and result summary.
- Strategy results must never be written as if they were market-data facts. They are experiment artifacts linked to a specific dataset snapshot.
