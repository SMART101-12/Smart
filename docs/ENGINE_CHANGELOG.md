# SMART Engine Changelog

این فایل باید تاریخچه قابل بازبینی تکامل موتور پیش‌بینی را نگه دارد.

## v0.1 — Daily Prediction Learning Specification
- Added: daily walk-forward prediction protocol.
- Added: strict no-look-ahead rule.
- Added: 1/3/5-day forecast evaluation.
- Added: error taxonomy and learning loop.
- Added: baseline comparison requirements.
- Added: requirement to version engine/weights and record rationale.
- Commit: 4400a79d1b47ab93db309b4681364ba36350ef5b

## Next
- Build executable daily prediction runner.
- Start from the earliest valid trading record available for each symbol.
- Produce immutable prediction/outcome records.
- Repair and verify test suite before trusting performance results.
- Run Palayesh first as validation symbol.
- Compare every iteration against naive and prior engine versions.
