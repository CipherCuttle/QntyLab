# Hostile governance review — Stage-A V1R3R2 production DSH_HOME materialization authorization V0

Review type: exactly one independent, read-only hostile governance review,
conducted as a dedicated adversarial pass after the authorization artifact,
focused tests, and registry/roadmap entries were frozen.

Reviewed candidate:

- authorization project: `DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_MATERIALIZATION_AND_ACTION_TIME_PARITY_AUTHORIZATION_V0`
- authorized future project: `DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_MATERIALIZATION_AND_REQUALIFICATION_V0`
- canonical predecessor: `DSH_STAGE_A_V1R3R2_ONE_EPISODE_LIVE_EXECUTION_V0R4` (`CLOSED_BLOCKED` / `BLOCK_RUNTIME_IDENTITY`)
- canonical base: `1913df60545616cb8eaf94f36f73f6686c683993` (merge of PR #204)
- predecessor qualified contract: `a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be`
- composite launcher: `6f212de0576127fea1dd2778a69c49a3b755a017a9d55f97f18b9057dc15c329`

The review was repository-read-only with respect to runtime state. It made no
runtime, launcher, package, or ambient-directory change, read no real secret,
created no claim, invoked no DSH or native child, made no provider request, and
incurred no spend.

## Adversarial checks

| # | Attack | Result | Evidence |
| --- | --- | --- | --- |
| 1 | Authorization secretly allows direct V0R5 | PASS | `v0r5_authorized` / `v0r5_created` false; create/activate/execute V0R5 all in `forbidden_scope`; `authorization_does_not_authorize_v0r5` true; `next_phase_after_implementation = SEPARATE_FRESH_GIT_BACKED_AUTHORITY_REQUIRED`; tests assert no V0R5 registry entry, directory, or tracked path exists. |
| 2 | Old scratch home remains authoritative | PASS | `old_scratch_dsh_home_is_authoritative_source` false; all four observed ambient roots explicitly denied; `freeze_ambient_machine_directory_as_authority` false; negative control 16 requires that the stale scratch DSH_HOME cannot substitute. A test proves every ambient root found in the forensic sweep is a subset of the denied set, so a newly discovered root cannot be silently tolerated. |
| 3 | Implementation may manually patch a machine-global home | **FAIL → repaired (H-01)** | Original candidate forbade *declaring* an ambient directory authoritative but never forbade *mutating* it. See findings. |
| 4 | Qualification-only helper can remain outside production path | PASS | `may_remain_the_production_authority_path` false; `was_executed_on_the_live_v0r4_path` false; negative control 20; parity requires one production preparation path and forbids qualification-only prerequisite creation. Helper bytes are pinned by digest `11a35328…`. |
| 5 | New materializer not required in successor contract | PASS | `must_be_bound_into_successor_contract` true; successor bindings include materializer path *and* digest plus the materialized DSH_HOME manifest schema; `must_compute` requires both new digests; `a392_remains_final_complete_live_contract` false. |
| 6 | Action-time parity requirement can be skipped | PASS | `required` true, `skippable` false, `waivable` false; exact six-step chain from an empty destination; all seven expected receipts pinned to zero; stop boundary is `IMMEDIATELY_BEFORE_REAL_SECRET_READ`; asserted by test. |
| 7 | Production stub package allowed accidentally | PASS | `production_stub_provider_allowed` false; `FAIL_CLOSED` on presence; stub excluded from required packages; negative control 9. Finding F7 records that the qualified launcher itself tolerates the stub as optional, and the authorization therefore places enforcement in the materializer and production preflight rather than in the launcher it may not modify. A test reads the launcher and confirms the tolerance is real. |
| 8 | Runtime rebuild authority leaked | PASS (with M-01) | `physical_runtime_byte_change_authorized`, `runtime_rebuild_authorized`, `runtime_repatch_authorized`, `composite_launcher_modification_authorized`, `stage_a_package_modification_authorized` all false; expected unchanged manifest/executable identities frozen; `silent_rebuild_forbidden` true; divergence must `STOP_AND_REPORT_SOURCE_CONFLICT_OR_SCOPE_EXPANSION_REQUIRED`. Residual ambiguity recorded as M-01. |
| 9 | Secret / claim / provider authority leaked | PASS | All frozen authority flags false; every firewall field false or `NONE`; all fifteen construction receipts zero; parity stops before any secret read; forbidden scope names secret read, claim creation, provider I/O, real children, and spend. |
| 10 | Stage B / Qnty / scientific / trading authority leaked | PASS | `stage_b_authorized`, `scientific_execution_authorized`, `production_deployment_authorized` false; `qnty_runtime_authority`, `trading_authority`, `capital_authority`, `promotion_authority`, `broader_production_authority` all `NONE`; `active_project_after_closure = NONE`; `qnty_agent_eval = NOT_APPLICABLE`. |

Supplementary checks:

| Attack | Result | Evidence |
| --- | --- | --- |
| Authorization phase silently implements the materializer | PASS | Phase diff against canonical master is a subset of five governance files; a test asserts the subset and that no `.mjs` file was touched. `materializer_artifacts_created = 0`. |
| Authorization phase pre-applies the stale-test repair | PASS | A test asserts the V0R4 authorization test file is unchanged in this phase's diff, so the repair remains the future phase's work. |
| Stale-test repair authority used to delete or trivialize the test | PASS | `deletion_of_the_test_authorized` false; `weakening_to_a_trivially_true_assertion_authorized` false; `must_preserve_historical_purpose` true; `production_semantics_change_allowed` false. |
| Stale-test repair claimed without the staleness being real | PASS | A test independently runs `git log` against canonical master and requires the activation artifact to actually be present, so the repair authority is void if the premise is false. |
| Registry and artifact disagree (projection drift) | PASS | A test cross-checks project id, authority level, base sha, verdict, review counters, and requires every artifact the registry claims as authoritative to exist and be Git-tracked. |
| Predecessor binding forged | PASS | Predecessor closure and execution-evidence bytes are bound by sha256 and recomputed by test; the recorded failed DSH_HOME is cross-checked against the canonical V0R4 evidence. |

## Findings

```text
Critical = 0
High     = 1  (repaired)
Medium   = 2  (accepted without repair; Medium/Low repair not authorized this phase)
Low      = 0
```

### H-01 — High — REPAIRED

**Ambient DSH_HOME mutation was not prohibited.**

The candidate forbade *declaring* the ambient scratch DSH_HOME authoritative and
forbade *depending* on it at action time, but no clause forbade the future
implementation phase from writing into it. An implementer could have made the
V0R4 blocker disappear by backfilling `profiles/node_modules/@qntylab` into
`/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/dsh-home` and then
reported success without ever building a production materializer. That both
defeats the entire purpose of this repair authorization and destroys the
forensic reproducibility of the immutable V0R4 evidence, whose physical referent
is that exact directory.

Repair applied to the authorization artifact and registry:

- `historical_ambient_dsh_home_mutation_authorized = false`
- `historical_ambient_dsh_home_repair_or_backfill_authorized = false`
- `ambient_root_mutation_authorized = false`
- `ambient_cross_check_must_be_read_only = true`
- `ambient_mutation_behavior = FORBIDDEN_BLOCKS_IMPLEMENTATION`
- `ambient_immutability_basis` records the reasoning
- `forbidden_scope` gains "modify, repair, or backfill the historical ambient scratch DSH_HOME" and "modify, repair, or backfill any forbidden ambient root"

### M-01 — Medium — ACCEPTED WITHOUT REPAIR

**The boundary between "materializing DSH_HOME packages" and "rebuilding the
runtime" is not defined.**

Forensic finding F6 shows the pinned materialization root carries an
identity-bound lockfile and a 925-entry pnpm virtual store, so a plausible
implementation resolves the DSH_HOME package graph by a lockfile-pinned install.
The authorization forbids runtime rebuild and runtime byte modification but does
not state whether such an install counts as one. An implementer could read this
either as forbidden (blocking the phase) or as permitted (quietly widening
scope).

Not repaired: Medium/Low repair is outside this phase's authority. The residual
risk is bounded because `expected_unchanged_runtime_manifest_digest` and
`expected_unchanged_executable_identity_digest` are frozen and any divergence
must `STOP_AND_REPORT_SOURCE_CONFLICT_OR_SCOPE_EXPANSION_REQUIRED`, so a scope
widening that changes runtime identity fails closed rather than passing
silently. The implementation phase should resolve this explicitly in its own
plan before writing code.

### M-02 — Medium — ACCEPTED WITHOUT REPAIR

**The ambient cross-check allowance is a narrow residual channel.**

`ambient_directory_may_be_used_as_a_cross_check_only = true` permits reading the
ambient home to compare against canonically derived bytes. A careless
implementer could let a cross-check drift into a fallback source.

Not repaired: Medium/Low repair is outside this phase's authority. The residual
risk is substantially reduced by the H-01 repair, which makes the cross-check
explicitly read-only, and by `ambient_cross_check_may_not_confer_authority`,
`required_derivation = GIT_BOUND_OR_CONTRACT_BOUND_CANONICAL_SOURCES_ONLY`, and
negative controls 16, 17, and 20.

## Targeted rereview

One targeted rereview was performed, scoped strictly to the H-01 repair.

| Rereview check | Result |
| --- | --- |
| H-01 repair present in the authorization artifact | PASS |
| H-01 repair projected into the registry | PASS |
| Ambient mutation prohibition reaches `forbidden_scope` | PASS |
| Repair introduces no live, secret, claim, provider, spend, V0R5, or Stage-B authority | PASS |
| Repair does not modify runtime, launcher, or Stage-A package bytes | PASS |
| Repair does not implement the materializer | PASS |
| Phase diff remains within the five allowed governance files | PASS |
| Authorization tests still pass | PASS |
| `project_context doctor --strict`, `render --check`, `research_ledger doctor` still clean | PASS |

Rereview verdict: `PASS`. No further Critical or High finding was introduced by
the repair. No review recursion beyond this single targeted rereview is
authorized, and none was performed.

## Review verdict

`PASS`: freeze this bounded repair authorization only.

This review and its repair create no implementation, no production DSH_HOME
materializer, no successor launch contract digest, no activation, no V0R5, no
effective live authority, no claim, no secret read, no provider or model I/O, no
DSH invocation, no native child turn, no fixture mutation, no spend, no Stage-B
authority, no Qnty authority, no scientific execution authority, no trading
authority, no capital authority, no promotion authority, and no broader
production deployment authority. `ACTIVE_PROJECT` remains `NONE`.
