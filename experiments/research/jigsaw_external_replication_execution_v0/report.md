# JIGSAW — Frozen External Replication of the Drawdown Piece (V0, final execution)

RESEARCH_STATUS: FROZEN_EXTERNAL_REPLICATION  
AUTHORITY: NON_AUTHORITATIVE  
PROMOTION_ELIGIBLE: NO  
ROUTER_AUTHORITY: NONE  
CAUSAL_CLAIM: NONE  
NETWORK_ACCESS: NONE

## Contract reconciliation

- request_digest `51f9aba2e9b5e02439e32290349af1cb70a56429db7fa14a9b0852afdf42c8be`
- cohort_digest `8a37866705efa5d68d80fb6770db49dbaba84c6e2c4848df6a406b885f0b5c1e`
- piece_contract_digest `de0cae86adf96a8fedb6b4f9531190265da2bf201e293a342b033fc0a498778a`
- materialization commit `6c0a8ad80cdc5cba0086b8e446c2d1ecfffa117e`
- qualified input adapter `2167a3be24b125e47524b4540dcb338b53d30b2a`
- Every INPUT_READY normalized file re-hashed to its committed manifest SHA256 before any science ran.

## Aggregation contract

Unit of analysis: `EQUAL_WEIGHT_DAILY_CROSS_ASSET_PORTFOLIO_UTILITY`.  Recovered from qntylab/jigsaw_trend_condition_dependence_v0.py::materialize (utilities row) and ::analyze (primary uses `rows`, not `asset_rows`); discovery result digest `b1d722f9ec89c021f7e7fbf4992fa509d7de4562340004ba2a849b98b7dcc22d`.

## State counts

- state_panel_hours: 22583
- state_panel_start: 2023-12-03T01:00:00Z
- state_panel_end: 2026-06-30T23:00:00Z
- state_panel_gaps: 0
- first_drawdown_available_timestamp: 2024-01-02T00:00:00Z
- daily_state_observation_count: 911
- first_normalizable_decision: 2025-01-01T00:00:00Z
- no_future_state_input: True
- normalization_days: 365
- drawdown_lookback_hours: 720
- scheduled_decision_state_counts: {'LOW': 211, 'MID': 191, 'HIGH': 144}
- aggregate_row_state_counts: {'LOW': 210, 'MID': 191, 'HIGH': 144}

## Missingness

- frozen members: 20
- scheduled decisions: 546
- scheduled member-decision opportunities: 10920
- usable observations: 10355
- missing observations: 565
- usable fraction: 0.948260
- accounting complete (every opportunity has exactly one terminal state): True

  - IDENTITY_CONFLICT_AFTER_FREEZE: 0
  - SOURCE_DATA_MISSING: 546
  - STATE_INPUT_GAP: 0
  - INSUFFICIENT_STATE_HISTORY: 0
  - MEASUREMENT_STRATEGY_PATH_MISSING: 0
  - OUTCOME_MISSING: 19
  - POST_DELIST_OR_OTHER_DECLARED_UNUSABLE: 0
  - USABLE_REPLICATION_OBSERVATION: 10355

## Primary result

| cost | bin | mean | median | positive rate | N |
|---|---|---:|---:|---:|---:|
| BASELINE | LOW | -0.2597% | -0.0486% | 0.3333 | 210 |
| BASELINE | MID | -0.1799% | -0.0360% | 0.4188 | 191 |
| BASELINE | HIGH | -0.2148% | -0.0272% | 0.4792 | 144 |
| STRESS | LOW | -0.2896% | -0.0646% | 0.3143 | 210 |
| STRESS | MID | -0.2120% | -0.0600% | 0.3979 | 191 |
| STRESS | HIGH | -0.2458% | -0.0478% | 0.4444 | 144 |

| contrast | BASELINE | STRESS |
|---|---:|---:|
| HIGH_MINUS_LOW_MEAN_UTILITY | +0.0449% | +0.0438% |
| HIGH_MINUS_LOW_POSITIVE_RATE | +14.58 pp | +13.02 pp |

MAGNITUDE VS DISCOVERY: `SMALLER_BUT_MEANINGFUL` (18.5% of the discovery stress spread; negligible-epsilon scale is 0.01%/day)

Co-primary HIGH_MINUS_LOW_POSITIVE_RATE contrast: +13.02 pp stress, 19/19 usable assets positive, 2/2 temporal blocks positive; breadth_credible=True.

## Asset by asset

| symbol | usable | missing | LOW mean | MID mean | HIGH mean | base H-L | stress H-L | base H-L pos | stress H-L pos | classification |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|
| BCHUSDT | 545 | 1 | -0.3010% | +0.0339% | -0.3580% | -0.0628% | -0.0570% | +8.47 pp | +8.95 pp | OPPOSITE_DIRECTION |
| XRPUSDT | 545 | 1 | +0.1130% | -0.2755% | +0.0163% | -0.1041% | -0.0966% | +10.00 pp | +9.78 pp | OPPOSITE_DIRECTION |
| LTCUSDT | 545 | 1 | -0.0882% | -0.1310% | -0.4323% | -0.3370% | -0.3441% | +10.48 pp | +11.43 pp | OPPOSITE_DIRECTION |
| TRXUSDT | 545 | 1 | -0.1882% | -0.1044% | +0.0911% | +0.2738% | +0.2793% | +21.33 pp | +21.59 pp | SAME_DIRECTION |
| ETCUSDT | 545 | 1 | -0.3291% | -0.4631% | -0.2478% | +0.0905% | +0.0813% | +12.86 pp | +13.81 pp | SAME_DIRECTION |
| LINKUSDT | 545 | 1 | -0.4732% | -0.2263% | +0.0041% | +0.4732% | +0.4773% | +17.54 pp | +17.80 pp | SAME_DIRECTION |
| XLMUSDT | 0 | 546 | n/a | n/a | n/a | n/a | n/a | n/a | n/a | INSUFFICIENT_DATA |
| CHZUSDT | 545 | 1 | -0.1724% | -0.1086% | -0.1104% | +0.0621% | +0.0620% | +23.53 pp | +22.84 pp | SAME_DIRECTION |
| SANDUSDT | 545 | 1 | -0.4648% | -0.1993% | -0.1947% | +0.2694% | +0.2701% | +18.10 pp | +17.40 pp | SAME_DIRECTION |
| REEFUSDT | 545 | 1 | -0.0354% | +0.0975% | -0.1880% | -0.1534% | -0.1526% | +0.22 pp | +0.22 pp | OPPOSITE_DIRECTION |
| CHRUSDT | 545 | 1 | -0.3851% | -0.4275% | -0.6178% | -0.2296% | -0.2327% | +14.50 pp | +14.98 pp | OPPOSITE_DIRECTION |
| ALICEUSDT | 545 | 1 | -0.1286% | -0.4023% | -0.3718% | -0.2421% | -0.2432% | +13.19 pp | +13.19 pp | OPPOSITE_DIRECTION |
| ONEUSDT | 545 | 1 | -0.4568% | -0.1668% | -0.6988% | -0.2399% | -0.2420% | +17.14 pp | +16.45 pp | OPPOSITE_DIRECTION |
| API3USDT | 545 | 1 | -0.0614% | +0.0252% | -0.5398% | -0.4696% | -0.4784% | +13.37 pp | +12.94 pp | OPPOSITE_DIRECTION |
| GMTUSDT | 545 | 1 | -0.6632% | -0.2491% | -0.6645% | -0.0020% | -0.0012% | +17.14 pp | +17.62 pp | APPROXIMATELY_NULL |
| APEUSDT | 545 | 1 | -0.4987% | -0.3954% | -0.2164% | +0.2903% | +0.2823% | +15.06 pp | +16.01 pp | SAME_DIRECTION |
| OPUSDT | 545 | 1 | -0.5053% | -0.2640% | -0.0879% | +0.4162% | +0.4174% | +14.25 pp | +14.03 pp | SAME_DIRECTION |
| INJUSDT | 545 | 1 | -0.2273% | -0.2544% | +0.2171% | +0.4429% | +0.4444% | +22.88 pp | +22.88 pp | SAME_DIRECTION |
| LDOUSDT | 545 | 1 | -0.3720% | -0.3466% | +0.0063% | +0.3801% | +0.3783% | +18.27 pp | +18.75 pp | SAME_DIRECTION |
| APTUSDT | 545 | 1 | -0.2646% | -0.1713% | -0.2768% | -0.0048% | -0.0122% | +14.76 pp | +15.24 pp | OPPOSITE_DIRECTION |

## Asset breadth

- usable asset count: 19
- SAME_DIRECTION: 9 (47.4% of usable) — TRXUSDT, ETCUSDT, LINKUSDT, CHZUSDT, SANDUSDT, APEUSDT, OPUSDT, INJUSDT, LDOUSDT
- OPPOSITE_DIRECTION: 9 (47.4% of usable) — BCHUSDT, XRPUSDT, LTCUSDT, REEFUSDT, CHRUSDT, ALICEUSDT, ONEUSDT, API3USDT, APTUSDT
- APPROXIMATELY_NULL: 1 (5.3% of usable) — GMTUSDT
- INSUFFICIENT_DATA: 1 — XLMUSDT

## 2025 vs 2026H1

| block | base H-L | stress H-L | stress H-L positive | usable decisions |
|---|---:|---:|---:|---:|
| 2025 | -0.0447% | -0.0446% | +14.74 pp | 365 |
| 2026H1 | +0.1900% | +0.1870% | +10.40 pp | 180 |

## Leave-one-asset-out (stress primary aggregation)

- original spread: +0.0438%
- minimum LOO spread: +0.0197%
- maximum LOO spread: +0.0728%
- removal weakens most: LINKUSDT
- removal strengthens most: API3USDT
- runs retaining sign: 19
- runs reversing sign: 0
- excluded (no observations): XLMUSDT

## Top-five attack

- BASELINE: original +0.0449%, trimmed -0.1229%, retained -273.7%; removed 2025-05-08(HIGH), 2025-05-10(HIGH), 2025-07-10(HIGH), 2025-11-07(LOW), 2026-04-16(HIGH)
- STRESS: original +0.0438%, trimmed -0.1246%, retained -284.5%; removed 2025-05-08(HIGH), 2025-05-10(HIGH), 2025-07-10(HIGH), 2025-11-07(LOW), 2026-04-16(HIGH)

## Moving-block bootstrap (7-day blocks, 1000 resamples, seed 271828)

- BASELINE: point +0.0449%, 2.5% -0.4272%, 97.5% +0.4886% — SIGN_UNCERTAIN
- STRESS: point +0.0438%, 2.5% -0.4311%, 97.5% +0.4905% — SIGN_UNCERTAIN

## Discovery vs external replication

| Metric | BTC/ETH/SOL discovery | External cohort |
|---|---:|---:|
| Baseline H-L mean | +0.2326% | +0.0449% |
| Stress H-L mean | +0.2370% | +0.0438% |
| Stress positive-rate spread | +22.80 pp | +13.02 pp |
| Asset breadth | 3/3 positive | 9/19 positive |
| Temporal sign consistency | 2024/25/26 positive | 1/2 blocks |
| Top-five retention | 68.9% | -284.5% |
| Bootstrap | sign uncertain | sign uncertain |

## Replication criteria

- PASS — aggregate_direction_preserved
- PASS — magnitude_not_trivial
- PASS — stress_survives
- FAIL — asset_breadth_reasonably_broad
- PASS — not_one_asset_driven
- FAIL — not_five_observation_driven
- FAIL — both_temporal_blocks_supportive
- PASS — missingness_does_not_manufacture_result
- PASS — bootstrap_compatible

PRIMARY DECISION: DRAWDOWN_PIECE_REPLICATION_WEAK_OR_MIXED
JIGSAW STATUS: PREDICTIVE_PIECE_REMAINS_WEAK
VERDICT: EXTERNAL_REPLICATION_MIXED
NEXT ACTION: DEFER_DRAWDOWN_PIECE_AND_RETURN_TO_JIGSAW_DISCOVERY
