# Hostile review — real-execution consumer-seam implementation authorization V0

Review count: 1. This is the single bounded hostile review required by the
phase policy. No targeted rereview was used because no Critical/High repair was
made; the Critical findings close the phase BLOCKED.

## Findings

| Severity | Finding | Disposition |
| --- | --- | --- |
| Critical | The frozen incremental entrypoint accepts only `SYNTHETIC_VALIDATION`, so verified real rows cannot reach it under an honest execution label. | Open; closes the phase BLOCKED. |
| Critical | Calling lower-level helpers or recreating the orchestration would bypass the frozen entrypoint invariant or duplicate the frozen statistical algorithm. | Open; no source refactor is authorized here. |
| Critical | The V2 controlled seam returns a different `FrozenExperimentResult` for the 610-decision V2 contract and cannot substitute for incremental `ForecastRow` evaluation. | Open; V2 result semantics are explicitly rejected. |
| High | None beyond the Critical gate findings. | — |
| Medium | None. | — |
| Low | None. | — |

## Attack coverage

The review checked frozen-source mutation disguised as plumbing, statistical
algorithm duplication, synthetic-mode laundering, private/internal-call
invariant bypass, V2 result-contract substitution, provenance and current-
materializer laundering, exact panel and schedule drift, PIT leakage, runtime
bypass, claim-after-outcome ordering, hidden data acquisition, and Router/Qnty/
trading/capital escalation. The static governance artifacts contain no real
evidence loader invocation, no evaluation values, no claim transport call, and
no scientific executor call.

## Review verdict

`FUNDING_INCREMENTAL_REAL_EXECUTION_CONSUMER_SEAM_IMPLEMENTATION_AUTHORIZATION_V0 = CLOSED_BLOCKED`

The only truthful successor is a separately governed scientific-source
refactor or successor seam that preserves the frozen mathematical semantics,
provides an explicit `REAL_SCIENTIFIC_EXECUTION` boundary, and supplies
authority-bound real `ForecastRow` values without copying the algorithm. No
implementation or scientific execution authority is created by this closure.
