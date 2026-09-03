#!/usr/bin/env python3
"""Deterministic synthesizer for the top-level artifacts of
QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0.

Reads only raw/ JSON outputs at HEAD be291300; writes only inside this
forensics directory. Pure stdlib; no network; no timestamps.
"""
import collections
import json
import os
import shutil

BASE = "docs/forensics/QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0"
RAW = BASE + "/raw"
HEAD = "be291300abb70f3ffc6ba0dd8b1bea570daf5377"
AUDIT = "QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0"


def dump(obj, path):
    with open(path, "w") as fh:
        json.dump(obj, fh, indent=2, sort_keys=True)
        fh.write("\n")


cm = json.load(open(RAW + "/context_metrics.json"))
pt = json.load(open(RAW + "/projects_toml_metrics.json"))
wf = json.load(open(RAW + "/workflow_metrics.json"))
pk = json.load(open(RAW + "/packaging_metrics.json"))
bw = json.load(open(RAW + "/repo_byte_weight.json"))
mi = json.load(open(RAW + "/module_inventory.json"))
tg = json.load(open(RAW + "/test_gap_findings.json"))
# Canonical deletion matrix is the top-level deletion_matrix.json; the
# raw/ verbatim copy was removed from the repo in the evidence-slimming
# pass. Fall back to the canonical location when the raw copy is absent.
try:
    dm = json.load(open(RAW + "/deletion_matrix.json"))
except FileNotFoundError:
    dm = json.load(open(BASE + "/deletion_matrix.json"))
cf = json.load(open(RAW + "/contract_findings.json"))

# ---------------------------------------------------------------- repository_metrics.json
sub = {}
for s in wf["project_context_yml"]["steps"]:
    sub[s["subsystem"]] = sub.get(s["subsystem"], 0) + s.get("span_lines", 0)
dsh_hist = sub.get("DSH", 0) + sub.get("HISTORICAL_REPAIR_REGRESSION", 0)
span_total = sum(sub.values())
tot_lines = wf["TOTAL_WORKFLOW_LINES"]

rm = {
    "audit": AUDIT,
    "repo_head": HEAD,
    "note": ("Consolidated from raw/ outputs only; no scans were re-run. "
             "Byte counts are worktree/CI-stdout measurements at HEAD be291300."),
    "sources": {
        "context_size": "raw/context_metrics.json",
        "project_state_size_and_counts": "raw/context_metrics.json + raw/projects_toml_metrics.json",
        "workflow_size": "raw/workflow_metrics.json",
        "packaging": "raw/packaging_metrics.json",
        "tracked_repo_byte_weight": "raw/repo_byte_weight.json",
        "code_test_module_counts": "raw/module_inventory.json",
        "deletion_candidates": "raw/deletion_matrix.json",
        "test_gaps": "raw/test_gap_findings.json",
    },
    "context_size": {
        "AGENTS_MD_BYTES": cm["AGENTS_MD_BYTES"],
        "README_BYTES": cm["README_BYTES"],
        "CURRENT_ROADMAP_BYTES": cm["CURRENT_ROADMAP_BYTES"],
        "PROJECTS_TOML_BYTES": cm["PROJECTS_TOML_BYTES"],
        "PROJECTS_TOML_LINES": cm["PROJECTS_TOML_LINES"],
        "PROJECT_CONTEXT_PY_BYTES": cm["PROJECT_CONTEXT_PY_BYTES"],
        "BRIEF_BYTES": cm["BRIEF_BYTES"],
        "BRIEF_LINES": cm["BRIEF_LINES"],
        "BRIEF_TRUNCATED": cm["BRIEF_TRUNCATED"],
        "SPINE_BYTES": cm["SPINE_BYTES"],
        "SPINE_LINES": cm["SPINE_LINES"],
        "SPINE_MODE": cm["SPINE_LINES_OR_SINGLE_LINE_BYTES"],
        "DUPLICATIVE_AUTHORITY_PROSE_BYTES_AGENTS_README_ROADMAP":
            cm["DUPLICATIVE_SIGNAL"]["byte_weight_agents_readme_roadmap"],
    },
    "project_state": {
        "total_project_records": pt["total_project_records"],
        "terminal_records": pt["terminal_record_count"],
        "non_terminal_records": pt["non_terminal_record_count"],
        "planned_records": pt["state_distribution"].get("PLANNED_NOT_AUTHORIZED", 0),
        "active_non_terminal_state": "BLOCKED",
        "state_distribution": pt["state_distribution"],
        "distinct_authority_field_names": len(pt["authority_field_names"]),
        "distinct_field_names_observed": len(pt["field_frequency"]),
        "records_with_hash_bindings": pt["records_with_hash_bindings"],
        "records_referencing_authoritative_artifacts":
            pt["records_referencing_authoritative_artifacts"],
        "next_action_length": pt["next_action_length"],
        "repo_wide_projects_toml_references": pt["projects_toml_references"]["count"],
    },
    "workflow": {
        "workflow_count": wf["WORKFLOW_COUNT"],
        "total_lines": tot_lines,
        "total_bytes": wf["TOTAL_WORKFLOW_BYTES"],
        "job_count": wf["JOB_COUNT"],
        "step_count": wf["STEP_COUNT"],
        "subsystem_span_lines": sub,
        "step_span_lines_total": span_total,
        "historical_repair_plus_dsh_span_lines": dsh_hist,
        "historical_repair_plus_dsh_share_of_step_spans_pct":
            round(100.0 * dsh_hist / span_total, 1),
        "lines_outside_core_and_ledger": tot_lines - sub.get("PROJECT_CONTEXT_CORE", 0)
        - sub.get("RESEARCH_LEDGER", 0),
        "project_context_core_span_lines": sub.get("PROJECT_CONTEXT_CORE", 0),
        "research_ledger_span_lines": sub.get("RESEARCH_LEDGER", 0),
        "project_context_core_share_of_total_lines_pct":
            round(100.0 * sub.get("PROJECT_CONTEXT_CORE", 0) / tot_lines, 1),
        "inline_scripts_over_30_lines": wf["inline_scripts_over_30_lines"],
        "pytest_selection": wf["pytest_selection"],
        "note_93pct_task_spec_figure": (
            "Measured: DSH+HISTORICAL_REPAIR_REGRESSION = 243 of 303 step-span lines "
            "(80.2%); 302 of 323 total YAML lines (93.5%) sit outside PROJECT_CONTEXT_CORE "
            "(16 lines) and RESEARCH_LEDGER (5 lines) combined."),
    },
    "packaging": {
        "HAS_PYPROJECT": pk["HAS_PYPROJECT"],
        "HAS_SETUP_PY": pk["HAS_SETUP_PY"],
        "HAS_SETUP_CFG": pk["HAS_SETUP_CFG"],
        "HAS_PYTEST_INI": pk["candidate_existence_at_repo_root"]["pytest.ini"],
        "HAS_CONFTEST_PY": pk["candidate_existence_at_repo_root"]["conftest.py"],
        "HAS_MAKEFILE": pk["HAS_MAKEFILE"],
        "HAS_TOX_INI": pk["HAS_TOX_INI"],
        "pytest_config_location": pk["pytest_config_location"],
        "qntylab_toml_bytes": pk["qntylab_toml_structure"]["bytes"],
        "requirements_files": [r["name"] for r in pk["requirements_files"]],
        "documented_verify": pk["documented_verify_lines"],
    },
    "tracked_repo_byte_weight": {
        "total_tracked_bytes": bw["total_tracked_bytes"],
        "total_tracked_mib": round(bw["total_tracked_bytes"] / 1048576.0, 1),
        "tracked_file_count": bw["tracked_file_count"],
        "bytes_by_top_level_directory": bw["bytes_by_top_level_directory"],
        "experiments_share_pct": round(
            100.0 * bw["bytes_by_top_level_directory"]["experiments"]
            / bw["total_tracked_bytes"], 1),
        "tracked_json_jsonl_bytes": bw["tracked_json_jsonl_weight_total_bytes"],
        "tracked_csv_bytes": bw["tracked_csv_weight_total_bytes"],
        "generated_looking_artifact_count": len(bw["generated_looking_artifacts"]),
        "git_count_objects": bw["git_count_objects_vH"],
        "largest_tracked_file": bw["largest_50_tracked_files"][0],
    },
    "code_test_module_counts": {
        "qntylab_python_modules": mi["module_count"],
        "qntylab_classification_distribution": mi["classification_distribution"],
        "near_duplicate_name_families": len(mi["near_duplicate_name_families"]),
        "zero_inbound_orphan_candidates": len(mi["orphan_candidates_zero_inbound"]),
        "duplicated_function_machinery_entries": len(mi["duplicated_function_machinery"]),
        "go_main": mi["go_main"],
        "tracked_test_files_tests_dir": 227,
        "tracked_test_python_files": 215,
        "note": ("file counts measured via git ls-files at HEAD be291300; "
                 "classification distribution from raw/module_inventory.json"),
    },
    "deletion_candidates": {
        "candidate_count": dm["candidate_count"],
        "classification_distribution": dm["classification_distribution"],
        "delete_safe_count": len(dm["delete_safe_list"]),
    },
}
dump(rm, BASE + "/repository_metrics.json")

# ---------------------------------------------------------------- inventory.json
SCHEMA = ["finding_id", "domain", "severity", "classification", "path",
          "lines_or_symbol", "claim", "evidence", "risk", "recommended_disposition",
          "implementation_authorized"]
# Optional extension field: contract findings CI-1/CI-23 carry an explicit
# "reachability" marker (LATENT_ON_MASTER / BRANCH_ONLY); it is not required
# on every finding, so it is intentionally excluded from the SCHEMA check.


def norm(f):
    out = {
        "finding_id": f["finding_id"],
        "domain": f["domain"],
        "severity": f["severity"],
        "classification": f["classification"],
        "path": f["path"],
        "lines_or_symbol": f.get("lines_or_symbol"),
        "claim": f["claim"],
        "evidence": f["evidence"],
        "risk": f["risk"],
        "recommended_disposition": f["recommended_disposition"],
        "implementation_authorized": False,
        "source_raw": "raw/contract_findings.json",
    }
    if f.get("reachability"):
        out["reachability"] = f["reachability"]
    return out


findings = [norm(f) for f in cf]

derived = [
    {
        "finding_id": "CTX-1", "domain": "D7", "severity": "MEDIUM",
        "classification": "DEFAULT_CONTEXT_OVERWEIGHT",
        "path": "docs/state/projects.toml",
        "lines_or_symbol": "whole file (9,933 lines)",
        "claim": ("docs/state/projects.toml is 576,993 bytes / 9,933 lines and is the default "
                  "loaded context surface for agent onboarding; it holds 149 project records "
                  "(139 terminal) and 474 distinct authority-field names, so the default context "
                  "is dominated by frozen historical state."),
        "evidence": [
            "raw/context_metrics.json: PROJECTS_TOML_BYTES=576993, PROJECTS_TOML_LINES=9933",
            ("raw/projects_toml_metrics.json: total_project_records=149, "
             "terminal_record_count=139, 474 distinct authority field names"),
            ("raw/context_metrics.json: PROJECT_COUNT_TERMINAL=139 of PROJECT_COUNT_TOTAL=149"),
        ],
        "risk": ("Cold-start context cost and attention dilution: terminal projects (93.3%) "
                 "outweigh live state; authority semantics spread across 474 field-name variants."),
        "recommended_disposition": (
            "KEEP (canonical authority, untouched); bound the agent-facing surface via a "
            "cold-start context packet (P1); any projects.toml restructuring requires "
            "separate governance."),
        "implementation_authorized": False,
        "source_raw": "raw/context_metrics.json + raw/projects_toml_metrics.json",
    },
    {
        "finding_id": "CTX-2", "domain": "D7", "severity": "MEDIUM",
        "classification": "SINGLE_LINE_MONOLITH_OUTPUT",
        "path": "qntylab/project_context.py",
        "lines_or_symbol": "spine command (rendered context spine stdout)",
        "claim": ("The rendered context spine is 50,150 bytes emitted as a single line, so it "
                  "cannot be diffed, streamed, partially consumed, or budgeted by line; any "
                  "consumer must take the whole blob or nothing."),
        "evidence": [
            ("raw/context_metrics.json: SPINE_BYTES=50150, SPINE_LINES=1, "
             "SPINE_LINES_OR_SINGLE_LINE_BYTES.mode=single_line, single_line_bytes=50150"),
            "raw/context_metrics.json: PROJECT_CONTEXT_PY_BYTES=110441 (generator itself is 110KB)",
        ],
        "risk": ("Unbudgeted context consumption; single-line format blocks incremental "
                 "loading and makes regressions invisible in diffs."),
        "recommended_disposition": (
            "KEEP output semantics; design a bounded packet (agent_context_target.md) as the "
            "agent-facing surface instead (P1); spine rendering changes require separate "
            "governance."),
        "implementation_authorized": False,
        "source_raw": "raw/context_metrics.json",
    },
    {
        "finding_id": "CTX-3", "domain": "D7", "severity": "MEDIUM",
        "classification": "BRIEF_TRUNCATION",
        "path": "qntylab/project_context.py",
        "lines_or_symbol": "brief command (stdout)",
        "claim": ("The project-context brief renders 14,468 bytes over 118 lines and is TRUNCATED "
                  "at HEAD be291300, so the canonical cold-start summary does not fully render "
                  "within its own bound."),
        "evidence": [
            "raw/context_metrics.json: BRIEF_BYTES=14468, BRIEF_LINES=118, BRIEF_TRUNCATED=true",
        ],
        "risk": ("Agents operating from the brief receive a partial projection and may miss "
                 "load-bearing invariants or blockers; truncation is silent in the artifact."),
        "recommended_disposition": (
            "KEEP behavior; treat truncation as a signal that the cold-start packet design "
            "(agent_context_target.md, <=8KB budget) must be explicit (P1)."),
        "implementation_authorized": False,
        "source_raw": "raw/context_metrics.json",
    },
    {
        "finding_id": "CTX-4", "domain": "D7", "severity": "LOW",
        "classification": "DUPLICATIVE_AUTHORITY_PROSE",
        "path": "AGENTS.md, README.md, docs/CURRENT_ROADMAP.md",
        "lines_or_symbol": "combined 77,057 bytes",
        "claim": ("AGENTS.md (2,805B), README.md (5,293B) and docs/CURRENT_ROADMAP.md (68,959B) "
                  "total 77,057 bytes and restate the same authority/exploratory-only invariants "
                  "with differing phrasing ('authority' appears 89 times in CURRENT_ROADMAP.md "
                  "alone), so invariant wording is not single-sourced."),
        "evidence": [
            "raw/context_metrics.json DUPLICATIVE_SIGNAL.byte_weight_agents_readme_roadmap=77057",
            ("raw/context_metrics.json DUPLICATIVE_SIGNAL.invariant_phrase_counts: "
             "CURRENT_ROADMAP.md authority=89; AGENTS.md authority=3, source_conflict=1; "
             "README.md authority=8"),
        ],
        "risk": ("Divergent paraphrases of invariants can drift; an agent reading only one "
                 "file may get a weaker variant of the rule."),
        "recommended_disposition": (
            "KEEP files (canonical prose); record invariant phrasing once in the cold-start "
            "packet with pointers (P1); consolidation requires separate governance."),
        "implementation_authorized": False,
        "source_raw": "raw/context_metrics.json",
    },
    {
        "finding_id": "CIX-1", "domain": "D9", "severity": "MEDIUM",
        "classification": "CI_DOMINATED_BY_HISTORICAL_REPLAY",
        "path": ".github/workflows/project-context.yml",
        "lines_or_symbol": "steps spanning lines 39-311; subsystem spans DSH=99, HISTORICAL_REPAIR_REGRESSION=144",
        "claim": ("The single CI workflow (323 lines, 19 steps) spends 243 of 303 step-span lines "
                  "(80.2%) on historical-repair regression and DSH replay; 302 of 323 total YAML "
                  "lines (93.5%) sit outside the project-context core (16 lines) and research-ledger "
                  "(5 lines) steps, so the authority-guarding core is only 5.0% of the workflow."),
        "evidence": [
            ("raw/workflow_metrics.json project_context_yml.subsystem_line_counts: DSH=99, "
             "HISTORICAL_REPAIR_REGRESSION=144, PROJECT_CONTEXT_CORE=16, RESEARCH_LEDGER=5, "
             "RUNTIME_PROVISIONING=34, OTHER_SUBSYSTEM=5"),
            "raw/workflow_metrics.json: TOTAL_WORKFLOW_LINES=323, STEP_COUNT=19",
            "raw/workflow_metrics.json inline_scripts_over_30_lines: 3 shell blocks of 68/58/40 run lines",
        ],
        "risk": ("CI time and failure surface dominated by frozen historical scenarios; core "
                 "authority checks are a thin slice; 68-line inline shell blocks are unauditable "
                 "as code."),
        "recommended_disposition": (
            "KEEP (no CI mutation in this audit); future P2 DevOps work could split historical "
            "replay from core checks -- requires separate governance."),
        "implementation_authorized": False,
        "source_raw": "raw/workflow_metrics.json",
    },
    {
        "finding_id": "CIX-2", "domain": "D9", "severity": "LOW",
        "classification": "INLINE_SCRIPT_COMPLEXITY",
        "path": ".github/workflows/project-context.yml",
        "lines_or_symbol": "run blocks at lines 125-194 (68), 194-254 (58), 270-311 (40)",
        "claim": ("Three inline shell run blocks exceed 30 lines (68, 58, 40 lines) implementing "
                  "DSH runtime provisioning and a provenance receipt inside YAML, outside any "
                  "tested Python module."),
        "evidence": [
            "raw/workflow_metrics.json inline_scripts_over_30_lines (3 entries with start/end lines)",
        ],
        "risk": "Untested inline logic in CI; provisioning regressions surface only at CI runtime.",
        "recommended_disposition": ("KEEP; extraction into tested scripts is P2 and requires "
                                    "separate governance."),
        "implementation_authorized": False,
        "source_raw": "raw/workflow_metrics.json",
    },
    {
        "finding_id": "PKG-1", "domain": "D10", "severity": "MEDIUM",
        "classification": "NO_PACKAGING_MANIFEST",
        "path": ". (repo root)",
        "lines_or_symbol": "absent files: pyproject.toml, setup.py, setup.cfg",
        "claim": ("The repository has no pyproject.toml, setup.py, setup.cfg, Makefile, tox.ini, "
                  "or lint/pre-commit configs; the qntylab package (133 modules, ~49.2k LOC) is "
                  "not installable as a declared package and tool behavior depends on CWD and "
                  "ad-hoc pip installs in CI."),
        "evidence": [
            ("raw/packaging_metrics.json: HAS_PYPROJECT=false, HAS_SETUP_PY=false, "
             "HAS_SETUP_CFG=false, HAS_MAKEFILE=false, HAS_TOX_INI=false, "
             "candidates_found_anywhere_tracked={}"),
            ("raw/packaging_metrics.json ci_bootstrap_sequence: 'python -m pip install pytest "
             "requests' at .github/workflows/project-context.yml:72"),
            "raw/module_inventory.json: module_count=133",
        ],
        "risk": ("Non-reproducible environments; module resolution differences between CI and "
                 "local runs; no single dependency declaration for the package itself."),
        "recommended_disposition": (
            "KEEP structure; introducing packaging metadata is a P2/P3 change requiring separate "
            "governance (must not alter import semantics of frozen modules)."),
        "implementation_authorized": False,
        "source_raw": "raw/packaging_metrics.json",
    },
    {
        "finding_id": "PKG-2", "domain": "D10", "severity": "LOW",
        "classification": "NONSTANDARD_PYTEST_CONFIG",
        "path": "qntylab.toml",
        "lines_or_symbol": "whole file (585 bytes, 18 lines)",
        "claim": ("There is no pytest.ini, pyproject.toml pytest section, or conftest.py at the "
                  "repo root; pytest configuration lives only in the nonstandard qntylab.toml "
                  "(585B), while README.md:65 documents 'python -m pytest -q' as the verify "
                  "command."),
        "evidence": [
            ("raw/packaging_metrics.json pytest_config_location: pytest.ini=false, "
             "pyproject.toml=false, conftest.py=false, qntylab.toml=true"),
            ("raw/packaging_metrics.json documented_verify_lines: README.md:65 "
             "'python -m pytest -q'"),
            "raw/packaging_metrics.json qntylab_toml_structure: bytes=585, lines=18",
        ],
        "risk": ("Tooling that expects standard pytest discovery config behaves differently; "
                 "new contributors may miss marker/option semantics."),
        "recommended_disposition": (
            "KEEP (qntylab.toml is referenced by canonical tooling); standardization is P2 and "
            "requires separate governance."),
        "implementation_authorized": False,
        "source_raw": "raw/packaging_metrics.json",
    },
    {
        "finding_id": "DUP-1", "domain": "D11", "severity": "MEDIUM",
        "classification": "MODULE_PROLIFERATION_FROZEN_HISTORICAL",
        "path": "qntylab/",
        "lines_or_symbol": "133 modules; classification distribution",
        "claim": ("qntylab/ holds 133 Python modules (~49.2k LOC) of which 64 are "
                  "FROZEN_HISTORICAL_EVIDENCE, 8 FROZEN_ORACLE, 35 TEST_SUPPORT, 6 "
                  "GOVERNANCE_SUPPORT, 15 LIVE_RUNTIME_CODE and 5 POSSIBLE_DEAD_CODE; only ~15 "
                  "modules are live runtime code, so the package is majority frozen history."),
        "evidence": [
            "raw/module_inventory.json: module_count=133",
            ("raw/module_inventory.json classification_distribution: "
             "{FROZEN_HISTORICAL_EVIDENCE:64, FROZEN_ORACLE:8, GOVERNANCE_SUPPORT:6, "
             "LIVE_RUNTIME_CODE:15, POSSIBLE_DEAD_CODE:5, TEST_SUPPORT:35}"),
            "raw/repo_byte_weight.json: qntylab directory = 2,454,793 bytes",
        ],
        "risk": ("Cold-start comprehension cost, import-graph complexity, and a large surface "
                 "for accidental coupling to frozen modules."),
        "recommended_disposition": (
            "KEEP frozen modules (bound to hash-anchored evidence); consolidation only via the "
            "deletion matrix with per-candidate reference checks (P3/P4, separate governance)."),
        "implementation_authorized": False,
        "source_raw": "raw/module_inventory.json",
    },
    {
        "finding_id": "DUP-2", "domain": "D11", "severity": "LOW",
        "classification": "NEAR_DUPLICATE_VERSION_FAMILIES",
        "path": "qntylab/",
        "lines_or_symbol": ("4 families: jh01_rv_persistence_incremental_forecast_value_prereg_v0/v1; "
                            "jh01_rv_persistence_temporal_replication_execution_v0/v0r1; "
                            "jigsaw_fast_prospective_signal_discovery_prereg_v0/v1; "
                            "pinned_dsh_codex_write_path_materialization_v0/v0r1"),
        "claim": ("Four near-duplicate version-suffix module families exist, each with a successor "
                  "module retained alongside its predecessor (inbound qntylab imports = 0 for all "
                  "listed members; only test imports bind them)."),
        "evidence": [
            ("raw/module_inventory.json near_duplicate_name_families: 4 families with member "
             "inbound counts (qntylab_inbound=0 for all listed members; test_inbound 1-2 each)"),
        ],
        "risk": "Successor/predecessor confusion; tests pinning the wrong member keep dead machinery alive.",
        "recommended_disposition": ("KEEP (hash-bound frozen artifacts); supersession-based "
                                    "consolidation is P3 and requires separate governance."),
        "implementation_authorized": False,
        "source_raw": "raw/module_inventory.json",
    },
    {
        "finding_id": "DUP-3", "domain": "D11", "severity": "LOW",
        "classification": "ORPHANS_AND_DUPLICATED_MACHINERY",
        "path": "qntylab/",
        "lines_or_symbol": "10 zero-inbound orphan candidates; 122 duplicated-function-machinery entries",
        "claim": ("10 modules have zero inbound qntylab imports (orphan candidates, incl. "
                  "acquire_v2, dsh_stage_a_v1r1_cli, jigsaw_external_replication_execution_v0) and "
                  "122 same-name/similar-body function-machinery entries recur across 2+ modules."),
        "evidence": [
            "raw/module_inventory.json orphan_candidates_zero_inbound (10 entries)",
            "raw/module_inventory.json duplicated_function_machinery: list of 122 entries",
            ("raw/deletion_matrix.json: of 42 candidates, DELETE_SAFE=6, "
             "DELETE_BLOCKED_BY_FROZEN_BINDING=28, DELETE_BLOCKED_BY_ACTIVE_USE=8"),
        ],
        "risk": ("Dead code and copy-pasted machinery inflate maintenance surface; only 6 "
                 "candidates are provably delete-safe today."),
        "recommended_disposition": ("Defer to raw/deletion_matrix.json classifications; any "
                                    "deletion is P3/P4 and requires separate governance (this "
                                    "audit deletes nothing)."),
        "implementation_authorized": False,
        "source_raw": "raw/module_inventory.json + raw/deletion_matrix.json",
    },
    {
        "finding_id": "BYT-1", "domain": "D13", "severity": "MEDIUM",
        "classification": "TRACKED_BYTE_WEIGHT",
        "path": "experiments/",
        "lines_or_symbol": "experiments/ = 72,935,668 of 100,472,910 tracked bytes (72.6%)",
        "claim": ("The tracked tree weighs 100,472,910 bytes (~95.8 MiB) over 4,115 files; "
                  "experiments/ alone is 72,935,668 bytes (72.6%) and data/ is 21,093,250 bytes; "
                  "git pack size is 85.86 MiB."),
        "evidence": [
            ("raw/repo_byte_weight.json: total_tracked_bytes=100472910, tracked_file_count=4115, "
             "bytes_by_top_level_directory.experiments=72935668, .data=21093250"),
            "raw/repo_byte_weight.json git_count_objects_vH: size-pack=85.86 MiB, in-pack=12492",
            ("raw/repo_byte_weight.json largest tracked file: "
             "experiments/results/breadth_v2_development_v0/BREADTH_V2_DEVELOPMENT_DECISION_V0.json "
             "(15,655,624 bytes)"),
        ],
        "risk": ("Clone/fetch cost, editor indexing cost, and diff noise; growth compounds as "
                 "results accumulate in-tree."),
        "recommended_disposition": ("KEEP (frozen evidence bindings); relocation/archival of "
                                    "result blobs is P4 and requires separate governance."),
        "implementation_authorized": False,
        "source_raw": "raw/repo_byte_weight.json",
    },
    {
        "finding_id": "BYT-2", "domain": "D13", "severity": "LOW",
        "classification": "GENERATED_ARTIFACTS_IN_TREE",
        "path": "experiments/, data/",
        "lines_or_symbol": "98 generated-looking artifacts; JSON/JSONL 59,972,906B + CSV 32,709,614B",
        "claim": ("98 tracked files match generated-artifact heuristics; tracked JSON/JSONL totals "
                  "59,972,906 bytes and CSV 32,709,614 bytes, together ~92% of tracked weight -- "
                  "machine-derived outputs stored alongside source."),
        "evidence": [
            ("raw/repo_byte_weight.json: tracked_json_jsonl_weight_total_bytes=59972906, "
             "tracked_csv_weight_total_bytes=32709614, generated_looking_artifacts list length=98"),
        ],
        "risk": ("Result blobs dominate repo weight and are the raw material of any future "
                 "slimming; accidental mutation would be indistinguishable from evidence without "
                 "hash bindings."),
        "recommended_disposition": ("KEEP (hash-bound); relocation is P4, separate governance; "
                                    "note raw/repo_byte_weight.json records -1 for "
                                    "tracked-but-missing worktree paths."),
        "implementation_authorized": False,
        "source_raw": "raw/repo_byte_weight.json",
    },
    {
        "finding_id": "TST-1", "domain": "D14", "severity": "MEDIUM",
        "classification": "TEST_EFFECTIVENESS_GAP_SUMMARY",
        "path": "tests/",
        "lines_or_symbol": ("PR #241 branch tests (tests/test_funding_incremental_real_execution_consumer_seam_successor_v0.py); "
                            "probes over tests/*.py at HEAD"),
        "claim": ("Test-effectiveness gaps (not test absence) let both P1 contract defects on "
                  "unmerged PR #241 pass: constructor-trust fixtures, weak assertions, no "
                  "restart/multiprocess coverage (probe 'multiprocess_or_restart_coverage' "
                  "returned zero files), and no adversarial-provenance tests; 7 repository-wide "
                  "invariant-test recommendations are recorded."),
        "evidence": [
            ("raw/test_gap_findings.json p1_findings: 2 P1s with gap classes "
             "MISSING_ADVERSARIAL_PROVENANCE_TEST / FIXTURE_ASSUMES_CONTRACT / "
             "ASSERTION_TOO_WEAK / OVERFIT_TO_IMPLEMENTATION and MISSING_RESTART_TEST / "
             "MISSING_MULTIPROCESS_TEST"),
            ("raw/test_gap_findings.json master_blind_spot_probes.probes.multiprocess_or_restart_coverage "
             "= [] (no files)"),
            ("raw/test_gap_findings.json invariant_test_recommendations: 7 entries; "
             "no_tests_added=true"),
            "raw/test_gap_findings.json context: pr=241, merged=false",
        ],
        "risk": ("Fixtures that assume the contract under test cannot detect provenance "
                 "laundering or exactly-once persistence lies; the same gap classes generalize "
                 "to other seams."),
        "recommended_disposition": ("Adopt invariant-test recommendations in future PRs "
                                    "(P0-adjacent hardening for any successor of #241); this "
                                    "audit added no tests."),
        "implementation_authorized": False,
        "source_raw": "raw/test_gap_findings.json",
    },
]
for d in derived:
    missing = [k for k in SCHEMA if k not in d]
    assert not missing, (d["finding_id"], missing)
findings.extend(derived)

sev = collections.Counter(f["severity"] for f in findings)
dom = collections.Counter(f["domain"] for f in findings)
inv = {
    "audit": AUDIT,
    "repo_head": HEAD,
    "finding_count": len(findings),
    "severity_counts": dict(sorted(sev.items())),
    "domain_counts": dict(sorted(dom.items())),
    "schema_fields": SCHEMA,
    "sources": {
        "CI-1..CI-26": "raw/contract_findings.json",
        "CTX-*": "raw/context_metrics.json + raw/projects_toml_metrics.json (domain D7)",
        "CIX-*": "raw/workflow_metrics.json (domain D9)",
        "PKG-*": "raw/packaging_metrics.json (domain D10)",
        "DUP-*": "raw/module_inventory.json + raw/deletion_matrix.json (domain D11)",
        "BYT-*": "raw/repo_byte_weight.json (domain D13)",
        "TST-*": "raw/test_gap_findings.json (domain D14)",
    },
    "findings": findings,
}
dump(inv, BASE + "/inventory.json")

# ---------------------------------------------------------------- deletion_matrix.json
# The canonical deletion matrix is the top-level deletion_matrix.json. The
# raw/ verbatim copy was removed in the evidence-slimming pass, so the copy
# step only runs when a raw copy is present (e.g. regenerated from an
# earlier scanner run); otherwise the canonical file is left untouched.
if os.path.exists(RAW + "/deletion_matrix.json"):
    shutil.copyfile(RAW + "/deletion_matrix.json", BASE + "/deletion_matrix.json")
else:
    print("raw/deletion_matrix.json absent; canonical deletion_matrix.json "
          "left unchanged")

print("severity:", dict(sorted(sev.items())))
print("domains:", dict(sorted(dom.items())))
print("findings:", len(findings))
print("wrote repository_metrics.json, inventory.json, deletion_matrix.json")
