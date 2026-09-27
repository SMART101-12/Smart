# SMART Project State — 2026-08-17

## 1. Mission
SMART is a research-grade decision-support engine for Iran's stock market. The target is a daily, testable pipeline that eventually produces direction/price-range forecasts and, only after forecast validation, Entry/Stop/Target/Exit decisions.

The project is evidence-first: a model is promoted only when reproducible tests show improvement over simple baselines on untouched data.

## 2. Non-negotiable rules
- Historical price inputs for experiments come from Git-versioned SMART data. Do not silently substitute outside price data when validating a Git-based experiment.
- No look-ahead, leakage, survivor bias, or tuning on the final OOS window.
- Signal day and executable entry day must be aligned correctly.
- Non-trading dates must not be treated as missing trading sessions.
- Thursday/Friday and official closures must be handled by a market-type/symbol-aware trading calendar.
- Iranian market types differ: ordinary exchange sessions and gold funds have different trading hours.
- Every material model/data change gets a version/experiment record and a Git commit.
- Failed experiments stay in history.
- Win rate alone is never sufficient.
- A complex model must demonstrate measurable OOS value over Naive before promotion.
- A 99% accuracy target is not a requirement and must never be achieved through leakage/overfit.

## 3. Data architecture
The project has:
- `runtime/history/` for Git-versioned market history.
- `runtime/data_quality/` for data-quality outputs.
- `runtime/experiments/` for reproducible experiment artifacts.
- `runtime/result.json` and `runtime/command.json` as runtime transport/reporting artifacts.
- Local SQLite/raw snapshots are used by the Windows command agent; Git remains the historical experiment source when the experiment is defined that way.

The command bridge is explicit and allow-listed:
ChatGPT -> `runtime/command.json` -> local Windows SMART command agent -> TSETMC through the user's Iranian connection -> local DB/raw snapshot -> `runtime/result.json`.
It does not execute arbitrary shell commands.

## 4. Data-quality/calendar decisions
- Start walk-forward testing from the earliest valid trading record available in Git for each symbol.
- Remove only confirmed non-trading dates from the analytical sequence.
- A date that is merely missing from the data is not automatically a holiday; it must be classified as holiday, market closure, symbol halt, data miss, or other valid state.
- Once a closure is confirmed for one market-wide date, the same market-wide closure applies to the relevant symbols.
- Symbol-specific halts remain symbol-specific.
- Calendar logic must understand at least ordinary stock-market hours and gold-fund hours.

## 5. Learning loop
The canonical loop is:
Observe -> Predict -> Record -> Reveal Actual -> Diagnose Error -> Learn -> Next Day

For each trading date, the system should persist:
symbol, date, current price, predicted next close, predicted return, predicted direction, predicted high/low range, confidence, market regime, stock regime, feature snapshot, engine version, model/weight version, rationale, realized outcome, error classification, and learning update.

Horizons 1, 3 and 5 sessions are recorded. The 5-session path is for trajectory analysis and must not leak future information into intermediate forecasts.

## 6. Baselines and model history
Minimum baselines:
- Naive: tomorrow = today
- simple momentum/previous-return baseline
- Buy & Hold for investment comparison

`daily-prediction-v1.0` used Naive, SMA20, EMA20, Momentum5 and Trend20 with online exponential error penalties.

The Palayesh validation run was rejected:
- Coverage: 2020-08-26 to 2026-08-15
- Rows: 1,425
- Walk-forward predictions: 1,394
- Direction accuracy: 50.7174%
- Model MAE: 1.8333%
- Naive MAE: 1.8115%
- Share beating Naive: 49.5349%
- Final weights: Naive 69.7773%, Momentum5 8.0923%, Trend20 22.1304%; SMA20/EMA20 effectively eliminated.

Conclusion: online learning with this expert set does not add predictive value; reject as production model.

## 7. Current research direction
The project has moved beyond the rejected v1 toward:
- Ichimoku
- roughly 200 indicator variants
- single, pairwise and triple combinations
- small ensembles
- model-of-models
- regime-conditioned models
- Walk-Forward
- frozen OOS
- positive and negative learning memory
- research-driven Market Intelligence features

A 2026-08-17 comparison records:
- Market Intelligence v1 OOS 221: MAE 1.8915%, Direction Accuracy 67.8733%, HGB-conservative.
- Ensemble v2.0 E080: MAE 1.3775%, Direction Accuracy 53.52%, OOS 213.
- Ensemble v2.1 full pairwise E00280: MAE 1.5722%, Direction Accuracy 64.06%, OOS 256.

Interpretation: Market Intelligence v1 currently has the strongest direction accuracy among these candidates, but worse magnitude error than E080/E00280; it is promising, not promoted as a replacement. Split construction/sample sizes differ, so this is directional evidence rather than a formal league table.

Missing historical layers that must not be faked:
- point-in-time order-book depth/queue
- real retail/institutional flow
- historical Persian news/social sentiment
These require genuine historical ingestion before testing.

## 8. Model-selection metrics
Forecast: MAE, RMSE, MAPE with caution, Direction Accuracy, directional precision/recall where sample size permits, range coverage, confidence calibration.

Trading: Profit Factor, Expectancy, total return/CAGR, Max Drawdown, Sharpe/Sortino where appropriate, average win/loss, MFE/MAE, turnover, trade count.

Robustness: OOS stability, regime stability, window stability, parameter sensitivity, complexity penalty.

## 9. Walk-forward contract
For every window:
Train -> Validate -> Freeze -> Test

Model selection happens only on Train/Validation. Test is untouched for final evaluation of that window. Once the window is completed and the outcome is known, realized information may enter future learning memory.

## 10. Error taxonomy
At minimum: regime, trend, momentum, volume, smart-money, breakout failure, false reversal, volatility, data/calendar, execution/entry, exit/target.

The system must learn from failures as well as successes.

## 11. Entry/Exit stage
Entry/Stop/Target/Exit simulation is downstream of forecast validation. It must use executable next-session prices and include transaction costs/slippage assumptions when trading evaluation is introduced.

## 12. Current Git/repository state
Repository: `SMART101-12/Smart`
Default branch: `main`.

Important existing specifications include:
- `docs/AI_HANDOFF.md`
- `docs/SMART_MASTER_ROADMAP.md`
- `docs/DAILY_PREDICTION_LEARNING.md`
- `docs/FINAL_MODEL_ROADMAP.md`
- `docs/EXPERIMENT_RESULTS.md`
- `docs/MODEL_COMPARISON_2026-08-17.md`
- `SMART_COMMAND_BRIDGE.md`

Recent Git activity on 2026-08-17 includes Market Intelligence implementation, experiment execution, result persistence, and comparison recording.

## 13. User's operating expectation
The project should evolve daily, with every test and conclusion written to Git. The AI must read the current Git state before continuing, avoid re-asking settled questions, and treat Git artifacts as the source of project truth.

## 14. Immediate next priorities
1. Preserve the current Market Intelligence comparison as a non-promoted research result.
2. Build the isolated `AI_TRAINING/` section so a new AI can understand SMART logic before changing code.
3. Continue the data-entry expansion by sector, beginning with the Basic Metals group, with the same data-quality/calendar rules.
4. Run the next model experiment only with frozen OOS and baseline comparison.
5. Add transaction-cost-aware evaluation before promoting a trading strategy.
6. Keep a daily project-state/handoff record in Git.

## 15. Continuation instruction for any AI
Before making changes:
1. Read `AI_TRAINING/README.md` and `AI_TRAINING/SMART_LOGIC.md`.
2. Read `docs/AI_HANDOFF.md`, `docs/SMART_MASTER_ROADMAP.md`, and the latest experiment/comparison files.
3. Inspect the latest commits and runtime artifacts.
4. Identify what is proven, rejected, pending, and missing.
5. Never overwrite history to make a model look better.
6. Implement one controlled change, run the appropriate tests/experiment, record metrics, and only then decide Promote/Reject/Hold.
