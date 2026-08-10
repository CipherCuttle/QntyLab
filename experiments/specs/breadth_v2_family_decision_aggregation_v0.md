# Breadth V2 family decision aggregation V0

Contract: `BREADTH_V2_FAMILY_DECISION_CONTRACT_V0`.

This is a deterministic downstream reducer for future Breadth V2 receipts and
paths. It consumes no market data and never invokes the runner, PortfolioKernel,
evaluation preparation, evaluation recording, or the research ledger.

The identity is bound to screen `QNTYLAB_BREADTH_V2_20260810`, input contract
`BREADTH_V2_DEV_INPUT_UNIVERSE_V0R1`, its SHA-256
`8fef4c02d113027630072bcbb0802e35ab31be17c835aa2ebdae4261265589fb`, 28
registered variants, seven families, 20 assets, three development periods, and
the two registered cost modes. The module exposes `contract_manifest()` and a
timestamp-free `CONTRACT_DIGEST`.

Only V0R1 READY executions enter arithmetic. BLOCKED registrations remain in
the fixed 20-asset, 3-period, and 4-variant denominators and never become a
zero or negative score. Integrity is checked before economic adjudication;
integrity failures produce `BLOCKED`, while valid economic gate failures
produce `FAIL` and unresolved frozen missingness produces `INCONCLUSIVE`.

Scores are equal-weight means. Asset-window means average usable variants;
window and pooled-asset means average assets/windows respectively. Positive
support concentration uses only positive pooled-asset scores. Variant
neighbour support uses the frozen registration-order adjacency map. Cost
survival uses the exactly matched baseline/stress set and the preregistered
50% retention rule. No new return, Sharpe, turnover, beta, or optimization
threshold is introduced.

Panel contribution cells are normalized by each receipt's recorded initial
equity and reconciled to portfolio candidate and benchmark totals. Relative
value diagnostics attribute price plus funding PnL at boundary `t` to the
previous boundary target, exclude rebalance costs from leg attribution, and
enforce the frozen +1/-1/2/0 exposure invariant.

The receipt is canonical JSON (sorted keys, compact separators) and contains
the contract identity, denominators, observations, all gate inputs/results,
diagnostics, final status, and reason codes. No wall-clock timestamp is used.
