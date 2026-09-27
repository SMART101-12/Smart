# Analysis layer

Consumes only versioned processed datasets and AI outputs.

It must not:
- fetch market data directly
- mutate validated records
- bypass the processing layer

Responsibilities:
- analytical features
- trend analysis
- signal generation
- analysis snapshots

Outputs are versioned under `runtime/analysis/`.
