# SMART

Excel-first, modular, adaptive decision-support system for Iran capital market.

## Current stage
Sprint 1 — Scanner MVP foundation.

Workflow:
1. Data collection
2. Multi-source validation
3. Pre-filter
4. Daily Top 10
5. Operator selects 2–3
6. Analysis modules
7. Risk / trade plan
8. Outcome logging
9. Learning & optimization

## Principles
- Adaptive thresholds; no universal fixed thresholds
- Regime-dependent and horizon-dependent weights
- Scanner and Portfolio are separate
- Explainable AI + human decision
- Multi-source data validation
- Smart Money requires multiple confirming signals

## Development
Python package under `src/smart/` with tests under `tests/`.
