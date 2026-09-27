# AI layer

Consumes only versioned processed datasets. It must not fetch market data or mutate validated records.

Every training, inference, evaluation and weight-optimization run must record:
- run id
- model version
- feature-set version
- input dataset snapshot
- time range
- parameters
- metrics
- result path
