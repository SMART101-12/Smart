# Stage 7: conditional setup and risk

`setup` adds the lifecycle `NO_SETUP`, `WATCH`, `SETUP_FORMING`, `CONFIRMED`, or `INVALIDATED` to the existing `entry_exit` contract. The plan is confirmed only when a fresh valid daily bar, ready price/volume breakout, non-adverse market and industry, dated individual inflow, and accepted model validation agree. Otherwise a possible entry/stop/two targets are marked `hypothetical`; the `confirmed_plan` stays null. Missing historical index/industry data therefore prevents confirmed current orders while still exposing conditional research levels.

The section reports source date, seven calendar day expiry, ATR percentage, stop risk and reward/risk ratios with formulas `(entry-stop)/entry` and `(target-entry)/(entry-stop)`. Liquidity and gap execution risks remain `UNVERIFIED` without measured data. The previous entry/exit representation stays readable in old reports.
