# Stage-A runnable profile — frozen build/materialization procedure

This is the exact, deterministic procedure the later
`DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_EXECUTION_V0` phase must follow to
produce a runnable DSH build that actually exposes both child delegation
tools and consumes the canonical repaired Codex provider — not a procedure
it must invent.

## 0. Directory layout (all disposable, created fresh per run)

```text
build_root/                            disposable copy of the pinned commit, built
├── packages/subagent/subagent-codex/       -> repaired wire.ts after step 3+4
├── packages/subagent/subagent-claude-code/
├── apps/cli/lib/bin.js                     the `dsh` binary this procedure invokes
└── .dsh-home/                              DEDICATED disposable DSH_HOME (env DSH_HOME=build_root/.dsh-home)
    └── profiles/
        └── stage-a-v0/
            ├── package.json                frozen, this directory, byte-exact
            └── cordis.patch.yml             frozen, this directory, byte-exact
```

`DSH_HOME` must be set to `build_root/.dsh-home` for every command below.
Nothing outside `build_root` is read or written. An ambient `~/.dsh` (the
real host DSH_HOME, if any) is never referenced: `--dump-config`'s home-layer
lookup (`$DSH_HOME/cordis.patch.yml`) resolves under the dedicated,
freshly-created `build_root/.dsh-home`, which this procedure never populates
with a home-level patch file, so that lookup is always empty. `HOME` itself
(distinct from `DSH_HOME`) stays the normal host `HOME`, because native Codex
and Claude Code child auth reads real host product/account state — `HOME`
and `DSH_HOME` are separate controls, and only `DSH_HOME` is disposable here.

## 1. Reference checkout (read-only)

`source_root` = a pristine checkout of pinned commit
`99f6f02fecdb7dff40c3fbc9470f5907c29f74ca` (tree
`3bc8f89fe494a4755c188be354add4e8b1e7b188`, tag `dsh-v0.1.0-rc.7`) of
`deepseek-ai/deepseek-harness`. Never written to.

## 2. Disposable build root

`build_root` = a full copy of `source_root` (e.g. `git worktree add` or an
equivalent copy) outside the upstream checkout. This is the only tree that
gets built or mutated.

## 3. Materialize the repaired provider

Call the existing, unmodified
`qntylab.pinned_dsh_provider_boundary_repair_v0.materialize_provider_boundary(source_root, build_root)`.
This fails closed on any pinned-identity or digest mismatch, and writes the
repaired `packages/subagent/subagent-codex/src/wire.ts` into `build_root` at
the same relative path. Record the returned `postimage_source_sha256`.

## 4. Build

```sh
cd build_root
pnpm install
pnpm run build
```

This step recompiles `packages/subagent/subagent-codex`'s `lib/` output (and
everything else) from the now-repaired `src/wire.ts`, and is what makes the
running provider code the repaired one rather than the pristine upstream
compiled output.

## 5. Compose the disposable Stage-A profile

Create `build_root/.dsh-home/profiles/stage-a-v0/` and copy this directory's
`package.json` and `cordis.patch.yml` into it byte-exact (digests below).
Their content assumes exactly this directory depth (`link:../../../...`
resolves to `build_root/packages/subagent/...`); do not relocate the profile
elsewhere without recomputing those relative paths.

```sh
mkdir -p "$DSH_HOME/profiles/stage-a-v0"
cp profile/package.json profile/cordis.patch.yml "$DSH_HOME/profiles/stage-a-v0/"
cd "$DSH_HOME/profiles/stage-a-v0"
pnpm install
```

The profile's `pnpm install` here only resolves the two `link:` entries in
its `dependencies` (see step 5a) -- symlinks to the real packages inside
`build_root`, never a registry fetch for either of them, and no other
dependency is declared.

### 5a. Why the two subagent provider packages need an explicit link

`dsh-base`'s own patch layer (`packages/bundle/base/cordis.patch.yml`)
already inserts generic subagent spawn/fork infrastructure (`subagent`,
`subagent-spawn-in-process`, `subagent-fork-in-process`,
`tool-subagent-control`, `tool-subagent` provider:spawn, `tool-subagent-fork`
provider:fork, `tool-subagent-report`) and a *dormant* `llm-pi-ai` row and a
*default* `agent-default-model` row -- but neither `dsh-base` nor
`dsh-headless` lists `@deepseek-ai/dsh-subagent-codex` or
`@deepseek-ai/dsh-subagent-claude-code` as a dependency (confirmed: absent
from both bundle `package.json` files). Per the pinned resolution algorithm
(`packages/boot/app-boot/src/profile.ts`, `healProfilesModuleFallback`),
packages outside the `dsh` app's own dependency closure are **not** included
in the flat `$DSH_HOME/profiles/node_modules` fallback, so they must resolve
from the profile's own `node_modules` -- populated by the profile's own
`pnpm install`. Declaring them as ordinary registry dependencies there would
default to fetching a published (unrepaired) copy from the npm registry,
silently bypassing the repair. The `link:` protocol used in
`profile/package.json` avoids that entirely: it is a local symlink, resolved
with no registry lookup, pointed at the exact `build_root` packages this
procedure just built in step 4.

### 5b. Why the patches target existing rows, not new ones

`dsh-base` already declares `id: llm-pi-ai` (mounted dormant, zero routes)
and `id: agent-default-model` (defaulting to `deepseek-official`/
`deepseek-v4-flash`). `cordis.patch.yml` in this directory therefore
**patches** both by `id` (no `name`, replacing the row's whole `config`, per
the base bundle's own documented "last write wins per row" semantics) rather
than inserting a second, colliding `llm-pi-ai` row. `subagent-codex`,
`subagent-claude-code`, and their two delegation tools genuinely do not
exist in the base composition and are `insert`ed, in the same shape as the
pinned source's own `examples/acp-agent/product-subagent-both.cordis.yml`.

## 6. Verify before any live call (no network, no model call)

Three independent, offline checks, all required to pass before the later
phase makes its first live call:

1. **Provider-source identity.** Call
   `qntylab.pinned_dsh_provider_boundary_repair_v0.captured_thread_start_contract(build_root/packages/subagent/subagent-codex/src/wire.ts)`.
   A clean return (no `ProviderBoundaryError`) is the byte-identity proof
   against raw upstream source.
2. **Composition identity, exact allowlist.** Run
   `build_root/apps/cli/lib/bin.js --profile stage-a-v0 --dump-config`
   (documented by the pinned CLI's own `dump-config.ts` as composing patch
   layers only -- no cordis context is booted, so no plugin `apply()` runs
   and no network or model call occurs). Assert the dumped tree:
   - patches `llm-pi-ai` (not re-inserts it) to exactly one route, `openai`,
     with `apiKeyEnv: OPENAI_API_KEY`, `retryPolicy.maxRetries: 0` (H-04: not
     2 -- `step/start` fires once per step before `step()`'s own internal
     retry loop, so a retry never creates a new `step/start` event, and a
     step-count-only guard cannot see or bound them; disabling retries
     entirely makes one step exactly one request attempt), and a
     `models` override of exactly `[{id: gpt-5-mini, maxTokens: 4096}]`;
   - patches `agent-default-model` to exactly
     `{provider: openai, model: gpt-5-mini}`;
   - inserts exactly `subagent-codex`, `subagent-claude-code`,
     `tool-subagent-codex` (provider `codex`, toolName `subagent_codex`),
     and `tool-subagent-claude-code` (provider `claude-code`, toolName
     `subagent_claude_code`);
   - contains no other `llm-*` row, and no other `tool-subagent*` row beyond
     the ones `dsh-base` itself already inserts (`tool-subagent`
     provider:spawn, `tool-subagent-fork` provider:fork,
     `tool-subagent-control`, `tool-subagent-report`) plus the two new ones
     above -- i.e. the assertion is an exact allowlist of expected
     base/headless infrastructure plus exactly the required Stage-A
     additions, not a bare "nothing else" check.
3. **Package resolution identity.** Confirm
   `$DSH_HOME/profiles/stage-a-v0/node_modules/@deepseek-ai/dsh-subagent-codex`
   is a symlink whose real path is `build_root/packages/subagent/subagent-codex`
   (not a `.pnpm` store copy of a registry-fetched package).

Only after all three checks pass may the later phase run
`build_root/apps/cli/lib/bin.js --profile stage-a-v0 "<task>"` for its one
authorized parent episode.

## 7. Raw-upstream fallback is structurally excluded

`source_root` is never built or run directly; only `build_root`, whose
provider source and package resolution have been verified by step 6, is
ever invoked. There is no code path in this procedure that runs the DSH
parent against unrepaired upstream provider source or a registry-fetched
provider package.

## 8. This authorization phase did not execute this procedure

Steps 2-6 were not run live during authorization or its repairs.
Steps 1-5b are verified by direct reading of the pinned source (bundle
patch files, provider `src/index.ts` registration calls, the `profile.ts`
resolution algorithm, and `dump-config.ts`'s own boot-free implementation) --
cited by exact file path throughout this document -- rather than asserted.
A live `build_root` with pre-existing `node_modules`/`lib/` output does
exist locally and step 6's checks are technically executable without a new
`pnpm install`, but this repair did not exercise that authority: a real
`pnpm`/build invocation cannot be guaranteed free of incidental network
activity (registry/version/telemetry checks), which would exceed the
explicit "no network request is intentionally made" condition of the
narrow offline authority granted for this repair. If a live, executed
`--dump-config` proof is wanted, it requires separate explicit
authorization that accepts that residual network-activity risk.
