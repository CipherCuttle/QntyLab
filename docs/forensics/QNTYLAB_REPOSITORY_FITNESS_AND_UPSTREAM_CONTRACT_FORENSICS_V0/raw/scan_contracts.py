#!/usr/bin/env python3
"""CONTRACT-INTEGRITY FORENSIC SCAN — deterministic candidate generator.

Stdlib only. Emits raw/scan_candidates.json with per-domain hit lists over
qntylab/*.py and tests/*.py. Read-only; writes only the candidates JSON.
"""
import ast
import json
import os
import re
import sys

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scan_candidates.json")

TARGET_DIRS = ["qntylab", "tests"]

D1_PATTERNS = [
    r"synthetic", r"\breal\b", r"holdout", r"\bdev\b", r"outer",
    r"claim", r"authority", r"authorization", r"execution_mode",
    r"authority_scope", r"synthetic_only",
]
D2_PATTERNS = [
    r"exactly_once", r"exactly one", r"idempotent", r"idempotency",
    r"duplicate", r"replay", r"persist", r"record", r"one-shot",
    r"consumed",
]
D4_NAME_TOKENS = [
    "record", "persist", "exactly_once", "verified", "synthetic",
    "canonical", "immutable", "claim_once", "frozen",
]
D5_PATTERNS = [
    r"execution_mode", r"authority_scope", r"evaluation_scope",
    r"authorization", r"real_capable", r"synthetic_only",
    r"data_classification", r"result_contract", r"provider",
    r"allow_real", r"enable_real", r"force_synthetic",
]
D6_PATTERNS = [
    r"object\.__new__", r"object\.__setattr__", r"dataclasses\.replace",
    r"\basdict\b", r"\.__dict__\s*=", r"\bcopy\.(?:copy|deepcopy)\b",
    r"frozen=True", r"field\(default_factory",
]

FAMILY_RE = re.compile("|".join(D1_PATTERNS), re.IGNORECASE)


def iter_files():
    for d in TARGET_DIRS:
        base = os.path.join(REPO, d)
        if not os.path.isdir(base):
            continue
        for name in sorted(os.listdir(base)):
            if name.endswith(".py"):
                yield os.path.join(base, name), f"{d}/{name}"


def grep_hits(rel, lines, patterns, tag):
    out = []
    for i, line in enumerate(lines, 1):
        for pat in patterns:
            if re.search(pat, line, re.IGNORECASE):
                out.append({"tag": tag, "file": rel, "line": i,
                            "pattern": pat, "text": line.rstrip()[:200]})
                break
    return out


def module_state_assigns(tree, rel):
    """Module-level Assign nodes whose value is Dict/Set/List literal or call."""
    hits = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            tgt = node.targets[0]
            name = getattr(tgt, "id", getattr(tgt, "attr", "?"))
            v = node.value
            kind = None
            if isinstance(v, ast.Dict):
                kind = "dict"
            elif isinstance(v, (ast.Set,)):
                kind = "set"
            elif isinstance(v, ast.List):
                kind = "list"
            elif isinstance(v, ast.Call):
                fn = v.func
                nm = getattr(fn, "id", getattr(fn, "attr", ""))
                if nm in ("dict", "set", "OrderedDict", "defaultdict"):
                    kind = nm
            if kind:
                hits.append({"file": rel, "line": node.lineno,
                             "name": name, "kind": kind})
    return hits


def provenance_params(tree, rel):
    """__init__/function params whose names look provenance-flavored,
    incl. forcing defaults (str/bool/enum-ish)."""
    hits = []
    keys = re.compile(
        r"synthetic|synthetic_only|real|execution_mode|authority|"
        r"authorization|holdout|provenance|allow_real|data_class",
        re.IGNORECASE)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for a in node.args.args + node.args.kwonlyargs:
                if keys.search(a.arg):
                    default = None
                    defaults = list(node.args.defaults) + list(node.args.kw_defaults)
                    idx = len(node.args.args + node.args.kwonlyargs) - len(defaults)
                    # approximate; simple positional mapping
                    pos = [x.arg for x in node.args.args]
                    if a.arg in pos:
                        di = pos.index(a.arg) - (len(pos) - len(node.args.defaults))
                        if 0 <= di < len(node.args.defaults):
                            d = node.args.defaults[di]
                            try:
                                default = ast.unparse(d)
                            except Exception:
                                default = "?"
                    hits.append({"file": rel, "line": node.lineno,
                                 "func": node.name, "param": a.arg,
                                 "default": default})
    return hits


def private_imports(tree, rel, modname):
    """from qntylab.x import _y  AND  alias._y(  cross-module."""
    hits = []
    aliases = {}  # alias -> qntylab module
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("qntylab"):
            for a in node.names:
                if a.name.startswith("_"):
                    hits.append({"file": rel, "line": node.lineno,
                                 "kind": "from_import",
                                 "module": node.module, "name": a.name,
                                 "bound_as": a.asname or a.name})
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("qntylab."):
                    local = a.asname or a.name.split(".")[-1]
                    aliases[local] = a.name
    # attribute calls on imported qntylab modules to _names
    src_classes = {n.name for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}
    src_funcs = {n.name for n in ast.walk(tree)
                 if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr.startswith("_"):
            base = node.value
            if isinstance(base, ast.Name):
                if base.id in aliases:
                    hits.append({"file": rel, "line": node.lineno,
                                 "kind": "attr_use", "module": aliases[base.id],
                                 "name": node.attr})
                elif node.attr in src_classes or node.attr.lstrip("_") in src_funcs:
                    pass  # intra-module self reference
                elif node.attr in {n.name for n in
                                   [x for x in ast.walk(tree)
                                    if isinstance(x, (ast.FunctionDef, ast.ClassDef))]}:
                    pass  # defined in this module
    return hits


def misleading_names(tree, rel):
    hits = []
    for node in ast.walk(tree):
        names = []
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
        hits.extend({"file": rel, "line": node.lineno, "name": nm}
                    for nm in names
                    if any(t in nm.lower() for t in D4_NAME_TOKENS))
    return hits


def hardening_scan(tree, rel, lines):
    hits = grep_hits(rel, lines, D6_PATTERNS, "d6")
    # mutable default args
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for d in list(node.args.defaults) + [x for x in node.args.kw_defaults if x]:
                if isinstance(d, (ast.List, ast.Dict, ast.Set)):
                    hits.append({"tag": "d6_mutable_default", "file": rel,
                                 "line": node.lineno, "pattern": "mutable_default",
                                 "text": f"def {node.name}(... default={ast.dump(d)[:60]}"})
        if isinstance(node, ast.ClassDef):
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call) and getattr(dec.func, "id", "") == "dataclass":
                    kw = {k.arg: k.value for k in dec.keywords}
                    if "frozen" in kw and getattr(kw["frozen"], "value", None) is True:
                        for b in node.body:
                            if isinstance(b, ast.ClassDef):
                                hits.append({"tag": "d6_frozen_subclass", "file": rel,
                                             "line": b.lineno, "pattern": "frozen_subclass",
                                             "text": f"class {b.name}({node.name})"})
    return hits


def main():
    result = {
        "repo_head": os.popen(f"git -C {REPO} rev-parse HEAD").read().strip(),
        "d1_provenance_grep": [], "d2_persistence_grep": [],
        "d2_module_state": [], "d3_private_imports": [],
        "d4_misleading_names": [], "d5_authority_strings": [],
        "d6_hardening": [], "d1_provenance_params": [],
    }
    for path, rel in iter_files():
        with open(path, encoding="utf-8", errors="replace") as f:
            src = f.read()
        lines = src.splitlines()
        try:
            tree = ast.parse(src)
        except SyntaxError as e:
            result["d1_provenance_grep"].append(
                {"tag": "SYNTAX_ERROR", "file": rel, "line": e.lineno, "text": str(e)})
            continue
        modname = rel[:-3].replace("/", ".")
        result["d1_provenance_grep"].extend(grep_hits(rel, lines, D1_PATTERNS, "d1"))
        result["d2_persistence_grep"].extend(grep_hits(rel, lines, D2_PATTERNS, "d2"))
        result["d2_module_state"].extend(module_state_assigns(tree, rel))
        result["d3_private_imports"].extend(private_imports(tree, rel, modname))
        result["d4_misleading_names"].extend(misleading_names(tree, rel))
        result["d5_authority_strings"].extend(grep_hits(rel, lines, D5_PATTERNS, "d5"))
        result["d6_hardening"].extend(hardening_scan(tree, rel, lines))
        result["d1_provenance_params"].extend(provenance_params(tree, rel))

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)
    summary = {k: len(v) for k, v in result.items() if isinstance(v, list)}
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    sys.exit(main())
