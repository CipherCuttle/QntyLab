# JFPV3 R2 hostile review

Review scope: the activation transaction, exact schedule binding, crash/replay behavior, collection authority, temporal gates, source seam, status surface, and runtime canonicality in `qntylab/jfp_v3_shadow.py`.

## Findings and disposition

1. **High — partial schedule rows must not become authority.** The review required `ACTIVATION_PREPARED` before any schedule row, exact 365-row verification before `SHADOW_ACTIVATED`, duplicate-index rejection, and fail-closed payload binding. Covered by the partial-recovery, orphan, mutation, and commit tests.
2. **High — collection must not run from a scheduled row alone.** Every lifecycle transition now requires a valid committed activation and exact run, activation-record, and schedule bindings. Covered by pre-activation and wrong-run tests.
3. **High — temporal and PIT gates must remain fail-closed.** Metadata is bounded by origin, feature inputs and features by the origin boundary, and outcomes by origin+24h. Covered by temporal tests.
4. **Medium — source invocation must remain test-isolated.** Production transport is an explicit standard-library requester behind `BinanceUmTransport`; focused tests use `FixtureTransport` only and make no live calls.

## Final hostile-review verdict

Critical findings: 0. High findings: 0 open after repair. Medium findings: 1 bounded and accepted. No activation, prospective market-data access, scientific inference, or result classification occurred.

## Targeted rereview of Critical/High repairs

The repaired paths were reread and re-exercised: a committed ledger is revalidated before idempotent replay, partial schedule recovery remains non-active until the exact 365-row set is present, and collection cannot proceed without the committed run/schedule binding. The focused suite and the 142-test regression slice pass. No new Critical or High finding is open.
