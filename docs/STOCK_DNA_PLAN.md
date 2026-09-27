# SMART Stock DNA / Historical Learning Plan

## Goal
For every symbol, evaluate the full available history from its first valid trading day to the latest day, while enforcing point-in-time rules: a date may only use information available on or before that date.

## Per-date engine
- Trend regime: bull / sideways / bear using price and SMA50/SMA200 alignment.
- Trend-following signal.
- Momentum/RSI signal.
- Volume confirmation / RVOL20.
- Regime-aware weights.
- Transparent SMART Score.

## Planned next layers
1. Price-action structure: HH/HL, LH/LL, breakouts and pullbacks.
2. Support/resistance and volatility-aware stops.
3. Smart-money / real-money-flow features from available TSETMC fields.
4. News timeline per symbol and point-in-time news sentiment/event tags.
5. Backtest outcomes at 1/3/5/10/20 trading days, MAE/MFE and risk-adjusted returns.
6. Per-symbol learning: estimate which strategy families work best for each symbol and regime.
7. Walk-forward validation so learned weights never leak future data.

## First stock
Palayesh (`پالایش`) is the first validation symbol. After the engine is connected to its GitHub history, run the full history from the first available date through the latest available date and produce a Stock DNA report before expanding to شلرد and عیار.

## Rule
Do not call a strategy "good" because it looks good on the same data used to tune it. Separate training, validation and walk-forward periods.
