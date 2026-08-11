# JIGSAW_CROSS_SECTIONAL_DISPERSION_EXECUTION_V0

PLAN: Reconcile the canonical master, persist the authorized PIT warm-up, reopen the exact blocked candidate once, execute the frozen measurement, run the frozen attacks, and record one decision.

CANONICAL_START_SHA: `eb2e89542242ba9a37308155226d9ca09b7cf8e4`  
CONTRACT_DIGEST: `d2227ac387852a23d5fb2b09d8656ba7678f460cffc2478afaa1ea5b7d882182`  
BLOCKED_DECISION_PRESERVED: `event_decision_jigsaw_cross_sectional_dispersion_blocked_v0`  
REOPEN_EVENT: `event_reopen_jigsaw_cross_sectional_dispersion_warmup_v0`  
WARMUP_INPUTS_DURABLE: YES — `/home/swirky/DevHub/qntylab-evidence/jigsaw_cross_sectional_dispersion_v0_warmup_v0`  
WARMUP_PROVENANCE: 240 authenticated source archives, 20 normalized OHLCV files, 20 manifests, 240 monthly receipts, census, and readiness receipt.  
WARMUP_HASH_MATCH: YES — all 522 promoted files byte-hash matched the support worktree.

DEV_2024_PRICE_INPUT: Existing authorized Breadth V2 DEV_2024 panel bundles, four exact CSMOM variants.  
DEV_2024_FUNDING_INPUT: Existing authorized realized Binance USD-M funding settlement bundles; missingness fail-closed.  
ELIGIBLE_DAILY_CENSUS: 364 DEV_2024 observations; 364 pre-2024 warm-up states; 0 partial-panel states; exact 20/20 throughout.

## Primary result

| Variant | STRESS LOW | STRESS MID | STRESS HIGH | STRESS HIGH−LOW | Consistent |
|---:|---:|---:|---:|---:|:---:|
| 24 | -0.0336062209 | -0.0335728703 | -0.0286373472 | 0.0052432106 | NO |
| 72 | -0.0206428955 | -0.0148081625 | -0.0161837209 | 0.0049759051 | NO |
| 168 | -0.0170520687 | -0.0150553545 | -0.0096833818 | 0.0078889464 | NO |
| 336 | -0.0072890496 | -0.0049259742 | -0.0080856297 | -0.0001012365 | YES |

PRIMARY_CONSISTENT_COUNT: 1  
PRIMARY_REQUIRED_COUNT: 3  
PRIMARY_FAMILY_CRITERION_MET: NO

BASELINE HIGH−LOW contrasts for 24/72/168/336: `0.0035258842`, `0.0033061356`, `0.0064660842`, `-0.0005489472`.

## Robustness

COST: all four variants serialized; signs agree with stress.  
H1_H2: both calendar halves serialized for all variants.  
LEAVE_ONE_ASSET_OUT: exact 20/20 process retained; no unauthorized 19-asset economic rerun.  
TAIL: exact five-best/five-worst removals serialized.  
MISSINGNESS: 0 partial-panel states.  
STATE_DISTINCTNESS: absolute correlations with `MARKET_DRAWDOWN_30D`, `MARKET_RV_7D`, and `MARKET_CORR_7D` were `0.2837433`, `0.1133620`, and `0.0788222`; none reached 0.90.  
BOOTSTRAP: moving blocks of 7 calendar days, 1000 resamples, seed 271828, per variant.

## Kill criteria

`NO_CONDITION_DEPENDENCE_FOUND` TRIGGERED: YES — `consistent_count=1/4`, below `3/4`. All other frozen criteria were not triggered. No rescue test was added.

## Scientific decision

SCIENTIFIC_DECISION: `KILLED`  
CROSS_SECTIONAL_MOMENTUM_STRATEGY_STATUS: `UNCHANGED_FAIL`  
ROUTER_AUTHORITY: `NONE`  
QNTY_AUTHORITY: `NONE`  
TRADING_AUTHORITY: `NONE`  
POST_SEALED_T0_ACCESSED: `NO`

HOSTILE_REVIEW: No Critical/High finding; no targeted re-review required.  
EVALUATOR: No matching QntyAgentEval contract was applicable.

VERDICT: `KILLED`  
NEXT_SMALLEST_SCIENTIFIC_ACTION: Return to Jigsaw discovery; do not rescue this proposition.
