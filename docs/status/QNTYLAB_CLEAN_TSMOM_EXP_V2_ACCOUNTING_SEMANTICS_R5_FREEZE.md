# QNTYLAB Clean TSMOM EXP_V2 Accounting Semantics R5 Freeze

`ACCOUNTING_SEMANTICS_R5` is a recoverable preregistration accounting
amendment. It freezes a canonical per-interval ledger, full entry and
liquidation turnover, additive fixed-quantity cash accounting, complete main
and tail USD attribution, artifact-only metrics, and a no-extra-liquidation-
observation convention.

The R3 producer and R4 verifier agreed on equations that contradicted these
requirements. No real EXP_V2 result or corrected metric was observed before
R5. R5 does not change strategy or source definitions and is not a real
experiment execution.

Required freeze evidence is produced by the focused R5 tests, strict tests,
producer A/B byte comparison, independent verifier, mutation gate, and the
preservation inventory recorded with the commit.

## Preservation inventory

- starting HEAD: `11084b622d8bf64e908dc990f1144a80b4e7c5cb`
- frozen V2/R1/R2/R3/R4 path-hash inventory: 45 paths; aggregate SHA-256 `9f0f69bf01f018e773cbbdc637283b463a4896fd3f08b35b80d95e6387d36dfd`
- frozen source-bundle manifest SHA-256: `0c7f58447833999676ce9053dbcb69165e7ab502798509d8e825e8cc7c8d8e0f`
- source-bundle file-hash inventory aggregate SHA-256: `c16e18bed1a974d5aee13f1afc5b13f27928114435eafc933813ee9657f4047f`
- source bundle bytes changed: `0`
- Qnty repository access attempts: `0`
- real strategy evaluation attempts: `0`
- corrected metrics observed: `0`
