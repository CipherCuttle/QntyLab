# Raw Metrics — QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0

Forensic artifacts only. Nothing in this directory is production code; do not
import it from `qntylab/` or reference it from canonical state.

## Contents

| File | Domain | What it measures |
|---|---|---|
| `context_metrics.json` | 7 | Context spine weight: AGENTS.md / README / roadmap / projects.toml sizes, `brief` + `spine` stdout sizes and truncation flag, project state counts and vocabulary, invariant-phrase occurrence counts |
| `projects_toml_metrics.json` | 8 | `docs/state/projects.toml` record inventory: state distribution, terminal/non-terminal split, field frequency, authority-field NONE counts, `next_action` length distribution, artifact/hash bindings, top-10 prose records, repo-wide `projects.toml` references (file:line) |
| `workflow_metrics.json` | 9 | `.github/workflows/` inventory: per-workflow lines/bytes/triggers/jobs/steps, `project-context.yml` subsystem line split, inline scripts > 30 lines, duplicated setup steps, pytest selection mode |
| `packaging_metrics.json` | 10 | Packaging/config existence inventory (pyproject/setup/Makefile/tox/lint configs), pytest config location, `qntylab.toml` structure, requirements files, CI bootstrap sequence, documented verify commands |
| `repo_byte_weight.json` | 13 | Tracked byte weight via `git ls-files -z`: total, per top-level directory, largest 50 files, generated-looking artifacts, CSV/JSON totals, `git count-objects -vH` |
| `module_inventory.json` | 11 | Inventory of all 133 `qntylab/*.py` modules (+ `qualifications/jh01_v0r3/main.go`): bytes, line counts, top-level defs/classes, AST qntylab import graph, inbound test imports, zero-inbound orphan candidates, near-duplicate version-suffix name families, duplicated function machinery (same name, similar body length across 2+ modules), one classification per module (LIVE_RUNTIME_CODE / LIVE_TOOLING / FROZEN_ORACLE / FROZEN_HISTORICAL_EVIDENCE / GOVERNANCE_SUPPORT / TEST_SUPPORT / POSSIBLE_DUPLICATE / POSSIBLE_DEAD_CODE) with evidence, cross-referenced against `docs/state/projects.toml` and `experiments/research/` |
| `deletion_matrix.json` | 12 | For every deletion/consolidation candidate (module orphans, largest tracked artifacts from `repo_byte_weight.json`, `docs/status/` files): 12 reference checks (PYTHON_IMPORT_REFERENCES, DOCSTRING_PROSE_REFERENCES, TEST_REFERENCES, PROJECT_REGISTRY_REFERENCES, AUTHORITATIVE_ARTIFACT_REFERENCES, HASH_BINDINGS, PREREGISTRATION_BINDINGS, CLOSURE_REFERENCES, ADR_REFERENCES, RESEARCH_LEDGER_REFERENCES, CI_REFERENCES, GENERATED_VIEW_REFERENCES), each `{count, evidence_paths[]}`, plus KEEP/CONSOLIDATE/ARCHIVE/DELETE classification. DELETE_SAFE requires zero load-bearing references across all checks |
| `test_gap_findings.json` | 14 | PR #241 (unmerged, commits `cd999bc`/`d181d120`) test-effectiveness forensics: tests added on the branch, why each of the two P1 contract failures slipped through (per-finding gap classes and mechanisms), repository-wide blind-spot probes over `tests/*.py` at HEAD, and 7 repository-wide INVARIANT TEST recommendations (invariant + detection strategy + what it would have caught). No tests were added |
| `scan_metrics.py` | — | The single deterministic generator for domains 7/8/9/10/13 (pure stdlib) |
| `scan_slim_tests.py` | — | Deterministic stdlib-only generator for domains 11/12/14 (`module_inventory.json`, `deletion_matrix.json`, `test_gap_findings.json`) |

## How to re-run

From the repository root, on the audited commit (HEAD `be291300`, branch
`audit/qntylab-repository-fitness-and-upstream-contract-forensics-v0`):

```bash
# Domains 7/8/9/10/13
python docs/forensics/QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0/raw/scan_metrics.py
# Domains 11/12/14 (module inventory, deletion matrix, test-gap findings)
python docs/forensics/QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0/raw/scan_slim_tests.py
```

Requirements: Python >= 3.11 (uses `tomllib`), a clean checkout of the audited
commit. No network, no timestamps, no dependencies beyond the stdlib.

### Determinism notes

- All JSON is written with `sort_keys=True`, fixed indent, trailing newline.
- No timestamps or randomness are emitted.
- `context_metrics.json` shells out to `python -m qntylab.project_context brief`
  and `... spine` and records stdout byte/line counts only; these are
  deterministic for a fixed HEAD.
- `repo_byte_weight.json` sizes come from `git ls-files -z` +
  `os.path.getsize` on the worktree, so re-running on a different checkout
  state (e.g. after committing these forensic artifacts themselves) changes
  the tracked-file numbers. Byte-identical reproduction requires the same
  tracked tree.
- Two consecutive runs on the same tree were diffed byte-identical
  (verification receipt in the audit summary).

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
