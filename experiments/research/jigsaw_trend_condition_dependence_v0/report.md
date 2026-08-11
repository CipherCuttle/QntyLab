# JIGSAW — Trend Condition Dependence V0

RESEARCH_STATUS: RETROSPECTIVE_EXPLORATORY  
JIGSAW_PIECE_TYPE: CONDITION_DEPENDENCE  
AUTHORITY: NON_AUTHORITATIVE  
PROMOTION_ELIGIBLE: NO  
PIT_UNIVERSE_CLAIM: NONE  
ROUTER_AUTHORITY: NONE

## New proposition

This does not assert that H003 24/96 has validated excess return or alpha. It asks only whether the realized 24-hour net utility of the fixed process relative to FLAT=0 varies with three predeclared, point-in-time market states. The label is MEASUREMENT_STRATEGY_UTILITY, not GATED_STRATEGY_UTILITY; no gate-transition cost is claimed.

## Repository / evidence reconciliation

Clean isolated worktree base: `b9af95d6b8b5de631cfea4211dded608d3383714` (`origin/master` at reconciliation); local dirty worktree was not altered. Focused-trend holdout review digest: `d1ab443d4caecacfc84ae2af4a964626100f3501d74a03700e010fab44476ac5`; focused specification digest: `d5221566f2e368654e10b25402ba3b6a1c6ffd9c181be30dd263f91f6b882d6d`; curated breadth review digest: `97a9a88998ffa3e4e1c490d00e7cba6ba3bb71a13027f92903ec0ef8745afacc`. The earlier plan registered matched-bar position/return correlation, disagreement, concurrent drawdown, and forward paper-shadow tracks; the holdout review explicitly records them as not tested, and this experiment does not execute them. Router Headroom Sanity V0 was read only as contextual evidence and remains semantically independent.

## Data / path verdict

The longest common contiguous existing hourly path is 2023-03-24T14:00:00Z through 2026-07-28T18:00:00Z (29333 hours). After the 720-hour state construction, 365 prior daily state observations, 00:00 UTC grid, and one 24-hour forward label, the usable sample is 2024-04-23T00:00:00Z through 2026-07-27T00:00:00Z (826 non-overlapping daily decisions). Gaps are not filled or bridged; other segments are unavailable opportunities.

## State distributions and redundancy

- MARKET_DRAWDOWN_30D: n=826, mean=-0.11360245, median=-0.09929493.
- MARKET_RV_7D: n=826, mean=0.00613459, median=0.00575190.
- MARKET_CORR_7D: n=826, mean=0.80769837, median=0.82182278.
- contemporaneous MARKET_DRAWDOWN_30D__MARKET_RV_7D: -0.488652 (descriptive only).
- contemporaneous MARKET_DRAWDOWN_30D__MARKET_CORR_7D: -0.372405 (descriptive only).
- contemporaneous MARKET_RV_7D__MARKET_CORR_7D: 0.084457 (descriptive only).

## Primary conditional results

Each table reports equal-weight three-asset daily utility; assets are not treated as independent rows.

### MARKET_DRAWDOWN_30D

| cost | LOW mean / median / positive / n | MID mean / median / positive / n | HIGH mean / median / positive / n | high-low mean | high-low positive |
|---|---:|---:|---:|---:|
| BASELINE | -0.0014859 / 0.0000000 / 0.272 / 327 | 0.0004102 / 0.0000000 / 0.337 / 252 | 0.0008404 / 0.0000000 / 0.490 / 247 | 0.0023263 | 0.218 |
| STRESS | -0.0018217 / 0.0000000 / 0.254 / 327 | 0.0000763 / 0.0000000 / 0.313 / 252 | 0.0005481 / 0.0000000 / 0.482 / 247 | 0.0023699 | 0.228 |

### MARKET_RV_7D

| cost | LOW mean / median / positive / n | MID mean / median / positive / n | HIGH mean / median / positive / n | high-low mean | high-low positive |
|---|---:|---:|---:|---:|
| BASELINE | 0.0011960 / 0.0000000 / 0.389 / 316 | -0.0008203 / 0.0000000 / 0.333 / 276 | -0.0013952 / 0.0000000 / 0.342 / 234 | -0.0025912 | -0.047 |
| STRESS | 0.0009089 / 0.0000000 / 0.377 / 316 | -0.0011581 / 0.0000000 / 0.319 / 276 | -0.0017464 / 0.0000000 / 0.316 / 234 | -0.0026553 | -0.060 |

### MARKET_CORR_7D

| cost | LOW mean / median / positive / n | MID mean / median / positive / n | HIGH mean / median / positive / n | high-low mean | high-low positive |
|---|---:|---:|---:|---:|
| BASELINE | -0.0030125 / -0.0000347 / 0.347 / 170 | 0.0008056 / 0.0000000 / 0.381 / 231 | 0.0003554 / 0.0000000 / 0.348 / 425 | 0.0033679 | 0.001 |
| STRESS | -0.0033514 / -0.0004512 / 0.324 / 170 | 0.0005001 / 0.0000000 / 0.372 / 231 | 0.0000309 / 0.0000000 / 0.329 / 425 | 0.0033823 | 0.006 |

## Temporal replication

Signed high-minus-low mean contrasts under STRESS; LEAVE_2024_OUT is mandatory.
- MARKET_DRAWDOWN_30D: 2024=0.0036398, 2025=0.0024401, 2026=0.0011649, LEAVE_2024_OUT=0.0017751
- MARKET_RV_7D: 2024=-0.0016047, 2025=-0.0061732, 2026=0.0015219, LEAVE_2024_OUT=-0.0033813
- MARKET_CORR_7D: 2024=0.0052648, 2025=0.0045545, 2026=-0.0050868, LEAVE_2024_OUT=0.0025970

## Cross-asset replication

Signed STRESS contrasts, descriptive only.
- MARKET_DRAWDOWN_30D: BTCUSDT=0.0004925, ETHUSDT=0.0052346, SOLUSDT=0.0013825, LEAVE_BTC_OUT=0.0033086, LEAVE_ETH_OUT=0.0009375, LEAVE_SOL_OUT=0.0028635
- MARKET_RV_7D: BTCUSDT=-0.0011625, ETHUSDT=-0.0042970, SOLUSDT=-0.0025064, LEAVE_BTC_OUT=-0.0034017, LEAVE_ETH_OUT=-0.0018344, LEAVE_SOL_OUT=-0.0027297
- MARKET_CORR_7D: BTCUSDT=0.0020491, ETHUSDT=0.0026826, SOLUSDT=0.0054151, LEAVE_BTC_OUT=0.0040488, LEAVE_ETH_OUT=0.0037321, LEAVE_SOL_OUT=0.0023659

## Cost and tail / concentration attacks
- MARKET_DRAWDOWN_30D: COST_ROBUST; STRESS full=0.0023699, five-best-removed=0.0016331; year contributions={'2024': 0.0036397903166622554, '2025': 0.002440123709891464, '2026': 0.0011649204998235053}; asset contrasts={'BTCUSDT': 0.0004924679702399488, 'ETHUSDT': 0.005234600374534245, 'SOLUSDT': 0.001382545335298778}.
- MARKET_RV_7D: COST_ROBUST; STRESS full=-0.0026553, five-best-removed=-0.0023992; year contributions={'2024': -0.0016046941566000435, '2025': -0.006173164511535375, '2026': 0.0015219301548955743}; asset contrasts={'BTCUSDT': -0.0011624891523562303, 'ETHUSDT': -0.004296988485478064, 'SOLUSDT': -0.0025063966984629673}.
- MARKET_CORR_7D: COST_ROBUST; STRESS full=0.0033823, five-best-removed=0.0030577; year contributions={'2024': 0.005264815486453346, '2025': 0.004554510163800903, '2026': -0.005086843028614329}; asset contrasts={'BTCUSDT': 0.00204913417937804, 'ETHUSDT': 0.002682576849964602, 'SOLUSDT': 0.005415119226434273}.

## Dependence-aware uncertainty

Moving-block bootstrap, 7 calendar-day blocks, 1,000 resamples, fixed seed 271828; descriptive only.
- MARKET_DRAWDOWN_30D: STRESS 95% interval [-0.0006768031844655908, 0.005739773930645473].
- MARKET_RV_7D: STRESS 95% interval [-0.005911653919456308, 0.0003613060401401434].
- MARKET_CORR_7D: STRESS 95% interval [0.0007248541301737786, 0.005922442031050425].

## Ten-stack verdict

Socratic: one limited association survived the frozen attacks. Hegelian: fixed exposure and conditional measurement remain distinct. Popperian: RV and correlation timing propositions are killed for V0. Causal: association is not mechanism. Systems: strategy ≠ piece ≠ sleeve ≠ Router. Cybernetics: negative variables reduce architecture. Bayesian: evidence updates only this narrow measurement relation. MDL/DOE: one process, three states, one horizon were frozen. Adversarial: 2024, asset, tail, cost, PIT, and overlap attacks were run.

## Jigsaw piece and decision
- PIECE_TYPE: CONDITION_DEPENDENCE; MEASUREMENT_STRATEGY: H003 MA 24/96; CONDITION: MARKET_DRAWDOWN_30D; OBSERVED_RELATION: STRESS HIGH_MINUS_LOW_MEAN_UTILITY=0.0023699; SCOPE: BTC/ETH/SOL, declared sample, 24h daily non-overlapping decisions; STATUS: PREDICTIVE_PIECE_CANDIDATE.

PRIMARY DECISION: TREND_CONDITION_DEPENDENCE_PIECE_EARNED
NEXT SMALLEST ACTION: BOUNDED_EXTERNAL_REPLICATION_10_TO_30_ASSETS
VERDICT: JIGSAW_V0_PIECE_READY_FOR_REPLICATION
