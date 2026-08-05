# Clean TSMOM EXP_V2 R4 freeze receipt

## R3 VERIFICATION DEFECT RECEIPT

R3 independently reconstructed only panel, signals, weights, and funding
assignments. It did not independently recompute funding returns, turnover,
costs, equity, metrics, tail metrics, benchmarks, classifications, comparison,
or final liquidation. It accepted producer controls as booleans and reported
`maximum_independent_difference=0.0` without complete numerical comparison.
Its mutation tests changed artifact bytes without updating the manifest, so
integrity rejection could be mistaken for semantic rejection. Classification:
`RECOVERABLE_PREREGISTRATION_INDEPENDENT_VERIFICATION_DEFECT`.

## R4 INDEPENDENT ARCHITECTURE

R4 uses a separate verifier implementation with local source aggregation,
target reconstruction, portfolio/equity/metric/benchmark/classification
derivation, recursive comparison, and evidence-bearing controls. It does not
import or invoke R2/R3 producer or verifier implementations.

## FREEZE BOUNDARY

The real source bundle is not invoked during this freeze. No market-data
network attempt, real strategy evaluation, corrected metric observation, or
source-bundle byte change occurred. V2, R1, R2, and R3 files remain unchanged.

## VERIFY

- Combined R3 and R4 focused surface: `60 passed` with warnings as errors.
- R4 semantic mutations: `17 rejected`; integrity-gate rejections for value
  mutations: `0`.
- Producer A/B output trees: byte-identical.
- Complete comparison: all 17 required artifacts independently recomputed;
  maximum difference `0.0`, tolerance `1e-12`.
- Static boundary checks, compileall, JSON parsing, and `git diff --check`:
  passed.
- Repository-wide suite: `804 passed, 41 failed, 32 errors`. The 73 red nodes
  reproduce the pinned R3 baseline failures caused by absent external research
  fixtures/caches; R4-only regressions: `0`.

## PRESERVED COUNTERS

```text
market_data_network_attempts_during_r4_freeze=0
real_strategy_evaluation_attempts_during_r4_freeze=0
corrected_metrics_observed=0
source_bundle_byte_changes=0
v2_contract_changes=0
v2r1_contract_changes=0
v2r2_contract_changes=0
v2r3_contract_changes=0
```
