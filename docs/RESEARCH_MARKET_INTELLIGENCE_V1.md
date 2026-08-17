# SMART Iran Market Intelligence v1 — Research & Implementation

## Research conclusion

A broad review of research on Tehran Stock Exchange and general market microstructure supports a layered approach rather than blindly increasing the number of technical indicators.

Key findings:
- TSE studies support using volume, turnover, return volatility and liquidity measures as distinct information, not as one generic indicator.
- Research on TSE and limit-order books supports order-book imbalance / order-flow features for short-horizon direction prediction when historical depth data is available.
- Persian news/social sentiment has shown incremental value for TSE forecasting, especially when combined with quantitative/technical inputs; news appears more useful at short horizons while social sentiment can add value at longer horizons.
- TSE-specific structural constraints (low liquidity, price limits, queues and one-sided trading) make generic deep-learning assumptions risky; model complexity must be controlled and evaluated OOS.
- Research comparing ML/DL on TSE data supports tree ensembles and LSTM-family models as candidates, but no model is accepted without point-in-time validation.

## What is implemented now

The current Git history reliably contains daily OHLC/close, volume, trade value and trade count. Therefore v1 implements:
1. price/trend and multi-horizon returns
2. SMA/EMA distance and slope
3. volume acceleration / relative volume
4. trade value acceleration
5. trade-count acceleration
6. volatility
7. Amihud-like illiquidity proxy
8. intraday range / close-location features
9. empirical price-limit proximity (learned from rolling return distribution rather than assuming a fixed historical limit)
10. bull/bear/sideways and volatility regime features

The model has two heads:
- Direction classifier: next-day return > 0
- Magnitude regressor: next-day return

Candidate models are HistGradientBoosting variants. Selection is made only on the validation period, then the selected model is retrained on train+validation and evaluated once on frozen OOS.

## Deliberately NOT fabricated

Historical Git files do not contain point-in-time order-book depth/queue, حقیقی/حقوقی flow, or Persian news/social sentiment for the full sample. These are excluded rather than reconstructed from future or incomplete data.

When historical feeds for those layers are available, they should be added as separate feature families and tested incrementally against this v1 baseline.

## Why this architecture

The objective is to predict two economically different quantities: direction and magnitude. Direction alone can look strong while expected return is too small to cover trading costs. Magnitude alone can have low MAE while getting direction wrong. The two-head design keeps these objectives visible and separately testable.

## Research sources

- Jahangiri & Corazza (2026), *Sentiment-based stock price prediction in developing countries: Evidence from Iran* — Persian news/social sentiment and combination with technical indicators.
- Mehrkian & Davari-Ardakani (2025), *An integrated model of sentiment analysis and quantitative index data for predicting stock market trends: A case study of Tehran Stock Exchange* — sentiment + quantitative data and deep models.
- Sarmadi et al. (2020), *Deep Learning for Stock Market Prediction* — TSE groups, technical indicators and comparison of ML/DL methods.
- Fathi et al. (2020), *Analysing the effect of trading characteristics on liquidity measures — evidences from Tehran Stock Exchange* — liquidity, turnover, volume, volatility and zero-return measures.
- Qureshi (2018/2019), *Investigating Limit Order Book Features for Short-Term Price Prediction* — order-book features and short-horizon prediction.
- Kolm, Turiel & Westray (2023), *Deep order flow imbalance* — stationary order-flow features and multi-horizon short-term forecasting.

## Test protocol

Compare v1 against:
- Naive baseline
- SMART daily-prediction baseline
- Custom MACD/RSI/Ichimoku/Bollinger/MA
- 200-feature full-pairwise ensemble
- E00280 / best historical ensemble candidate

Required metrics:
- MAE
- Direction Accuracy
- Mean Absolute Move Error
- Beats Naive
- regime breakdown
- frozen OOS
- transaction-cost-aware trading test in the next layer

No claim of production readiness is allowed from prediction metrics alone.

Implementation status: code committed; GitHub Actions test is the source of truth for final numeric results.
