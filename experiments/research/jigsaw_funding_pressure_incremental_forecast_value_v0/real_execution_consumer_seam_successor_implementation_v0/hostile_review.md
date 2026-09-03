# Hostile review — real-execution consumer-seam successor implementation V0

Review count: 1. This is the single terminal hostile review required by the
one-review lifecycle of
`FUNDING_INCREMENTAL_REAL_EXECUTION_CONSUMER_SEAM_SUCCESSOR_IMPLEMENTATION_V0`
(governing decision:
`FUNDING_INCREMENTAL_REAL_EXECUTION_CONSUMER_SEAM_SUCCESSOR_DECISION_V0`).
No targeted rereview was used and no repair was made after the review; the
blocking findings close the phase `CLOSED_BLOCKED`.

## Review identity

- Reviewed pull request: #241 (implementation PR for the successor seam).
- Reviewed candidate commit: `d181d12096e19c1dbe2f89585e73b8f8f7b6b21f`.
- Codex review ID: 5103186304.
- Candidate canonicalized: NO. The candidate implementation source was never
  merged, cherry-picked, or copied onto canonical master; it is referenced
  here only by its historical commit hash and its source does not exist on
  master.
- Blocking severity counts: 2 Critical/P1, 0 High, 0 Medium, 0 Low.

## Findings

| Severity | ID | Finding | Disposition |
| --- | --- | --- | --- |
| P1 (blocking) | 3925566255 | Synthetic provenance laundering: the public constructor accepts ordinary `ForecastRow` objects without verifiable synthetic provenance and unconditionally sets `synthetic_only=True`, so real observations can be wrapped as `SYNTHETIC_VALIDATION` via the synthetic constructor and passed to the frozen executor. This violates the kill criteria against synthetic relabeling, authority laundering, and real-data admission through the synthetic ordering boundary. | Open; closes the phase BLOCKED. |
| P1 (blocking) | 3925566262 | Exactly-once recording is process-local: the module-local `_RECORDS` dict means a restart or a second worker re-evaluates the same record identity; no lifecycle-level deterministic exactly-once or duplicate suppression is established. | Open; closes the phase BLOCKED. |
| High | None beyond the two P1 findings. | — |
| Medium | None. | — |
| Low | None. | — |

## Attack coverage

The review checked frozen-source mutation disguised as plumbing, synthetic
relabeling and authority laundering through the synthetic constructor, real-row
admission through the synthetic ordering boundary, private-entrypoint bypass,
V2 result-contract substitution, process-local versus lifecycle-level
exactly-once recording, replay conflict handling, claim-before-outcome
ordering, and real data, outcome, provider, claim, or evaluation-origin access.
No real data was accessed, no outcome consumed, no provider called, no real
claim consumed, and no evaluation origin advanced during the review.

## Review verdict

`FUNDING_INCREMENTAL_REAL_EXECUTION_CONSUMER_SEAM_SUCCESSOR_IMPLEMENTATION_V0 = CLOSED_BLOCKED`

Terminal state: `CLOSED_BLOCKED`. Under the governing one-review lifecycle
there is no rereview, no repair continuation, no reopen, no successor phase,
and no downstream authority. PR #241 remains unmerged and its implementation
source remains absent from canonical master.
