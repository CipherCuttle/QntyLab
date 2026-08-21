# DSH Stage-A V1R3 launch-plane qualification

`DSH_STAGE_A_V1R3_LAUNCH_PLANE_QUALIFICATION_V0`. Authority level
`BOUNDED_OFFLINE_LAUNCH_PLANE_QUALIFICATION`. Predecessor: PR #175 (reviewed
head `f3c864bead33d383a581200d582d1e62baca02c6`) merged to `master`
(canonical merge commit `549e8e947086aeef1ec18ea77dfb18e6f30f36ac`).

## Why this phase exists

V1R2's single authorized live episode never booted DSH: the runtime clone
actually launched had no `node_modules` and no build output, while a
*separate* clone on the same machine had the install. A pre-live
boot-readiness dry run separately crashed from the orchestrating agent's own
QntyLab worktree — not a disposable fixture — and was saved from silently
binding the DSH agent workspace to that worktree only because that
particular worktree happened to lack `tsx`. Root cause:
`LAUNCH_PLANE_NOT_HERMETIC`, refined into three additive failure modes this
phase closes:

1. Runtime materialization was not part of the qualified graph.
2. Caller cwd discipline was the only thing preventing workspace escape.
3. Executable identity binding is asymmetric (Node/Python bindable but
   unverified at the boundary at the time; Claude resolves-then-pins;
   Codex has no seam at all).

## What this phase authorizes

Local DSH runtime materialization from the pinned commit under a
frozen/offline package-manager contract; local built-profile boot of that
materialized runtime; exactly one deterministic **loopback** mock-parent
request per full-profile qualification run; a qualification-only scratch
controller/budget state; zero-model local probes (reusing V1R2's own
already-qualified native-compatibility evidence, not repeating it);
deterministic offline tests including workspace symlink/containment,
executable-fingerprint TOCTOU, and caller-cwd negative controls. (A
dedicated PATH-substitution negative control against a live DSH process is
out of scope for this offline test suite — this launcher rejects any
non-absolute executable argv outright, so there is no PATH-relative
resolution path in the launcher itself to test; the equivalent gap lives
inside pinned DSH's own Codex provider and is addressed by
`repairs/codex-executable-binding.patch`, whose landing this suite cannot
verify without a materialized checkout. See "Known residual scope" below.)

## What this phase does not authorize

Real Stage-A OpenAI secret access, any external/paid model request, any real
Codex or Claude model turn, Stage-A fixture implementation,
Qnty/QntyAgentEval execution, trading/capital execution, or Stage B. After
closure, `ACTIVE_PROJECTS = NONE`. A later live episode requires a separate,
Git-backed authorization + activation, exactly as V1R2 required after V1R2's
qualification (PR #173 → PR #174 pattern).

## Changeset

- `materializer/qntylab-materialize-dsh-runtime.mjs` — verifies pinned
  source identity via `git`, applies canonical QntyLab-owned repair patches,
  installs offline/frozen, builds, emits `runtime_manifest.json`.
- `launcher/qntylab-launch-dsh.mjs` — absolute-everything launcher; fails
  closed before any DSH spawn on identity mismatch, argv defects, or
  workspace containment violations; passes an explicit `cwd` into the child
  spawn so the launcher, not its own caller, decides where DSH runs.
- `repairs/codex-executable-binding.patch` — proposed repair routing Codex's
  executable resolution through the same `resolveExecutable` seam Claude's
  provider already uses. **Not yet verified against a materialized pinned
  checkout** — this offline environment does not clone the pinned source
  over the network, so `qntylab-materialize-dsh-runtime.mjs`'s
  `git apply --check` step is what will actually confirm or reject this
  hunk against the real tree at a future materialization run. Flagged, not
  silently assumed landed.
- `mock/qualification-openai-mock.mjs` — a small, self-contained loopback
  HTTP server satisfying the plan's mock contract (one deterministic
  plain-assistant completion, no tool call, inspectable captured request).
  **Deviation from the plan's literal wording**: the plan calls for reusing
  the pinned source's own `packages/test-support/llm-mock-server`; no
  materialized pinned checkout is available in this offline environment to
  import that package from, so this file is a compatible stand-in, not that
  package. Flagged explicitly rather than mislabeled as reuse.
- `qualification.json` — the offline qualification receipt for this run of
  the launcher/materializer/mock contract tests.
- `hostile_review.md` — the one independent hostile review this phase's
  bounded-completion policy requires.
- `tests/test_dsh_stage_a_v1r3_launch_plane_qualification.py` — offline,
  no-network tests covering the launcher/materializer contract logic and the
  negative/variance matrix rows that do not require a real pnpm-installed
  pinned checkout.

## Known residual scope (named, not silently assumed closed)

- **No live pinned-commit materialization was executed in this phase.**
  This sandboxed implementation environment has no network access to clone
  `deepseek-ai/deepseek-harness` and no local pnpm store pre-populated with
  its dependency graph. `qntylab-materialize-dsh-runtime.mjs` is
  unit/contract-tested against synthetic fixtures (a fake pinned-source
  tree and a fake node_modules/build layout), not against a real
  materialization of commit `99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`. A
  real materialization run is required before any later live episode, and
  will be the first real exercise of `verifySourceIdentity`,
  `applyCanonicalPatches`, `installOffline`, and `buildRuntime` against
  the actual pinned tree — including confirming the exact
  `pnpm install --offline --frozen-lockfile`-class contract from
  `package.json#packageManager`/`pnpm-workspace.yaml`, and the pinned
  adapter's exact wire protocol (Chat Completions vs. Responses API), both
  named as open PLAN RISKS rather than assumed here.
- **The Codex executable-binding repair is proposed, not landed or
  compiled.** See the flag on `repairs/codex-executable-binding.patch`
  above. PASS 3 of the plan's red team names this as the one item whose
  closure depends on new code actually landing and passing its own review,
  not configuration alone; that remains true after this implementation
  pass.
- **The full-profile mock boot end-to-end run (materializer → launcher →
  real DSH `--profile headless` boot → loopback mock → clean exit) was not
  executed**, for the same reason: no materialized pinned runtime exists in
  this environment to boot. The launcher's own preflight/containment/
  fingerprint logic, and the mock server's request/response contract, are
  tested directly; the end-to-end boot is not.

These three items are exactly the ones that make `QUALIFIED_LAUNCH_CONTRACT_DIGEST`
non-issuable from this phase alone — this phase closes the *launch-plane
contract* (materializer/launcher/manifest/executable-identity logic,
workspace isolation, offline test coverage) but does not itself produce a
real qualified runtime instance. A later phase that runs materialization
against the real pinned commit on a machine with the required offline pnpm
store and network-clone access is required before any live episode may cite
this phase's digest.

## Verification

```sh
node --test tests/fixtures/dsh_stage_a_v1r3/*.mjs   # (if present)
python -m pytest tests/test_dsh_stage_a_v1r3_launch_plane_qualification.py -q
```

No live DSH, OpenAI, Codex, or Claude call is part of this phase.
