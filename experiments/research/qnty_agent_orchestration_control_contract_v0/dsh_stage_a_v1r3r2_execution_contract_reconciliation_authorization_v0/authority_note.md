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