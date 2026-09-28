# Stage 8: frozen validation and trade diagnostics

The existing learner selects candidates using validation, then evaluates the frozen test with costs and a comparable buy-and-hold baseline. `backtest.audit` adds trade-level profit factor, expectancy, compounded drawdown, longest loss streak, recovery in trades, failure counts and an explicit count of bars that hit both target and stop. The existing conservative fill policy exits at the stop first on those ambiguous bars; a gap through the stop uses the opening price.

Each phase includes only trades decided and closed within that phase. A validation trade that closes in the frozen test is excluded. Sharpe and Sortino are per trade and require at least 10 closed trades; they are never labeled as annualized. Slippage remains `UNVERIFIED` because it is not separately measured; existing round-trip fees are disclosed. Frozen test gains cannot override a failed validation gate.
