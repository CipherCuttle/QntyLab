# Independent hostile implementation review — production Stage-A DSH_HOME materialization V0

One independent hostile review was run against the frozen implementation, tests,
receipts, and successor contract, attacking the eighteen vectors the governing
authorization enumerates. The reviewer verified claims by execution rather than
by reading the phase's own evidence, and re-derived every digest independently.

## Initial verdict

`FAIL — 0 Critical, 1 High, 3 Medium, 2 Low`

Fifteen of the eighteen vectors held on first contact. Determinism, evidence
reproducibility, action-time parity, ambient independence, and every frozen
identity were reproduced bit-for-bit by the reviewer's own runs.

## Vectors

| # | Vector | Result |
| --- | --- | --- |
| 1 | ambient scratch fallback still possible | ATTACK HELD |
| 2 | ambient directory mutation occurred | ATTACK HELD |
| 3 | materializer does not truly start from empty state | ATTACK HELD |
| 4 | unverified node_modules packages remain | FINDING — F2 (Medium) |
| 5 | symlink escapes survive | FINDING — F1 (High) |
| 6 | package-manager action actually rebuilt runtime | ATTACK HELD |
| 7 | runtime identity changed | ATTACK HELD |
| 8 | missing canonical package provenance silently tolerated | FINDING — F4 (Medium) |
| 9 | stub provider leaks into production | ATTACK HELD |
| 10 | qualification path still creates hidden prerequisites | ATTACK HELD |
| 11 | parity path differs from future live path | ATTACK HELD |
| 12 | home manifest can be substituted | FINDING — F1 (High) |
| 13 | materializer can be substituted without changing contract | ATTACK HELD |
| 14 | a392 incorrectly still treated as final contract | ATTACK HELD |
| 15 | successor contract accidentally grants live authority | ATTACK HELD |
| 16 | secret/claim/provider operation occurred | ATTACK HELD |
| 17 | stale-test repair became trivial | ATTACK HELD |
| 18 | V0R5 was created or preauthorized | ATTACK HELD |

## F1 — HIGH (repaired)

`verifyHomeManifest` derived its containment authority from
`materializationRootAbsolutePath` **inside the manifest being verified**. That
field is deliberately excluded from the identity digest, so an attacker could
set it freely and still recompute a self-consistent `homeManifestDigest`. The
reviewer demonstrated the bypass by executing it: repointing
`profiles/node_modules/ws` at an attacker directory, widening the recorded root
to `/`, re-relativizing every target, and recomputing the digest produced a home
that **passed** verification with loader-visible attacker code on the profile's
resolution path.

An end-to-end bypass was already blocked — the production path only verifies a
home it just materialized in-process, and the recomputed successor contract
digest diverged from the frozen artifact — so no evidence was invalidated and no
frozen identity was violated. The defect was nonetheless a fail-open hole in the
phase's own whole-home identity primitive.

**Repair.** `verifyHomeManifest` now takes the runtime root from the pinned
runtime manifest via `readRuntimeIdentity`, never from the home manifest, and
requires the recorded value to equal it — the recorded root is treated as a
claim to confirm, not as authority. Covered by new control **NC-19b**, which
reproduces the reviewer's exact forgery and requires it to block.

## F2 — MEDIUM (repaired alongside F1)

Verification detected drift and deletion but never **addition**: an extra
unrecorded package, an extra profile file, or a stub provider copied outside the
`@qntylab` scope all passed unblocked. This was the completeness half of the
authorization's whole-home identity coverage requirement, and it lived in the
same function as F1.

**Repair.** `verifyHomeManifest` now enumerates everything physically present
under `profiles/` and rejects any object the manifest does not record. Covered by
new control **NC-19c**, which exercises all four of the reviewer's cases.

## F4 — MEDIUM (disclosure repaired)

The closure BFS skipped declared-but-uninstalled dependency edges silently, while
the registry claimed `unresolved_packages = 0`. The reviewer confirmed the skip
is *substantively* correct — it is a faithful reproduction of DSH's own
`healProfilesModuleFallback`, and a real DSH boot over a materialized home adds
zero links — but the record was misleading.

**Repair.** The DSH_HOME manifest now records the skipped set explicitly
(`provenance.skippedDependencyEdges`: 88 deterministic names,
`loaderVisibleUnresolvedPackages: 0`), and the registry states the distinction
rather than asserting a bare zero. No graph content changed.

## F5 — LOW (repaired)

`nondeterministicResidue` named a field path that did not exist
(`provenance.pinnedRuntime.materializationRootAbsolutePath`) rather than the
actual top-level `materializationRootAbsolutePath` — obscuring exactly the field
implicated in F1. The entry now names the real field and records why it is never
trusted as authority.

## F6 — LOW (repaired)

The frozen successor-contract comparison in `prepareProductionLaunch` was guarded
by `existsSync`, so deleting the artifact silently disabled the outer binding
that mitigates F1. It is now mandatory and fails closed.

## F3 — MEDIUM (resolved by closure)

The registry cited a `hostile_review.md` that did not yet exist and carried a
placeholder verdict with pre-recorded zero-High counts. This document is that
artifact; the registry now records the real verdict and counts.

## Targeted re-review

Scope: the F1 repair surface and its companions only; no vector was re-attacked
beyond it, and no other finding reopened the phase.

Verdict: `PASS_NO_CRITICAL_HIGH` — 0 Critical, 0 High.

The re-reviewer re-executed the original forgery and twelve variants. The
original attack now blocks with `BLOCK_HOME_MANIFEST: DSH_HOME manifest names a
foreign materialization root: /`. The repair is defense in depth rather than one
equality check: recording the *true* root and still repointing a symlink outside
it blocks at `BLOCK_SYMLINK_CONTAINMENT`, and substituting the pinned runtime
manifest itself — the new anchor — also blocks, because relocating the anchor
requires forging a Git-tracked artifact whose digest the production path pins.

No false positives were introduced. The deliberate qualification overlay still
works (it is applied *after* the only production `verifyHomeManifest` call), and
a real DSH boot writes only `<home>/sessions/…` at the home root, adding nothing
under `profiles/` — confirmed by inspecting a post-boot home and re-verifying it.

### Accepted without repair

Two observations were recorded and deliberately not repaired, because the
phase's review policy does not let Medium/Low findings reopen a phase and,
more importantly, because changing code after the re-review would mean the
committed bytes were never the reviewed bytes.

- **D1 (Low, fails closed).** If `profiles/` is missing entirely, the addition
  walk now raises a raw `ENOENT` instead of a classified `BLOCK_*` code. It
  still fails closed — only the error classification regressed — and the
  condition cannot arise from the production path, which verifies a home it
  just materialized in-process.
- **D2 (Info).** Addition detection is scoped to `profiles/`. That scoping is
  what keeps it free of false positives against a real DSH boot, which writes
  `sessions/` at the home root. Widening it later would require excluding
  `dsh-home-manifest.json` and `sessions/`.

The re-reviewer also noted three pre-existing completeness gaps in the
standalone verification primitive (resealed omission of a non-mandatory link, an
unknown object `type` skipping per-object checks, and unguarded `lstatSync` on a
deleted recorded object). All are unreachable end-to-end: the production path
asserts the verified digest equals the in-process freshly materialized value, so
any resealed forgery is rejected regardless, and the six Stage-A runtime packages
plus both `@qntylab` production packages remain mandatory.

## Final verdict

`PASS_NO_CRITICAL_HIGH` — 0 Critical, 0 High unrepaired.

All six findings from the initial review are repaired, and the re-review's own
two observations are recorded above as accepted-without-repair Lows. The twenty
required negative controls remain exactly the twenty the authorization
enumerates and all pass; two supplementary controls (NC-19b, NC-19c) hold the
repaired surface. No production semantics changed, no frozen identity moved, and
the phase still creates no live authority and no V0R5.

The bytes the re-review verified are the bytes committed: production materializer
`ce18ebb9bb65cc01a07509189437cd1041ad09afaaee5ba318a6e822d82a09be`, successor
contract `50bd776263d05e9f2fe3e026c5e8904a12fa257a1667d11c1e22ef32376c24de`. No
executable byte changed after the re-review.
