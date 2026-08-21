# Stage-A runnable profile — frozen build/materialization procedure

This is the exact, deterministic procedure the later
`DSH_MULTI_AGENT_ORCHESTRATION_STAGE_A_EXECUTION_V0` phase must follow to
produce a runnable DSH build that consumes the canonical repaired Codex
provider — not the procedure it must invent.

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

## 5. Compose the disposable Stage-A profile

Copy this directory's `package.json` and `cordis.patch.yml` (frozen, byte-exact,
digests below) to `$DSH_HOME/profiles/stage-a-v0/`. This is a profile
dedicated to Stage-A, not the ambient user `headless` profile. It resolves to
exactly:

- `@deepseek-ai/dsh-base` + `@deepseek-ai/dsh-headless` bundle layers (empty
  patches, per the pinned bundle defaults), then
- this profile's `cordis.patch.yml`, inserting `subagent-codex`,
  `subagent-claude-code`, and `llm-pi-ai` (registered with exactly one route,
  `openai`, reading `OPENAI_API_KEY`, `retryPolicy.maxRetries: 2`, and a
  `gpt-5-mini` catalog override narrowing `maxTokens` to `4096` — the H-01
  spend-boundedness control, unchanged), and patching `agent-default-model`
  to `{provider: openai, model: gpt-5-mini}`.

No other plugin, provider, or model is registered by this patch layer.

## 6. Verify before any live call (no network, no model call)

Two independent, offline checks, both required to pass before the later
phase makes its first live call:

1. **Provider-source identity.** Call
   `qntylab.pinned_dsh_provider_boundary_repair_v0.captured_thread_start_contract(build_root/packages/subagent/subagent-codex/src/wire.ts)`.
   This function itself raises `ProviderBoundaryError` unless the file's
   `startThread` span byte-matches the frozen repaired postimage digest — so
   a clean return *is* the byte-identity gate against raw upstream source.
2. **Profile-composition identity.** Run
   `build_root/apps/cli/lib/bin.js --profile stage-a-v0 --dump-config`
   (documented by the pinned CLI as inspecting the composed plugin tree
   without booting it — no model or network call). Assert the dumped tree
   contains exactly the four inserted/patched ids above with the exact
   config in this directory's `cordis.patch.yml`, and no other `llm-*` or
   `subagent-*` plugin instance.

Only after both checks pass may the later phase run
`build_root/apps/cli/lib/bin.js --profile stage-a-v0 "<task>"` for its one
authorized parent episode.

## 7. Raw-upstream fallback is structurally excluded

`source_root` is never built or run directly; only `build_root`, whose
provider source has been verified by step 6.1 to be the repaired postimage,
is ever invoked. There is no code path in this procedure that runs the DSH
parent against unrepaired upstream provider source.
