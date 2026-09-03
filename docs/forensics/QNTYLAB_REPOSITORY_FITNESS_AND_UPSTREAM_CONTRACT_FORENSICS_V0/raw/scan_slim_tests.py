#!/usr/bin/env python3
"""Deterministic, stdlib-only forensics scanner for QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0.

Covers the mechanical parts of three domains:

* Domain 11 (module_inventory.json):
  - inventory of qntylab/*.py (+ qualifications/jh01_v0r3/main.go count)
  - bytes / line count / top-level defs+classes
  - AST import graph among qntylab modules
  - inbound test imports (tests/*.py)
  - zero-inbound-import orphan candidates
  - near-duplicate name families (_v0r1/_v0r2/_v1 suffix families)
  - constant/attestation-data-heavy modules (>70% literal/assignment lines)
  - duplicated machinery: same function name in 2+ modules with
    approximate body length within tolerance
  - classification of every module (deterministic rules + evidence greps)

* Domain 12 (deletion_matrix.json):
  - deletion/consolidation candidates = module orphans + largest tracked
    artifacts (from repo_byte_weight.json inputs, recomputed here) + docs/status
  - 9 reference checks: PYTHON_IMPORT_REFERENCES, TEST_REFERENCES,
    PROJECT_REGISTRY_REFERENCES, AUTHORITATIVE_ARTIFACT_REFERENCES,
    HASH_BINDINGS, PREREGISTRATION_BINDINGS, CLOSURE_REFERENCES,
    ADR_REFERENCES, RESEARCH_LEDGER_REFERENCES, CI_REFERENCES,
    GENERATED_VIEW_REFERENCES (all count + evidence paths)

* Domain 14 (test_gap_findings.json):
  - tests added on PR #241 branch (master...d181d120)
  - grep-based blind-spot probes over master tests (module-dict state asserts,
    happy-path authority construction, multiprocess/restart coverage)

Usage (from repo root):
    python3 docs/forensics/QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0/raw/scan_slim_tests.py

Outputs are written next to this script (raw/ dir). Deterministic: sorted
everywhere, no wall clock, no network. Requires only the Python stdlib.
"""
from __future__ import annotations

import ast
import json
import os
import re
import sys
from pathlib import Path

AUDIT = "QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0"
RAW = Path(__file__).resolve().parent
REPO = RAW.parents[3]  # raw/ -> AUDIT dir -> forensics -> docs -> repo root
HEAD = "be291300abb70f3ffc6ba0dd8b1bea570daf5377"

QNTYLAB_DIR = REPO / "qntylab"
TESTS_DIR = REPO / "tests"
PROJECTS_TOML = REPO / "docs" / "state" / "projects.toml"
RESEARCH_DIR = REPO / "experiments" / "research"
DECISIONS_JSONL = RESEARCH_DIR / "decisions.jsonl"
ADR_DIR = REPO / "docs" / "ADR"
CI_DIR = REPO / ".github" / "workflows"
DOCS_STATUS = REPO / "docs" / "status"
DOCS_STATE = REPO / "docs" / "state"

# --------------------------------------------------------------------------- helpers


def read_text(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def walk_sorted(root: Path, suffixes=None):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d not in {"__pycache__", ".git", "node_modules"})
        for fn in sorted(filenames):
            p = Path(dirpath) / fn
            if suffixes is None or p.suffix in suffixes:
                out.append(p)
    return sorted(out)


def repo_files():
    """All text-searchable tracked-ish files (uses filesystem + known ignore dirs)."""
    results = []
    for root in (REPO / "qntylab", REPO / "tests", REPO / "docs", REPO / "experiments",
                 REPO / ".github", REPO / "ops", REPO / "qualifications", REPO / "data"):
        if not root.exists():
            continue
        for p in walk_sorted(root):
            if p.suffix in {".py", ".md", ".json", ".jsonl", ".toml", ".yml", ".yaml", ".txt",
                            ".csv", ".jsonl", ".sig", ".go", ".ts", ".js", ".sha256", ""}:
                results.append(p)
    for name in ("AGENTS.md", "README.md", "qntylab.toml"):
        p = REPO / name
        if p.exists():
            results.append(p)
    return sorted(set(results))


def grep_files(pattern: str, files=None, flags=0):
    rx = re.compile(pattern, flags)
    hits = []
    for p in (files if files is not None else repo_files()):
        text = read_text(p)
        if rx.search(text):
            hits.append(str(p.relative_to(REPO)))
    return sorted(hits)


def grep_count(pattern: str, files=None, flags=0):
    rx = re.compile(pattern, flags)
    total = 0
    for p in (files if files is not None else repo_files()):
        total += len(rx.findall(read_text(p)))
    return total


# --------------------------------------------------------------------------- Domain 11


def module_imports(tree: ast.Module) -> set[str]:
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                mods.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module)
            elif node.level and node.level > 0:
                mods.add("__relative__")
    return mods


def qntylab_deps(mods: set[str]) -> set[str]:
    out = set()
    for m in mods:
        parts = m.split(".")
        if parts[0] == "qntylab":
            out.add(parts[1] if len(parts) > 1 else "__package__")
        # "from qntylab import x" handled above; also handle "from qntylab.mod import y"
    return out


def literal_assignment_line_ratio(source: str, tree: ast.Module) -> float:
    """Fraction of module-body-level statements that are Assign/AnnAssign with
    constant values, or constant-only containers. Constant-heavy = attestation data."""
    body = list(tree.body)
    if not body:
        return 0.0
    const_like = 0

    def is_const_expr(node):
        if isinstance(node, ast.Constant):
            return True
        if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
            return all(is_const_expr(e) for e in node.elts)
        if isinstance(node, ast.Dict):
            return all(is_const_expr(k) and is_const_expr(v) for k, v in zip(node.keys or [], node.values))
        return False

    for stmt in body:
        if isinstance(stmt, (ast.Assign, ast.AnnAssign)) and is_const_expr(stmt.value):
            const_like += 1
    return const_like / len(body)


def classify_module(rel_path: str, source: str, tree: ast.Module,
                    tests_importing: set[str], qnty_inbound: set[str],
                    projects_hits: list[str], research_hits: list[str],
                    constant_ratio: float) -> tuple[str, list[str]]:
    """One classification per module, deterministic rules with evidence."""
    name = Path(rel_path).stem
    evidence: list[str] = []
    is_test_only = bool(tests_importing) and not qnty_inbound
    referenced_binding = bool(projects_hits) or bool(research_hits)

    # frozen historical implementations: versioned suffix families referenced
    # by registry/research bindings, or test-only with a versioned suffix
    versioned = re.search(r"_v\d", name) is not None
    authorization_like = "authorization" in name
    prereg_like = "prereg" in name

    if name in {"__init__", "project_context", "research_ledger", "cli", "strategy_test"}:
        return "GOVERNANCE_SUPPORT", ["core governance/tooling module name"]
    if name == "test_support_never":
        return "TEST_SUPPORT", []

    if authorization_like or prereg_like:
        cls = "FROZEN_ORACLE" if referenced_binding else "GOVERNANCE_SUPPORT"
        return cls, (["referenced in projects.toml / experiments/research"] if referenced_binding else ["governance-named module, no registry binding"])

    if versioned and referenced_binding:
        return "FROZEN_HISTORICAL_EVIDENCE", ["versioned module name bound in projects.toml / experiments/research"]

    if is_test_only:
        if versioned:
            return "FROZEN_HISTORICAL_EVIDENCE", ["imported only by tests, versioned name"]
        return "TEST_SUPPORT", ["imported only by tests"]

    if qnty_inbound:
        return "LIVE_RUNTIME_CODE", ["imported by other qntylab modules"]

    # zero inbound from qntylab and tests:
    if constant_ratio > 0.7:
        return "FROZEN_ORACLE", [f"{constant_ratio:.0%} module-body lines are constant assignments (attestation/data)"]
    if referenced_binding:
        return "FROZEN_HISTORICAL_EVIDENCE", ["no inbound imports, but bound in projects.toml / experiments/research"]
    return "POSSIBLE_DEAD_CODE", ["zero inbound imports from qntylab and tests, no registry binding found"]


def build_module_inventory() -> dict:
    modules = {}
    py_paths = sorted(QNTYLAB_DIR.glob("*.py"))
    # parse sources once
    parsed = {}
    for p in py_paths:
        src = read_text(p)
        try:
            tree = ast.parse(src)
        except SyntaxError:
            tree = ast.Module(body=[], type_ignores=[])
        parsed[p] = (src, tree)

    # test imports of qntylab modules
    test_import_map: dict[str, set[str]] = {}
    for tp in sorted(TESTS_DIR.glob("*.py")):
        tsrc = read_text(tp)
        try:
            ttree = ast.parse(tsrc)
        except SyntaxError:
            continue
        mods = module_imports(ttree)
        # also handle "from qntylab import mod1, mod2"
        for node in ast.walk(ttree):
            if isinstance(node, ast.ImportFrom) and node.module == "qntylab":
                for alias in node.names:
                    mods.add(f"qntylab.{alias.name}")
        for m in mods:
            if m.startswith("qntylab."):
                short = m.split(".")[1]
                if short != "__init__":
                    test_import_map.setdefault(short, set()).add(tp.name)
    # direct "import qntylab.x" in tests
    for tp in sorted(TESTS_DIR.glob("*.py")):
        tsrc = read_text(tp)
        for m in re.findall(r"import\s+qntylab\.([A-Za-z_][A-Za-z0-9_]*)", tsrc):
            test_import_map.setdefault(m, set()).add(tp.name)

    # projects.toml / experiments/research filename references
    toml_text = read_text(PROJECTS_TOML)
    research_files = walk_sorted(RESEARCH_DIR)

    for p in py_paths:
        src, tree = parsed[p]
        short = p.stem
        mods = module_imports(tree)
        # from qntylab import executor  (alias=module)
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "qntylab":
                for alias in node.names:
                    mods.add(f"qntylab.{alias.name}")
        deps = sorted(qntylab_deps(mods))
        tests = sorted(test_import_map.get(short, set()))

        qnty_inbound_hits = sorted(
            q.stem for q, (osrc, otree) in parsed.items() if q != p and short in qntylab_deps(module_imports(otree))
        )
        # also from-import forms in other qntylab modules
        for q, (osrc, _otree) in parsed.items():
            if q == p:
                continue
            if re.search(rf"from\s+qntylab\s+import\s+.*\b{re.escape(short)}\b", osrc) or \
               re.search(rf"import\s+qntylab\.{re.escape(short)}\b", osrc):
                if q.stem not in qnty_inbound_hits:
                    qnty_inbound_hits.append(q.stem)
        qnty_inbound_hits = sorted(qnty_inbound_hits)

        const_ratio = literal_assignment_line_ratio(src, tree)
        fname = p.name
        projects_hits = [str(PROJECTS_TOML.relative_to(REPO))] if re.search(rf"\b{re.escape(fname)}\b", toml_text) else []
        # docstring/prose references from sibling qntylab modules (non-import bindings)
        docstring_refs = sorted(
            q.stem for q, (osrc, _t) in parsed.items()
            if q != p and re.search(rf"qntylab\.{re.escape(short)}\b|``{re.escape(short)}\b", osrc)
        )
        research_hits = []
        for rp in research_files:
            if fname in read_text(rp):
                research_hits.append(str(rp.relative_to(REPO)))

        classification, evidence = classify_module(
            str(p.relative_to(REPO)), src, tree, set(tests), set(qnty_inbound_hits),
            projects_hits, research_hits, const_ratio,
        )

        top_defs = sum(1 for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
        functions = {
            n.name: (n.end_lineno - n.lineno + 1) if hasattr(n, "end_lineno") else 0
            for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }

        modules[short] = {
            "path": str(p.relative_to(REPO)),
            "bytes": p.stat().st_size,
            "line_count": src.count("\n") + (1 if src and not src.endswith("\n") else 0),
            "top_level_defs_classes": top_defs,
            "imports_qntylab_modules": deps,
            "imported_by_qntylab_modules": qnty_inbound_hits,
            "imported_by_tests": tests,
            "constant_assignment_ratio": round(const_ratio, 3),
            "docstring_prose_references": docstring_refs,
            "projects_toml_filename_hits": projects_hits,
            "research_filename_hits": sorted(research_hits)[:10],
            "classification": classification,
            "classification_evidence": evidence,
            "top_level_function_line_lengths": functions,
        }

    # orphan list: zero inbound from qntylab or tests
    orphans = sorted(
        short for short, m in modules.items()
        if not m["imported_by_qntylab_modules"] and not m["imported_by_tests"]
        and short not in {"__init__", "cli"}  # entry points are re-export/CLI surfaces
    )

    # near-duplicate name families: base name + version suffix
    fam_rx = re.compile(r"^(?P<base>.*?)_v\d+[a-z0-9]*$")
    fams: dict[str, list[str]] = {}
    for short in modules:
        m = fam_rx.match(short)
        base = m.group("base") if m else short
        fams.setdefault(base, []).append(short)
    families = {}
    for base, members in sorted(fams.items()):
        if len(members) > 1:
            families[base] = {
                "members": sorted(members),
                "member_import_inbound_counts": {
                    mem: {
                        "qntylab_inbound": len(modules[mem]["imported_by_qntylab_modules"]),
                        "test_inbound": len(modules[mem]["imported_by_tests"]),
                    }
                    for mem in sorted(members)
                },
            }

    # duplicated machinery: identical top-level function names across 2+ modules
    name_index: dict[str, list[tuple[str, int]]] = {}
    for short, m in modules.items():
        for fname, length in m["top_level_function_line_lengths"].items():
            name_index.setdefault(fname, []).append((short, length))
    duplicates = []
    for fname, sites in sorted(name_index.items()):
        if len(sites) < 2:
            continue
        dupes = []
        for i in range(len(sites)):
            for j in range(i + 1, len(sites)):
                (a, la), (b, lb) = sites[i], sites[j]
                if abs(la - lb) <= max(3, int(0.15 * max(la, lb))):
                    dupes.append({
                        "module_a": a, "module_b": b,
                        "line_length_a": la, "line_length_b": lb,
                    })
        if dupes:
            duplicates.append({"function_name": fname, "duplicated_pairs": dupes})

    go_count = None
    go_main = REPO / "qualifications" / "jh01_v0r3" / "main.go"
    if go_main.exists():
        go_src = read_text(go_main)
        go_count = {
            "path": str(go_main.relative_to(REPO)),
            "bytes": go_main.stat().st_size,
            "line_count": go_src.count("\n") + 1,
            "func_count": len(re.findall(r"^func\s+", go_src, re.M)),
        }

    classification_distribution = {}
    for m in modules.values():
        classification_distribution[m["classification"]] = classification_distribution.get(m["classification"], 0) + 1

    return {
        "audit": AUDIT,
        "repo_head": HEAD,
        "domain": 11,
        "module_count": len(modules),
        "go_main": go_count,
        "modules": {k: modules[k] for k in sorted(modules)},
        "orphan_candidates_zero_inbound": orphans,
        "near_duplicate_name_families": families,
        "duplicated_function_machinery": duplicates,
        "constant_heavy_modules": sorted(
            short for short, m in modules.items() if m["constant_assignment_ratio"] > 0.7
        ),
        "classification_distribution": dict(sorted(classification_distribution.items())),
        "method": "AST import graph over qntylab/*.py + tests/*.py; filename grep over docs/state/projects.toml and experiments/research/",
    }


# --------------------------------------------------------------------------- Domain 12

REFERENCE_CHECKS = [
    "PYTHON_IMPORT_REFERENCES",
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


def classify_deletion(checks: dict) -> tuple[str, list[str]]:
    load_bearing = []
    for k in ("PYTHON_IMPORT_REFERENCES", "DOCSTRING_PROSE_REFERENCES", "TEST_REFERENCES",
              "PROJECT_REGISTRY_REFERENCES", "AUTHORITATIVE_ARTIFACT_REFERENCES",
              "HASH_BINDINGS", "PREREGISTRATION_BINDINGS", "CLOSURE_REFERENCES",
              "ADR_REFERENCES", "RESEARCH_LEDGER_REFERENCES", "CI_REFERENCES"):
        if checks[k]["count"] > 0:
            load_bearing.append(k)
    reasons = []
    if not load_bearing:
        return "DELETE_SAFE", ["zero load-bearing references across all checks"]
    reasons.append("load-bearing references: " + ",".join(load_bearing))
    if "PROJECT_REGISTRY_REFERENCES" in load_bearing or "HASH_BINDINGS" in load_bearing or "PREREGISTRATION_BINDINGS" in load_bearing:
        return "DELETE_BLOCKED_BY_FROZEN_BINDING", reasons
    if "PYTHON_IMPORT_REFERENCES" in load_bearing or "TEST_REFERENCES" in load_bearing or "CI_REFERENCES" in load_bearing:
        return "DELETE_BLOCKED_BY_ACTIVE_USE", reasons
    if "ADR_REFERENCES" in load_bearing or "RESEARCH_LEDGER_REFERENCES" in load_bearing or "CLOSURE_REFERENCES" in load_bearing:
        return "DELETE_BLOCKED_BY_PROVENANCE", reasons
    return "UNKNOWN", reasons


def build_deletion_matrix(inventory: dict) -> dict:
    projects_text = read_text(PROJECTS_TOML)
    # authoritative_artifacts arrays in projects.toml
    auth_artifacts = set(re.findall(r'"([^"]+)"', projects_text))
    decisions_text = read_text(DECISIONS_JSONL)
    ledger_texts = {}
    ledger_dir = RESEARCH_DIR / "ledger"
    if ledger_dir.exists():
        for p in walk_sorted(ledger_dir):
            ledger_texts[str(p.relative_to(REPO))] = read_text(p)
    docs_state_files = {str(p.relative_to(REPO)): read_text(p) for p in walk_sorted(DOCS_STATE)}
    adr_texts = {str(p.relative_to(REPO)): read_text(p) for p in walk_sorted(ADR_DIR)}
    ci_texts = {str(p.relative_to(REPO)): read_text(p) for p in walk_sorted(CI_DIR)}
    qnty_sources = {str(p.relative_to(REPO)): read_text(p) for p in QNTYLAB_DIR.glob("*.py")}
    test_sources = {str(p.relative_to(REPO)): read_text(p) for p in sorted(TESTS_DIR.glob("*.py"))}

    candidates: list[dict] = []

    def add_candidate(rel_path: str, kind: str, extra: str | None = None):
        base = os.path.basename(rel_path)
        stem = base[:-3] if base.endswith(".py") else base
        # split python refs into import-graph refs and docstring/prose refs
        inv_mod = inventory["modules"].get(stem)
        doc_refs = sorted(f"qntylab/{s}.py" for s in (inv_mod.get("docstring_prose_references", []) if inv_mod else []))
        py_hits = sorted(f for f, t in qnty_sources.items() if f != rel_path and (base in t or stem in t))
        test_hits = sorted(f for f, t in test_sources.items() if base in t or stem in t)
        registry_hits = [str(PROJECTS_TOML.relative_to(REPO))] if base in projects_text or stem in projects_text else []
        auth_hits = sorted(a for a in auth_artifacts if base in a or stem in a)
        # hash bindings: literal 64-hex near the name in projects.toml/manifests
        hash_hits = []
        for f, t in {**docs_state_files, **{str(PROJECTS_TOML.relative_to(REPO)): projects_text}}.items():
            for line in t.splitlines():
                if (base in line or stem in line) and re.search(r"[0-9a-f]{64}", line):
                    hash_hits.append(f)
                    break
        hash_hits = sorted(set(hash_hits))
        prereg_hits = sorted(
            f for f, t in {**ledger_texts, **{str(p.relative_to(REPO)): read_text(p) for p in walk_sorted(RESEARCH_DIR, suffixes={".json", ".jsonl"})}}.items()
            if ("prereg" in f or "preregistration" in t) and base in t
        )[:10]
        closure_hits = sorted(
            f for f, t in {**ledger_texts, **{str(p.relative_to(REPO)): read_text(p) for p in walk_sorted(RESEARCH_DIR, suffixes={".json", ".jsonl", ".md"})}}.items()
            if "closure" in Path(f).name.lower() and base in t
        )[:10]
        adr_hits = sorted(f for f, t in adr_texts.items() if base in t or stem in t)
        ledger_hits = sorted(
            f for f, t in {str(DECISIONS_JSONL.relative_to(REPO)): decisions_text, **ledger_texts}.items()
            if base in t or stem in t
        )
        ci_hits = sorted(f for f, t in ci_texts.items() if base in t or stem in t)
        view_hits = sorted(f for f, t in docs_state_files.items() if base in t or stem in t)

        checks = {
            "PYTHON_IMPORT_REFERENCES": {"count": len(py_hits), "evidence_paths": py_hits},
            "DOCSTRING_PROSE_REFERENCES": {"count": len(doc_refs), "evidence_paths": doc_refs},
            "TEST_REFERENCES": {"count": len(test_hits), "evidence_paths": test_hits},
            "PROJECT_REGISTRY_REFERENCES": {"count": len(registry_hits), "evidence_paths": registry_hits},
            "AUTHORITATIVE_ARTIFACT_REFERENCES": {"count": len(auth_hits), "evidence_paths": sorted(auth_hits)[:10]},
            "HASH_BINDINGS": {"count": len(hash_hits), "evidence_paths": hash_hits},
            "PREREGISTRATION_BINDINGS": {"count": len(prereg_hits), "evidence_paths": prereg_hits},
            "CLOSURE_REFERENCES": {"count": len(closure_hits), "evidence_paths": closure_hits},
            "ADR_REFERENCES": {"count": len(adr_hits), "evidence_paths": adr_hits},
            "RESEARCH_LEDGER_REFERENCES": {"count": len(ledger_hits), "evidence_paths": ledger_hits},
            "CI_REFERENCES": {"count": len(ci_hits), "evidence_paths": ci_hits},
            "GENERATED_VIEW_REFERENCES": {"count": len(view_hits), "evidence_paths": view_hits},
        }
        classification, reasons = classify_deletion(checks)
        row = {
            "candidate_path": rel_path,
            "candidate_kind": kind,
            "reference_checks": checks,
            "classification": classification,
            "classification_reasons": reasons,
        }
        if extra:
            row["notes"] = extra
        candidates.append(row)

    # 1) module orphans + POSSIBLE_DEAD_CODE from inventory
    for short in inventory["orphan_candidates_zero_inbound"]:
        m = inventory["modules"][short]
        if m["classification"] in {"POSSIBLE_DEAD_CODE", "FROZEN_HISTORICAL_EVIDENCE", "TEST_SUPPORT", "FROZEN_ORACLE"}:
            add_candidate(m["path"], "MODULE_ORPHAN_CANDIDATE",
                          extra=f"inventory_classification={m['classification']}")

    # 2) largest tracked artifacts (recompute from repo_byte_weight.json)
    rbw_path = RAW / "repo_byte_weight.json"
    if rbw_path.exists():
        rbw = json.loads(rbw_path.read_text(encoding="utf-8"))
        big = rbw.get("largest_50_tracked_files", [])
        gen = rbw.get("generated_looking_artifacts", [])
        seen = set()
        for entry in sorted(big + gen, key=lambda e: (-e["bytes"], e["path"]))[:60]:
            p = REPO / entry["path"]
            if entry["path"] in seen or not p.exists():
                continue
            seen.add(entry["path"])
            add_candidate(entry["path"], "LARGE_TRACKED_ARTIFACT", extra=f"bytes={entry['bytes']}")

    # 3) doc/status files
    for p in walk_sorted(DOCS_STATUS):
        add_candidate(str(p.relative_to(REPO)), "DOC_STATUS")

    # dedupe
    uniq = {}
    for row in candidates:
        uniq.setdefault(row["candidate_path"], row)
    rows = [uniq[k] for k in sorted(uniq)]

    dist = {}
    for row in rows:
        dist[row["classification"]] = dist.get(row["classification"], 0) + 1
    delete_safe = sorted(r["candidate_path"] for r in rows if r["classification"] == "DELETE_SAFE")

    return {
        "audit": AUDIT,
        "repo_head": HEAD,
        "domain": 12,
        "candidate_count": len(rows),
        "classification_distribution": dict(sorted(dist.items())),
        "delete_safe_list": delete_safe,
        "rows": rows,
        "method": "filename/stem grep across qntylab, tests, projects.toml (+authoritative_artifacts arrays), 64-hex hash-line binding check, preregistration/closure JSON in experiments/research, decisions.jsonl + ledger dir, ADRs, CI workflows, docs/state projection views. DELETE_SAFE requires zero load-bearing hits.",
    }


# --------------------------------------------------------------------------- Domain 14

PR241_TEST_FILE = "tests/test_funding_incremental_real_execution_consumer_seam_successor_v0.py"


def build_test_gap_findings() -> dict:
    import subprocess

    def git(args: list[str]) -> str:
        r = subprocess.run(["git"] + args, cwd=REPO, capture_output=True, text=True)
        return r.stdout if r.returncode == 0 else ""

    tests_on_branch = [l for l in git(["diff", "--name-only", "master...d181d120", "--", "tests/"]).splitlines() if l.strip()]

    # blind-spot probes over master tests (HEAD)
    probes = {}
    test_files = sorted(TESTS_DIR.glob("*.py"))
    probe_specs = {
        "module_private_state_asserts": r"_RECORDS\b|module\.__dict__|globals\(\)\[|_STATE\[|_LEDGER\[",
        "monkeypatch_of_qntylab_modules": r"monkeypatch\.setattr\([\"']?qntylab",
        "multiprocess_or_restart_coverage": r"multiprocessing|ProcessPool|mp\.Process|os\.execv|simulate.*restart|restart.*process",
        "direct_authority_or_provenance_construction": r"synthetic_only|authority_scope=|execution_mode=",
        "exactly_once_or_replay_asserts": r"replayed|exactly.once|idempoten",
    }
    for probe, pattern in probe_specs.items():
        hits = []
        rx = re.compile(pattern)
        for tp in test_files:
            if rx.search(read_text(tp)):
                hits.append(tp.name)
        probes[probe] = sorted(hits)

    findings = {
        "audit": AUDIT,
        "repo_head": HEAD,
        "domain": 14,
        "context": {
            "pr": 241,
            "branch": "agent/funding-incremental-real-execution-consumer-seam-successor-implementation-v0",
            "commits": ["cd999bc90191c43f42044f0f5fe47c2471614965", "d181d12096e19c1dbe2f89585e73b8f8f7b6b21f"],
            "merged": False,
            "tests_added_on_branch": tests_on_branch,
        },
        "p1_findings": [
            {
                "p1": "a_from_offline_synthetic_rows_forces_synthetic_only_true_on_arbitrary_rows",
                "defect": "ForecastRowBatch.from_offline_synthetic_rows accepts any sequence of typed ForecastRow values and unconditionally sets synthetic_only=True (branch module lines ~203-215), so rows of arbitrary provenance are laundered into a batch attested as synthetic.",
                "gap_class": "MISSING_ADVERSARIAL_PROVENANCE_TEST",
                "why_tests_passed": [
                    "FIXTURE_ASSUMES_CONTRACT: every batch in the test file is built via seam.ForecastRowBatch.from_offline_synthetic_rows(build_rows(...)) (test helper _batch), i.e. the sole constructor is also the defect; the tests trust the constructor name as the provenance statement.",
                    "ASSERTION_TOO_WEAK: test_typed_authority_boundary_preserves_frozen_result_and_ordering asserts synthetic behavior only indirectly (result_digest equality with the frozen executor run in EXECUTION_MODE_SYNTHETIC_VALIDATION); no test feeds a row whose origin field is a real/evidence origin and asserts rejection, because the seam's origin-interpretation helper _identity_scalar copies origin through without any origin allow-list check.",
                    "OVERFIT_TO_IMPLEMENTATION: tests assert structural properties (single public function, forbidden attribute names, manifest fields) but never the provenance invariant that inputs carrying non-synthetic origins must fail closed at the batch boundary.",
                ],
                "gap_tags": ["MISSING_ADVERSARIAL_PROVENANCE_TEST", "ASSERTION_TOO_WEAK", "FIXTURE_ASSUMES_CONTRACT", "OVERFIT_TO_IMPLEMENTATION"],
            },
            {
                "p1": "b_records_process_local_dict_claimed_exactly_once",
                "defect": "Exactly-once persistence is implemented as a process-local dict (_RECORDS at branch module line ~324, guarded by an RLock) and presented in ordering events/manifest as exactly-once recording; a process restart silently loses the ledger and re-records, and two processes each keep their own ledger.",
                "gap_class": "MISSING_RESTART_TEST",
                "why_tests_passed": [
                    "FIXTURE_ASSUMES_CONTRACT: the autouse fixture isolated_ephemeral_record_store clears seam._RECORDS around every test, normalizing ledger reset as expected behavior and never testing persistence across any state boundary.",
                    "MISSING_RESTART_TEST: no test re-imports the module, reloads it, or runs a second interpreter to observe that prior records vanish.",
                    "MISSING_MULTIPROCESS_TEST: no test runs consume_forecast_batch from two processes against the same record identity; the RLock only serializes threads within one process, so exactly-once holds only in-process and no test detects the multi-process divergence.",
                    "ASSERTION_TOO_WEAK: replay tests (test_typed_authority_boundary..., test_batch_and_record_serialization...) assert replayed is True for an in-process second call, which is satisfied equally by a dict lookup and by durable exactly-once storage; the manifest test asserts exactly_once.wall_clock_dependency is False but no test asserts the storage substrate survives process death.",
                ],
                "gap_tags": ["MISSING_RESTART_TEST", "MISSING_MULTIPROCESS_TEST", "ASSERTION_TOO_WEAK", "FIXTURE_ASSUMES_CONTRACT"],
            },
        ],
        "master_blind_spot_probes": {
            "method": "regex probes over tests/*.py at HEAD be291300 (filenames only, deterministic)",
            "probes": probes,
            "interpretation": {
                "module_private_state_asserts": "tests reaching into module-level private dicts/state directly (same class as the _RECORDS fixture clearing in #241): " + str(len(probes['module_private_state_asserts'])) + " file(s)",
                "monkeypatch_of_qntylab_modules": "tests monkeypatching qntylab module attributes (authority/behavior seams swappable in-test): " + str(len(probes['monkeypatch_of_qntylab_modules'])) + " file(s)",
                "multiprocess_or_restart_coverage": "nearly all hits are subprocess-based fixtures for external tools (pinned DSH, dvol smoke), not multiprocess/restart tests of claim/exactly-once paths: " + str(len(probes['multiprocess_or_restart_coverage'])) + " file(s)",
                "direct_authority_or_provenance_construction": "tests constructing objects with authority/provenance-bearing fields directly: " + str(len(probes['direct_authority_or_provenance_construction'])) + " file(s)",
                "exactly_once_or_replay_asserts": "tests asserting replay/exactly-once behavior; most only exercise in-process replay of happy paths: " + str(len(probes['exactly_once_or_replay_asserts'])) + " file(s)",
            },
        },
        "invariant_test_recommendations": [
            {
                "invariant": "PROVENANCE_CONSTRUCTOR_HONESTY: any constructor or wrapper that marks data as synthetic/offline must reject rows whose origin/provenance fields indicate real evidence or non-synthetic acquisition; a type check is not a provenance check.",
                "proposed_detection_strategy": "For every factory with a synthetic/offline/offline-only name, generate adversarial inputs: take the standard fixture rows and flip origin-like fields to real-world identifiers (e.g. exchange trade timestamps, evidence paths, acquired dataset digests); assert the constructor or the boundary call fails closed with a provenance error. Also assert synthetic_only cannot be set on batches whose rows carry real-origin markers.",
                "would_have_caught": "PR #241 P1(a): from_offline_synthetic_rows laundering arbitrary rows as synthetic_only.",
            },
            {
                "invariant": "EXACTLY_ONCE_SURVIVES_PROCESS_BOUNDARY: any record path claimed exactly-once must produce identical state (no duplicate records, no lost records) after process restart and across concurrent processes.",
                "proposed_detection_strategy": "Run the recording path in a child process, then in a fresh child process replay the same record identity and assert replayed=True with identical canonical record; run two child processes racing the same identity and assert exactly one record exists afterwards. Reject any ledger implemented purely as in-process memory by injecting a module reload between calls.",
                "would_have_caught": "PR #241 P1(b): _RECORDS process-local dict presented as exactly-once persistence.",
            },
            {
                "invariant": "NO_MODULE_DICT_STATE_FOR_PERSISTENCE: durable state must live outside the Python module namespace; tests must never need to clear module-private dicts for isolation.",
                "proposed_detection_strategy": "Static test-lint invariant: forbid test fixtures that clear/patch module-private dicts (_NAME patterns) of qntylab modules; pair with a runtime invariant that persistence APIs expose a storage substrate handle (file/db path) whose existence is asserted.",
                "would_have_caught": "PR #241 P1(b) and the same pattern in other modules whose tests clear private state to reset persistence.",
            },
            {
                "invariant": "AUTHORITY_FIELDS_ARE_FACTORY_ONLY_AND_MEANINGFUL: authority/attestation flags (synthetic_only, authority_scope, execution_mode, attestation maps) must be derived from verified inputs, not constants stamped by the constructor, and negative-attestation maps must be cross-checked against what the code actually touches.",
                "proposed_detection_strategy": "Property test: for each attested-negative flag (real_data_accessed=False etc.), attach canary instrumentation (e.g. sandboxed filesystem/network hooks or monkeypatched io primitives) and execute the public boundary; assert canaries never fire while attestation stays negative. Additionally require that flag-setting code paths reference input-derived evidence, via AST check that the flag is not a constant True assigned in a factory.",
                "would_have_caught": "PR #241 P1(a) (synthetic_only=True constant) and attestation drift in future offline seams.",
            },
            {
                "invariant": "REPLAY_CONFLICT_NEGATIVE_PATH: presenting the same record identity with different content must fail closed not only in-process but after restart (the durable record must win).",
                "proposed_detection_strategy": "Reuse the restart harness from the exactly-once invariant: record identity I with content A, restart, present identity I with content B, assert conflict error, then present A again and assert replayed=True.",
                "would_have_caught": "PR #241 conflict test only covered the in-process dict; the restart variant would have exposed the non-persistence.",
            },
            {
                "invariant": "HAPPY_PATH_ONLY_TEST_SMELL: tests of authority/attestation-bearing seams must include at least one negative input per authority axis (origin, outcome access, provider access, claim access).",
                "proposed_detection_strategy": "Coverage-matrix lint: for each module with an attestation map, require tests referencing each negative axis; CI check fails if a seam module's test file contains zero references to rejection of non-synthetic origins or unauthorized axes.",
                "would_have_caught": "Both #241 P1s: the test file contains fail-closed tests for untyped inputs but none for provenance-real inputs, and none for storage-substrate failure.",
            },
            {
                "invariant": "MANIFEST_CLAIMS_ARE_TESTABLE_BEHAVIOR: every claim in an implementation manifest (exactly_once, wall_clock_dependency, offline_firewall) must map to at least one behavioral test, not just a JSON field equality assert.",
                "proposed_detection_strategy": "Cross-reference lint: extract boolean claim keys from experiments/research/**/implementation_manifest.json files; require matching test names/keywords in the bound test file; report manifests whose claims are only string-compared in tests.",
                "would_have_caught": "PR #241: manifest asserted exactly_once semantics while tests only verified JSON field values.",
            },
        ],
        "no_tests_added": True,
        "method": "git diff master...d181d120 for branch tests; manual reading of branch test file and branch module source; regex probes over tests/*.py at HEAD; invariant classes derived from P1 mechanisms, not phase specifics.",
    }
    return findings


# --------------------------------------------------------------------------- main


def main() -> int:
    print("scanning module inventory (Domain 11)...", file=sys.stderr)
    inventory = build_module_inventory()
    (RAW / "module_inventory.json").write_text(json.dumps(inventory, indent=1, sort_keys=False) + "\n", encoding="utf-8")

    print("building deletion matrix (Domain 12)...", file=sys.stderr)
    matrix = build_deletion_matrix(inventory)
    (RAW / "deletion_matrix.json").write_text(json.dumps(matrix, indent=1, sort_keys=False) + "\n", encoding="utf-8")

    print("collecting test-gap findings (Domain 14)...", file=sys.stderr)
    gaps = build_test_gap_findings()
    (RAW / "test_gap_findings.json").write_text(json.dumps(gaps, indent=1, sort_keys=False) + "\n", encoding="utf-8")

    print("done: module_inventory.json, deletion_matrix.json, test_gap_findings.json", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
