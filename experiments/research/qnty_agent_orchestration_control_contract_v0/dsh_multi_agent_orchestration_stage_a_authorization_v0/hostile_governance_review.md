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

## Post-publication closure repair — H-02

**Source:** an external pre-merge closure review of the published draft PR
#165, not a self-generated finding.

**H-02 — RUNNABLE_PROFILE_NOT_FROZEN_AT_AUTHORIZATION_CLOSURE.** The
authorization required this phase to freeze the exact reproducible runnable
DSH profile/materialization path. The published candidate instead deferred
the exact build step, the exact `cordis.patch.yml` provider registration, and
the byte-identity gate to `later_phase_must_establish` — prose requiring the
*execution* phase to invent the profile, not a frozen contract for it to
*consume*. That is a real gap against the phase's own closure criteria, not a
manufactured one: this candidate's own VERIFY report before publication
already flagged `RUNNABLE_PROFILE_DEFINED = PARTIALLY`.

**Repair (this commit):** replaced the deferred prose with a frozen,
file-backed contract:

- `profile/package.json` and `profile/cordis.patch.yml` — byte-exact profile
  files, digested in `authorization.json.runnable_profile_composition.profile_files_sha256`.
  The `cordis.patch.yml` insert/id-patch shapes are not invented: they are
  adapted directly from two real files in the pinned source tree
  (`examples/acp-agent/product-subagent-both.cordis.yml` for the
  subagent-codex/subagent-claude-code insert entries, and
  `examples/headless-agent/tests/fixtures/headless-profile.cordis.yml` for
  the `agent-default-model` id-patch shape), and parsed with PyYAML in this
  repository's own test suite to confirm they produce the exact intended
  structure.
- `profile/PROFILE.md` — the seven-step deterministic procedure (reference
  checkout → disposable build root → call the existing unmodified
  `materialize_provider_boundary` → build → compose the frozen profile →
  two offline verification gates → only then the later phase's one live
  call), naming exact function calls and exact CLI invocations
  (`--dump-config`, documented by the pinned `apps/cli` README as inspecting
  the composed plugin tree with no model or network call) rather than
  prose intentions.
- `authorization.json.runnable_profile_composition` renamed its governing
  field from `later_phase_must_establish` to
  `later_phase_must_materialize_and_verify` and now points at these frozen
  files instead of describing them abstractly.

**H-01's spend controls, model selection, child routes, and synthetic task
are unchanged by this repair** — verified: `gpt-5-mini`, the `$1.00`
ceiling, the 8-step budget, the `4096`-token output override, the
parent-only `OPENAI_API_KEY` scope, and native Codex/Claude auth are
byte-identical to the previously reviewed values, and the `cordis.patch.yml`
frozen here encodes the exact same `maxTokens: 4096` / `maxRetries: 2` /
`gpt-5-mini` values as H-01's repair, not new ones.

**Live calls during this repair:** 0. **Authorization spend:** $0.

**Review-budget status:** the phase's frozen `review_policy` authorized
exactly one hostile review plus one targeted rereview, and both were already
consumed closing H-01. Per explicit instruction, no second independent
rereview was performed for H-02 — this repair is recorded as an externally
discovered, pre-merge closure-blocking fix applied directly, not as a second
rereview invented under the original budget. If canonical QntyLab governance
requires an independent rereview of a post-publication High repair before
this candidate may be treated as merge-ready, that is a distinct budget this
phase does not have standing authority to grant itself; it would require
explicit user extension before being performed.

Critical (H-02 pass): 0. High (H-02 pass): 1, repaired as above. Medium: 0.
Low: 0.

## Post-publication closure repair — H-03

**Source:** a single explicitly-authorized supplemental closure rereview of
the H-02 repair, externally performed, not a self-generated finding and not
a second broad hostile review. Per explicit instruction, this is the final
independent review round for this authorization; H-03's closure is
mechanical (source evidence + tests + CI), not another review cycle.

**H-03 — FROZEN_STAGE_A_PROFILE_NOT_ACTUALLY_DELEGATION_CAPABLE.** The H-02
repair froze a `cordis.patch.yml` that mounted `subagent-codex`,
`subagent-claude-code`, `llm-pi-ai`, and patched `agent-default-model`, but:

1. It never mounted the model-facing delegation tools
   (`tool-subagent-codex`, `tool-subagent-claude-code`). Confirmed by
   reading `packages/subagent/subagent-codex/src/index.ts` and
   `.../subagent-claude-code/src/index.ts`: each calls only
   `ctx.subagents.registerProvider(...)` — the provider packages add no
   parent-visible tool by themselves, so the frozen profile, as written,
   would have booted with no way for the DSH parent to actually delegate to
   either child.
2. `packages/bundle/base/cordis.patch.yml` (read directly) already inserts
   `id: llm-pi-ai` (dormant, zero routes) and `id: agent-default-model`
   (defaulting to `deepseek-official`/`deepseek-v4-flash`). H-02's
   `cordis.patch.yml` re-`insert`ed a second `llm-pi-ai` row instead of
   patching the existing one — a colliding duplicate id, not a working
   override.
3. `profile/package.json`'s empty `dependencies` gave no resolution path for
   `@deepseek-ai/dsh-subagent-codex`/`-claude-code`, which are confirmed
   absent from both `dsh-base` and `dsh-headless` bundle dependencies and
   therefore excluded from the flat `$DSH_HOME/profiles/node_modules`
   fallback (`packages/boot/app-boot/src/profile.ts`,
   `healProfilesModuleFallback`, BFS over the app's own dependency closure
   only). Left unresolved, a naive fix (declaring them as ordinary registry
   dependencies) would silently fetch an unrepaired published copy from the
   npm registry instead of the QntyLab-repaired `build_root` package.
4. The dump-config assertion ("no other llm-* or subagent-* instance") was
   overbroad: `dsh-base` itself already mounts generic
   `subagent`/`subagent-spawn-in-process`/`subagent-fork-in-process`/
   `tool-subagent-control`/`tool-subagent`(spawn)/`tool-subagent-fork`/
   `tool-subagent-report` rows unrelated to Stage-A.

**Repair (this commit):** `cordis.patch.yml` now **patches** the existing
`llm-pi-ai` and `agent-default-model` rows by `id` (no `name`, replacing
their whole `config`, matching the base bundle's own documented "last write
wins per row" semantics — the same shape already used correctly for
`agent-default-model` in H-02) instead of re-inserting `llm-pi-ai`, and
`insert`s two new tool rows (`tool-subagent-codex`, provider `codex`,
toolName `subagent_codex`; `tool-subagent-claude-code`, provider
`claude-code`, toolName `subagent_claude_code`), in the exact config shape
used by the pinned source's own
`examples/acp-agent/product-subagent-both.cordis.yml`. `profile/package.json`
now declares both provider packages via `link:../../../packages/subagent/...`
— a local-path protocol that never queries a registry — relative to a newly
frozen, fixed directory layout (`build_root/.dsh-home/profiles/stage-a-v0/`,
documented in `PROFILE.md` section 0) that also serves as the dedicated,
non-ambient `DSH_HOME` H-03 point 4 required. `PROFILE.md`'s verification
section now names three gates (provider-source identity, an exact allowlist
composition check distinguishing `dsh-base`'s own infrastructure from the
required Stage-A additions, and package-resolution identity confirming the
installed symlink resolves into `build_root`) instead of two.

**H-01's spend controls, model selection, child auth routes, and the
synthetic task are unchanged** — verified: the patched `llm-pi-ai` row
encodes the identical `gpt-5-mini`/`4096`/`OPENAI_API_KEY`/`maxRetries: 2`
values as before, cross-checked directly against `parent_model_route` in a
new test.

**Live calls:** 0. Two offline `--dump-config` invocations were authorized
for this repair; **zero were exercised**. A locally pre-built checkout
(`node_modules`/`lib/` already present from an earlier, unrelated setup)
makes the check technically runnable without a fresh `pnpm install`, but a
real `pnpm`/build invocation cannot be guaranteed free of incidental network
activity (registry/version/telemetry checks), which would exceed the
narrow authority's explicit "no network request is intentionally made"
condition — so this repair relied on direct source-file verification only
(every claim above cites an exact pinned-source path). **Authorization
spend:** $0.

**Review-budget status:** this was the single explicitly-authorized
supplemental closure rereview; per instruction, no further independent
review was initiated. Closure of H-03 rests on the source citations above
plus the mechanical gates below, not another review round.

Critical: 0. High: 1 (H-03, repaired as above). Medium: 0. Low: 0.

Conclusion (updated): the frozen Stage-A profile is now delegation-capable
by construction (both child tools mounted, provider resolution pinned
off-registry into the repaired build, existing dsh-base rows patched rather
than collided with) and verified against 28/28 targeted tests plus the full
canonical check suite. Still effective only after canonical merge; still
authorizes zero live execution in this phase.
