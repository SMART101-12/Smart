# Processing layer

Consumes only `validated_market` records. It must not call TSETMC directly.

Responsibilities:
- normalization
- derived fields
- technical indicators
- feature generation

Outputs are versioned under `runtime/processed_market/` and reference the exact validated dataset snapshot.
