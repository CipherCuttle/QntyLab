# Breadth V2: strategy-family catalog and preregistration

Status: `REGISTERED_NOT_EXECUTED`  
Registration ID: `QNTYLAB_BREADTH_V2_20260810`  
Registered date: `2026-08-10`  
Instrument: `BINANCE_USDM_PERPETUAL_USDT_V1`  
Research classification: exploratory only; no scientific validation, trading authority, paper/live trading, or promotion is introduced.

This document freezes the Breadth V2 research universe before any V2 strategy outcome is calculated. It is a family-level screen, not a search for the best individual tuple.

## 1. Reconciliation and hard boundaries

The canonical preflight was run with `python -m qntylab.research_ledger context`. At registration it reported 19 candidate variants, 378 completed trials, one active baseline, no follow-up candidates, and no trusted strategy edge. V1 findings remain prior evidence: slow trend variants were stronger during breadth exploration but failed the 2023 holdout; short-horizon reversal failed under tested costs; H003 24/96 is a baseline, not a validated edge; H007 remains blocked.

The V2 instrument is USD-M USDT perpetuals. V1 spot cells and V2 perpetual cells are never pooled as one experiment. V2 requires funding accounting for every position-bearing cell. No V2 strategy is executed by this registration.

The current worktree contains unrelated manifest and run-artifact changes. They are outside this registration and must not be included in the V2 commit.

## 2. Literature and mechanism adjudication

The following distinction is frozen for later interpretation:

| Family | Source-supported mechanism | Empirical precedent | QntyLab design inference | Unresolved |
|---|---|---|---|---|
| `TIME_SERIES_MOMENTUM` | Own past return sign can predict continuation over intermediate horizons. | Moskowitz, Ooi & Pedersen document time-series momentum across 58 liquid futures and partial longer-horizon reversal. | Retain as one price-only continuation family; horizons are a neighbourhood, not separate families. | Whether the effect survives this source-conditioned perp panel and funding costs. |
| `MOVING_AVERAGE_TREND` | Smoothed price state can represent delayed trend participation. | The V1 family is historical precedent; it is not treated as fresh evidence. | Keep as a price-overlay comparator and family anchor. | Whether its path is distinct from momentum and breakout after V2. |
| `PRICE_BREAKOUT` | New-high/new-low states can capture directional persistence and convex exit timing. | Breakout/trend-following is established systematic-manager and futures practice; V1 supplies local precedent. | Keep bounded and separate from MA because entry/exit path is event-triggered, not average-crossing. | Empirical return-path distinctness versus MA remains a V2 diagnostic. |
| `CROSS_SECTIONAL_MOMENTUM` | Relative winners may continue while common market movement is removed by ranking. | Jegadeesh & Titman establish winner-minus-loser momentum; Liu, Tsyvinski & Wu find market, size and momentum factors in crypto. | Add as a genuinely cross-sectional mechanism absent from the V1 price-overlay corpus. | Fixed-panel concentration, delistings, and common beta. |
| `CROSS_SECTIONAL_REVERSAL` | Relative losers may rebound after temporary price pressure or overreaction. | Cross-sectional reversal is a documented asset-pricing mechanism and has crypto-specific empirical precedent. | Add as a relative-value counter-mechanism; do not reuse V1 intraday reversal formulas. | Holding horizon and costs may erase the effect. |
| `FUNDING_CARRY` | Perpetual funding is a contract-level transfer related to perp/spot dislocation and positioning. | He, Manela, Ross & von Wachter model perpetual-futures funding and document persistent deviations; Schmeling, Schrimpf & Todorov study crypto carry. | Add one crypto-native, delta-neutral carry family, with realized settlements as accounting rather than a free signal. | Funding intervals, caps, basis risk, and whether data coverage is sufficient. |
| `VOLATILITY_TARGETING` | Position scale can change risk and drawdown without asserting volatility itself predicts returns. | Volatility scaling is a portfolio/risk-management transformation used in systematic futures research. | Test only as a controlled transformation of one frozen trend parent; benchmark is the unscaled parent. | It may improve risk metrics while reducing economic return; it is not an independent alpha claim. |

Primary references: [Moskowitz, Ooi & Pedersen, *Time Series Momentum*](https://pages.stern.nyu.edu/~lpederse/papers/TimeSeriesMomentum.pdf); [Jegadeesh & Titman, *Returns to Buying Winners and Selling Losers*](https://www.jstor.org/stable/2328882); [Liu, Tsyvinski & Wu, *Common Risk Factors in Cryptocurrency*](https://onlinelibrary.wiley.com/doi/10.1111/jofi.13119); [He et al., *Fundamentals of Perpetual Futures*](https://arxiv.org/abs/2212.06888); [Schmeling, Schrimpf & Todorov, *Crypto Carry*](https://doi.org/10.1287/mnsc.2024.05069); [Binance USDⓈ-M public developer documentation](https://developers.binance.com/docs/derivatives/usds-margined-futures/market-data/rest-api/Get-Funding-Rate-History).

Excluded from V2: order-book/liquidation/flow families (Tier C), social/news features (Tier C), ML/router/portfolio optimisation, and dynamic universe selection. Existing H007 funding-extremes, premium, and flow experiments are prior evidence and are not silently reopened as V2 results.

## 3. Frozen asset panel and exposure map

V2 uses the exact 20 identities from the previously frozen Jigsaw external cohort, selected by the historical Catalog-48 launch rule before its outcome. This is a hybrid in the sense that it reuses a fixed source-conditioned development cohort rather than pretending a new exchange-wide universe exists. No current listing, liquidity, return, V2 result, or missingness information may alter membership.

Panel, in canonical order:

`BCHUSDT, XRPUSDT, LTCUSDT, TRXUSDT, ETCUSDT, LINKUSDT, XLMUSDT, CHZUSDT, SANDUSDT, REEFUSDT, CHRUSDT, ALICEUSDT, ONEUSDT, API3USDT, GMTUSDT, APEUSDT, OPUSDT, INJUSDT, LDOUSDT, APTUSDT`

`ASSET_RESEARCH_EXPOSURE_MAP`:

- `PRIOR_JIGSAW_MEASUREMENT_EXPOSED`: all 20 V2 panel assets above. The source freeze explicitly excludes BTCUSDT, ETHUSDT, and SOLUSDT and has cohort digest `8a37866705efa5d68d80fb6770db49dbaba84c6e2c4848df6a406b885f0b5c1e`.
- `PRIOR_STRATEGY_EXPOSED`: BTCUSDT, ETHUSDT, SOLUSDT; contextual V1 anchors only, not V2 panel members.
- `IDENTITY_ONLY_EXPOSED`: none among the V2 panel.
- `OUTCOME_UNEXPOSED`: none claimed. The historical receipt records outcome exposure, so V2 development is explicitly not pristine OOS evidence.

The claim boundary is: results across the frozen Breadth V2 panel, under this source-conditioned identity and exposure map. No claim about the Binance perpetual universe is allowed. Missing observations are retained as missing; no replacement, backfill, survivorship filtering, or top-N ranking is allowed.

## 4. Periods, evaluation layers, and timing

Development windows are fixed before execution:

| ID | Start | End | Role | Exposure and limitation |
|---|---|---|---|---|
| `DEV_2022` | 2022-01-01 00:00Z | 2022-12-31 23:00Z | Stress/deleveraging and post-boom transition | Historically exposed in QntyLab research and Jigsaw context; development only. |
| `DEV_2024` | 2024-01-01 00:00Z | 2024-12-31 23:00Z | Recovery and expansion | Historically exposed; development only. |
| `DEV_2025` | 2025-01-01 00:00Z | 2025-12-31 23:00Z | Broad post-2024 market regime | Historically exposed through the frozen Jigsaw replication period; development only. |

No 2023 interval is called a fresh holdout. 2026 history is not used to manufacture a clean historical holdout.

The sealed evaluation layer is forward time: it starts at the first complete UTC hour after the registration commit and after all registered input contracts are materially available. It remains sealed until the development corpus is closed, the family decision record is written, and the minimum observation horizon is met: 2,160 complete hourly observations (90 days) for a family. The endpoint is fixed by calendar time, never moved retrospectively.

Prospective shadow begins only for a family that passes the sealed advancement rules. It uses the same exact family coordinates, frozen code and benchmark, append-only observations, no parameter or gate changes, and no automatic trading authority. Shadow is observation, not paper or live trading.

## 5. Family catalog and bounded variants

All formulas use information available by bar `t` to set the position for bar `t+1`. All families use the same 1h bar path, no interpolation, no forward fill, and no return across a source gap.

| Family | Tier | Benchmark / proposition | Frozen variants |
|---|---|---|---|
| `TIME_SERIES_MOMENTUM` | A | BUY_AND_HOLD primary; cash secondary. Market-timing overlay. | lookback `{72, 168, 336, 720}` hours; sign of close-to-close lookback return, long/flat. |
| `MOVING_AVERAGE_TREND` | A | BUY_AND_HOLD primary; cash secondary. Smoothed timing overlay. | `(fast, slow)` `{(12,48),(24,96),(72,288),(168,720)}`; long/flat when fast MA exceeds slow MA. |
| `PRICE_BREAKOUT` | A | BUY_AND_HOLD primary; cash secondary. Event-triggered timing overlay. | lookback `{72,168,336,720}` hours; long/flat on close above prior rolling high, exit below prior rolling low using the same lookback. |
| `CROSS_SECTIONAL_MOMENTUM` | A | FLAT primary; equal-weight long top quintile / short bottom quintile. Relative-value proposition. | ranking lookback `{24,72,168,336}` hours; fixed 20-asset panel; 20% tails; dollar-neutral gross exposure 2.0. |
| `CROSS_SECTIONAL_REVERSAL` | A | FLAT primary; equal-weight long bottom quintile / short top quintile. Relative-value proposition. | ranking lookback `{6,24,72,168}` hours; otherwise identical to cross-sectional momentum. |
| `FUNDING_CARRY` | B | FLAT primary; delta-neutral carry proposition. | trailing funding window `{8,24,72,168}` settlement events; cross-section long lowest realized funding / short highest realized funding, 20% tails, equal notional. No price-trend input. |
| `VOLATILITY_TARGETING` | A | H003 MA 24/96 unscaled parent primary; BUY_AND_HOLD secondary. Risk-transformation proposition. | realized-volatility window `{24,72,168,336}` hours; multiplier `clip(annualized target 25% / trailing RV, 0.25, 1.0)` applied to the frozen H003 24/96 long/flat signal. Target and clamps are fixed, not fitted. |

The three cross-sectional families are distinct by sign and economic proposition; their shared ranking mechanics are intentional, not extra families. Volatility targeting is not counted as an independent alpha source. No second parameter dimension is tested except the fixed 20% tail rule; there is no optimization around it.

## 6. Funding and data burden contract

Tier A uses the already-qualified Binance USD-M 1h OHLCV plus existing accounting. Tier B adds exactly one narrow source: realized Binance USD-M funding settlement events, materialized as `BINANCE_USDM_FUNDING_SETTLEMENT_MATERIALIZER_V0`. Tier C is deferred.

Funding is an economic cash flow, not a scenario knob. The materializer must preserve symbol, settlement timestamp, realized funding rate, source URL/archive identity, source checksum, and coverage/gap status. A position earns or pays the realized settlement only when the position was open at the settlement event under the preregistered event-time rule. Funding source gaps fail closed for the affected cell; they are not zero-filled. The materializer is a dependency to be built and verified before execution, not work performed by this registration.

## 7. Cost, metric, and benchmark contract

Two modes are registered:

- `BASELINE_EXECUTION`: 10 bps fee per one-way turnover and 0 bps slippage, plus realized funding.
- `STRESS_EXECUTION`: 10 bps fee per one-way turnover and 10 bps slippage, plus the same realized funding.

Funding is identical in both modes because it is incurred economics. No third cost mode is registered. Fee/slippage assumptions cannot be changed after outcomes are seen.

Common metrics are deliberately limited. Primary: net return and benchmark excess, reported at family aggregate and cell level. Robustness: annualized volatility, Sharpe-like return/volatility ratio, maximum drawdown, positive-cell breadth, temporal breadth, neighbour support, and cost delta. Descriptive: gross return, turnover, trade count, exposure fraction, fee cost, slippage cost, funding cost, and price/funding PnL decomposition. All paths and receipts are retained for later diagnostics.

## 8. Family-level advancement rule

No individual variant advances for being the best. A family is eligible for sealed evaluation only if all of these predeclared conditions hold:

1. All registered development cells that are usable under the missingness contract complete with valid receipts; no silent deletion of a losing or missing asset/period.
2. The family has positive stressed benchmark excess in at least 2 of 3 development windows and at least 10 of 20 assets in the pooled window-by-asset table, with no single asset contributing more than 35% of aggregate stressed excess.
3. At least two adjacent parameter variants show directionally compatible stressed benchmark excess and net-return behaviour. An isolated maximum fails neighbourhood support.
4. The family retains at least 50% of its stressed net-return advantage over the corresponding benchmark after costs, and turnover is compatible with the declared horizon.
5. No accounting, causality, provenance, gap, non-finite, or receipt-integrity failure remains unresolved.
6. For relative-value families, the long and short legs both contribute across at least 8 assets and the pooled beta/exposure diagnostic does not show a single-leg market substitute.

These are triage gates, not universal statistical laws. Failure graveyards the family for this screen; it does not authorise ad hoc variant replacement.

## 9. Multiplicity and budget

`registered_screen_id = QNTYLAB_BREADTH_V2_20260810`

- Families: 7
- Variants: 28 total (`4 + 4 + 4 + 4 + 4 + 4 + 4`, with the MA family’s four two-number coordinates counted as four variants)
- Assets: 20
- Development windows: 3
- Cost modes: 2
- Planned cells: `28 variants × 20 assets × 3 windows × 2 modes = 3,360`
- Registered denominator: 3,360 planned cells, before any later sealed or shadow layer

Every later result must carry the full denominator and may not delete losers, replace unavailable assets, or add coordinates. Exact duplicate trials require explicit replication intent. New candidate events must be appended to the canonical ledger before execution; this document alone does not authorize a strategy run.

## 10. Later diagnostic stack

The primary decision remains family breadth, cost survival, temporal repeatability, and sealed/future evidence. At most two secondary diagnostics are permitted after per-bar paths exist:

1. Hansen SPA over the full registered variant universe, using matched net benchmark-difference paths and dependence-aware resampling, only if the path contract is valid.
2. Deflated Sharpe Ratio as a descriptive multiple-testing diagnostic, using the registered 28-variant denominator and stated non-normality/serial-dependence assumptions.

No PBO, White test, FDR stack, or aggregate-summary pseudo-p-values is registered. Diagnostics cannot overturn integrity or family-breadth failures.

## 11. Hostile review and stop condition

Before any candidate proposal or strategy execution, one hostile reviewer must check: family duplication; outcome leakage; Jigsaw exposure disclosure; fixed panel/digest; window immutability; funding event-time accounting; benchmark semantics; cost completeness; denominator arithmetic; missingness; isolated-peak advancement; and the prohibition on implementation expansion into Tier C.

The reviewer may amend this document only before registration commit and before any V2 outcome. After commit, corrections are append-only amendments with a new digest and no retroactive result reinterpretation. Once the preregistration, exposure map, candidate proposal events, and funding dependency contract are committed, stop. Do not execute a strategy in this task.
