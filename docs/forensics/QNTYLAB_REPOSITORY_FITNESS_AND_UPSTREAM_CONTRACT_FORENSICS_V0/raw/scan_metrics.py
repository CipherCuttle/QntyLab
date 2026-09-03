#!/usr/bin/env python3
"""MECHANICAL METRICS SCAN for QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0.

Pure stdlib. Deterministic: no timestamps, no network, sorted JSON keys.
Re-running on the same checkout (same HEAD, same tracked tree) reproduces
byte-identical JSON outputs, with one caveat: repo_byte_weight.json counts
tracked files, so outputs differ if the tracked tree itself differs.

Covers audit domains 7, 8, 9, 10, 13 and writes:
  context_metrics.json      (Domain 7  - context spine weight)
  projects_toml_metrics.json (Domain 8 - projects.toml records)
  workflow_metrics.json      (Domain 9 - GitHub Actions workflows)
  packaging_metrics.json     (Domain 10- packaging/config inventory)
  repo_byte_weight.json      (Domain 13- tracked byte weight)
"""

import json
import math
import os
import re
import statistics
import subprocess
import sys
import tomllib
from pathlib import Path

REPO = Path(__file__).resolve().parents[4]
OUT_DIR = Path(__file__).resolve().parent
AUDIT_NAME = "QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0"

TERMINAL_PREFIXES = ("CLOSED_", "SEALED", "ARCHIVED")
PLANNED_PREFIXES = ("PLANNED_",)


def run_bytes(args):
    proc = subprocess.run(args, cwd=REPO, capture_output=True)
    if proc.returncode != 0:
        sys.stderr.write(proc.stderr.decode(errors="replace"))
        raise SystemExit(f"command failed: {args}")
    return proc.stdout


def git_ls_files():
    return run_bytes(["git", "ls-files", "-z"]).split(b"\0")


def read_bytes(rel):
    p = REPO / rel
    return p.read_bytes() if p.exists() else b""


def write_json(name, payload):
    with open(OUT_DIR / name, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2, sort_keys=True)
        fh.write("\n")


def git_head():
    return run_bytes(["git", "rev-parse", "HEAD"]).decode().strip()


def classify_state(state):
    if state.startswith(TERMINAL_PREFIXES):
        return "terminal"
    if state.startswith(PLANNED_PREFIXES):
        return "planned"
    return "non_terminal"


def load_projects_toml():
    with open(REPO / "docs/state/projects.toml", "rb") as fh:
        return tomllib.load(fh)


# --------------------------------------------------------------------------
# Domain 7: context metrics
# --------------------------------------------------------------------------

INVARIANT_PHRASES = [
    "exploratory-only",
    "exploratory only",
    "no trading",
    "authority",
    "source_conflict",
    "prohibited",
]


def context_metrics():
    agents = read_bytes("AGENTS.md")
    readme = read_bytes("README.md")
    roadmap = read_bytes("docs/CURRENT_ROADMAP.md")
    projects_toml = read_bytes("docs/state/projects.toml")
    pc = read_bytes("qntylab/project_context.py")

    brief_out = run_bytes([sys.executable, "-m", "qntylab.project_context", "brief"])
    spine_out = run_bytes([sys.executable, "-m", "qntylab.project_context", "spine"])

    doc = load_projects_toml()
    records = doc.get("project", [])
    states = [r.get("state", "") for r in records]
    state_counts = {}
    for s in states:
        state_counts[s] = state_counts.get(s, 0) + 1

    classified = {"terminal": 0, "planned": 0, "non_terminal": 0}
    for s in states:
        classified[classify_state(s)] += 1

    phrase_counts = {}
    for label, blob in (("AGENTS.md", agents), ("README.md", readme),
                        ("CURRENT_ROADMAP.md", roadmap)):
        low = blob.lower()
        phrase_counts[label] = {
            p: low.count(p.encode("latin-1").decode("latin-1").lower().encode())
            for p in INVARIANT_PHRASES
        }

    return {
        "audit": AUDIT_NAME,
        "repo_head": git_head(),
        "AGENTS_MD_BYTES": len(agents),
        "README_BYTES": len(readme),
        "PROJECTS_TOML_LINES": len(projects_toml.splitlines()),
        "PROJECTS_TOML_BYTES": len(projects_toml),
        "PROJECT_CONTEXT_PY_BYTES": len(pc),
        "CURRENT_ROADMAP_LINES": len(roadmap.splitlines()),
        "CURRENT_ROADMAP_BYTES": len(roadmap),
        "BRIEF_BYTES": len(brief_out),
        "BRIEF_LINES": len(brief_out.splitlines()),
        "BRIEF_TRUNCATED": (b"LINE_TRUNCATED" in brief_out
                            or b"ORIENTATION_ROWS_REDUCED" in brief_out),
        "SPINE_BYTES": len(spine_out),
        "SPINE_LINES": len(spine_out.splitlines()),
        "SPINE_LINES_OR_SINGLE_LINE_BYTES": (
            {"mode": "single_line", "single_line_bytes": len(spine_out)}
            if len(spine_out.splitlines()) == 1
            else {"mode": "multi_line", "line_count": len(spine_out.splitlines())}
        ),
        "PROJECT_COUNT_TOTAL": len(records),
        "PROJECT_COUNT_ACTIVE": classified["non_terminal"],
        "PROJECT_COUNT_IN_REVIEW": 0,  # no IN_REVIEW state present in vocabulary
        "PROJECT_COUNT_PLANNED": classified["planned"],
        "PROJECT_COUNT_TERMINAL": classified["terminal"],
        "STATE_VOCABULARY": dict(sorted(state_counts.items())),
        "STATE_CLASSIFICATION": {
            "rule": "CLOSED_*/SEALED/ARCHIVED=terminal; PLANNED_*=planned; else non_terminal",
            **{k: v for k, v in sorted(classified.items())},
        },
        "DUPLICATIVE_SIGNAL": {
            "byte_weight_agents_readme_roadmap": len(agents) + len(readme) + len(roadmap),
            "invariant_phrase_counts": phrase_counts,
            "phrases": INVARIANT_PHRASES,
            "note": "raw case-insensitive substring counts; no interpretation",
        },
    }


# --------------------------------------------------------------------------
# Domain 8: projects.toml metrics
# --------------------------------------------------------------------------

def p90(values):
    if not values:
        return None
    s = sorted(values)
    idx = max(0, min(len(s) - 1, math.ceil(0.9 * len(s)) - 1))
    return s[idx]


def is_hashish(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def projects_toml_metrics():
    doc = load_projects_toml()
    records = doc.get("project", [])

    state_dist = {}
    for r in records:
        s = r.get("state", "")
        state_dist[s] = state_dist.get(s, 0) + 1

    terminal = sum(1 for r in records if classify_state(r.get("state", "")) == "terminal")

    field_freq = {}
    for r in records:
        for k in r:
            field_freq[k] = field_freq.get(k, 0) + 1

    authority_like = sorted(k for k in field_freq
                            if re.search(r"authorit|authoriz", k))

    all_none_count = 0
    for r in records:
        present = [r[k] for k in authority_like if k in r]
        if present and all(v in ("NONE", None, False) for v in present):
            all_none_count += 1

    na_lens = [len(r["next_action"]) for r in records
               if isinstance(r.get("next_action"), str)]
    na_over_500 = sum(1 for n in na_lens if n > 500)

    artifact_ref_count = 0
    hash_binding_count = 0
    for r in records:
        has_art = any(k in r and r[k] for k in
                      ("authoritative_artifacts", "authorization_artifact"))
        if has_art:
            artifact_ref_count += 1
        if any("sha" in k.lower() and isinstance(v, str) for k, v in r.items()) or \
           any(is_hashish(v) for v in r.values()):
            hash_binding_count += 1

    prose = []
    for r in records:
        size = (len(r.get("next_action") or "") + len(r.get("summary") or ""))
        prose.append((size, r.get("project_id", "?")))
    prose.sort(key=lambda t: (-t[0], t[1]))
    top10 = [{"project_id": pid, "prose_bytes": sz} for sz, pid in prose[:10]]

    refs = []
    for raw in git_ls_files():
        path = raw.decode()
        if not path or path == "docs/state/projects.toml":
            continue
        fp = REPO / path
        try:
            blob = fp.read_bytes()
        except OSError:
            continue
        if b"\0" in blob or b"projects.toml" not in blob:
            continue
        text = blob.decode(errors="replace")
        for i, line in enumerate(text.splitlines(), 1):
            if "projects.toml" in line:
                refs.append({"file": path, "line": i})
    refs.sort(key=lambda e: (e["file"], e["line"]))

    return {
        "audit": AUDIT_NAME,
        "repo_head": git_head(),
        "total_project_records": len(records),
        "state_distribution": dict(sorted(state_dist.items())),
        "terminal_record_count": terminal,
        "non_terminal_record_count": len(records) - terminal,
        "authority_field_names": authority_like,
        "records_with_authority_fields_all_NONE": all_none_count,
        "field_frequency": dict(sorted(field_freq.items())),
        "next_action_length": {
            "records_with_next_action": len(na_lens),
            "min": min(na_lens) if na_lens else None,
            "median": statistics.median(na_lens) if na_lens else None,
            "p90": p90(na_lens),
            "max": max(na_lens) if na_lens else None,
            "records_over_500_chars": na_over_500,
        },
        "records_referencing_authoritative_artifacts": artifact_ref_count,
        "records_with_hash_bindings": hash_binding_count,
        "top10_prose_records": top10,
        "projects_toml_references": {
            "count": len(refs),
            "excluded_self": "docs/state/projects.toml",
            "file_line_list": refs,
        },
    }


# --------------------------------------------------------------------------
# Domain 9: workflow metrics
# --------------------------------------------------------------------------

SUBSYSTEM_RULES = [
    ("RESEARCH_LEDGER", ("research_ledger",)),
    ("PROJECT_CONTEXT_CORE", ("project_context", "spine", "brief", "doctor")),
    ("FUNDING_JFP_JH01", ("funding", "jfp", "jh01")),
    ("HISTORICAL_REPAIR_REGRESSION", ("repair", "regression", "historical")),
    ("DSH", ("dsh", "stage-a", "stage_a", "dsh_home", "runtime_manifest", "claim")),
    ("RUNTIME_PROVISIONING", ("checkout", "setup-python", "setup-node",
                              "pip install", "provision")),
]


def classify_step_subsystem(name, run_text):
    text = (name + "\n" + run_text).lower()
    for subsystem, needles in SUBSYSTEM_RULES:
        if any(n in text for n in needles):
            return subsystem
    return "OTHER_SUBSYSTEM"


def parse_workflow(path):
    """Lightweight indentation-based parse; pure stdlib, no yaml dep."""
    text = path.read_text()
    lines = text.splitlines()
    info = {
        "file": str(path.relative_to(REPO)),
        "lines": len(lines),
        "bytes": path.stat().st_size,
        "triggers": [],
        "job_count": 0,
        "step_count": 0,
        "pytest_invocations": [],
        "steps": [],
    }

    # triggers: keys directly under 'on:'
    for i, line in enumerate(lines):
        m = re.match(r"^on:\s*(?:#.*)?$", line)
        if m:
            for follow in lines[i + 1:]:
                fm = re.match(r"^(\s{2,})([A-Za-z_-]+):\s*(.*)$", follow)
                if not fm:
                    break
                if len(fm.group(1)) == 2 and fm.group(2) not in ("description",
                                                                 "inputs", "required",
                                                                 "default", "type"):
                    info["triggers"].append(fm.group(2))
            break
    info["triggers"] = sorted(set(info["triggers"]))

    info["job_count"] = sum(1 for l in lines if re.match(r"^\s*runs-on:", l))
    info["step_count"] = sum(1 for l in lines
                             if re.match(r"^\s*-\s+(name:|uses:|run:|shell:)", l))

    # steps block spans
    steps_idx = next((i for i, l in enumerate(lines)
                      if re.match(r"^\s*steps:\s*$", l)), None)
    if steps_idx is not None:
        steps_indent = len(lines[steps_idx]) - len(lines[steps_idx].lstrip())
        child_re = re.compile(r"^(\s*-\s+)")
        starts = []
        for i in range(steps_idx + 1, len(lines)):
            l = lines[i]
            if not l.strip() or l.strip().startswith("#"):
                continue
            ind = len(l) - len(l.lstrip())
            if ind <= steps_indent:
                break
            if child_re.match(l):
                starts.append(i)
        ends = starts[1:] + [next((j for j in range(starts[-1], len(lines))
                                   if lines[j].strip() and
                                   len(lines[j]) - len(lines[j].lstrip()) <= steps_indent
                                   and j > starts[-1]), len(lines)) - 1]
        for k, s in enumerate(starts):
            e = ends[k]
            span = lines[s:e + 1]
            name = next((re.match(r"^\s*(?:-\s+)?name:\s*\"?(.*?)\"?\s*$", l).group(1)
                         for l in span
                         if re.match(r"^\s*(?:-\s+)?name:", l)), None)
            uses = next((re.match(r"^\s*(?:-\s+)?uses:\s*(\S+)", l).group(1)
                         for l in span
                         if re.match(r"^\s*(?:-\s+)?uses:", l)), None)
            run_idx = next((j for j, l in enumerate(span)
                            if re.match(r"^\s*(?:-\s+)?run:", l)), None)
            run_block = []
            if run_idx is not None:
                run_line = span[run_idx]
                run_ind = len(run_line) - len(run_line.lstrip())
                if re.match(r"^\s*(?:-\s+)?run:\s*[|>]", run_line):
                    run_block = [l for l in span[run_idx + 1:]]
                else:
                    inline = re.match(r"^\s*(?:-\s+)?run:\s*(.+)$", run_line)
                    run_block = [inline.group(1)] if inline else []
            run_text = "\n".join(run_block)
            info["steps"].append({
                "name": name,
                "uses": uses,
                "start_line": s + 1,
                "end_line": e + 1,
                "span_lines": e - s + 1,
                "run_block_lines": len(run_block),
                "subsystem": classify_step_subsystem(name or "", run_text),
                "run_preview_first_line": (run_block[0].strip()[:120]
                                           if run_block else None),
            })
            seen_pytest = set()
            for l in run_block:
                if "pytest" in l and "pip install" not in l:
                    selected = bool(re.search(r"\btests/", l))
                    line_no = s + 1 + run_idx + run_block.index(l) + 1 - 1
                    key = (line_no, l.strip()[:160])
                    if key not in seen_pytest:
                        seen_pytest.add(key)
                        info["pytest_invocations"].append({
                            "line": line_no,
                            "selected_by_path": selected,
                            "excerpt": l.strip()[:160],
                        })
    return info


def inline_script_language(run_text):
    low = run_text.lower()
    if "node " in low or "require(" in low or ".mjs" in low:
        return "javascript"
    if "python" in low:
        return "python"
    return "shell"


def workflow_metrics():
    wf_dir = REPO / ".github/workflows"
    files = sorted(list(wf_dir.glob("*.yml")) + list(wf_dir.glob("*.yaml")))
    parsed = [parse_workflow(p) for p in files]

    per_workflow = []
    total_lines = 0
    total_bytes = 0
    job_count = 0
    step_count = 0
    for p in parsed:
        total_lines += p["lines"]
        total_bytes += p["bytes"]
        job_count += p["job_count"]
        step_count += p["step_count"]
        per_workflow.append({
            "file": p["file"], "lines": p["lines"], "bytes": p["bytes"],
            "triggers": p["triggers"], "job_count": p["job_count"],
            "step_count": p["step_count"],
        })

    pc = next((p for p in parsed if p["file"].endswith("project-context.yml")), None)
    pc_block = None
    if pc:
        sub_lines = {}
        for st in pc["steps"]:
            sub_lines[st["subsystem"]] = (sub_lines.get(st["subsystem"], 0)
                                          + st["span_lines"])
        pc_block = {
            "subsystem_line_counts": dict(sorted(sub_lines.items())),
            "steps": pc["steps"],
            "rule_priority": [r[0] for r in SUBSYSTEM_RULES],
            "note": "span_lines counts every YAML line inside the step span, "
                    "first-match priority classification on step name + run text",
        }

    inline_scripts = []
    for p in parsed:
        for st in p["steps"]:
            if st["run_block_lines"] > 30:
                inline_scripts.append({
                    "file": p["file"], "step_name": st["name"],
                    "start_line": st["start_line"], "end_line": st["end_line"],
                    "run_block_lines": st["run_block_lines"],
                    "language": inline_script_language(
                        st.get("run_preview_first_line") or ""),
                })

    all_text = "\n".join((REPO / p["file"]).read_text() for p in parsed)
    setup_dupes = {
        "actions/checkout": len(re.findall(r"uses:\s*actions/checkout@", all_text)),
        "actions/setup-python": len(re.findall(r"uses:\s*actions/setup-python@", all_text)),
        "actions/setup-node": len(re.findall(r"uses:\s*actions/setup-node@", all_text)),
        "pip_install_commands": len(re.findall(r"pip install\b", all_text)),
    }

    pytest_calls = []
    selected_by_path = False
    wholesale = False
    for p in parsed:
        for call in p["pytest_invocations"]:
            pytest_calls.append({"file": p["file"], **call})
            if call["selected_by_path"]:
                selected_by_path = True
            else:
                wholesale = True

    return {
        "audit": AUDIT_NAME,
        "repo_head": git_head(),
        "WORKFLOW_COUNT": len(files),
        "TOTAL_WORKFLOW_LINES": total_lines,
        "TOTAL_WORKFLOW_BYTES": total_bytes,
        "JOB_COUNT": job_count,
        "STEP_COUNT": step_count,
        "per_workflow": per_workflow,
        "project_context_yml": pc_block,
        "inline_scripts_over_30_lines": inline_scripts,
        "duplicated_setup_step_occurrences": setup_dupes,
        "pytest_invocation_lines": pytest_calls,
        "pytest_selection": {
            "selected_by_path": selected_by_path,
            "wholesale": wholesale,
        },
    }


# --------------------------------------------------------------------------
# Domain 10: packaging metrics
# --------------------------------------------------------------------------

PACKAGING_CANDIDATES = [
    "pyproject.toml", "setup.py", "setup.cfg", "Makefile", "tox.ini",
    "pytest.ini", ".mypy.ini", "mypy.ini", "ruff.toml", ".ruff.toml",
    ".flake8", ".isort.cfg", ".black", "pyrightconfig.json", "noxfile.py",
    "conftest.py", ".pre-commit-config.yaml", "Pipfile", "poetry.lock",
]


def packaging_metrics():
    candidates = {name: (REPO / name).exists() for name in sorted(PACKAGING_CANDIDATES)}
    found_anywhere = {}
    for raw in git_ls_files():
        path = raw.decode()
        base = os.path.basename(path)
        if base in PACKAGING_CANDIDATES:
            found_anywhere.setdefault(base, []).append(path)

    requirements = []
    for raw in git_ls_files():
        path = raw.decode()
        if os.path.basename(path).startswith("requirements") and path.endswith(".txt"):
            requirements.append({"name": path,
                                 "bytes": (REPO / path).stat().st_size,
                                 "content": (REPO / path).read_text().splitlines()})
    requirements.sort(key=lambda r: r["name"])

    qntylab_toml_struct = None
    if (REPO / "qntylab.toml").exists():
        with open(REPO / "qntylab.toml", "rb") as fh:
            doc = tomllib.load(fh)
        qntylab_toml_struct = {
            "top_level_keys": sorted(doc.keys()),
            "sections": {k: (sorted(v.keys()) if isinstance(v, dict) else type(v).__name__)
                         for k, v in sorted(doc.items())},
            "bytes": (REPO / "qntylab.toml").stat().st_size,
            "lines": len((REPO / "qntylab.toml").read_text().splitlines()),
        }

    # CI bootstrap sequence: ordered uses/run commands from workflow provisioning steps
    ci_bootstrap = []
    wf = REPO / ".github/workflows/project-context.yml"
    if wf.exists():
        for i, line in enumerate(wf.read_text().splitlines(), 1):
            m = re.match(r"^\s*(?:-\s+)?uses:\s*(\S+)", line)
            if m:
                ci_bootstrap.append({"line": i, "kind": "uses", "command": m.group(1)})
            else:
                m = re.match(r"^\s*(?:-\s+)?run:\s*(\S.*)$", line)
                if m and "run: |" not in line:
                    ci_bootstrap.append({"line": i, "kind": "run",
                                         "command": m.group(1)[:160]})

    # documented one-command verify: lines mentioning verify/pytest in root docs
    verify_docs = []
    for docname in ("AGENTS.md", "README.md", "qntylab.toml"):
        p = REPO / docname
        if not p.exists():
            continue
        for i, line in enumerate(p.read_text(errors="replace").splitlines(), 1):
            low = line.lower()
            if ("verify" in low or "pytest" in low) and (
                    "python" in low or "pytest" in low or "verify" in low):
                verify_docs.append({"file": docname, "line": i,
                                    "excerpt": line.strip()[:160]})

    return {
        "audit": AUDIT_NAME,
        "repo_head": git_head(),
        "HAS_PYPROJECT": candidates["pyproject.toml"],
        "HAS_SETUP_PY": candidates["setup.py"],
        "HAS_SETUP_CFG": candidates["setup.cfg"],
        "HAS_MAKEFILE": candidates["Makefile"],
        "HAS_TOX_INI": candidates["tox.ini"],
        "candidate_existence_at_repo_root": candidates,
        "candidates_found_anywhere_tracked": dict(sorted(found_anywhere.items())),
        "pytest_config_location": {
            "pytest.ini": (REPO / "pytest.ini").exists(),
            "pyproject.toml": (REPO / "pyproject.toml").exists(),
            "setup.cfg": (REPO / "setup.cfg").exists(),
            "qntylab.toml": (REPO / "qntylab.toml").exists(),
            "conftest_py_tracked": any(
                p.endswith("conftest.py")
                for p in (r.decode() for r in git_ls_files())),
        },
        "qntylab_toml_structure": qntylab_toml_struct,
        "requirements_files": requirements,
        "ci_bootstrap_sequence": ci_bootstrap,
        "documented_verify_lines": verify_docs,
    }


# --------------------------------------------------------------------------
# Domain 13: repo byte weight
# --------------------------------------------------------------------------

def repo_byte_weight():
    tracked = [raw.decode() for raw in git_ls_files() if raw]
    sizes = {}
    for path in tracked:
        fp = REPO / path
        try:
            sizes[path] = fp.stat().st_size
        except OSError:
            sizes[path] = -1  # tracked but absent from worktree

    total = sum(v for v in sizes.values() if v >= 0)

    by_top = {}
    for path, sz in sizes.items():
        if sz < 0:
            continue
        key = path.split("/")[0] if "/" in path else "(root)"
        by_top[key] = by_top.get(key, 0) + sz

    largest = sorted(sizes.items(), key=lambda kv: (-kv[1], kv[0]))[:50]

    generated = []
    csv_total = 0
    json_total = 0
    for path in sorted(sizes):
        sz = sizes[path]
        if sz < 0:
            continue
        low = path.lower()
        ext = os.path.splitext(path)[1].lower()
        reasons = []
        if ext == ".csv":
            csv_total += sz
            reasons.append("csv_extension")
        if ext in (".json", ".jsonl"):
            json_total += sz
        if ext == ".jsonl":
            reasons.append("jsonl_extension")
        if ext == ".json" and sz > 100 * 1024:
            reasons.append("json_over_100KB")
        if "sigstore" in low:
            reasons.append("sigstore_in_path")
        if reasons:
            generated.append({"path": path, "bytes": sz, "reasons": reasons})

    count_objects = run_bytes(["git", "count-objects", "-vH"]).decode()
    co = {}
    for line in count_objects.splitlines():
        if ":" in line:
            k, v = line.split(":", 1)
            co[k.strip()] = v.strip()

    return {
        "audit": AUDIT_NAME,
        "repo_head": git_head(),
        "tracked_file_count": len(tracked),
        "total_tracked_bytes": total,
        "bytes_by_top_level_directory": dict(sorted(by_top.items(),
                                                    key=lambda kv: -kv[1])),
        "largest_50_tracked_files": [{"path": p, "bytes": s} for p, s in largest],
        "generated_looking_artifacts": generated,
        "tracked_csv_weight_total_bytes": csv_total,
        "tracked_json_jsonl_weight_total_bytes": json_total,
        "git_count_objects_vH": co,
        "method": "git ls-files -z + os.path.getsize on worktree; -1 marks "
                  "tracked-but-missing worktree paths",
    }


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    write_json("context_metrics.json", context_metrics())
    write_json("projects_toml_metrics.json", projects_toml_metrics())
    write_json("workflow_metrics.json", workflow_metrics())
    write_json("packaging_metrics.json", packaging_metrics())
    write_json("repo_byte_weight.json", repo_byte_weight())
    for name in sorted(os.listdir(OUT_DIR)):
        if name.endswith(".json"):
            print(f"wrote {name}")


if __name__ == "__main__":
    main()
