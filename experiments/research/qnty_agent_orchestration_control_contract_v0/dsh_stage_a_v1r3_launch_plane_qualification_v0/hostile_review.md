# V1R3 hostile review

One independent, read-only, adversarial review of the launcher/materializer/
mock changeset, run against the changed files listed in `PHASE.md`, plus one
narrowly-scoped targeted rereview of the resulting Critical/High fixes
(bounded-completion policy: fix Critical/High only, one targeted rereview
only if repairs occurred).

## Pass 1 — independent hostile review

Scope: `launcher/qntylab-launch-dsh.mjs`, `materializer/qntylab-materialize-dsh-runtime.mjs`,
`mock/qualification-openai-mock.mjs`, `repairs/codex-executable-binding.patch`,
`PHASE.md`, `qualification.json`, `test/qntylab-dsh-v1r3.test.mjs`,
`tests/test_dsh_stage_a_v1r3_launch_plane_qualification.py`,
`docs/state/projects.toml` and `docs/CURRENT_ROADMAP.md` diffs.

### Critical (fixed)

**1. Workspace-containment check bypassable via a not-yet-existing workspace
leaf under a symlinked ancestor.** `preflightLaunch` resolved `--workspace`
with `realpathSync` only if the path already existed, else fell back to a
purely lexical `resolve()`. A symlinked *ancestor* directory (with the leaf
itself not yet created — the documented common case for a disposable
fixture) would not be dereferenced by the containment check, while the OS
would still dereference it for real at `chdir`/spawn time — reproducing the
exact V1R2 workspace-escape near-miss this phase exists to close.
*Fix*: added `realpathAllowingMissing()`, which walks up to the nearest
existing ancestor, realpath-resolves it, then re-appends the literal
remaining path components. `--workspace` resolution now uses it.
*Regression test*: `preflightLaunch: FAIL_WORKSPACE_ISOLATION when workspace
leaf does not exist yet but an ancestor is symlinked into a forbidden root`.

### High (fixed)

**2. `spawnDsh` executed the raw, un-resolved `nodeExecutable` argv value,
not the realpath verified at preflight**, leaving a TOCTOU window between
fingerprint verification and the actual `execve` — the same bug class the
Codex repair patch in this same phase fixes in DSH's own source.
*Fix*: `preflightLaunch` now records `{ digest, resolvedPath }` per
executable; `spawnDsh` spawns `resolvedPath`, not the raw argv.
*Regression test*: `spawnDsh: executes the preflight-resolved realpath, not
a post-preflight-swapped symlink target`.

**3. Fingerprint-verified `codexExecutable`/`claudeExecutable` paths were
never propagated to the spawned child**, so the preflight verification of
those two executables was disconnected from what DSH would actually invoke.
*Fix*: `spawnDsh` now sets `QNTYLAB_CODEX_EXECUTABLE` /
`QNTYLAB_CLAUDE_EXECUTABLE` from the resolved fingerprints. Noted in-code and
in `PHASE.md` that this is necessary-but-not-sufficient until a DSH build
that has landed the Codex repair (or an equivalent Claude seam) actually
consumes these — verifying that consumption requires a materialized pinned
checkout, out of scope for this offline environment.
*Regression test*: `spawnDsh: propagates fingerprint-verified codex/claude
executable paths into the child env`.

**4. `builtCliDigest` manifest field was optional; a missing field silently
skipped content-tamper detection on the entrypoint about to be spawned**,
inconsistent with every other identity check in the same function, which
fails closed when its expected value is absent.
*Fix*: `preflightLaunch` now throws `BLOCK_RUNTIME_IDENTITY` if
`manifest.builtCliDigest` is falsy, before comparing.
*Regression test*: `preflightLaunch: BLOCK_RUNTIME_IDENTITY when manifest
omits builtCliDigest`.

### Medium / informational (not fixed — outside Critical/High policy scope)

- **5.** `workspaceBundledChunks` are containment-checked but not
  content-fingerprinted; a bundled chunk's content could be altered post-
  materialization without detection. Left open — named as a residual gap
  worth a future manifest-schema addition (`workspaceBundledChunkDigests`),
  not required by the bounded Critical/High policy for this phase.
- **6.** `forbiddenRoots` defaults to an empty array in the exported
  `preflightLaunch` API; the CLI `main()` entrypoint supplies it from
  `QNTYLAB_LAUNCH_FORBIDDEN_ROOTS`, and `manifestRoot` is always forbidden
  regardless. Informational only — flagged so a future caller of the library
  function doesn't assume forbidden-root protection it didn't ask for.
- **7.** `PHASE.md` claimed offline PATH-substitution test coverage that
  did not exist (the launcher architecturally has no PATH-relative
  resolution path to test — it rejects non-absolute executables outright;
  the real PATH-substitution gap lives in DSH's own Codex provider). Fixed
  by correcting the PHASE.md wording rather than adding a vacuous test.

### Clean

`verifySourceIdentity`/`applyCanonicalPatches` fail-closed behavior,
`installOffline`'s no-network-fallback behavior, the mock server's loopback
binding, and the docs/qualification.json honesty about what did *not*
actually execute (no real pinned-commit materialization) all checked out
with no findings.

## Pass 2 — targeted rereview of the four Critical/High fixes

Scope: only the four fixes above, in `launcher/qntylab-launch-dsh.mjs`.
Checked `realpathAllowingMissing`'s termination and multi-level-missing
correctness, that the `fingerprints[key]` shape change didn't break any
other reader in the file, that `spawnDsh` has no remaining reference to raw
`args.nodeExecutable`/`args.pythonExecutable` in the spawn path, and that the
`builtCliDigest` presence check has no off-by-something error.

**Outcome: no new Critical/High finding.** All four fixes confirmed
correct; the accompanying regression tests genuinely exercise the fixed
code paths. One coverage gap noted (multi-level-missing-ancestor path is
untested, though the algorithm is correct by induction from the tested
single-level case) — Low severity, not required to fix under this phase's
bounded-completion policy.

## Result

19/19 offline `node --test` cases pass after fixes (up from 15/15 before
this review). No further repair or rereview iteration is authorized by the
bounded-completion policy for this phase.
