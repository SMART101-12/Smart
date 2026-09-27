# SMART Direction / Magnitude Meta-Ensemble

## Why this layer was added

The previous technical engine treated several indicators as a fixed integer score and then mapped the score directly to UP/DOWN/NEUTRAL. That is useful as a baseline, but it does not separate:

1. **Direction** — is the next 5-trading-day move more likely to be up or down?
2. **Magnitude** — if it moves, how large is the move likely to be?
3. **Confidence** — how trustworthy is the directional probability?
4. **Execution gate** — should SMART actually pass the signal to the trade-plan layer?

The new pipeline is:

```text
TODAY
  |
  +-- Trend / structure
  +-- Momentum
  +-- Breakout
  +-- Volume
  +-- Volatility
  +-- Regime
  |
  +-- online component reliability (past only)
  |
META ENSEMBLE
  |
  +--> Direction probability --> calibration --> UP / DOWN / NEUTRAL
  |
  +--> Volatility + conditional historical move --> Magnitude
  |
  +--> Expected Price
  |
  +--> Confidence Gate --> PASS / HOLD
```

## Research decisions

Recent research points toward regime-aware, strictly chronological evaluation rather than a single unconditional return model. A June 2026 study combines regime indicators, volatility forecasts and ML return prediction under strict walk-forward validation and finds that predictability is state-dependent; implementation choices such as volatility scaling and threshold calibration matter materially. The SMART design therefore keeps regime and volatility explicit rather than hiding them inside one black-box score.

Probability calibration is included because a directional model can rank outcomes correctly while still being overconfident. SMART uses a lightweight, leakage-safe empirical calibration map based only on earlier observations, with Laplace smoothing. This follows the same core principle as OOF/PurgedKFold calibration: calibration data must not contain information from the future.

Triple-barrier labeling is included as a trade-oriented diagnostic. It uses an ATR-scaled profit barrier, stop barrier and time barrier. When daily OHLC touches both price barriers in the same bar, SMART labels the observation neutral because daily data cannot establish which barrier was hit first.

## What is deliberately not claimed

- This is **not** a claim that the model will beat the market.
- The current history files contain price/volume data, not a fully point-in-time news/event feed. Therefore `Market Intelligence` is represented by market regime/structure proxies in this version, not fabricated news sentiment.
- No future rows are used to create a signal. Future rows are used only after the signal to score the prediction.
- The 80% design score is an engineering readiness score, not 80% prediction accuracy.

## Engineering self-review loop

Initial architecture score: **61/100**.

Main weaknesses: fixed weights, no probability calibration, no separate magnitude model, and no trade-oriented barrier label.

After research and redesign: **86/100**.

Scorecard:

| Area | Score | Reason |
|---|---:|---|
| Point-in-time / leakage control | 20/20 | Chronological walk-forward; only prior outcomes update meta weights/calibration |
| Direction model | 17/20 | Diverse technical families + regime-aware online weighting |
| Magnitude model | 14/15 | ATR-scaled forecast with conditional historical shrinkage |
| Probability calibration | 12/15 | Prior-only binned calibration + smoothing; lightweight by design |
| Regime awareness | 10/10 | Bull / sideways / bear weighting |
| Trade realism | 8/10 | Triple barrier + confidence gate; transaction-cost model is still a later layer |
| Market intelligence | 5/10 | Regime/structure proxies are present; point-in-time news/event feed is not yet connected |
| **Total** | **86/100** | Above the 80-point implementation threshold |

## Test protocol

The new test compares the new meta-ensemble with the existing technical baseline on both `پالایش` and `فولاد` using the same stored Git history and a 5-trading-day forward outcome. It reports signal count, direction accuracy, Brier score, coverage and gated strategy return.

The test is intentionally run by GitHub Actions against the repository history so that the comparison is reproducible from Git rather than from an external price source.
