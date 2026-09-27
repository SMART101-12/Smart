# SMART strategy research and walk-forward exam

## What was implemented

SMART now contains 200 deterministic strategy variants. They are organized as
20 research families with 10 parameter variants each:

1. SMA crossover
2. EMA crossover
3. MACD regime
4. RSI mean reversion
5. RSI momentum
6. Bollinger mean reversion
7. Bollinger breakout
8. Donchian breakout
9. ROC momentum
10. Volume breakout
11. ATR trend
12. Stochastic oscillator
13. CCI trend/reversion
14. Williams %R
15. OBV trend
16. VWAP deviation
17. Triple moving average
18. Support/resistance
19. Price action
20. Multi-confirmation

The catalog is intentionally a research universe, not a claim that any
strategy is universally “best”. Each variant is ranked on the selected
symbol's own history and can be rejected by out-of-sample results.

## Exam protocol

The endpoint `GET /api/exam?symbol=...` runs an expanding/rolling,
event-by-event exam:

1. The first 20 bars form the initial visible history.
2. At each following date, only bars up to that date are visible to the
   strategy selector.
3. Historical labels are eligible only after their target date has passed.
4. The next 30 decisions are reported as the first evaluation segment.
5. The process continues in 30-bar segments through the available history.
6. A strategy ensemble votes at each date; realized return is attached only
   after the decision.
7. The complete exam artifact is stored under
   `runtime/learning/<symbol>/exams/`.

The response includes segment metrics, a strategy leaderboard, confidence,
selected strategies, indicators, and a leakage audit. It does not use
`future_return_5d` or `prediction_correct` in the decision feature payload.

## Research basis

The family selection follows common technical-analysis categories such as
moving averages, RSI, MACD, Bollinger bands, ATR, ADX/CCI/stochastics, channels
and volume studies. Fidelity's technical-analysis material lists these
indicator families and describes multi-panel price/volume/indicator analysis.
The QuantStart backtesting material is used for the engineering constraints:
chronological event processing, separate unseen evaluation data, rolling
statistics, transaction-cost awareness, and explicit avoidance of look-ahead,
survivorship and optimisation bias.

The implementation is intentionally conservative: it does not assert that
historical accuracy will persist, and it does not place orders.

## Sources consulted

- Fidelity, Technical Indicator Guide:
  `https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/overview`
- Fidelity, What is technical analysis?:
  `https://www.fidelity.com/learning-center/trading-investing/technical-analysis/what-is-technical-analysis`
- Fidelity, MACD:
  `https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/macd`
- Fidelity, RSI:
  `https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/RSI`
- Fidelity, Bollinger Bands:
  `https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/bollinger-bands`
- Fidelity, ATR:
  `https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/atr`
- Fidelity, Fast Stochastic:
  `https://www.fidelity.com/learning-center/trading-investing/technical-analysis/technical-indicator-guide/fast-stochastic`
- QuantStart, successful backtesting and look-ahead bias:
  `https://www.quantstart.com/articles/Successful-Backtesting-of-Algorithmic-Trading-Strategies-Part-I/`
