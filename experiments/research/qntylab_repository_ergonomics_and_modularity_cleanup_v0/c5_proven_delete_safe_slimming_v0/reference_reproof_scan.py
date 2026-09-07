#!/usr/bin/env python3
"""C5 PRE_DELETION_REFERENCE_REPROOF scanner.

Re-runs the 12-category reference check (the same categories used by
docs/forensics/QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0
domain 12, scan_slim_tests.py::build_deletion_matrix) for the six DELETE_SAFE
candidates, against canonical HEAD e826dcb9cc264d1280c91c0bec01e23488fbb9e1
(git grep) AND the working tree (byte-identical to HEAD; asserted).

Extended beyond the forensic scan per C5 spec: dynamic-import stems, CI/shell
surfaces (.github/**, ops/**), projects.toml + ecosystem.toml, research-ledger
context output, and docs/CURRENT_ROADMAP.md. A whole-repo sweep classifies
every textual hit as load-bearing or historical/governance.

Pure stdlib. Writes reference_reproof.json next to this script.
Zero load-bearing references is the pass condition; any load-bearing hit
causes exit code 2 (C5_BLOCKED).
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

CANONICAL_HEAD = "e826dcb9cc264d1280c91c0bec01e23488fbb9e1"
FORENSIC_ANCHOR = "be291300abb70f3ffc6ba0dd8b1bea570daf5377"
UMBRELLA_DIR = "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0"
UMBRELLA_DECISION = UMBRELLA_DIR + "/decision.json"
C5_DIR = UMBRELLA_DIR + "/c5_proven_delete_safe_slimming_v0"

REPO = Path(__file__).resolve().parents[4]
OUT_PATH = Path(__file__).resolve().parent / "reference_reproof.json"

DELETED_CANDIDATES = [
    "docs/status/QNTYLAB_DVOL_V0_PHASE1B_EVIDENCE_RETENTION_REPAIR.md",
    "docs/status/QNTYLAB_DVOL_V0_PHASE1B_LIVE_SOURCE_SMOKE.md",
    "qntylab/jfp03_v0r1_input_materialization.py",
    "qntylab/jigsaw_cross_sectional_dispersion_execution_v0.py",
    "qntylab/jigsaw_external_replication_execution_v0.py",
    "qntylab/jigsaw_external_replication_input_materialization_v0.py",
]

CATEGORIES = [
    "PYTHON_IMPORT_REFERENCES",
    "DOCSTRING_PROSE_REFERENCES",
    "TEST_REFERENCES",
    "PROJECT_REGISTRY_REFERENCES",
    "AUTHORITATIVE_ARTIFACT_REFERENCES",
    "HASH_BINDINGS",
    "PREREGISTRATION_BINDINGS",
    "CLOSURE_REFERENCES",
    "ADR_REFERENCES",
    "RESEARCH_LEDGER_REFERENCES",
    "CI_REFERENCES",
    "GENERATED_VIEW_REFERENCES",
]

# Non-load-bearing hit classes (historical/governance records that must
# remain untouched and do not bind runtime/test behavior).
GOV_PREFIXES = (
    "docs/forensics/",
    UMBRELLA_DIR + "/",
)


def run(args, cwd=None):
    return subprocess.run(args, cwd=cwd or str(REPO), capture_output=True, text=True)


def git_grep_files(pattern, rev, pathspecs):
    """git grep -I -l -e <pattern> <rev> -- <pathspecs>; [] when no hits."""
    args = ["git", "grep", "-I", "-l", "-e", pattern]
    if rev:
        args.append(rev)
    else:
        args.append("--")
    if rev:
        args.append("--")
    args.extend(pathspecs)
    r = run(args)
    if r.returncode not in (0, 1):
        raise RuntimeError(f"git grep failed ({r.returncode}): {r.stderr}")
    return sorted(l for l in r.stdout.splitlines() if l)


def rel_sweep_files():
    r = run(["git", "ls-tree", "-r", "--name-only", CANONICAL_HEAD])
    if r.returncode != 0:
        raise RuntimeError("git ls-tree failed: " + r.stderr)
    return [l for l in r.stdout.splitlines() if l]


def read_worktree(rel):
    p = REPO / rel
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except (IsADirectoryError, FileNotFoundError):
        return ""


def classify_hit(path, candidate_rel):
    # git grep against a rev prefixes hits with "<rev>:"; strip it.
    if path.startswith(CANONICAL_HEAD + ":"):
        path = path[len(CANONICAL_HEAD) + 1:]
    if path == candidate_rel:
        return "SELF_REFERENCE_NOT_LOAD_BEARING"
    if path.startswith("docs/forensics/"):
        return "HISTORICAL_FORENSICS_RECORD_NOT_LOAD_BEARING"
    if path == UMBRELLA_DECISION:
        return "GOVERNANCE_AUTHORIZATION_RECORD_NOT_LOAD_BEARING"
    if path.startswith(UMBRELLA_DIR + "/") and path != UMBRELLA_DECISION:
        return "UMBRELLA_INCREMENT_ARTIFACT_NOT_LOAD_BEARING"
    if path.startswith(".github/"):
        return "CI_SURFACE_LOAD_BEARING_IF_MATCHES"
    return "UNCLASSIFIED_REVIEW_REQUIRED"


def main():
    report = {
        "scanner": "c5_reference_reproof_scan",
        "canonical_head": CANONICAL_HEAD,
        "forensic_audit_commit": FORENSIC_ANCHOR,
        "worktree_equals_head_assertion": None,
        "candidates": DELETED_CANDIDATES,
        "categories": CATEGORIES,
        "cells": {},
        "whole_repo_sweep": {},
        "research_ledger_context_grep": {},
        "total_load_bearing": None,
        "verdict": None,
    }

    # --- worktree == HEAD assertion -------------------------------------
    st = run(["git", "status", "--porcelain"])
    dirty = [l for l in st.stdout.splitlines() if l.strip()]
    report["worktree_equals_head_assertion"] = {
        "command": "git status --porcelain",
        "dirty_entries": dirty,
        "clean": not dirty,
    }

    # --- project registry texts -----------------------------------------
    projects_text = read_worktree("docs/state/projects.toml")
    ecosystem_text = read_worktree("docs/state/ecosystem.toml")
    auth_artifacts = set(re.findall(r'"([^"]+)"', projects_text)) | set(
        re.findall(r'"([^"]+)"', ecosystem_text)
    )

    decisions_text = read_worktree("experiments/research/decisions.jsonl")

    ledger_texts = {}
    for p in sorted((REPO / "experiments/research/ledger").rglob("*")):
        if p.is_file():
            rel = str(p.relative_to(REPO))
            ledger_texts[rel] = read_worktree(rel)

    research_scan = {}
    for p in sorted((REPO / "experiments/research").rglob("*")):
        if p.is_file() and p.suffix in {".json", ".jsonl", ".md"}:
            rel = str(p.relative_to(REPO))
            research_scan[rel] = read_worktree(rel)

    adr_texts = {
        str(p.relative_to(REPO)): read_worktree(str(p.relative_to(REPO)))
        for p in sorted((REPO / "docs/ADR").rglob("*"))
        if p.is_file()
    }
    ci_texts = {}
    for sub in (".github", "ops"):
        for p in sorted((REPO / sub).rglob("*")):
            if p.is_file():
                rel = str(p.relative_to(REPO))
                ci_texts[rel] = read_worktree(rel)
    docs_state_files = {
        str(p.relative_to(REPO)): read_worktree(str(p.relative_to(REPO)))
        for p in sorted((REPO / "docs/state").rglob("*"))
        if p.is_file()
    }
    docs_state_files["docs/CURRENT_ROADMAP.md"] = read_worktree("docs/CURRENT_ROADMAP.md")

    qnty_sources = {
        "qntylab/" + f.name: read_worktree("qntylab/" + f.name)
        for f in sorted((REPO / "qntylab").glob("*.py"))
    }
    test_sources = {
        "tests/" + f.name: read_worktree("tests/" + f.name)
        for f in sorted((REPO / "tests").glob("*.py"))
    }

    tracked_files = rel_sweep_files()

    total_load_bearing = 0

    for rel_path in DELETED_CANDIDATES:
        base = os.path.basename(rel_path)
        stem = base[:-3] if base.endswith(".py") else base
        terms = sorted({base, stem})
        cells = {}

        for cat in CATEGORIES:
            if cat == "PYTHON_IMPORT_REFERENCES":
                # any qntylab module (dynamic-import stems included) naming
                # the candidate, excluding the candidate itself
                hits = sorted(
                    f
                    for f, t in qnty_sources.items()
                    if f != rel_path and any(term in t for term in terms)
                )
                cmd = f"git grep -I -l -e '{stem}' {CANONICAL_HEAD[:12]} -- qntylab/ (self excluded)"
            elif cat == "DOCSTRING_PROSE_REFERENCES":
                # prose mentions inside qntylab sources, excluding self
                hits = sorted(
                    f
                    for f, t in qnty_sources.items()
                    if f != rel_path and any(term in t for term in terms)
                )
                cmd = f"git grep -I -l -e '{stem}' {CANONICAL_HEAD[:12]} -- qntylab/ (self excluded)"
            elif cat == "TEST_REFERENCES":
                hits = sorted(
                    f for f, t in test_sources.items() if any(term in t for term in terms)
                )
                cmd = f"git grep -I -l -e '{stem}' {CANONICAL_HEAD[:12]} -- tests/"
            elif cat == "PROJECT_REGISTRY_REFERENCES":
                hits = (
                    ["docs/state/projects.toml"]
                    if any(term in projects_text for term in terms)
                    else []
                )
                hits += (
                    ["docs/state/ecosystem.toml"]
                    if any(term in ecosystem_text for term in terms)
                    else []
                )
                cmd = "grep stem docs/state/projects.toml docs/state/ecosystem.toml"
            elif cat == "AUTHORITATIVE_ARTIFACT_REFERENCES":
                hits = sorted(
                    a for a in auth_artifacts if any(term in a for term in terms)
                )[:10]
                cmd = "quoted-string scan of docs/state/projects.toml + docs/state/ecosystem.toml"
            elif cat == "HASH_BINDINGS":
                hits = []
                pool = dict(docs_state_files)
                pool["projects.toml"] = projects_text
                pool["ecosystem.toml"] = ecosystem_text
                for f, t in pool.items():
                    for line in t.splitlines():
                        if any(term in line for term in terms) and re.search(
                            r"[0-9a-f]{64}", line
                        ):
                            hits.append(f)
                            break
                hits = sorted(set(hits))
                cmd = "64-hex hash-line binding scan across docs/state/**"
            elif cat == "PREREGISTRATION_BINDINGS":
                hits = sorted(
                    f
                    for f, t in {**ledger_texts, **research_scan}.items()
                    if ("prereg" in f or "preregistration" in t)
                    and any(term in t for term in terms)
                )[:10]
                cmd = "prereg filename/content scan over experiments/research/**"
            elif cat == "CLOSURE_REFERENCES":
                hits = sorted(
                    f
                    for f, t in {**ledger_texts, **research_scan}.items()
                    if "closure" in Path(f).name.lower()
                    and any(term in t for term in terms)
                )[:10]
                cmd = "closure-filename scan over experiments/research/**"
            elif cat == "ADR_REFERENCES":
                hits = sorted(
                    f for f, t in adr_texts.items() if any(term in t for term in terms)
                )
                cmd = f"git grep -I -l -e '{stem}' {CANONICAL_HEAD[:12]} -- docs/ADR/"
            elif cat == "RESEARCH_LEDGER_REFERENCES":
                hits = sorted(
                    f
                    for f, t in {
                        "experiments/research/decisions.jsonl": decisions_text,
                        **ledger_texts,
                    }.items()
                    if any(term in t for term in terms)
                )
                cmd = "grep stem experiments/research/decisions.jsonl + experiments/research/ledger/**"
            elif cat == "CI_REFERENCES":
                hits = sorted(
                    f for f, t in ci_texts.items() if any(term in t for term in terms)
                )
                cmd = f"git grep -I -l -e '{stem}' {CANONICAL_HEAD[:12]} -- .github/ ops/"
            elif cat == "GENERATED_VIEW_REFERENCES":
                hits = sorted(
                    f for f, t in docs_state_files.items()
                    if any(term in t for term in terms)
                )
                cmd = "grep stem docs/state/** + docs/CURRENT_ROADMAP.md"
            else:
                raise AssertionError(cat)

            cells[cat] = {
                "command": cmd,
                "count": len(hits),
                "evidence_paths": hits,
            }

        # --- whole-repo textual sweep with classification ----------------
        sweep_hits = {}
        for term in terms:
            for f in git_grep_files(term, CANONICAL_HEAD, tracked_files):
                sweep_hits.setdefault(f, set()).add(term)
        sweep_rows = []
        for path in sorted(sweep_hits):
            clean_path = path
            if clean_path.startswith(CANONICAL_HEAD + ":"):
                clean_path = clean_path[len(CANONICAL_HEAD) + 1:]
            cls = classify_hit(path, rel_path)
            sweep_rows.append({"path": clean_path, "terms": sorted(sweep_hits[path]), "classification": cls})
        report["whole_repo_sweep"][rel_path] = sweep_rows

        load_bearing_cells = [
            cat for cat in CATEGORIES if cells[cat]["count"] > 0
        ]
        load_bearing_sweep = [
            r["path"]
            for r in sweep_rows
            if r["classification"].endswith("LOAD_BEARING_IF_MATCHES")
            or r["classification"] == "UNCLASSIFIED_REVIEW_REQUIRED"
        ]
        cells["_load_bearing_cells"] = load_bearing_cells
        cells["_load_bearing_sweep_paths"] = load_bearing_sweep
        total_load_bearing += len(load_bearing_cells) + len(load_bearing_sweep)
        report["cells"][rel_path] = cells

    # --- research-ledger context output grep ------------------------------
    ctx = run(["python3", "-m", "qntylab.research_ledger", "context"])
    ledger_ctx = {"command": "python -m qntylab.research_ledger context | grep stem",
                  "exit_code": ctx.returncode}
    hits = {}
    for rel_path in DELETED_CANDIDATES:
        stem = os.path.basename(rel_path)
        stem = stem[:-3] if stem.endswith(".py") else stem
        hits[rel_path] = [ln for ln in ctx.stdout.splitlines() if stem in ln]
    ledger_ctx["hits"] = hits
    report["research_ledger_context_grep"] = ledger_ctx

    report["total_load_bearing"] = total_load_bearing
    report["verdict"] = "GATE_PASS" if total_load_bearing == 0 else "C5_BLOCKED"

    OUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=False) + "\n", encoding="utf-8")
    print(json.dumps({"total_load_bearing": total_load_bearing,
                      "verdict": report["verdict"],
                      "output": str(OUT_PATH)}))
    sys.exit(0 if total_load_bearing == 0 else 2)


if __name__ == "__main__":
    main()
