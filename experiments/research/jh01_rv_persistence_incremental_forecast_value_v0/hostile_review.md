# Hostile review — JH01 incremental forecast-value preregistration V0

Review scope: the frozen preregistration, static validator, tests, project
state, and append-only ledger recording. No market-data directory, source, or
result artifact was opened or executed.

## Findings

- CRITICAL: 0
- HIGH: 0
- MEDIUM: 1 — The 2026-07-20 start is calendar-past at preregistration time,
  so its integrity depends on the documented distinction between data existing
  and outcomes being accessed. The contract correctly makes an unproven
  outcome-unseen attestation a hard block and requires a later materialization
  phase to prove it. This is not repairable by silently moving the window after
  inspection, so no design change is made.
- LOW: 1 — A 5% MSE reduction is a governance materiality threshold rather
  than a universal literature constant. The artifact labels it as such and
  cannot tune it after outcome access.

## Questions answered

The question is new; C_JH01 is exactly specified; B2 is mechanically
redundant and removed; B1 is the unambiguous primary benchmark; B0/B3 cannot
rescue; MSE and the 24-hour horizon are fixed; refitting and all information
boundaries are point-in-time constrained; nested primary handling is explicit;
materiality is required in addition to the one-sided adjusted-MSPE inference
gate; and failure preserves the Jigsaw evidence without granting downstream
authority.

The only compatibility search for QntyAgentEval found no existing evaluator or
contract for this static, prospective, unexecuted protocol. No evaluator was
created or run.

No Critical or High repair was required, so no targeted re-review is used.
