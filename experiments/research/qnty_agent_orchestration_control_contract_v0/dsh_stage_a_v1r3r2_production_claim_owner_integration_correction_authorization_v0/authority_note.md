# DSH Stage-A V1R3R2 production claim-owner integration correction authorization V0

Project: `DSH_STAGE_A_V1R3R2_PRODUCTION_CLAIM_OWNER_INTEGRATION_CORRECTION_AUTHORIZATION_V0`

Phase type: `GOVERNANCE_ONLY_BOUNDED_CORRECTION_AUTHORIZATION`

Authority level: `AUTHORIZED_IF_CANONICAL` — effective only after exact canonical merge.

## Canonical binding

- Repository: `QntyLab`
- Canonical ref: `origin/master`
- Canonical master: `07f97f4c645c35bf7a17593ca093e50789c4d620` (PR #216 merge)
- Canonical merge parents:
  - `ded772d59c6135689ac4bda8878979721855a955`
  - `f73a15fb5cb84ace8c6ee1d58d60f4d39706fb49`
- Blocked predecessor: `PR #217` (`DSH_STAGE_A_V1R3R2_EXECUTION_CONTRACT_RECONCILIATION_V0`)
- Predecessor head: `f5e41c2c24009b66ff906e14fbd439a3d9754a48`
- Predecessor required state: `OPEN_DRAFT_NOT_MERGED`
- Predecessor terminal outcome: `PR217_CORRECTION_BLOCKED`
- Previous correction authority: `DSH_STAGE_A_V1R3R2_EXECUTION_CONTRACT_RECONCILIATION_CORRECTION_AUTHORIZATION_V0`
- Canonical drift behavior: `STOP_SOURCE_CONFLICT`
- Git wins over prompt memory or handoff: `true`

## Root cause (frozen)

The remaining production claim-owner path is:

`prepareProductionLaunch` → launcher `extraEnv` → `cordis.patch.yml` →
parent-enforcement `index.js` Config → `guard.mjs ensureClaim()` → Python
`claim` operational entrypoint.

`prepareProductionLaunch` already derives the current execution-contract root,
runtime identity digest, and executable identity digest from resolved production
inputs. However, the Stage-A launcher `ALLOWED_EXTRA_ENV`, `cordis.patch.yml`,
parent-enforcement `index.js` Config, and `guard.mjs` only transport legacy claim
fields (`QNTYLAB_DSH_CLAIM_STATE_DIR`, `QNTYLAB_DSH_CLAIM_REMOTE`,
`QNTYLAB_DSH_CLAIM_REF`, `QNTYLAB_DSH_CLAIM_SOURCE_REPO`,
`QNTYLAB_DSH_SESSION_NONCE`).

The hardened Python `claim` operational entrypoint now correctly requires:
authorized execution source SHA, actual execution-contract root,
revocation/supersession state, runtime identity digest, executable identity
digest. The sole production claim-owner path therefore fails closed before claim
acquisition. Blocking High: the Python seam is hardened, but the actual sole
production claim owner cannot supply its newly required inputs.

## Claim binding model (frozen)

Two provenance classes — no static digest is universal future authority:

- Class A — RESOLVED PRODUCTION IDENTITY: `executionContractRoot`,
  `runtimeIdentityDigest`, `executableIdentityDigest` — derived from the SAME
  `prepareProductionLaunch` execution, transported directly from resolved
  current production inputs. NOT copied from stale constants or recomputed from
  unrelated source.
- Class B — FUTURE LIVE AUTHORITY IDENTITY: `authorizedExecutionSourceSha`,
  revocation/supersession proof/state — supplied by the applicable future
  canonical live authorization. NOT invented by the non-live reconciliation
  phase. No origin/master identity, no ambient HEAD identity, no hardcoded
  future merge SHA, no unconditional `NOT_REVOKED` default.

All values must survive byte/value identical across transport
(`prepareProductionLaunch` → launcher → `cordis.patch.yml` → `index.js` Config →
`guard.mjs ensureClaim()` → Python `claim`). No layer may silently substitute
another value.

## Candidate-only authority

This authorization artifact is a branch-local candidate. It does **not** self-authorize.
`authorization_effective = AFTER_EXACT_CANONICAL_MERGE_ONLY`,
`effective_repair_authority = false`, `implementation_authorized = false` on
branch. The future implementation phase must independently reconcile the
canonical source again before any repair.

## Live firewall (all zero)

- Real secret reads: 0
- Production claims: 0
- Provider calls: 0
- Live DSH invocations: 0
- Real Codex turns: 0
- Real Claude turns: 0
- Spend USD: 0

## Forbidden scope

Merge, V0R7, live authorization, scientific execution, real secret read, claim
creation, provider call, V0R5/V0R6 replay, Stage B, a new implementation PR
(other than amending the existing PR #217), hardcoded future merge SHA, an
origin/master or ambient HEAD identity binding, an unconditional `NOT_REVOKED`
default, and mutation of historical artifacts are all forbidden. The historical
firewall keeps byte-identical: historical composite `contract.json`, historical
composite `digests.json`, historical `successor_contract.json`, V0R5 evidence,
V0R6 evidence, and prior execution receipts. Current-generation evidence may
change only through deterministic derivation.

## Authorized future implementation paths (exclusive list)

- `experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/preparation/prepare-production-launch.mjs`
- `.../dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_v0/launcher/qntylab-launch-dsh.mjs`
- `.../dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_v0/profile/cordis.patch.yml`
- `.../dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_v0/profile/qntylab-stage-a-parent-enforcement/lib/index.js`
- `.../dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_v0/profile/qntylab-stage-a-parent-enforcement/lib/guard.mjs`
- direct parent-enforcement tests including `prelive-enforcement.test.mjs`
- reconciliation `claim-source-model.md`
- direct deterministic integration tests
- `.github/workflows/project-context.yml` (ONLY to ensure the real
  production-owner integration test runs in CI)
- current-generation dependency/DAG/evidence artifacts whose identities
  mechanically change because authorized hashed leaves change

Historical artifacts are NOT authorized to be mutated.

## End-to-end offline test (mandatory)

The future repair MUST test the ACTUAL production claim-owner chain:
instantiate/use the real cordis profile semantics, parent-enforcement
`index.js`, `guard.mjs`, and observe the actual Python `claim` invocation. Scratch
Git repo, scratch claim remote/ref, fake/non-production claim namespace are
permitted; no secret, no provider, no DSH live episode. The positive test must
prove the real production owner sends exactly: authorized execution source SHA,
actual independent execution-contract root, runtime identity digest, executable
identity digest, `NOT_REVOKED` proof/state to the Python operational entrypoint.
Negative controls through the SAME production owner:

- missing source SHA → BLOCK
- missing execution root → BLOCK
- wrong execution root → BLOCK
- missing revocation proof → BLOCK
- REVOKED → BLOCK
- SUPERSEDED → BLOCK
- wrong runtime identity → BLOCK
- wrong executable identity → BLOCK
- transport substitution at launcher/profile/plugin layer → BLOCK

All failures occur before claim COMMITTED, budget reservation, provider I/O.

## CI requirement

The real production-owner integration test MUST run in GitHub candidate-head CI
(`.github/workflows/project-context.yml`). Do not rely only on Python
EpisodeClaim unit tests or repository-deterministic contract inspection. The
exact interface that failed hostile review must become an executable CI
regression gate.

## Dependency invalidation

`guard.mjs`, `index.js`, `cordis.patch.yml`, the launcher, and any other changed
production leaf are content-bound inputs. The future implementation must compute
the reverse-transitive closure mechanically, rederive every affected
current-generation identity, prove unaffected nodes unchanged, and produce a new
`POST_REPAIR_CURRENT_ROOT` from final bytes. `a31eb46...` is the current
pre-repair root only; it is NOT frozen as the required post-repair root.

## What this phase does NOT do

This governance-only phase performs no future implementation, repairs no
launcher/plugin/guard/Python bytes, no CI workflow, no documentation bytes, and
touches no live boundary. It opens one DRAFT governance-only authorization PR
and stops. It does not modify PR #217.

## Budget

- future implementation episodes: 1
- final candidate commits: 1
- draft implementation PR: existing PR #217 only
- hostile reviews: 1
- Critical/High repairs: at most 1
- targeted rereviews: at most 1, only if a C/H repair occurred
- review-of-review: forbidden