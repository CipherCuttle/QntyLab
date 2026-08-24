# DSH Stage-A V1R3R2 execution contract reconciliation authorization V0

Project: `DSH_STAGE_A_V1R3R2_EXECUTION_CONTRACT_RECONCILIATION_AUTHORIZATION_V0`

Phase type: `GOVERNANCE_ONLY_BOUNDED_REPAIR_AUTHORIZATION`

Authority level: `AUTHORIZED_IF_CANONICAL` — effective only after exact canonical merge.

## Canonical binding

- Repository: `QntyLab`
- Canonical ref: `origin/master`
- Canonical master: `ded772d59c6135689ac4bda8878979721855a955` (PR #214 merge)
- Canonical merge parents:
  - `4195433872140634784c404f88fa0c70a6bcfd11`
  - `3dc9b1d28d2170fde33c09ba123ce81209acb505`
- Predecessor project: `DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R6`
- Predecessor required state: `CLOSED_BLOCKED`
- Predecessor terminal outcome: `V0R6_LIVE_EPISODE_CLOSED_BLOCKED_NO_REPLAY`
- Canonical drift behavior: `STOP_SOURCE_CONFLICT`
- Git wins over prompt memory or handoff: `true`

## Candidate-only authority

This authorization artifact is a branch-local candidate. It does **not** self-authorize.
`authorization_effective = AFTER_EXACT_CANONICAL_MERGE_ONLY` and
`effective_repair_authority = false`. The future repair phase
(`DSH_STAGE_A_V1R3R2_EXECUTION_CONTRACT_RECONCILIATION_V0`) must independently
reconcile the canonical source again before any repairation.

## Live firewall (all zero)

- Real secret reads: 0
- Production claims: 0
- Provider calls: 0
- Live DSH invocations: 0
- Real Codex turns: 0
- Real Claude turns: 0
- Spend USD: 0

## Forbidden scope

Replay V0R5/V0R6, create V0R7, start another Stage-A live episode, Stage B,
scientific execution, Qnty runtime, Qnty promotion, trading, capital, and
broader production use are all forbidden.

## What this phase does NOT do

This governance-only phase performs no future reconciliation, repairs no
runtime/contract/digest bytes, and touches no live boundary. The accidental
spelling untracked directory `dsh_stage_stage_a_v1r3r2_execution_contract_reconciliation_v0/`
is non-canonical and is left untouched.

## Authorized future repair scope (non-live, candidate-only)

The future repair phase `DSH_STAGE_A_V1R3R2_EXECUTION_CONTRACT_RECONCILIATION_V0`
is authorized, NON-LIVE, to perform the bounded class-level execution-contract
reconciliation: reconstruct the complete execution dependency DAG; separate
historical verification from current contract derivation; mechanically compute
reverse-transitive invalidation; create new current-generation contract
artifacts where required; preserve historical a392/50bd and V0R5/V0R6 evidence
immutable; rewire prepare-production-launch and directly related production
contract selection, and composite/immediate pre-spawn verification, to the
CURRENT contract root; remove stale historical contract paths from current
production truth; establish exactly one EpisodeClaim acquisition owner; verify
and freeze the executable secret → claim → budget → provider → child state
machine; ensure provider I/O cannot precede claim COMMITTED; bind claim source
to an exact immutable commit SHA with separate canonicality/revocation checks;
verify clean source/worktree semantics before the irreversible claim boundary;
verify actual current Node/Python/Codex/Claude executable identities;
deterministically verify or rematerialize the PINNED DSH runtime from canonical
resolved inputs (NON-LIVE); repair runtime/action-time contract selection if
required; make directly required Project Context projection and CI changes
(distinguishing CANDIDATE_HEAD / SYNTHETIC_PR_MERGE_RESULT / CANONICAL_MASTER);
add dependency-closure / unaffected-node / action-time parity tests; run the
complete production-equivalent NON-SECRET preflight; perform exactly one
independent hostile security review; repair Critical/High only; perform at most
one targeted rereview if such repair occurred; create one candidate commit AND
one draft implementation PR; then stop.

This is NOT permission for unrelated refactors. Every mutation must be directly
justified by the frozen execution-contract reconciliation objective. Historical
a392/50bd and V0R5/V0R6 evidence remains immutable, and the live boundary
remains zero/forbidden.