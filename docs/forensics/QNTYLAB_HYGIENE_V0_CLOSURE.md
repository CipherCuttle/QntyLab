# Executive Verdict

`QNTYLAB_HYGIENE_V0 = CLOSED`. Repository authority is unambiguous, operational state is bounded, and scientific recoverability is proven. Local and remote `master` histories were reconciled by a non-rewriting merge and are now equal at `42bbe120af6e376127286edb3d3c0c18720a61d5`. All 105 evidence-cited commits and all 169 known repository commits remain durably reachable from refs. No scientific experiment was rerun and no frozen research result was altered. This is an administrative closure receipt only; it registers no candidate, trial, or research decision.

# Scope

Phase ID: `QNTYLAB_HYGIENE_V0`, executed as `H0` → `H0R` → `HYGIENE_B` → `HYGIENE_C`. Documentation-only artifact recording repository hygiene. It does not modify, supersede, or reinterpret any research receipt.

# Why Hygiene Was Required

`H0` failed under concurrent mutation: multiple agent sessions held the same repository and phase simultaneously, so no forensic snapshot could be trusted. `H0R` re-established a stable single-writer baseline at `81b3345cce78076344e996c5c1908e0b2d5651ab` with 30 local branches, 35 worktree registrations (20 existing, 15 missing), 2 dirty worktrees, and 0 stashes, and declared 91 evidence-cited commits.

# Hygiene B — Preservation Envelope

Recovery root `/home/swirky/DevHub/recovery/QntyLab-hygiene-v0-20260809T223059Z/`, source mutations 0, GitHub mutations 0. Portable bundle `git/qntylab-precleanup.bundle`, sha256 `78f33f249e10e758977fe7be6286f6a609c930da82c7be910a77c3c0e7c4a1eb`, `git bundle verify` reporting a complete history. The evidence inventory was regenerated deterministically rather than inherited, yielding **105** cited commits, a strict superset of H0R's 91. Preserved: 30/30 branch tips, 35/35 worktree HEADs pinned under `refs/recovery/worktree-head/*`, 105/105 cited commits, 169/169 total commits, both dirty-worktree patches, both untracked archives, and a byte copy of the 531 MB canonical artifact. One restoration proof and one Option-A merge simulation were executed in clone space. Hostile review returned 0 CRITICAL and 4 HIGH, all repaired in the plan artifacts.

# H3 — Accepted Same-Device Residual Risk

The recovery envelope resides on the same physical device as the repository (`/dev/nvme0n1`, the machine's only block device; no independent writable filesystem is mounted). Under an explicit user decision, H3 was narrowed to `H3_LOGICAL_RECOVERY`, verified against twelve conditions: envelope outside the repository, byte-verifiable, bundle verifying, 30/30 tips, 35/35 worktree HEADs, 105/105 and 169/169 recoverable, both patches, both archives, the digest-verified 531 MB copy, a valid restoration proof, and zero source drift confirmed by exact reproduction of the frozen `ref_digest` `50c0c927…8a062e` and `status_digest` `9bbe470f…64625f`.

`H3_OFF_DEVICE_DISASTER_RECOVERY: DEFERRED_ACCEPTED_RISK`. This design protects against logical, repository, and operator failure but not against total device failure. The targeted hostile check of that amendment returned 0 CRITICAL and 0 HIGH: every Hygiene C mutation is reversible from same-device artifacts, and the reconciliation push materially *improved* off-device durability by placing the previously unpushed local commits — including sole-held evidence commits `12f57d47` and `1cfa2d5e` — on GitHub.

# H4 — Single-Writer Resolution

Hygiene B had classified several MCP/helper processes as orphans of terminated sessions. They were not orphans: each had a live parent. Under explicit authorization, 17 processes were terminated with `SIGTERM` (none required `SIGKILL`) — a second live Claude session on this repository and its `playwright-mcp` subtree, three Codex-owned MCP trees (`playwright-mcp`, `context7-mcp`, `chrome-devtools-mcp`) holding CWD inside the repository, and a GitHub MCP tree capable of remote mutation. The global Codex app-server was left running and untouched. No process respawned. That the untracked-set digest still reproduced afterwards proves the terminations left no filesystem trace.

# Hygiene C — Executed Reclamation

Branches: exactly one deleted, `research/official-announcement-boundary-v1`, a proven exact tip alias of the evidence-named `research/scout-lifecycle-expansion-v1r3` at `45a9e7fb588f95e57ee5ee9e0a201d92c4f11efc` with zero name citations in history. `git branch -d` refused (worktree attachment, then the merge heuristic), so deletion used the stricter atomic compare-and-delete `git update-ref -d <ref> 45a9e7fb…`, which additionally asserts the expected SHA. Local branches 30 → 29. The canonical `v1r3` ref and the commit both survive.

Worktrees: 18/18 clean worktrees removed by explicit path, never by glob, each re-verified for path, existence, HEAD, identity, and empty `status --porcelain -uall` immediately before removal; 15/15 stale registrations reclaimed only after asserting the prunable set equalled exactly the reviewed 15; 2/2 dirty worktrees preserved (main and the suspended `research/clean-tsmom-exp-v2-causal-vol`). Every removed HEAD remained object-present and ref-reachable afterwards.

Untracked: only the two reviewed `ARCHIVE_PATH_THEN_REMOVE` surfaces were removed — `.playwright-mcp/` (4 files) and two `logs/sprint_v2_*.log` — after confirming all six files inside the verified archive. No `git clean`, no globbed `rm`. `.gitignore` changes remain proposals, not edits.

# M1 — 33 Unique Ignored Raw-Data CSVs

An added guard inspected `--ignored` content before each worktree removal, a class the reviewed cleanliness gate does not list and no Hygiene B archive covers. Of 2249 ignored entries, 2216 were disposable caches. The remaining 33 were `data/raw/*.csv` market-data files inside two worktrees, and all 33 were byte-different from the same-named files in the main worktree — present in no commit and in no archive. Removal would have destroyed them. Both removals were stopped.

They were preserved additively, without modifying the frozen Hygiene B manifest: supplement `untracked/held-worktree-raw-data/` with per-source-worktree top-level directories (14 basenames collide across the two sources, so source separation is required for correctness), two deterministic tars, and manifest `manifests/HYGIENE_C_HELD_RAW_DATA.json` recording source worktree, branch, HEAD, relative path, size, sha256, and mtime for each file. Verification: 33/33 inventoried, 33/33 copied, 33/33 loose-copy digests equal, 33/33 extracted in restoration space, 33/33 extracted digests equal, 5,069,886 bytes total. Only then were the two worktrees removed.

# Master Reconciliation

Local `master` was not a descendant of `origin/master`; both sides carried unique, non-patch-equivalent work with **zero path overlap**. Rebase, reset, force-push, and cherry-pick were rejected because each rewrites or discards evidence-bearing commit identities. The reviewed Option A was executed: a normal non-rewriting merge of `e7dde95c487716107857e253b63635df7ee85ce5` into `81b3345cce78076344e996c5c1908e0b2d5651ab`, producing `42bbe120af6e376127286edb3d3c0c18720a61d5` with 0 conflicts and 19 files, all additions.

The resulting tree `f4078eab8f6a0365ffdc9388b37f0e092bd3ecdd` is byte-identical to the tree of the frozen Hygiene B simulation, confirming the exact union. All ten original commit SHAs on both sides are unchanged, merge base `a7e6c6f9b49dffeff1419ad592ceb518b0b9a5f9` remains reachable, and both pre-merge parents are ancestors of the new master. The push was an ordinary fast-forward, `e7dde95..42bbe12`; no force push occurred at any point. Draft PR #6 and all remote research branches were left untouched.

# Verification Results

Evidence reachability 105/105 and known-commit recoverability 169/169, both evaluated against `rev-list --all` so no commit depends on reflog. `git fsck --full` exits 0 with zero error, missing, corrupt, or broken entries. Local `master` equals live `origin/master`.

Scientific WIP is byte-identical throughout: the main unstaged diff still digests to `eb408af690cee9b626f29219a6901c7aceef423d92af3c40a59013566455c4a7`, the causal-vol diff to `586deffe804c3f393591bacf4977d4ccb1e660800c301139303c84200956b87d`, 351 main untracked files and 29 causal-vol untracked research files are unchanged with zero changed and zero missing, and the canonical artifact `experiments/results/sprint_v2_results.json` remains in place at `01868090cb77068e8524da67976121152a62034c7fa4ea4c9993366bcce4844d` under its no-rerun constraint.

Final state: 29 local branches, 4 remote heads, 2 worktree registrations (both existing, both intentionally dirty), 0 missing registrations, 0 stashes, 3 modified tracked manifests, 352 untracked files.

# Prevention Controls

Installed: `delete_branch_on_merge=true`; GitHub ruleset `master-protection` (id 20615814, enforcement active) carrying exactly the `deletion` and `non_fast_forward` rules; repository-local `fetch.prune=true` with tag pruning deliberately left unset. Remote merged-PR branch cleanup does not imply deletion of local historical evidence refs.

Deliberately not installed: signed commits, linear history, merge queue, `CODEOWNERS`, approval counts, restricted merge method. Mandatory PR integration is deferred — it would break the solo research workflow this phase exercised.

Operational convention, recorded here rather than as a governance framework: one active logical phase → one clearly named task branch → one task worktree where isolation is needed → at most one live integration PR. Temporary worktrees, especially under `/tmp`, are removed when the phase closes; missing registrations are not allowed to accumulate; a dirty worktree is never removed without preservation first.

# Known Safe Remaining State

Not defects, and not to be reclaimed by reflex: 29 historical evidence-bearing local branches, including seven reachability-redundant Tier-2 candidates deletable only by explicit future decision; the suspended `research/clean-tsmom-exp-v2-causal-vol` branch and worktree with its uncommitted implementation and test suite behind draft PR #6; three modified tracked data manifests; 352 untracked provenance receipts and manifests; the 531 MB canonical artifact retained in place; and the 33-file raw-data supplement in recovery. The goal was never a clean `git status`.

Real remaining debt: off-device disaster recovery (accepted, deferred); `experiments/runs/**` and `data/manifests/*.json` remain untracked though load-bearing, to be formalised by a research phase, not by hygiene; `data/raw/` is gitignored yet can hold unique unbacked data, which is what M1 caught.

# Reopen Triggers

Reopen if current project authority becomes ambiguous; if stale or missing worktree registrations accumulate significantly again; if any evidence-cited commit becomes unreachable from refs; if concurrent agents again mutate the same phase; if default-branch histories diverge unexpectedly; or if a recovery or restore invariant breaks. Do not reopen merely because branch or worktree counts grow slightly.
