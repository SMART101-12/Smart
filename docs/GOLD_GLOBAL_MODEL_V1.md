# SMART Gold Global Multi-Factor Model v1

## Purpose

Daily, reproducible analysis of global gold (XAU/USD) and its transmission to Iranian 18K gold and gold ETF exposure. The model is designed for the SMART learning engine: every run must be versioned, traceable to an input snapshot, and reusable for later training/evaluation.

## Data flow

`Sources -> validated snapshot -> processed features -> gold analysis -> daily prediction -> realized outcome -> learning dataset`

The model must not consume unvalidated market records. It consumes only versioned processed datasets and records the exact input snapshot, feature-set version, model version, run ID, time range, parameters, metrics and result path.

## Core factors

1. XAU/USD return and momentum
2. DXY return and momentum
3. US 10Y nominal yield change
4. US real-yield proxy change when available
5. Fed policy expectation / hike-cut probability change
6. Geopolitical risk score
7. Central-bank net gold demand
8. Gold ETF flows
9. Oil return / inflation-risk proxy
10. USD/IRR or USD/IRT return for the Iranian transmission layer

## Signal logic v1

Each factor is normalized to a comparable z-score or bounded score. Direction is mapped so positive means supportive of gold. Missing factors are excluded from the numerator and the remaining weights are renormalized; the run records the missing-data penalty.

Default weights:

- XAU/USD momentum: 0.25
- DXY: 0.15
- US 10Y: 0.10
- Real yield: 0.10
- Fed expectations: 0.10
- Geopolitical risk: 0.10
- Central banks: 0.07
- ETF flows: 0.05
- Oil/inflation risk: 0.04
- USD/IRR: 0.04 (Iran transmission only; excluded from pure XAU/USD score)

The global gold score is mapped to:

- `BULLISH_STRONG`: >= +0.60
- `BULLISH`: +0.25 to +0.60
- `NEUTRAL`: -0.25 to +0.25
- `BEARISH`: -0.60 to -0.25
- `BEARISH_STRONG`: <= -0.60

## Outputs

Every daily run creates:

- factor snapshot
- factor contributions
- composite score
- regime classification
- 1D / 3D / 5D directional probabilities
- target ranges
- confidence and data-quality score
- exact source references
- realized outcomes when the forecast horizon closes

## Learning record

The learning dataset must preserve the original forecast and later realized return side-by-side. Never overwrite an old forecast with hindsight. New model versions are compared out-of-sample against prior versions.

Required run metadata:

`run_id, model_version, feature_set_version, input_snapshot, generated_at, horizon, parameters, data_quality, output_path, source_manifest`

## Initial verified market snapshot: 2026-08-21

Reuters reported spot gold at $4,623.94/oz on 21 Aug 2026, up 2.4% on the day, with a peak of $4,631.99. U.S. gold futures closed at $4,680.60. Reuters also reported that gold had risen more than 5% during the week and had moved above its 200-day moving average around $4,513. The weaker dollar and Treasury buyback announcement were cited as important drivers. This verified snapshot supersedes the approximate $4,587 figure in the initial research note for model inputs.

World Gold Council Q2 2026 data: Q2 central-bank net purchases 288.9t; H1 345t; Q2 ETF flows -44.8t; Q2 jewellery consumption 278.2t; Q2 mine production 965.6t; Q2 LBMA average $4,506.29/oz.

## Validation rule

A daily run is `PASS` only when all mandatory fields are either present and validated or explicitly marked unavailable. No value may be silently substituted. Conflicts between sources are retained in the source manifest and resolved using source priority, not by deleting the conflicting observation.
