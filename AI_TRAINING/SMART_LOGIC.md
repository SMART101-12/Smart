# SMART LOGIC — Teaching Specification for AI

## 1. What SMART is
SMART is a research system for the Iranian equity market. Its job is to transform versioned market observations into daily predictions, measure what actually happened, learn from the error, and improve through controlled out-of-sample experiments.

It is not allowed to become a black-box score generator.

## 2. Information boundary
For a decision made on trading date T, only information available by the end of T may be used. The T+1 outcome is hidden until after the prediction has been persisted.

Correct:
`history <= T -> features(T) -> prediction(T+1) -> save prediction -> reveal T+1 -> measure error -> learn`

Incorrect:
`history <= T+1 -> features(T) -> prediction(T+1)`

## 3. Data hierarchy
1. Git-versioned historical data is the source of truth for Git-defined experiments.
2. Local SMART runtime may collect current Iranian market data through the command bridge.
3. Raw snapshots and SQLite are evidence for the collection layer; they do not silently rewrite historical experiment inputs.
4. Every record needs provenance and data-quality status.

## 4. Trading calendar logic
A missing date is a question, not a fact.

The AI must distinguish:
- official market holiday
- market-wide closure
- symbol-specific halt
- missing data
- delayed ingestion
- bad record

Ordinary stock-market sessions and gold-fund sessions are different market types and must not share blindly assumed hours.

## 5. Prediction contract
Each prediction should contain at least:
- symbol
- trading date
- current price
- predicted next close
- predicted return
- predicted direction
- predicted high/low range
- confidence
- market regime
- stock regime
- feature snapshot
- engine/model/weight version
- rationale

For 1/3/5-session horizons, the prediction for each horizon must be generated using only information available at the prediction date.

## 6. Baseline-first thinking
Before claiming a new feature helps, compare against:
- Naive next-close
- simple momentum/previous-return baseline
- Buy & Hold where investment performance is relevant

If a complicated model does not beat Naive on a fair OOS test, reject or hold it.

## 7. Model research ladder
Use the smallest useful experiment first:
1. baseline
2. single indicator/feature
3. pairwise combinations
4. triple combinations
5. small ensembles
6. model-of-models
7. regime-conditioned ensembles
8. frozen OOS

With roughly 200 indicator variants, exhaustive pairwise search is large and must be cached/parallelized and persisted immutably.

## 8. Feature families
Current research families include:
- Trend
- Moving Average
- Momentum
- Oscillator
- Volatility
- Volume
- Money Flow
- Price Action
- Breakout
- Support/Resistance
- Ichimoku
- Regime

Ichimoku must be time-aligned correctly. A forward-plotted span must never become a hidden future feature.

## 9. Learning memory
Store both success and failure.

Each experiment record should identify:
experiment_id, engine_version, parent_model, symbol, feature_set, parameters, train/validation/test dates, metrics, baseline metrics, regime, decision, reason, and error taxonomy.

A failure is valuable if it prevents the AI from repeating the same experiment without a new hypothesis.

## 10. Walk-forward
Every model-selection window follows:
`Train -> Validate -> Freeze -> Test`

The final test slice is not a tuning playground. Once the test result is revealed, that result can inform future windows, not retroactive parameter selection.

## 11. Error-driven improvement
When a prediction fails, classify the reason before changing the model. Examples:
- regime mismatch
- trend reversal
- momentum failure
- volume confirmation failure
- smart-money hypothesis failure
- breakout failure
- false reversal
- volatility shock
- calendar/data issue
- execution/entry mismatch
- exit/target mismatch

The next experiment should target the largest recurring and economically meaningful error only when the proposed fix can be tested without leakage.

## 12. Trading strategy comes later
Forecast validation comes before Entry/Stop/Target/Exit optimization. When trading simulation is introduced:
- entry must be executable on the correct next session
- signal/entry dates must never be mixed
- transaction costs and slippage must be explicit
- drawdown and expectancy matter
- a high hit rate with poor payoff is not a successful strategy

## 13. Current evidence
Palayesh `daily-prediction-v1.0` is rejected. Its historical walk-forward test did not beat Naive.

Market Intelligence v1 is promising for direction but not yet a replacement for the strongest historical ensembles because its magnitude error is worse. Its OOS comparison is directional evidence only because sample sizes and split construction differ.

## 14. Missing evidence
Do not invent historical versions of:
- order-book depth/queue
- حقیقی/حقوقی flow
- Persian news/social sentiment

If these are required, create a real historical ingestion layer first, validate provenance, then test.

## 15. AI decision discipline
Before modifying code, the AI must answer internally:
1. What is already proven?
2. What is rejected?
3. What is merely proposed?
4. What evidence is missing?
5. What is the smallest controlled experiment that can resolve the next uncertainty?

After the experiment:
- save metrics
- compare with baseline
- classify errors
- record Promote/Reject/Hold
- update the project state
- commit the result

Never optimize for a prettier report. Optimize for reproducible evidence.
