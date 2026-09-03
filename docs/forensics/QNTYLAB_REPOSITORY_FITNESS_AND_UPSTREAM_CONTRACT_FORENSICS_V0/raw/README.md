# Raw Metrics — QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0

Forensic artifacts only. Nothing in this directory is production code; do not
import it from `qntylab/` or reference it from canonical state.

## Canonical audit outputs (top level of this forensics directory)

The canonical audit outputs live one directory up, NOT in `raw/`:

| File | Role |
|---|---|
| [`../inventory.json`](../inventory.json) | merged 40-finding inventory (26 contract findings + 14 derived findings), `finding_count=40`, `severity_counts={HIGH:2, MEDIUM:17, LOW:11, INFO:10}` |
| [`../repository_metrics.json`](../repository_metrics.json) | consolidated repository weight/context/code/CI/packaging metrics |
| [`../deletion_matrix.json`](../deletion_matrix.json) | canonical deletion/consolidation matrix: 42 candidates × 12 reference checks, `DELETE_SAFE=6` |
| [`../agent_context_target.md`](../agent_context_target.md) | agent-context improvement target |
| [`../report.md`](../report.md) | synthesis report |
| [`verification_receipt.json`](verification_receipt.json) | verification receipt recorded at synthesis time (historical; see note below) |

## Evidence-slimming pass (what changed after synthesis)

Two files that were present at synthesis time were removed from the repo in
the bounded pre-merge slimming pass:

- `raw/scan_candidates.json` — a 3.0 MB exploratory candidate dump produced by
  [`scan_contracts.py`](scan_contracts.py). It was an already-consumed
  intermediate: the high-level CI/PC findings in
  [`contract_findings.json`](contract_findings.json) record the verdicts, not
  the raw grep lists. The scanner still runs the identical scan logic; the
  dump write is now opt-in (`SCAN_CANDIDATES_WRITE=1`) and the dump is
  intentionally NOT committed (regenerable via `scan_contracts.py`).
- `raw/deletion_matrix.json` — a byte-identical verbatim copy of the canonical
  top-level [`../deletion_matrix.json`](../deletion_matrix.json) (byte
  equality was proven with `cmp` before removal; recorded in
  [`verification_receipt.json`](verification_receipt.json)). The canonical
  deletion matrix is now ONLY the top-level
  [`../deletion_matrix.json`](../deletion_matrix.json).

[`synthesize.py`](../synthesize.py) was adjusted accordingly: it reads the
deletion matrix from `raw/` only as a fallback and otherwise uses the
canonical top-level file, so canonical synthesis works without either removed
dump at re-run time.

## Classification of remaining raw snapshots

| File | Classification |
|---|---|
| `contract_findings.json` | `CANONICAL_SNAPSHOT_EVIDENCE` — source of the 26 CI-*/PC-* findings; carries audit-time evidence lines that are not regenerable from any scanner alone |
| `context_metrics.json` | `CANONICAL_SNAPSHOT_EVIDENCE` — measured stdout sizes/truncation flags of `project_context brief`/`spine` at the audited base commit; deterministic only for that tree |
| `projects_toml_metrics.json` | `CANONICAL_SNAPSHOT_EVIDENCE` — measured `docs/state/projects.toml` record inventory at the audited base commit |
| `workflow_metrics.json` | `CANONICAL_SNAPSHOT_EVIDENCE` — measured `.github/workflows/` line/step inventory at the audited base commit |
| `packaging_metrics.json` | `CANONICAL_SNAPSHOT_EVIDENCE` — measured packaging/config existence inventory at the audited base commit |
| `repo_byte_weight.json` | `CANONICAL_SNAPSHOT_EVIDENCE` — measured tracked byte weight via `git ls-files` at the audited base commit; changes whenever the tracked tree changes |
| `module_inventory.json` | `CANONICAL_SNAPSHOT_EVIDENCE` — measured module inventory + classification at the audited base commit (regenerable deterministically for the same tree via `scan_slim_tests.py`, but the retained file is the audited evidence) |
| `test_gap_findings.json` | `CANONICAL_SNAPSHOT_EVIDENCE` — PR #241 test-effectiveness forensics; includes the `merged=false` context for CI-23 |
| `verification_receipt.json` | `CANONICAL_SNAPSHOT_EVIDENCE` — synthesis-time verification receipt (historical record; not rewritten by the slimming pass) |

No remaining raw file is classified
`DETERMINISTICALLY_REGENERABLE_INTERMEDIATE` — the only such file
(`scan_candidates.json`) was removed in the slimming pass. No further removal
was made: every remaining file fails at least one of the five removal
conditions (conservative disposition).

## How to re-run the scanners

Scanners are rerun against the audited base commit
`be291300abb70f3ffc6ba0dd8b1bea570daf5377`. Checkout that commit (or create a
worktree), run the scanner, and compare output against the retained snapshot:

```bash
# Example with a temporary worktree
git worktree add /tmp/qntylab-audit-base be291300abb70f3ffc6ba0dd8b1bea570daf5377
cd /tmp/qntylab-audit-base

# Domains 7/8/9/10/13 (context/projects.toml/workflow/packaging/byte-weight)
python docs/forensics/QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0/raw/scan_metrics.py

# Domains 11/12/14 (module inventory, deletion matrix, test-gap findings)
python docs/forensics/QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0/raw/scan_slim_tests.py

# Contract-integrity candidate scan (exploratory; dump write is opt-in)
SCAN_CANDIDATES_WRITE=1 python docs/forensics/QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0/raw/scan_contracts.py

# Then diff against the retained snapshots in this directory.
```

Requirements: Python >= 3.11 (uses `tomllib`), a clean checkout of the audited
commit. No network, no timestamps, no dependencies beyond the stdlib.

### Determinism notes

- All JSON is written with fixed indent and trailing newline.
- No timestamps or randomness are emitted.
- `context_metrics.json` shells out to `python -m qntylab.project_context brief`
  and `... spine` and records stdout byte/line counts only; these are
  deterministic for a fixed HEAD.
- `repo_byte_weight.json` sizes come from `git ls-files -z` +
  `os.path.getsize` on the worktree, so re-running on a different checkout
  state (e.g. after committing these forensic artifacts themselves) changes
  the tracked-file numbers. Byte-identical reproduction requires the same
  tracked tree.

## Warning: later-tree reruns do NOT reproduce audited metrics

**Rerunning the scanners on a later tree does NOT reproduce the audited
metrics exactly.** All retained metrics and findings are audited at the base
SHA `be291300abb70f3ffc6ba0dd8b1bea570daf5377` ONLY. Byte weights, module
counts, workflow line counts, `projects.toml` record counts, and context
spine sizes all change as the repository evolves; a rerun on `master` or any
newer commit measures that tree, not the audited one. Any comparison must
first check out the base SHA.

## Note on edited raw snapshot

[`contract_findings.json`](contract_findings.json) was edited in the
evidence-slimming pass: CI-1 and CI-23 prose was updated (reachability
markers `LATENT_ON_MASTER` / `BRANCH_ONLY` added and claim prefixes aligned)
to correct the HIGH-finding reachability wording. Severities, classifications,
evidence, risks, and dispositions are otherwise unchanged. The retained file
remains the snapshot evidence for the 26 contract findings.

## Method notes / known heuristics

- Project state classification rule (domains 7/8): `CLOSED_*`, `SEALED`,
  `ARCHIVED` = terminal; `PLANNED_*` = planned; everything else
  (here: the single `BLOCKED` record) = non-terminal. The actual state
  vocabulary found is recorded verbatim in `STATE_VOCABULARY`.
- Workflow subsystem classification (domain 9) uses first-match priority on
  step name + run text; the priority list is embedded in
  `workflow_metrics.json` under `project_context_yml.rule_priority`. Step
  spans count every YAML line inside the step. `HISTORICAL_REPAIR_REGRESSION`
  outranks `DSH`, so DSH steps whose run text mentions
  historical/repair/regression are counted under the former.
- pytest invocation detection (domain 9) excludes `pip install` lines;
  `selected_by_path` means the invocation lists explicit `tests/` paths.
- Generated-artifact detection (domain 13) is extension/path heuristics only
  (`.csv`, `.jsonl`, `.json` > 100 KB, `sigstore` in path); it is a signal,
  not a verdict.
- `projects_toml_metrics.json` reference scan excludes
  `docs/state/projects.toml` itself and non-text blobs; it matches the literal
  string `projects.toml`.
