# Claim Source Model — DSH Stage-A V1R3R2 Execution-Contract Reconciliation

## CLAIM_OWNER (exactly one)

The parent enforcement path — [`guard.mjs`](../../dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_v0/profile/qntylab-stage-a-parent-enforcement/lib/guard.mjs)
`ensureClaim()` inside `reserve()`, and `reserve()` runs before `next()` in
`applyParentGuard` — is the SOLE EpisodeClaim acquisition owner.

External orchestration may inspect prestate and launch the controlled DSH parent
path, but must NOT independently acquire the same production claim first.

## CLAIM_SOURCE_MODEL (IMPLEMENTED)

The claim-source seam is now IMPLEMENTED in
[`qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py`](../../../../qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py)
as an explicit exact-immutable-commit seam. A future live EpisodeClaim MUST bind
an EXPLICIT EXACT IMMUTABLE commit SHA supplied by the applicable future live
authority / resolved execution inputs:

- `EXACT_FORMAT`: the authorized source is an exact full commit object identity
  (40–64 hex), never a moving symbolic name (`master`, `origin/master`) and not
  `git rev-parse HEAD` alone.
- `OBJECT_EXISTS`: Git must resolve that exact commit object.
- `CURRENT_CHECKOUT_RELATION`: the source must be an ancestor of the execution
  checkout HEAD (`merge-base --is-ancestor <sha> HEAD`).
- `CANONICAL_ANCESTRY`: separately, the source must be an ancestor of the
  resolved canonical ref commit object (`merge-base --is-ancestor <sha>
  <canonical>`) — proven against the exact commit object, never a moving ref
  name alone.
- `REVOCATION_AND_SUPERSESSION`: a separately supplied revocation/supersession
  check must not invalidate the exact source.
- `RESOLVED_EXECUTION_INPUTS`: the source SHA is bound together with the current
  execution-contract root and the relevant immutable runtime/executable
  identities. THE EXECUTION-CONTRACT ROOT IS AN INDEPENDENTLY DERIVED
  CONTENT-ADDRESSED EXECUTION IDENTITY — it is NOT ``sha256(source_sha)`` and is
  never computed from the source SHA. The source SHA and the execution-contract
  root are two INDEPENDENT identities that are BOUND TOGETHER in the resolved
  execution inputs; a mismatched root, a mismatched source, or a substituted
  surrogate binding fails closed.
- `FAIL_CLOSED`: missing SHA, malformed SHA, unknown object, wrong ancestry,
  superseded/revoked source, or source/input mismatch all fail BEFORE any claim
  is COMMITTED.

The production owner (parent enforcement guard) transports the COMPLETE binding
— `authorizedExecutionSourceSha`, `executionContractRoot`,
`runtimeIdentityDigest`, `executableIdentityDigest`, and `revocationState` —
from the preparation output (resolved production identity) plus the future live
authority inputs. The launcher/profile/config/guard chain is transport-only:
it never re-derives, re-substitutes, or defaults any value, and no
`revocationState` default (e.g. NOT_REVOKED) is ever invented.

The claim record/intent carries the exact authorized SHA; it never substitutes an
ambient HEAD at action time. No exact future merge SHA is baked in as a
universal execution source.

## EXECUTION_STATE_MACHINE

canonical-authority → activation → qualified-contract →
physical-runtime-and-executable → workspace → budget-and-child-controls →
non-secret-gates → real-secret-read → claim-creation (parent sole owner) →
claim-committed → budget-reservation → provider-wire-io → child-lifecycle.

Required invariant: EpisodeClaim COMMITTED BEFORE durable provider-budget
reservation BEFORE provider wire I/O.

## ENFORCEMENT_SEAM_DISPOSITION (IMPLEMENTED)

The claim-source seam that previously bound `git rev-parse HEAD`
(`qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py:647`) is replaced by
`_resolve_authorized_source_sha()` with the seven fail-closed checks above. This
was authorized by the bounded correction
`DSH_STAGE_A_V1R3R2_EXECUTION_CONTRACT_RECONCILIATION_CORRECTION_AUTHORIZATION_V0`
(operation `IMPLEMENT_EXACT_COMMIT_CLAIM_SOURCE_SEAM`).

Defense-in-depth: independent of the seam, the contract state machine
(claim-creation by the parent sole owner) refuses provider wire I/O before the
EpisodeClaim is COMMITTED, so a moving-ref binding could not alone authorize a
provider write.
