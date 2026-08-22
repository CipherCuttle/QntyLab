# DSH Stage-A V1R3R1 real runtime qualification

`DSH_STAGE_A_V1R3R1_REAL_RUNTIME_QUALIFICATION_V0`. Authority level
`BOUNDED_OFFLINE_LAUNCH_PLANE_QUALIFICATION` (unchanged from V1R3). Predecessor:
PR #176 (reviewed head `24bf629de36258520cdb73866d907c5633ca1e2c`) merged to
`master` (canonical merge commit `8ad4a92f3447ba7fff27cefc72fc1f258f07f2be`).

## Why this phase exists

PR #176 closed the launch-plane *contract* (materializer/launcher/manifest
logic, workspace isolation, offline test coverage) but explicitly could not
run real pinned-commit materialization, land/compile the Codex
executable-binding repair, or run an end-to-end full-profile mock boot — no
network clone access and no offline pnpm store were available in that
implementation environment. V1R3R1 closes exactly those three residual items,
using the canonical #176 materializer/launcher/mock as the baseline and only
patching them where real execution against the actual pinned tree exposed a
concrete defect.

## What this phase authorizes

Real acquisition and materialization of `deepseek-ai/deepseek-harness`
commit `99f6f02fecdb7dff40c3fbc9470f5907c29f74ca` (tag `dsh-v0.1.0-rc.7`);
real compilation of a corrected Codex executable-binding repair; a real
built DSH CLI; a real headless-profile boot through the canonical launcher
against exactly one deterministic loopback mock-parent request; caller-cwd
variance proof; a scratch budget-gate ceiling proof; and issuance of
`QUALIFIED_LAUNCH_CONTRACT_DIGEST`.

## What this phase does not authorize

Real Stage-A OpenAI secret access, any external/paid model request, any real
Codex or Claude model turn, Stage-A fixture implementation,
Qnty/QntyAgentEval execution, trading/capital execution, or Stage B. After
closure, `ACTIVE_PROJECTS = NONE`. A later live episode requires a separate,
Git-backed authorization + activation.

## Concrete defects found by real execution, and their corrections

Real materialization and boot surfaced four defects the predecessor's
contract-only tests could not — each is a corrected QntyLab-owned artifact
here, not a hand-edit of pinned upstream source outside the patch/overlay
mechanisms:

1. **`repairs/codex-executable-binding.patch` did not apply.** The V1R3
   version was written from source citations with placeholder
   `index 0000000000..0000000000` hunk headers, never checked against a real
   tree. Real `git apply --check` against the pinned commit failed
   (`error: corrupt patch at line 46`): the real `codexAppServerArgv()`
   already takes a `platform` parameter with a `win32` `cmd.exe` branch, and
   the real resolve-then-pin seam for the sibling Claude provider lives in
   `subagent-claude-code/src/index.ts`'s `start()`, not in `run.ts`. This
   phase's `repairs/codex-executable-binding.patch` is a corrected
   QntyLab-owned repair generated directly from the real pinned tree,
   reproducing the same architectural intent (resolve `codex` once via
   `ctx.subprocess.resolveExecutable`, pin the absolute path into argv before
   spawn) against the real call sites in `index.ts`/`run.ts`, plus the one
   pinned unit-test file that asserted the old contract. `git apply --check`
   now passes cleanly against a pristine pinned checkout; the repaired
   package's own 32-test suite (`subagent-codex.spec.ts`) passes after the
   change; the built `packages/subagent/subagent-codex/lib/index.js` was
   inspected directly and shows `resolveExecutable("codex", ...)` feeding
   `codexAppServerArgv(spec.executable)` — the real native Codex spawn now
   uses a resolved absolute path pinned once, not a bare `'codex'` string
   re-resolved by the OS at `execve`.
2. **`npm run build:lib:host` alone does not produce a bootable runtime.**
   Several composition-critical packages (`dsh-typert-registry`,
   `dsh-api-gateway`, …) use a package-local `tsdown.config.ts` built on the
   shared `clientBundle()` preset, which — without `hostPhase: true` — emits
   the package's Node `lib/index.js` half only during the **Client** tsdown
   pass, not the Host pass the predecessor's materializer defaulted to. A
   real boot against a host-only build failed closed with
   `ERR_MODULE_NOT_FOUND` for exactly those packages. This phase's
   materialization driver runs the full `pnpm run build:lib` (host **and**
   client passes), matching what a real bootable runtime requires; this is a
   driver-level correction (the materializer's `buildRuntime()` function
   itself is unchanged and still accepts an explicit `buildScript`).
3. **The canonical launcher's `--profile` contract did not match the real
   pinned CLI.** V1R3's launcher required `--profile` to be an absolute,
   existing filesystem path, and forwarded that literal value into the
   spawned DSH argv. The real pinned CLI (`apps/cli/src/args.ts`,
   `packages/boot/app-boot/src/profile.ts`) takes a bare profile **name**
   resolved under `$DSH_HOME/profiles/<name>` — never a path. A real launch
   attempt reproduced exactly that rejection. `launcher/qntylab-launch-dsh.mjs`
   is corrected to require a non-empty, non-path profile name (DSH's own
   `resolveProfileDir` already rejects an unsafe name once it tries to
   resolve it under the launcher-verified absolute `--dsh-home`); the one
   affected offline unit-test fixture is updated to match.
4. **The V1R3 qualification mock spoke the wrong wire shape.** The real
   pinned `@earendil-works/pi-ai` `openai-completions` route always requests
   `stream: true` and parses an SSE `chat.completion.chunk` stream; V1R3's
   mock returned a single plain-JSON `chat.completion` body regardless. A
   real full-profile boot against the original mock reproduced exactly the
   adapter's own `Stream ended without finish_reason` error, and
   `dsh-llm-retry` silently resent the request three additional times
   (`MOCK_PARENT_WIRE_REQUESTS` briefly proven wrong: 4, not 1).
   `mock/qualification-openai-mock.mjs` now emits a minimal, valid SSE
   `chat.completion.chunk` stream when the real adapter's `stream: true`
   request arrives, while still serving a plain-JSON body for a
   non-streaming caller (kept for the existing contract tests, all 19 of
   which still pass unmodified against the corrected mock).

## Additional qualification-only artifacts this phase adds (not in #176)

- `driver/qualification.patch.yml` — a `--patch` overlay narrowing the
  headless profile's default tool surface to exactly `subagent_codex` /
  `subagent_claude_code` (disabling every other default model-facing tool
  row: bash/pwsh/jobs/fs/fs-search/skill/generic-subagent/fork/workflow/
  result-pruner/todo/goal/ralph/str-replace-editor/web/plan-mode), disabling
  `session-title-llm` (a second, title-generation parent request the base
  profile issues by default), and pointing the `openai` `llm-pi-ai` route at
  the loopback mock with a qualification-only fake credential env reference.
- `gate/qualification-budget-gate.mjs` — a minimal, generic scratch
  budget/controller gate (reservation-before-adapter-I/O semantics, 8-request
  ceiling) for this phase's own scratch state. Deliberately **not** the
  `qntylab.dsh_stage_a_v1_hard_orchestration` Python module from a prior,
  differently-scoped phase (`DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_V1_HARD_
  ORCHESTRATION_AUTHORIZATION_V0`) — that module is a specific
  IMPLEMENT/TEST/REVIEW workflow state machine tied to one frozen fixture,
  not a generic per-request ceiling gate, though its already-reviewed
  `gated-provider.mjs` architecture (`await gate.authorize()` fully resolves
  before `rawProvider.start()` is ever reached) is the pattern this gate's
  ordering guarantee mirrors.
- `driver/*.mjs` — the real materialization driver, the real launcher-driven
  full-profile driver, the caller-cwd-variance boot-only driver, and the
  budget-gate ceiling test driver used to produce this phase's evidence.
- `evidence/runtime_manifest.json`, `evidence/digests.json`,
  `evidence/compute-digests.mjs` — the real manifest this phase's
  materialization run emitted, and the four qualification digests computed
  from its identity-bearing fields only (ephemeral scratch paths and the
  materialization timestamp are excluded from every digest input).

## Evidence summary

- **Source identity**: cloned `deepseek-ai/deepseek-harness`, checked out
  `99f6f02fecdb7dff40c3fbc9470f5907c29f74ca`; `git rev-parse HEAD` and
  `git rev-parse HEAD^{tree}` both verified; `git tag --points-at HEAD`
  confirmed `dsh-v0.1.0-rc.7` points at the same commit; working tree clean.
- **Dependency acquisition**: `pnpm fetch --frozen-lockfile` against a
  dedicated store under the authorized scratch root (923 packages resolved).
- **Qualification install**: `pnpm install --offline --frozen-lockfile`
  against that store — no network fetch attempted or required.
- **Build**: `pnpm run build:lib` (host + client passes) — PASS.
- **Codex repair**: applied cleanly, compiled cleanly, package's own 32-test
  suite passes, compiled bytes inspected directly (see above).
- **Full-profile boot**: canonical launcher → real materialized runtime →
  built CLI → real `headless` profile → real Cordis/plugin composition → real
  Agent/session creation → actual parent llm/stream → actual `llm-pi-ai`
  OpenAI `openai-completions` route → loopback deterministic mock → clean
  settlement. Exit code 0. Stdout: the mock's exact deterministic completion
  text. Exactly **one** wire request; its `tools` field names exactly
  `subagent_codex` and `subagent_claude_code`; zero retries; zero auxiliary
  requests (title generation disabled).
- **Session/workspace proof**: the written session's own header records
  `"cwd":"/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1/workspace/run1"` —
  read directly from the real, decompressed session log, not inferred from
  argv — matching the launcher's `--workspace` and the launcher-computed
  `workspaceReal`.
- **Caller-cwd variance**: the same preflight+spawn path, run from the
  QntyLab repo root, the DSH source root, and an unrelated scratch directory,
  all bound the same explicit `--workspace` regardless of caller `cwd`
  (boot-only `--dump-default-config` variant — no additional parent mock
  request).
- **Budget gate**: attempts 1–8 reserved, attempt 9 denied
  (`qualification-budget-gate.mjs`), before any adapter I/O by construction
  (the reservation function performs no I/O other than the durable counter
  write itself).
- **Network (evidence level stated honestly, per hostile_review.md)**: no
  network namespace or firewall isolation was applied; evidence is
  configuration-plus-observation only. The `openai` route's `baseURL` was
  explicitly overridden to the loopback mock's own ephemeral `127.0.0.1`
  address, the credential was a fake, non-functional string, and the mock's
  request log shows exactly one request, from the DSH process, to itself —
  no package-registry, GitHub, OpenAI, or Anthropic access was observed
  during the boot. This does not constitute a kernel-level guarantee that no
  other outbound connection could have succeeded, only that the one
  configured route pointed at loopback and the one observed request came
  through it. The pnpm dependency fetch was a separate, earlier, explicitly
  network-permitted acquisition step, not part of the qualification
  execution itself.
- **Operational note (self-corrected)**: one intermediate diagnostic command
  (`dsh --profile headless --dump-config`) was run without `DSH_HOME`
  explicitly set and landed against the operator's real, pre-existing
  `~/.dsh` profile home instead of the scratch root. Its only effects were
  idempotent — a re-write of `~/.dsh/profiles/node_modules` symlinks (a
  BFS-derived, self-healing fallback DSH itself performs on every boot) and
  a re-write of the profile's already-templated `cordis.yml` root file (also
  rewritten by DSH on every `prepareProfile()` call) — plus two symlinks this
  phase's own driver added for the two subagent packages, which were
  identified and removed immediately upon discovery. No `~/.dsh` session,
  credential, or settings data was created, altered, or deleted. Every
  subsequent command in this phase explicitly sets `DSH_HOME` to the scratch
  root.

## Verification

```sh
node --test test/qntylab-dsh-v1r3r1.test.mjs   # 19 offline contract tests (copied/verified unmodified from #176's suite against the corrected artifacts)
node driver/run-materialize.mjs                # real materialization -> evidence/runtime_manifest.json
node driver/run-via-launcher.mjs <workspace>    # decisive full-profile boot (requires the real materialized runtime under the scratch root)
node driver/run-boot-only-variant.mjs <cwd>     # caller-cwd variance (boot-only, no parent request)
node driver/run-budget-gate-test.mjs            # 1..8 permitted / 9 denied
node evidence/compute-digests.mjs               # regenerate evidence/digests.json
```

No live DSH-driven model call, real OpenAI/Anthropic request, or paid spend
is part of this phase.

## Post-PR H-01..H-04 repair and targeted rereview

The previously issued contract digest `3bf649f5cbdd96dcc0edf91cd7dfb88b3245ff3617518c9d5da3dfbd5a01a18e` is invalidated as
`SUPERSEDED_INVALID_DIGEST_CANONICALIZATION`. The repair was performed once
on this existing PR branch:

- H-01: `evidence/canonical-json.mjs` recursively sorts every object key,
  preserves array order, and includes every field; the four new regression
  tests prove nested identity/policy drift changes the relevant digest and
  insertion order does not.
- H-02: `driver/run-materialize.mjs` requires a fresh pristine source,
  verifies identity, applies the committed V1R3R1 patch through
  `applyCanonicalPatches()`, then performs install/build/manifest emission.
  It contains no prior-session or already-patched bypass.
- H-03: `buildRuntime()` and the decisive driver use `pnpm run build:lib`.
  The full-build client artifacts were present and the real CLI booted.
- H-04: the manifest now binds phase, repository/commit/tree/tag, lockfile,
  declared and actual pnpm identity, installed Claude SDK identity, patch,
  overlay, and built artifacts. `verifySourceIdentity()` checks HEAD,
  HEAD\^{tree}, and the tag, failing closed on drift.

One targeted rereview attempted to falsify all four findings: nested digest
drift, pristine patch application, full build provenance, source identity
fail-closed behavior, pnpm identity visibility, invalid-digest retirement,
and conversation-independent reconstruction. Result: `CRITICAL = 0`,
`HIGH = 0`. The network limitation remains truthful and unchanged:
configuration-plus-observation, without a kernel/network namespace guarantee.
Per the bounded completion rule, no broad architecture review is reopened.

Corrected digests:

```text
RUNTIME_MANIFEST_DIGEST = de0cc23e5e71c034f6cd403627452305338d32a29a3282c71fd2315d005fd314
EXECUTABLE_IDENTITY_DIGEST = ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9
LAUNCH_POLICY_DIGEST = b73a3932d6f8f32966de717076cde532a7b6a8472685ffbc7383c73cd7bcafa1
QUALIFIED_LAUNCH_CONTRACT_DIGEST = 4cd2734f229a97d4258ace4576f23f76f3d36aeef888a19fa61d2f4a7bff37d4
```
