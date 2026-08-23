# SMART AI TRAINING — Gold ETF Knowledge Base

**Document ID:** GOLD-ETF-KB-001  
**Version:** 1.0  
**Created:** 2026-08-23  
**Scope:** Iranian gold ETF research and decision logic  
**Status:** PENDING / research knowledge — not a production trading rule yet

## 1. Purpose

This document is persistent training memory for future SMART AI sessions. It records the current reasoning, observations, hypotheses, and candidate scoring framework for comparing Iranian gold ETFs. Future AI instances must read this document before repeating the analysis and must append dated updates rather than silently replacing previous conclusions.

The objective is to move from a single-fund analysis (e.g. AYAR) to a cross-fund relative-value and trading framework.

## 2. Current candidate ranking (2026-08-23 research snapshot)

Candidate ranking from the current research, using a combined judgment of trend/momentum, premium/discount to NAV, liquidity, gold-bar vs coin exposure, historical returns, and money-flow/order-book quality:

1. **GANJ** — preferred current value candidate; high bar exposure, low/negative premium, strong multi-period performance.
2. **TALA** — preferred liquidity candidate; very deep market and low/negative premium, but much more coin exposure.
3. **KAHROBA** — balanced candidate; strong liquidity, low/negative premium, relatively high bar exposure.
4. **ZARVAN** — bar-focused, low/negative premium; attractive for direct gold exposure, but lower liquidity than the largest funds.
5. **AYAR** — strongest trading candidate and very liquid, but entry timing matters because its premium can become positive and elevated.
6. **MESGHAL** — good but with less relative advantage in the current snapshot.
7. **NAFIS** — acceptable candidate, but no decisive current edge over the top group.
8. **EMERALD** — good momentum, but shorter/less established evidence relative to the leading candidates.

**Important:** This ranking is a research hypothesis, not a proven predictive ranking. It must be re-tested with historical data before being promoted to production.

## 3. Snapshot metrics captured during research

Approximate current comparison used in the 2026-08-23 analysis:

| Fund | 1M return | 3M return | 6M return | 1Y return | Current total premium/discount | Research role |
|---|---:|---:|---:|---:|---:|---|
| GANJ | 7.48% | 5.35% | 6.52% | 157.17% | -1.1% | Value / bar-focused |
| TALA | 7.27% | 5.19% | 4.83% | 153.51% | -1.1% | Liquidity |
| KAHROBA | 7.25% | 5.18% | 4.84% | 153.77% | -1.2% | Balanced |
| AYAR | 7.09% | 6.37% | 5.93% | 159.74% | +1.9% | Trading / momentum |
| ZARVAN | 6.92% | 4.10% | 6.16% | 155.23% | -1.6% | Bar-focused / low premium |
| MESGHAL | 6.79% | 4.73% | 4.26% | 153.37% | -1.3% | Secondary |
| EMERALD | 7.64% | 4.47% | 5.31% | 151.71% | -1.6% | Momentum |
| NAFIS | 7.17% | 4.27% | 5.21% | 152.28% | -1.5% | Secondary |

These values are a dated research snapshot. They must not be treated as live values after the snapshot date.

## 4. Structural observations

### GANJ
- Research conclusion: strongest current combination of return, low/negative premium, and gold-bar exposure.
- Reported bar exposure in the research snapshot: about 99.5%.
- Main hypothesis: useful when the goal is to track gold itself rather than coin-specific premium.

### TALA
- Research conclusion: strongest liquidity-oriented candidate.
- Reported structure: roughly 85.6% coin and 14.3% bar in the cited snapshot.
- Main hypothesis: suitable when execution/liquidity is more important than minimizing coin exposure.

### KAHROBA
- Research conclusion: strong balance between liquidity, low premium, and bar exposure.
- Reported structure: roughly 83.8% bar and 15.9% coin in the cited snapshot.
- Main hypothesis: useful middle ground between TALA and the highly bar-focused funds.

### ZARVAN
- Research conclusion: attractive bar-focused alternative with negative premium.
- Reported structure: approximately 100% bar in the cited snapshot.
- Main limitation: lower liquidity than AYAR/TALA/KAHROBA.

### AYAR
- Research conclusion: best treated as a trading instrument in addition to a long-term gold exposure instrument.
- Recent snapshot showed strong momentum, high turnover, positive real-money flow, but also positive premium to NAV and occasional heavy sell-side walls.
- A fund can have strong trend while still being a poor immediate entry because premium/order-book conditions are unfavorable.

## 5. AYAR case study — persistent reasoning

Recent AYAR snapshots demonstrated why SMART must separate five concepts:

1. **Trend:** price can be strongly bullish.
2. **NAV value:** price can still be close to fair asset value.
3. **Premium:** a positive premium can increase downside if it compresses.
4. **Order book:** visible bid/ask imbalance can change within minutes.
5. **Real-money flow:** positive net flow does not necessarily mean buyers have stronger average size.

Example research snapshot:
- Price around 595,401 IRR-equivalent market quote.
- NAV redemption around 575,280.
- Premium around 3.5%.
- Daily change around +7.6%.
- Volume around 135.48M units.
- Five-level order-book calculation gave approximately 24,986 bid units vs 12,880 ask units, or bid/ask ≈ 1.94x.
- At the same time, reported real-person buying power was about 0.70, showing why order-book strength and real-person average buying strength must not be conflated.

Later snapshot showed AYAR around 590,993 while gold-18k was around 21.31M toman, producing a simple market ratio of approximately 0.002772. This was close to the earlier NAV-derived base ratio of about 0.002778.

**Learning:** AYAR was not necessarily expensive relative to gold merely because its price rose. The key question is whether its premium/order-book conditions justify the entry price.

## 6. Candidate gold-18k -> ETF conversion model

A first-pass empirical ratio was derived from AYAR observations:

- **Base/NAV coefficient K0 ≈ 0.002778**
- **Market coefficient at roughly 3.5% premium K3.5 ≈ 0.002875**

First-pass equations:

`AYAR_Fair_NAV ≈ Gold18_Rial × 0.002778`

`AYAR_Market_at_3.5%_premium ≈ Gold18_Rial × 0.002875`

The later snapshot produced an observed coefficient near **0.002772**, showing that the base relationship remained close in that observation.

**Warning:** These coefficients are NOT proven constants. They are candidate features/priors. SMART must estimate time-varying coefficients from historical validated data and separate the effects of gold-18k, USD/IRR, global gold, NAV, and ETF premium.

## 7. Proposed SMART Gold ETF Score

Candidate score for future research:

- 30% trend and momentum
- 20% premium/discount to NAV
- 15% relative value vs gold-18k
- 10% relative value vs global gold × USD/IRR
- 10% real-person net money flow
- 10% real-person buying power
- 5% liquidity/execution quality

The score should be normalized across all active gold ETFs on the same timestamp.

Suggested output labels:

- **BUY:** score >= 80, subject to risk/entry gates
- **WATCH:** 65–79
- **HOLD:** 50–64
- **SELL/AVOID:** <50

These thresholds are hypotheses and MUST NOT be promoted until backtested.

## 8. Relative-value logic

The future engine should not ask only "which fund has the highest return?" It should ask:

`Which ETF gives the best expected exposure to gold at the lowest unjustified premium and acceptable execution risk?`

For every fund calculate:

`Premium = MarketPrice / NAV - 1`

`Gold18Ratio = MarketPrice / Gold18Price`

`RelativePremium = ActualPremium - HistoricalMedianPremium`

`Momentum = multi-horizon normalized return`

`LiquidityScore = normalized turnover + depth + spread`

`FlowScore = normalized net real-person flow + buying-power quality`

Then compare every fund against the cross-sectional median and its own history.

## 9. Decision rules to test

### Value entry
Prefer funds where:
- premium is below their own historical median;
- price is not extended versus gold-18k and NAV;
- liquidity is adequate;
- trend is not structurally broken.

### Momentum entry
Prefer funds where:
- resistance breaks with increasing volume;
- sell-side depth is absorbed rather than merely moved;
- price remains supported above short-term VWAP/structure;
- premium expansion is not excessive.

### Avoid chasing
Avoid new entries when:
- daily return is already extreme;
- premium is materially above historical normal;
- sell-side wall is increasing;
- real-person buying power deteriorates;
- gold-18k or USD/IRR does not confirm the move.

## 10. What is PROVEN / PENDING / MISSING

### PROVEN
- Gold ETFs should be compared cross-sectionally rather than by return alone.
- NAV premium matters for entry quality.
- AYAR order-book strength and real-person buying power can diverge.
- Gold-18k can provide a useful reference for ETF relative value.
- Historical failures/observations must remain in AI training memory.

### PENDING
- The ranking above.
- The proposed 100-point score.
- The coefficient 0.002778 as a stable AYAR base coefficient.
- The proposed score thresholds.
- Claims that GANJ is always the best value fund.

### MISSING
- A validated historical daily dataset for every active gold ETF with synchronized NAV, price, volume, spread, order-book snapshots, real-person flow, gold-18k, USD/IRR, and global gold.
- Walk-forward tests of the score.
- Out-of-sample comparison against simple baselines.
- Historical premium distributions for each fund.

## 11. Learning protocol for future AI

When new gold-ETF data arrives:

1. Never overwrite this document's historical observations.
2. Add a dated section with the new snapshot.
3. Recalculate the same metrics for all comparable funds.
4. Compare the new result with the previous hypothesis.
5. Mark the hypothesis **CONFIRMED**, **WEAKENED**, or **REJECTED** only after sufficient repeated observations.
6. If a scoring rule changes, record old vs new weights and the reason.
7. If a backtest is performed, store the experiment artifact under `docs/` or `runtime/experiments/` and link it from this document.
8. Never train on future information or use the test period to tune weights.
9. Promote a rule to production only after reproducible out-of-sample evidence.

## 12. Source discipline

This document is a research memory layer. Live market numbers must always be re-fetched when making a current decision. Historical observations from this document should be treated as dated evidence, not current prices.

External snapshot sources used during the initial research included Fundbase/Tindex and market-data reports. The next implementation step is to replace manually copied snapshots with SMART's validated market-data pipeline.

## 13. Next controlled experiment

Build a **Gold ETF Cross-Sectional Benchmark v1** using synchronized daily observations for AYAR, GANJ, TALA, KAHROBA, ZARVAN, MESGHAL, NAFIS, EMERALD and all other active ETFs with sufficient history.

Baseline models:
- equal-weight ETF ranking by 1M return;
- lowest premium-to-NAV;
- gold-18k-only fair-value deviation;
- proposed SMART Gold ETF Score.

Acceptance metrics:
- forward 1D/5D/20D return;
- MAE/MAPE for fair-value estimates;
- maximum drawdown;
- turnover;
- hit rate only as a secondary metric;
- performance vs baselines.

**Promotion gate:** the proposed score must beat the relevant simple baseline out-of-sample after costs and without look-ahead bias.
