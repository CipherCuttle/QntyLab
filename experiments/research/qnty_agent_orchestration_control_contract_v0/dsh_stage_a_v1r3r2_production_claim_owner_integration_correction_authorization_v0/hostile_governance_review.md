# Hostile Governance Review — DSH_STAGE_A_V1R3R2_PRODUCTION_CLAIM_OWNER_INTEGRATION_CORRECTION_AUTHORIZATION_V0

Project: `DSH_STAGE_A_V1R3R2_PRODUCTION_CLAIM_OWNER_INTEGRATION_CORRECTION_AUTHORIZATION_V0`

Review type: bounded hostile governance review (exactly one, per budget).

Reviewed artifacts:
- `experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_production_claim_owner_integration_correction_authorization_v0/authorization.json`
- `experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_production_claim_owner_integration_correction_authorization_v0/authority_note.md`
- `docs/state/projects.toml` registry record
- `docs/CURRENT_ROADMAP.md` (generated)
- `tests/test_dsh_stage_a_v1r3r2_production_claim_owner_integration_correction_authorization_v0.py`

Severity scale: Critical / High / Medium / Low.

## Attack 1 — scope too narrow to propagate values end-to-end

**Attack**: the authorization authorizes only a fragment of the production
claim-owner chain, so the future repair cannot propagate the resolved claim
binding end-to-end to the Python `claim` entrypoint.

**Finding**: The 13 authorized operations include
`PROPAGATE_RESOLVED_CLAIM_BINDING_FROM_PRODUCTION_PREPARATION` →
`EXTEND_STAGE_A_LAUNCHER_CLAIM_BINDING_TRANSPORT` →
`EXTEND_CORDIS_PARENT_ENFORCEMENT_CONFIG_BINDING` →
`EXTEND_PARENT_ENFORCEMENT_CONFIG_SCHEMA` →
`EXTEND_GUARD_CLAIM_CLI_ARGUMENT_WIRING`, plus the mandatory end-to-end offline
test and CI gate. The operation constraints name every layer of the frozen
production path (`prepare-production-launch.mjs`, `qntylab-launch-dsh.mjs`,
`cordis.patch.yml`, `index.js`, `guard.mjs`) and demand byte/value-identical
transport with no silent substitution. The `production_binding_model` freezes
the two provenance classes (A resolved production identity, B future live
authority identity) that the transport must carry.

**Result**: PASS — scope is precisely the full frozen production claim-owner chain.

## Attack 2 — scope too broad

**Attack**: the authorization grants authority beyond the production claim-owner
integration correction (e.g., new research, new architecture, live execution,
new implementation PR).

**Finding**: `phase_type` is `governance_only_bounded_correction_authorization`;
`authorized_future_scope.allowed_operations` is a closed 13-item death list with
per-operation constraints, and `forbidden_operations` explicitly includes
`NO_V0R7`, `NO_LIVE_AUTHORIZATION`, `NO_SCIENTIFIC_EXECUTION`, `NO_STAGE_B`,
`NO_NEW_IMPLEMENTATION_PR`, `NO_MUTATION_OF_HISTORICAL_ARTIFACTS`. The
implementation paths are a bounded list; the reconcile said this is NOT a new
architecture/research campaign. Budget caps are explicit
(`implementation_episode_budget: 1`, `final_candidate_commit_budget: 1`,
`draft_implementation_pr: EXISTING_PR217_ONLY`).

**Result**: PASS — scope is bounded and cannot widen.

## Attack 3 — static/hardcoded current-root authorization

**Attack**: the authorization hardcodes a current digest (e.g., `a31eb46...`) as
universal future authority.

**Finding**: `MECHANICALLY_REDERIVE_CURRENT_EXECUTION_CONTRACT_ROOT_AND_DEPENDENTS`
explicitly states: "Do NOT freeze a31eb46... as the required post-repair root;
a31eb46... is the current pre-repair root only." The `production_binding_model`
sets `no_static_current_root_as_universal_authority: true` and Class A identity
must be derived from the SAME `prepareProductionLaunch` execution over resolved
current production inputs, not copied from stale constants.

**Result**: PASS — no static current-root authorization.

## Attack 4 — static NOT_REVOKED default

**Attack**: the authorization grants an unconditional `NOT_REVOKED` default for
the future live authority identity.

**Finding**: `production_binding_model.no_static_not_revoked_default: true` and
`forbidden_operations` includes `NO_UNCONDITIONAL_NOT_REVOKED_DEFAULT`. Class B
(revocation/supersession state) must be SUPPLIED by the applicable future
canonical live authorization; the non-live reconciliation phase may NOT invent
it. The negative control list requires `missing revocation proof → BLOCK`,
`REVOKED → BLOCK`, `SUPERSEDED → BLOCK`.

**Result**: PASS — no static NOT_REVOKED default.

## Attack 5 — ability to mutate historical evidence

**Attack**: the authorization would let the future repair rewrite historical
composite `contract.json` / `digests.json` / successor evidence / V0R5 / V0R6 /
prior receipts.

**Finding**: `historical_firewall` requires byte-identical preservation of all
listed historical artifacts; current-generation evidence may change only through
deterministic derivation. `forbidden_operations` includes
`NO_MUTATION_OF_HISTORICAL_ARTIFACTS`. No operation in the 13-item list targets
historical artifacts.

**Result**: PASS — historical evidence is firewall-protected.

## Attack 6 — ability to perform live claim/provider action

**Attack**: the candidate or its authorized future path could create a claim,
read a real secret, call a provider, or invoke DSH.

**Finding**: `live_firewall` and `construction_receipts` counters are all zero.
`forbidden_operations` includes `NO_REAL_SECRET_READ`, `NO_CLAIM_CREATION`,
`NO_PROVIDER_CALL`, `NO_LIVE_DSH_INVOCATION`-equivalent semantics
(`NO_LIVE_AUTHORIZATION`, `NO_SCIENTIFIC_EXECUTION`, `NO_STAGE_B`). The end-to-end
test is constrained to offline scratch (scratch Git repo / remote / ref, fake
non-production claim namespace, no secret, no provider, no DSH live episode),
and all negative controls must fail before claim COMMITTED, budget reservation,
and provider I/O.

**Result**: PASS — no live claim/provider action capability.

## Attack 7 — missing production-owner CI test requirement

**Attack**: the authorization authorizes the implementation without mandating
the real production-owner integration test in GitHub candidate-head CI.

**Finding**: `ADD_REAL_PRODUCTION_OWNER_TEST_TO_CI` is a mandatory authorized
operation with target `.github/workflows/project-context.yml`, stating the test
MUST run in GitHub candidate-head CI and must become an executable CI regression
gate (not merely Python EpisodeClaim unit tests or repository-deterministic
contract inspection). `ADD_REAL_PRODUCTION_OWNER_END_TO_END_OFFLINE_TEST` is the
mandatory, most-important operation with full positive and negative control
requirements. `stop_conditions` includes
`STOP_IF_PRODUCTION_OWNER_CI_GATE_IS_NOT_ADDED`, so a repair that omits the CI
gate violates the authorization and must stop, and the hostile-review budget
would fail it.

**Result**: PASS — production-owner CI gate is mandatory.

## Attack 8 — ability to create a new implementation PR instead of amending #217

**Attack**: the authorization would permit the future implementation to open a
fresh implementation PR rather than amending the existing blocked PR #217.

**Finding**: `AMEND_REPLACE_PR217_SINGLE_CANDIDATE` is constrained to
`draft_implementation_pr: EXISTING_PR217_ONLY`, `no_new_implementation_pr: true`,
`single_final_candidate_commit: true`, `one_draft_pr: true`,
`no_merge_authority: true`. `forbidden_operations` includes
`NO_NEW_IMPLEMENTATION_PR`. The task closure requires opening exactly ONE DRAFT
governance-only authorization PR and NOT modifying #217 in this phase.

**Result**: PASS — only amendment of the existing #217 is authorized.

## Attack 9 — candidate self-authorization

**Attack**: the branch-local candidate artifact claims effective authority
before canonical merge.

**Finding**: `phase_state: CANDIDATE_GOVERNANCE_ONLY`;
`authorization_effective: AFTER_EXACT_CANONICAL_MERGE_ONLY`;
`authority_firewall.effective_repair_authority: false`;
`authority_firewall.implementation_authorized_on_branch: false`;
`authority_firewall.branch_local_artifact_does_not_self_authorize: true`;
registry `state: PLANNED_NOT_AUTHORIZED`,
`candidate_state: ACTIVE_CANDIDATE`,
`effective_repair_authority: false`,
`implementation_authorized: false`. The focused test `test_candidate_only_semantics_and_no_self_authorization`
asserts these. The roadmap renders the project as `PLANNED_NOT_AUTHORIZED`.

**Result**: PASS — no self-authorization.

## Additional check — exact canonical/predecessor binding

The canonical base binds exactly `07f97f4c645c35bf7a17593ca093e50789c4d620`;
the blocked predecessor binds exactly PR #217 head
`f5e41c2c24009b66ff906e14fbd439a3d9754a48` (`OPEN_DRAFT_NOT_MERGED`,
terminal outcome `PR217_CORRECTION_BLOCKED`). Both are asserted by the focused
test and match the frozen task spec.

**Result**: PASS.

## Verdict

- Critical findings: 0
- High findings: 0
- Governance review outcome: PASS (Critical = 0, High = 0)
- No repair and no targeted rereview required.