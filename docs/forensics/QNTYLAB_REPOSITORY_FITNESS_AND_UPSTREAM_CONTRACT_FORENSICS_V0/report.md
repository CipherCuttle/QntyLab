# QNTYLAB Repository Fitness & Upstream Contract Forensics V0 — Synthesis Report

Audit: `QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0`
HEAD: `be291300abb70f3ffc6ba0dd8b1bea570daf5377`
Branch: `audit/qntylab-repository-fitness-and-upstream-contract-forensics-v0`

**Forensics only.** This report synthesizes the raw outputs in
[`raw/`](raw/README.md); no scans were re-run, no state was mutated, no files
were deleted, nothing is implemented, and nothing in this directory is
canonical.

> **Headline: no CRITICAL findings on master.** The merged inventory
> ([`inventory.json`](inventory.json), 40 findings) contains **2 HIGH** and
> **0 CRITICAL** findings. Both HIGH findings are latent/branch-only:
> [CI-1](#2-criticalhigh-bugs) (latent unguarded private assembly that could
> embed a digest attesting synthetic-only provenance) and
> [CI-23](#2-criticalhigh-bugs) (provenance laundering on **unmerged PR #241**,
> not reachable on master). **Current master has NO reachable authority
> violation — it fails closed.**

---

## 1. Executive summary

QntyLab at HEAD `be291300` is a **fail-closed, exploratory-only research
repository** whose contract core is sound on master but surrounded by
significant weight debt:

- **Weight**: 100,472,910 tracked bytes (~95.8 MiB) across 4,115 files;
  `experiments/` alone is 72,935,668 B (72.6%) and `data/` 21,093,250 B
  ([`repository_metrics.json`](repository_metrics.json) ← `raw/repo_byte_weight.json`).
- **Context**: default agent context is anchored on
  [`docs/state/projects.toml`](../../state/projects.toml) at **576,993 B /
  9,933 lines** with 149 records of which 139 (93.3%) are terminal; the `brief`
  renders 14,468 B and is **truncated**; the spine renders **50,150 B on one
  line** (`raw/context_metrics.json`).
- **Code**: 133 `qntylab/*.py` modules (~49.2k LOC), of which 64 are frozen
  historical evidence and only 15 are live runtime code
  (`raw/module_inventory.json`).
- **CI**: one workflow ([`project-context.yml`](../../.github/workflows/project-context.yml)),
  323 lines / 19 steps, of which DSH + historical-repair-replay span lines are
  243/303 (80.2% of step spans) and the project-context core is 16 lines (5.0%)
  (`raw/workflow_metrics.json`).
- **Contract findings**: 26 findings ([`raw/contract_findings.json`](raw/contract_findings.json)):
  2 HIGH, 9 MEDIUM, 5 LOW, 10 INFO — every reachable-on-master finding is
  already fail-closed.
- **Packaging**: no [`pyproject.toml`], `setup.py`, `setup.cfg`, pytest.ini, or
  conftest.py at root; pytest config lives only in nonstandard
  [`qntylab.toml`](../../qntylab.toml) (585 B) (`raw/packaging_metrics.json`).
- **Tests**: 215 tracked test Python files; effectiveness gaps (fixture-trust,
  missing restart/multiprocess coverage) let two P1 defects pass on unmerged
  PR #241 (`raw/test_gap_findings.json`).

Full numbers: [`repository_metrics.json`](repository_metrics.json). Full
finding list: [`inventory.json`](inventory.json). Deletion evidence:
[`deletion_matrix.json`](deletion_matrix.json).

---

## 2. Critical/High bugs

**0 CRITICAL. 2 HIGH.** Neither is a reachable authority violation on master.

| ID | Severity | Domain | Path | Claim (condensed) | Reachable on master? |
|---|---|---|---|---|---|
| CI-1 | HIGH | D1 | [`qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py`](../../qntylab/jigsaw_funding_pressure_incremental_forecast_value_executor_v0.py) | `_assemble_incremental_forecast_evaluation` (private, lines 565–712) performs no execution-mode guard; payload embeds static all-false `NO_REAL_EXECUTION_ATTESTATION` constants (line 684) regardless of row origin. Any caller routing real rows through the unguarded private assembly obtains a digest-bearing result attesting synthetic-only provenance. | **Latent** — the guard exists on the public entrypoint (`run_incremental_forecast_evaluation:715-724`); the defect requires a future caller to bypass it (see CI-11/CI-26, which do exactly that but are currently unreachable). |
| CI-23 | HIGH | PC | `qntylab/jigsaw_funding_pressure_incremental_forecast_value_consumer_seam…` (PR #241 branch) | Provenance laundering on **unmerged PR #241** (`agent/funding-incremental-real-execution-consumer-seam-successor-implementation-v0`, commits `cd999bc`/`d181d120`): `ForecastRowBatch.from_offline_synthetic_rows` accepts arbitrary rows and unconditionally sets `synthetic_only=True`, laundering arbitrary provenance into a batch attested as synthetic. | **No — branch-only.** PR #241 is `merged=false` (`raw/test_gap_findings.json: context`). |

Master disposition: **fail-closed**. CI-24 (PC domain) records explicitly that
the branch-only machinery is *not applicable* at master HEAD. The remaining
HIGH-adjacent mechanism, CI-11 (`_invoke_successor_shared_core` bypasses the
public guarded entrypoint) and CI-26 (wrapper unreachable because its canonical
auth artifact does not exist, verified at runtime), are MEDIUM latent design
debt — reachable only if a canonical authorization artifact were ever created.

---

## 3. Contract-integrity risks

From the 26 CI-*/PC-* findings ([`inventory.json`](inventory.json)):

- **Caller-asserted provenance (D1)** — CI-1 (HIGH), CI-2, CI-5, CI-23 (HIGH),
  CI-25: provenance is derived from caller inputs; digest-bearing payloads can
  attest static constants rather than row origin.
- **Declared-but-not-implemented persistence (D2)** — CI-7, CI-10, CI-26:
  `_record_exactly_one_result` claims exactly-once persistence but the "ledger"
  is process-local (dict + RLock) or entirely absent; a restart silently loses
  it (`raw/test_gap_findings.json` P1(b)).
- **Semantic bypass of public entrypoints (D3)** — CI-11 (MEDIUM),
  CI-12, CI-13, CI-14: private assembly invoked by successor modules,
  bypassing `require_authorized_execution_mode`.
- **Misleading names (D4)** — CI-15, CI-16, CI-17: names like
  `from_offline_synthetic_rows` / `record_exactly_one_result` assert contracts
  the code does not enforce — a type check is not a provenance check.
- **Positives**: CI-3, CI-4, CI-6, CI-8, CI-20 record *verified* provenance,
  durable cross-process ledger use, and canonical binding in the execution
  foundation and `research_ledger.py`; CI-18, CI-21, CI-22, CI-24 record
  safe/canonical/not-applicable statuses. Master's core ledger and foundation
  are sound.

**Net risk**: the danger is not present-day execution but **successor
modules** (PR #241 lineage and the wrapper) that reuse the unguarded private
assembly. Any future PR in that lineage must close CI-11/CI-1 first.

---

## 4. Context/LLM UX

Domain D7 findings (CTX-1..CTX-4, [`inventory.json`](inventory.json)):

- **CTX-1 (MEDIUM)**: [`docs/state/projects.toml`](../../state/projects.toml)
  is 576,993 B / 9,933 lines and is the default context surface; 149 records,
  139 terminal (93.3%), 474 distinct authority-field names,
  `next_action` max 2,640 B (`raw/projects_toml_metrics.json`).
- **CTX-2 (MEDIUM)**: spine output is 50,150 B on a **single line** —
  undiffable and all-or-nothing (`raw/context_metrics.json`).
- **CTX-3 (MEDIUM)**: brief is 14,468 B / 118 lines and **truncated** — the
  canonical cold-start summary does not fully render.
- **CTX-4 (LOW)**: AGENTS.md + README + CURRENT_ROADMAP restate invariants in
  77,057 B of prose ("authority" ×89 in the roadmap alone).

**Design response (not implemented)**: [`agent_context_target.md`](agent_context_target.md)
specifies a 20-field, ≤8 KB, fail-closed cold-start packet (REPOSITORY,
HEAD, WORKTREE, PHASE_ID, STATE, OBJECTIVE, AUTHORITY_SOURCE,
ALLOWED_OPERATIONS, FORBIDDEN_OPERATIONS, INPUT_CONTRACTS, OUTPUT_CONTRACTS,
LOAD_BEARING_INVARIANTS, RELEVANT_CODE, RELEVANT_TESTS, IMMUTABLE_PATHS,
OPEN_BLOCKERS, REVIEW_LIFECYCLE, NEXT_ACTION, VERIFY_COMMAND) that points into
canonical state instead of loading it.

---

## 5. CI/DevOps

Domain D9 findings (CIX-1..CIX-2):

- **CIX-1 (MEDIUM)**: the single workflow
  ([`.github/workflows/project-context.yml`](../../.github/workflows/project-context.yml))
  spends 243 of 303 step-span lines (80.2%; 93.5% of total YAML sits outside
  the project-context core and research-ledger steps) on DSH and
  historical-repair replay, while the authority-guarding core is 16 lines
  (5.0%). Spec shorthand "93% historical-repair/DSH vs 16-line core" refers to
  this measured split (`raw/workflow_metrics.json`).
- **CIX-2 (LOW)**: three inline shell blocks of 68/58/40 lines (CI fixture
  provisioning, DSH_HOME materialization, provenance receipt) live untested
  inside YAML.
- **Packaging (D10)**: PKG-1 (MEDIUM) — no `pyproject.toml`/`setup.py`/`setup.cfg`;
  CI bootstraps via ad-hoc `python -m pip install pytest requests` (workflow
  line 72). PKG-2 (LOW) — pytest config only in [`qntylab.toml`](../../qntylab.toml);
  documented verify is `python -m pytest -q` (README.md:65).

---

## 6. Project-state architecture

- [`docs/state/projects.toml`](../../state/projects.toml): 149 records;
  `CLOSED_PASS` 98, `CLOSED_BLOCKED` 38, `PLANNED_NOT_AUTHORIZED` 9,
  `CLOSED_NEGATIVE` 2, `ARCHIVED` 1, `BLOCKED` 1 → 139 terminal (93.3%).
  118/149 records carry hash bindings; 149 reference `authoritative_artifacts`.
- 474 distinct authority-field names across 2,186 distinct field names total —
  authority semantics are unbounded vocabulary, the single largest
  comprehension tax in the repo.
- 73 repo-wide file:line references to `projects.toml` (incl.
  [`qntylab/project_context.py`](../../qntylab/project_context.py) itself at
  110,441 B), so any restructuring is high-blast-radius.
- The single non-terminal record (1 `BLOCKED`) is the *actual live state*;
  everything else is frozen history.

---

## 7. Code duplication

Domain D11 findings (DUP-1..DUP-3):

- **DUP-1 (MEDIUM)**: 133 modules; 64 `FROZEN_HISTORICAL_EVIDENCE`, 35
  `TEST_SUPPORT`, 15 `LIVE_RUNTIME_CODE`, 8 `FROZEN_ORACLE`, 6
  `GOVERNANCE_SUPPORT`, 5 `POSSIBLE_DEAD_CODE`
  (`raw/module_inventory.json`).
- **DUP-2 (LOW)**: 4 near-duplicate version-suffix families
  (`jh01_rv_persistence_incremental_forecast_value_prereg_v0/v1`,
  `jh01_rv_persistence_temporal_replication_execution_v0/v0r1`,
  `jigsaw_fast_prospective_signal_discovery_prereg_v0/v1`,
  `pinned_dsh_codex_write_path_materialization_v0/v0r1`), all with
  `qntylab_inbound=0`, bound only by test imports.
- **DUP-3 (LOW)**: 10 zero-inbound orphan candidates; 122 duplicated
  function-machinery entries across 2+ modules.

---

## 8. Data/repo weight

Domain D13 findings (BYT-1..BYT-2):

- **BYT-1 (MEDIUM)**: 100,472,910 tracked bytes / 4,115 files;
  `experiments/` 72,935,668 B (72.6%), `data/` 21,093,250 B; largest file
  [`experiments/results/breadth_v2_development_v0/BREADTH_V2_DEVELOPMENT_DECISION_V0.json`](../../experiments/results/breadth_v2_development_v0/BREADTH_V2_DEVELOPMENT_DECISION_V0.json)
  at 15,655,624 B; git pack 85.86 MiB.
- **BYT-2 (LOW)**: 98 generated-looking artifacts; JSON/JSONL 59,972,906 B +
  CSV 32,709,614 B ≈ 92% of tracked weight.

---

## 9. Deletion/consolidation candidates

[`deletion_matrix.json`](deletion_matrix.json) (verbatim copy of
[`raw/deletion_matrix.json`](raw/deletion_matrix.json)): 42 candidates, 12
reference checks each.

| Classification | Count | Meaning |
|---|---:|---|
| `DELETE_SAFE` | **6** | zero load-bearing references across all 12 checks |
| `DELETE_BLOCKED_BY_FROZEN_BINDING` | 28 | hash/preregistration/authoritative-artifact bindings |
| `DELETE_BLOCKED_BY_ACTIVE_USE` | 8 | imported or CI-referenced today |

The 6 provably delete-safe candidates: 2 stale
[`docs/status/`](../../docs/status/) files and 4 zero-inbound orphan modules
(`jfp03_v0r1_input_materialization.py`,
`jigsaw_cross_sectional_dispersion_execution_v0.py`,
`jigsaw_external_replication_execution_v0.py`,
`jigsaw_external_replication_input_materialization_v0.py`). **This audit
deletes none of them**; deletion is P3/P4 and requires separate governance.

---

## 10. Test gaps

**TST-1 (MEDIUM, D14)** — from [`raw/test_gap_findings.json`](raw/test_gap_findings.json):

- Both P1 defects on unmerged PR #241 passed their tests because:
  - **P1(a)** provenance laundering: `MISSING_ADVERSARIAL_PROVENANCE_TEST`,
    `FIXTURE_ASSUMES_CONTRACT` (the sole batch constructor is the defect),
    `ASSERTION_TOO_WEAK`, `OVERFIT_TO_IMPLEMENTATION`.
  - **P1(b)** exactly-once persistence lie: `MISSING_RESTART_TEST`,
    `MISSING_MULTIPROCESS_TEST` (probe `multiprocess_or_restart_coverage`
    over `tests/*.py` at HEAD returned **zero files**).
- 7 repository-wide invariant-test recommendations are recorded
  (provenance-constructor honesty, persistence-across-boundary, etc.). This
  audit **added no tests** (`no_tests_added=true`).

---

## 11. Proposed cleanup sequence

Every item below is a **proposal only**. Each requires its own governance
(preliminary ledger event, hostile review, explicit authorization) before any
implementation. `REQUIRES_SEPARATE_GOVERNANCE=YES` applies to all.

### P0 — Contract correctness

| Item | Detail |
|---|---|
| Item | Close the private-assembly bypass: make `_assemble_incremental_forecast_evaluation` provenance-safe or private-and-dead; reject the PR #241 laundering constructor (`from_offline_synthetic_rows` on arbitrary origins). Adopt the 7 invariant-test recommendations for any successor PR. |
| PRIORITY | P0 |
| DEPENDENCIES | none |
| RISK | LOW on master (defect is latent/branch-only); touching frozen modules risks hash-binding breakage |
| EXPECTED_CONTEXT_REDUCTION | 0 (correctness, not weight) |
| EXPECTED_CODE_REDUCTION | 0 (adds guards/tests; net code likely +) |
| EXPECTED_CI_REDUCTION | 0 |
| MIGRATION_HAZARDS | successor modules (CI-26 wrapper) currently depend on the unguarded path; removing it strands them — intentional (they are unreachable) |
| REQUIRES_SEPARATE_GOVERNANCE | YES |

### P1 — Agent/context UX

| Item | Detail |
|---|---|
| Item | Implement the ≤8 KB cold-start packet per [`agent_context_target.md`](agent_context_target.md) (20 fields, fail-closed byte cap, pointers not contents). |
| PRIORITY | P1 |
| DEPENDENCIES | P0 not required; additive renderer |
| RISK | LOW-MEDIUM — must not alter `brief`/`spine`/`projects.toml`; `render --check` must stay green |
| EXPECTED_CONTEXT_REDUCTION | ~14.4 KB brief + 50.2 KB spine + up to 577 KB default state → ~8 KB packet for cold-start (~97% reduction of agent-facing surface) |
| EXPECTED_CODE_REDUCTION | 0 (adds a bounded renderer; [`qntylab/project_context.py`](../../qntylab/project_context.py) itself is already 110 KB) |
| EXPECTED_CI_REDUCTION | 0 |
| MIGRATION_HAZARDS | packet drift vs canonical state (mitigate: path:line:hash pointers, render-time verification) |
| REQUIRES_SEPARATE_GOVERNANCE | YES |

### P2 — DevOps

| Item | Detail |
|---|---|
| Item | Split CI historical-replay/DSH steps (243 span lines) from the core authority checks (16 lines); extract the three 68/58/40-line inline shell blocks into tested scripts; introduce minimal packaging metadata (`pyproject.toml`) without changing import semantics. |
| PRIORITY | P2 |
| DEPENDENCIES | P0 (guard correctness before CI reshuffle) |
| RISK | MEDIUM — CI is the enforcement plane for fail-closed behavior; workflow changes can silently drop guards |
| EXPECTED_CONTEXT_REDUCTION | ~0 |
| EXPECTED_CODE_REDUCTION | ~0 (relocation, not deletion) |
| EXPECTED_CI_REDUCTION | up to ~50% of workflow wall-time from de-prioritizing historical replay; YAML shrink 323 → ~120 lines core + replay job |
| MIGRATION_HAZARDS | dropping any of the 12 CI bootstrap commands (doctor --strict, render --check, spine, brief, research_ledger doctor, pinned tests) weakens the fail-closed net |
| REQUIRES_SEPARATE_GOVERNANCE | YES |

### P3 — Logical slimming

| Item | Detail |
|---|---|
| Item | Execute the 6 `DELETE_SAFE` deletion-matrix candidates; supersede the 4 near-duplicate module families via recorded supersession events; prune the 10 orphan candidates where binding checks permit. |
| PRIORITY | P3 |
| DEPENDENCIES | P0/P1 (guards + packet so comprehension does not regress); per-candidate re-run of the 12 reference checks |
| RISK | MEDIUM — `DELETE_BLOCKED_BY_FROZEN_BINDING` (28) and `DELETE_BLOCKED_BY_ACTIVE_USE` (8) must not be touched; hash bindings break silently |
| EXPECTED_CONTEXT_REDUCTION | minor (module list shrinks 133 → ~123) |
| EXPECTED_CODE_REDUCTION | ~6 modules + parts of 4 duplicate families (~50–80 KB of [`qntylab/`](../../qntylab/) source) |
| EXPECTED_CI_REDUCTION | minor (fewer test files if orphan-bound tests are superseded with governance) |
| MIGRATION_HAZARDS | prose/docstring references to deleted modules (12-check re-run required); `projects.toml` references (73 repo-wide) |
| REQUIRES_SEPARATE_GOVERNANCE | YES |

### P4 — Physical slimming

| Item | Detail |
|---|---|
| Item | Move/relocate the largest frozen result blobs (top file 15.7 MB; `experiments/` 72.9 MB; generated-looking artifacts 98 files) to external artifact storage with hash bindings retained in-tree. |
| PRIORITY | P4 |
| DEPENDENCIES | P3; binding-preservation design; storage decision |
| RISK | HIGH — frozen evidence; every relocation must preserve SHA bindings recorded in `projects.toml` (118 hash-bound records) and preregistration artifacts |
| EXPECTED_CONTEXT_REDUCTION | 0 (not context-facing) |
| EXPECTED_CODE_REDUCTION | 0 |
| EXPECTED_CI_REDUCTION | checkout time roughly halves if CSV/JSONL blobs (92.7 MB of 100.5 MB) leave the tree |
| MIGRATION_HAZARDS | any hash mismatch = evidence integrity failure; `git count-objects` pack (85.86 MiB) retains history regardless of worktree removal |
| REQUIRES_SEPARATE_GOVERNANCE | YES |

---

## 12. Explicit non-authorizations

This audit asserts **NO** authority for any of the following. These are the
non-authorization lines recorded in
[`raw/verification_receipt.json`](raw/verification_receipt.json):

- `RUNTIME_SOURCE_CHANGED = NO` — no file under [`qntylab/`](../../qntylab/) was created, modified, or deleted.
- `FROZEN_ARTIFACT_CHANGED = NO` — no frozen evidence, preregistration, closure, or manifest artifact was modified.
- `PROJECT_AUTHORITY_CHANGED = NO` — [`docs/state/projects.toml`](../../state/projects.toml) and [`docs/state/ecosystem.toml`](../../state/ecosystem.toml) are untouched; no `projects.toml` mutation occurred.
- `SCIENTIFIC_EXECUTION = NO` — no backtest, strategy run, batch, or evaluation was executed.
- `REAL_DATA_ACCESSED = NO` — no market data was fetched or read from providers.
- `OUTCOMES_ACCESSED = NO` — no frozen outcomes were consumed.
- `PROVIDERS_ACCESSED = NO` — no exchange/provider API was contacted.
- `REAL_CLAIMS_ACCESSED_OR_CONSUMED = NO` — no real claims were read or consumed.
- `EVALUATION_ORIGINS_CONSUMED = 0` — zero evaluation origins consumed.
- `ROUTER_QNTY_QNTYSPOT_TRADING_CAPITAL_AUTHORITY = NONE` — no trading-capital authority was assumed, requested, or exercised.
- `GIT_HISTORY_REWRITTEN = NO` — no commit, rebase, or history operation on canonical branches; this subtask does not commit.
- `FILES_DELETED = 0` — nothing deleted anywhere in the repository.

Everything in [`inventory.json`](inventory.json),
[`repository_metrics.json`](repository_metrics.json),
[`deletion_matrix.json`](deletion_matrix.json),
[`agent_context_target.md`](agent_context_target.md), and this report is
**forensic evidence and proposal only**. No finding carries
`implementation_authorized=true`. QntyLab remains exploratory-only; this audit
claims no scientific validation and no trading authority.

---

## Verification

Run in this subtask (receipts in [`raw/verification_receipt.json`](raw/verification_receipt.json)):

```
python -m qntylab.project_context doctor --strict   → PASS (exit 0)
python -m qntylab.project_context render --check    → PASS, unchanged (exit 0)
python -m json.tool <each top-level JSON>           → all VALID
git status --porcelain=v1                           → only docs/forensics/QNTYLAB_.../ untracked
git diff --name-status origin/master...HEAD         → empty (nothing committed)
```
