# QntySpot Ink shadow performance research authorization V0

This is exactly one governance-only authorization candidate. It does not
authorize implementation on this branch. The registry state is
`PLANNED_NOT_AUTHORIZED`; the candidate is effective only
`AFTER_EXACT_CANONICAL_MERGE_ONLY`. A branch-local copy cannot self-authorize.

The only later phase named by this candidate is
`QNTYSPOT_INK_SHADOW_PERFORMANCE_V0`. That future phase is bounded to one
preregistered KRAKMASK/WETH ladder-family evaluation against frozen baselines,
with the exact sequence `PREREGISTER -> DEFINE_CHRONOLOGICAL_DEV_OUTER ->
ACQUIRE_DEV -> SELECT_AND_FREEZE_EXACTLY_ONE_CANDIDATE -> ONLY_THEN_ACQUIRE_OUTER
-> RUN_EXACTLY_ONE_SEALED_OUTER_EVALUATION`.

The historical cutoff is `2026-08-25T17:02:37Z`. Data strictly later than that
cutoff belongs to a future prospective lineage. Outer results may not be
reused, the candidate may not be altered after freeze, parameters may not be
silently expanded, and the existing QntySpot V0B qualification fixture is not
a strategy.

The candidate branch is based on exact canonical QntyLab `origin/master`
commit `a4738278f42f961ad2f2470fefff6688ccde6bb6`. The source binding was
derived mechanically from exact canonical QntySpot
commit `b9a84c59bd43e7697ee970d2a7571647e5de4501` (`origin/main`), specifically
the `qntyspot/ink.py` blob recorded in `authorization.json`. The binding is
for Ink chain `57073`, the exact KRAKMASK and WETH9 contracts, the exact
InkySwap V2 pool and factory, the deployed runtime bytecode SHA-256, and V2
fee semantics `997/1000`. Chat values do not override Git; source drift is a
`STOP_SOURCE_CONFLICT`. QntyLab may not modify QntySpot and may not use
runtime cross-repository imports.

This phase performed no market-data acquisition, outcome inspection, backtest,
strategy test, candidate or trial event, metric calculation, outer evaluation,
prospective shadow, secret read, signing, approval, broadcast, or capital
action. The scientific firewall remains:

```text
TRADING_AUTHORITY = NONE
CAPITAL_AUTHORITY = NONE
QNTYSPOT_EXECUTION_AUTHORITY = NONE
SIGNING_AUTHORITY = NONE
PROMOTION_AUTHORITY = NONE
```

A later positive result is not proof of alpha. A negative result must be
preserved. This authorization grants no live, paper, shadow, promotion, or
capital authority.
