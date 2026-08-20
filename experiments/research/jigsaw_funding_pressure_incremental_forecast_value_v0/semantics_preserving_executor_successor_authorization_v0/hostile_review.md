# Hostile review — semantics-preserving successor authorization V0

Review count: exactly 1. Targeted rereview: not used.

## Verdict

`CLOSED_BLOCKED`. The proposed successor shape is conceptually clear, but it is
not mechanically implementable under the simultaneous requirements that the
historical V0 source remain byte-immutable, the successor expose a distinct
real mode, and HAR/OLS/forecast/loss/Clark-West/HAC/classification exist in one
shared scientific core.

## Findings

### Critical 1 — frozen source has no extractable core seam

`run_incremental_forecast_evaluation` performs mode authorization and then
contains the complete evaluation assembly. There is no pure evaluator that a
new wrapper can call. Extracting one requires changing the historical source,
which would invalidate its frozen implementation identity.

### Critical 2 — every immutable-source workaround duplicates or launders science

Calling the frozen entrypoint with real rows labeled
`SYNTHETIC_VALIDATION` violates the mode and outcome firewall. Reimplementing
the assembly in a successor duplicates the scientific algorithm. Calling V2
uses a different `FrozenExperimentResult` contract. None is an admissible
single-core successor.

### Critical 3 — claimed semantic equivalence cannot be established

The required differential corpus and exact canonical-serialization comparison
are valid acceptance gates for a future implementation, but no future
implementation exists here. A design record cannot truthfully assert frozen
digest reproduction or authorize a later implementation when the only
mechanically available routes fail the anti-duplication and identity gates.

## Attack coverage

The review explicitly attacked semantic drift, duplicate implementations,
weak differential coverage, false SHA continuity, synthetic/real laundering,
wrapper bypass, digest divergence, panel/schedule/PIT/runtime drift,
claim-after-outcome ordering, V2 result substitution, hidden outcome access,
post-result rescue authority, and Router/Qnty/trading/capital escalation.

## Disposition

No Critical/High repair is attempted because the findings are architectural,
not defects in an authorized implementation. No successor code, real data,
claim, evaluation, result, or downstream authority is created.
