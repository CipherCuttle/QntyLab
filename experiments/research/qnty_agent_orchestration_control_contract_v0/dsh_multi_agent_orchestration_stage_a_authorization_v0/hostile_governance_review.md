# Hostile governance review — DSH multi-agent orchestration Stage-A authorization V0

Review count: one independent hostile review of the drafted authorization
candidate. No DSH, Codex, Claude, OpenAI, or any other live model call was
made by this authorization phase.

## Attacks and disposition

1. **Does the authorization accidentally grant live execution now?** PASS.
   `governance_boundary.authorization_phase_dsh_invocations`,
   `..._codex_invocations`, `..._claude_invocations`, and
   `..._parent_api_calls` are all `0`, and `authorization_effective` is
   `AFTER_CANONICAL_MERGE_ONLY`. `hard_pr_budget` names exactly this PR and
   one later execution/closure PR; no separate forensic, canary, repair, or
   additional-authorization PR is authorized.

2. **Can paid DSH parent spend occur without explicit authority?** PASS on
   authority; **High finding on boundedness, repaired below (H-01).** Spend
   authority is recorded as explicit
   (`parent_model_route.spend_authority = YES`, with a named source),
   bounded to `spend_ceiling_usd = 1.00`, and scoped to the later phase only.
   But the original draft expressed the operational bound as a
   `parent_turn_ceiling` of 6-8. Direct inspection of
   `packages/core/agent-loop/src/agent.ts` shows `turn()` runs an outer
   `while (true)` over *steps*, and each step is roughly one billed LLM call;
   the framework places no cap on how many steps one turn may contain, so a
   turn-only ceiling does not actually bound spend — a single turn could in
   principle run many billed calls before yielding.
   **Repair:** added `parent_lifecycle_budget.parent_max_total_steps = 8`
   (inclusive of retries) as the actual binding, externally-enforced
   ceiling — the wrapper counts `step/start` session events (already emitted
   once per LLM call by the pinned loop) and hard-terminates the process the
   instant it's reached, independent of turn boundaries. Also added an
   explicit `max_output_tokens_per_call_override` (4096, overriding the
   model's raw 128000-token catalog cap via the `models[].maxTokens` route
   override documented in `llm-pi-ai/src/index.ts`) and a stated worst-case
   per-call cost ($0.058192, assuming a pessimistic 200000 resent input
   tokens) so that `worst_case_episode_cost_usd` (0.465536, 8 steps) carries
   roughly 2.1x margin under the $1.00 ceiling instead of an unbounded
   figure. This is disclosed as `EXTERNAL_WRAPPER_ENFORCED_NOT_FRAMEWORK_NATIVE`
   — a conservative-implausibility bound the later phase must implement and
   verify, not a framework guarantee — rather than overclaimed as
   impossible.

3. **Can native child credentials/API overlays escape the frozen policy?**
   PASS. `auth_secret_policy` and both `child_routes` entries state
   `api_key_override_prohibited = true` and require native host auth only;
   `openai_api_key_scope = DSH_PARENT_PROCESS_ENVIRONMENT_ONLY` with explicit
   "must not reach Codex/Claude child" fields.

4. **Can raw upstream Codex provider behavior be used instead of the repaired
   materialization?** PASS. `runnable_profile_composition.raw_upstream_fallback_prohibited
   = true`, and `later_phase_must_establish` requires a byte-identity check of
   the running build's provider source against the materializer's frozen
   postimage digest before any live call.

5. **Can the synthetic fixture mutate Qnty/QntyLab scientific state?** PASS.
   The fixture is a two-function, network-free, credential-free Python
   utility with no relationship to any QntyLab/Qnty module; execution happens
   only in a disposable copy outside both trees (`synthetic_fixture`
   workspace-boundary fields, and `TASK.md`'s explicit workspace-boundary
   section, verified: the stub raises `NotImplementedError` and fails all
   three tests, a reference implementation passes all three).
   `governance_boundary.qnty_mutation_authorized = false`.

6. **Can child-call or repair loops become unbounded?** PASS.
   `child_routes.*.call_budget` caps each child at 1 initial + 1 conditional
   call, with `no_autonomous_indefinite_loop`, `no_recursive_review`, and
   `no_review_of_review` all `true`.

7. **Can Claude review its own changes or otherwise lose independence?**
   PASS. `child_routes.claude_code.independence_requirement` states Claude
   must not review a diff it authored and must not share session/context with
   the Codex child; the two providers are architecturally separate subagent
   packages in the pinned source, each spawning its own native child process.

8. **Can DSH recursively spawn additional uncontrolled agents?** PASS.
   `parent_lifecycle_budget.no_child_created_subagent_swarm = true`; the
   frozen turn sequence names exactly the two children and no others.

9. **Can one Stage-A authorization silently become a benchmark suite?** PASS.
   `mission.not_a_benchmark_suite = true`,
   `governance_boundary.benchmark_suite_authority = false`,
   `synthetic_fixture.single_fixture_only = true`.

10. **Can orchestration PASS be misread as scientific/trading/promotion
    authority?** PASS. `governance_boundary` fixes
    `scientific_execution_authorized`, `market_data_access_authorized`,
    `jigsaw_mutation_authorized`, `state_snapshot_mutation_authorized`, and
    `router_mutation_authorized` all `false`, and
    `qnty_runtime_authority`/`trading_authority`/`promotion_authority`/
    `capital_authority`/`downstream_authority` all `"NONE"`.

11. **Is build/profile composition reproducible from the exact pinned
    source?** PASS. `later_phase_must_establish` requires the exact
    substitution build step, the exact `cordis.patch.yml` provider
    registration, and the byte-identity gate from item 4; the current local
    `~/.dsh/profiles/headless` scaffold is recorded as
    `EMPTY_SCAFFOLD_NO_PATCHES_APPLIED` at authorization time rather than
    silently relying on undocumented ambient state.

12. **Are parent model identity, auth, and cost surfaces actually frozen
    rather than hand-waved?** PASS, and materially strengthened by H-01's
    repair. `parent_model_route` names an exact provider package, backend,
    model id, its full catalog entry sourced directly from the pinned
    vendored `pi-ai` catalog file, an explicit non-value-bearing auth
    mechanism, and — after repair — an explicit output-token override and a
    reasoned worst-case cost derivation rather than an unexamined ceiling.

13. **Can mutable environment/profile state invalidate evidence without
    detection?** PASS. The empty local profile scaffold is recorded, and the
    byte-identity gate (item 4) prevents an unnoticed provider-source
    substitution from silently invalidating evidence.

14. **Is failure evidence sufficient to distinguish harness failure from
    child-task failure?** PASS. `failure_taxonomy` separates
    `FAIL_IMPLEMENTATION`/`FAIL_REVIEW` (task outcomes) from
    `BLOCK_CHILD_INFRA`/`BLOCK_PARENT_INFRA`/`BLOCK_AUTH`/`BLOCK_COST`
    (infrastructure outcomes), with `infrastructure_failure_and_task_failure_are_distinct
    = true`.

15. **Does the candidate reopen any invariant from PR #164?** PASS.
    `canonical_merge_gate.reopens_predecessor_permission_phase = false`; no
    field in this artifact touches Profile A, CODEX_HOME, trust state, or the
    historical B/C/D record, and the repaired provider contract
    (`approvalPolicy: never`, `sandbox: workspace-write`, preserving `cwd`
    and `ephemeral`) is referenced, not modified.

## Summary

Critical: 0

High: 1 (H-01 — the drafted spend bound was expressed in DSH "turns," but the
pinned agent-loop's per-turn step count is framework-unbounded, so a turn
ceiling alone does not bound spend). Repaired in this same candidate before
freeze, as detailed under attack 2.

Medium: 0

Low: 0

Targeted rereview: USED. One targeted rereview of H-01's repair confirmed the
added step ceiling, output-token override, and worst-case cost derivation
correctly bound worst-case episode spend to approximately $0.47 (≈2.1x margin
under the $1.00 ceiling), introduce no new live-execution authority or scope
change, and leave every other authorization field unchanged.

Conclusion: ACCEPTABLE GOVERNANCE-ONLY AUTHORIZATION, effective only after
canonical merge and bounded to one later Stage-A execution/closure PR.
