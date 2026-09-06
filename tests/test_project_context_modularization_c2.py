"""C2 architecture and parity tests for PROJECT_CONTEXT_MODULARIZATION_V0.

These tests pin the behavior-preserving decomposition of the former
``qntylab/project_context.py`` monolith (canonical parent
``78f3ca1b3566e9ea3d138796b7ce50e224c9e45a``) into a composition root plus
bounded sibling modules.

Determinism honesty:

- Byte-exact frozen digests exist only for outputs captured at the canonical
  parent in a clean worktree (``brief`` == ``6ddfa177...``, ``spine`` ==
  ``7dcf6c03...``, ``doctor --strict`` == ``6ae2bf9f...`` (19 bytes),
  ``render --check`` == ``8d3812e8...`` (16 bytes)).  ``doctor``/``render``
  stdout is state-independent here, so those digests are asserted directly.
  ``brief``/``spine`` embed ``head_sha`` and worktree state, so the primary
  deterministic assertion is byte equality against the pre-refactor monolith
  recovered from Git and evaluated over the *same* repository state in the
  same process; the frozen digests are asserted only under a state gate that
  makes them meaningful (see the individual tests).
"""

from __future__ import annotations

import ast
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from qntylab import project_context

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PARENT = "78f3ca1b3566e9ea3d138796b7ce50e224c9e45a"

# Frozen stdout digests recorded at the canonical parent (clean worktree).
CANONICAL_BRIEF_SHA256 = "6ddfa1779b180e700e154b28124750fc5f47c1cc07fce69035d4bd7655b44abf"
CANONICAL_SPINE_SHA256 = "7dcf6c03f4d872c49581721d9ffb24b4051cdb601d19924688986cd62f604ecd"
CANONICAL_DOCTOR_STRICT_STDOUT = b"project context ok\n"
CANONICAL_DOCTOR_STRICT_SHA256 = "6ae2bf9f6a49f2c25796068862831fd4b5f22fb00444b3fc868359ecb7d01169"
CANONICAL_RENDER_CHECK_STDOUT = b"roadmap current\n"
CANONICAL_RENDER_CHECK_SHA256 = "8d3812e8e4b37a923f2ddc5126595bcaa95c858493c20e8e97b584f08c7e5297"

GENERIC_MODULES = [
    "qntylab/project_context.py",
    "qntylab/project_context_core.py",
    "qntylab/project_context_registry.py",
    "qntylab/project_context_spine.py",
    "qntylab/project_context_brief.py",
]
DOMAIN_MODULE = "qntylab/project_context_execution_authority.py"
SIX_MODULES = GENERIC_MODULES + [DOMAIN_MODULE]

# DSH identity tokens that must not appear in the generic core.
DSH_TOKENS = ("DSH", "DSH_STAGE", "STAGE_A", "dsh", "pinned_dsh", "stage-a", "Stage-A")


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _git(*args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(ROOT), *args], check=True, capture_output=True, text=True
    ).stdout


def _head_is_canonical_parent() -> bool:
    return _git("rev-parse", "HEAD").strip() == CANONICAL_PARENT


def _dirty_paths() -> list[str]:
    lines = _git("status", "--porcelain=v1", "--untracked-files=all").splitlines()
    return sorted({line[3:] for line in lines if len(line) >= 4})


def _worktree_is_clean() -> bool:
    return not _dirty_paths()


def _canonical_state_holds() -> bool:
    """True when the frozen-digest gate is meaningful.

    The gate requires HEAD at the canonical parent and no local modification
    under ``docs/`` (the compiled inputs that legitimately change ``brief``/
    ``spine`` bytes).  Local qntylab/tests side changes do not affect them.
    """
    if not _head_is_canonical_parent():
        return False
    return not any(path.startswith("docs/") for path in _dirty_paths())


@pytest.fixture(scope="session")
def baseline(tmp_path_factory) -> object:
    """The pre-refactor monolith loaded from Git at the canonical parent.

    The oracle source is pinned to the canonical parent via
    ``git show CANONICAL_PARENT:qntylab/project_context.py`` — NOT to the
    current HEAD — so the parity tests run unchanged at any later commit
    (including the committed C2 candidate).  Loaded as a private module (never
    registered under the canonical name, so the production
    ``qntylab.project_context`` stays untouched) purely as the parity oracle
    for same-state comparisons.
    """
    source = subprocess.run(
        ["git", "-C", str(ROOT), "show", f"{CANONICAL_PARENT}:qntylab/project_context.py"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    directory = tmp_path_factory.mktemp("c2_baseline")
    path = directory / "project_context_c2_baseline.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location("project_context_c2_baseline", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["project_context_c2_baseline"] = module
    spec.loader.exec_module(module)
    return module




def _run_baseline_cli(argv: list[str], cwd: Path = ROOT) -> subprocess.CompletedProcess[bytes]:
    """Run the pre-refactor monolith's ``main()`` in a fresh subprocess."""
    baseline_path = sys.modules["project_context_c2_baseline"].__file__
    assert baseline_path is not None
    script = (
        "import sys, importlib.util\n"
        f"spec = importlib.util.spec_from_file_location('project_context_c2_baseline', {baseline_path!r})\n"
        "module = importlib.util.module_from_spec(spec)\n"
        "sys.modules['project_context_c2_baseline'] = module\n"
        "spec.loader.exec_module(module)\n"
        "module.main(sys.argv[1:])\n"
    )
    return subprocess.run([sys.executable, "-c", script, *argv], cwd=cwd, capture_output=True)


def _run_cli(*argv: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run([sys.executable, "-m", "qntylab.project_context", *argv], cwd=cwd, capture_output=True)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


# ---------------------------------------------------------------------------
# (1) generic core zero-DSH architecture test (inspects actual source)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", GENERIC_MODULES)
def test_generic_core_source_is_free_of_dsh_identities(path: str) -> None:
    source = (ROOT / path).read_text(encoding="utf-8")
    for token in DSH_TOKENS:
        assert token not in source, f"{path} must not embed the DSH identity token {token!r}"


def test_dsh_identities_live_only_behind_the_bounded_domain_seam() -> None:
    source = (ROOT / DOMAIN_MODULE).read_text(encoding="utf-8")
    # The seam must be a real extension point: it actually carries the DSH
    # identities (this keeps the zero-DSH assertions above meaningful and the
    # seam non-vacuous).
    assert any(token in source for token in ("DSH", "STAGE_A"))


def test_compatibility_surface_names_all_resolve() -> None:
    """Every ``project_context.<name>`` attribute used by external code resolves."""
    import re

    pattern = re.compile(r"project_context\.([A-Za-z_][A-Za-z0-9_]*)")
    skip = {Path(path).name for path in SIX_MODULES}
    names: set[str] = set()
    for tree_root in ("tests", "qntylab"):
        for file in (ROOT / tree_root).rglob("*.py"):
            if file.name in skip:
                continue
            names.update(pattern.findall(file.read_text(encoding="utf-8")))
    names.discard("py")  # filename strings like 'qntylab/project_context.py'
    missing = sorted(name for name in names if not hasattr(project_context, name))
    assert not missing, f"missing compatibility-surface attributes: {missing}"


# ---------------------------------------------------------------------------
# (2)+(3) brief / spine CLI byte parity vs the recorded canonical digests
# ---------------------------------------------------------------------------

def _refactored_brief_bytes() -> bytes:
    packet = project_context.compile_context_spine(ROOT)
    return (project_context.brief_text(packet) + "\n").encode("utf-8")


def _baseline_brief_bytes(baseline) -> bytes:
    packet = baseline.compile_context_spine(ROOT)
    return (baseline.brief_text(packet) + "\n").encode("utf-8")


def _refactored_spine_bytes() -> bytes:
    return project_context.context_spine_bytes(ROOT) + b"\n"


def _baseline_spine_bytes(baseline) -> bytes:
    return baseline.context_spine_bytes(ROOT) + b"\n"


def test_brief_cli_bytes_equal_same_state_baseline(baseline) -> None:
    refactored = _refactored_brief_bytes()
    oracle = _baseline_brief_bytes(baseline)
    assert refactored == oracle, "refactored brief differs from the pre-refactor monolith in the same state"
    assert _run_cli("brief").stdout == refactored, "CLI brief bytes differ from the in-process pipeline"
    if _canonical_state_holds():
        assert _sha256(refactored) == CANONICAL_BRIEF_SHA256
    else:
        pytest.skip(
            "frozen digest gate inactive (HEAD moved or docs/ modified); "
            f"same-state parity digests: refactored={_sha256(refactored)}"
        )


def test_spine_cli_bytes_equal_same_state_baseline(baseline) -> None:
    refactored = _refactored_spine_bytes()
    oracle = _baseline_spine_bytes(baseline)
    assert refactored == oracle, "refactored spine differs from the pre-refactor monolith in the same state"
    assert _run_cli("spine").stdout == refactored, "CLI spine bytes differ from the in-process pipeline"
    if not _canonical_state_holds():
        pytest.skip(
            "frozen digest gate inactive (HEAD moved or docs/ modified); "
            f"same-state parity digests: refactored={_sha256(refactored)}"
        )
    if _worktree_is_clean():
        assert _sha256(refactored) == CANONICAL_SPINE_SHA256
    else:
        # The only legitimate state-dependent field is worktree_status; prove
        # the frozen clean digest is reconstructible from the current packet
        # after reverting exactly that field to CLEAN.
        packet = json.loads(refactored)
        identity = packet["generated_from"]["canonical_git_identity"]
        identity["worktree_status"] = "CLEAN"
        # The frozen capture is CLI stdout and therefore carries the
        # trailing newline the CLI appends to the canonical bytes.
        reconstructed = project_context._canonical_json(packet) + b"\n"
        assert _sha256(reconstructed) == CANONICAL_SPINE_SHA256


# ---------------------------------------------------------------------------
# (4)+(5) doctor / render CLI behavior parity (exit codes + stdout/stderr)
# ---------------------------------------------------------------------------

def test_doctor_cli_success_matches_frozen_capture() -> None:
    result = _run_cli("doctor", "--strict")
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == CANONICAL_DOCTOR_STRICT_STDOUT
    assert _sha256(result.stdout) == CANONICAL_DOCTOR_STRICT_SHA256


def test_doctor_fail_closed_matches_baseline(baseline, tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    refactored_issues = project_context.doctor(empty)
    baseline_issues = baseline.doctor(empty)
    assert refactored_issues == baseline_issues
    assert refactored_issues, "expected a fail-closed issue list for an unconfigured root"


def test_render_check_cli_success_matches_frozen_capture() -> None:
    result = _run_cli("render", "--check")
    assert result.returncode == 0
    assert result.stderr == b""
    assert result.stdout == CANONICAL_RENDER_CHECK_STDOUT
    assert _sha256(result.stdout) == CANONICAL_RENDER_CHECK_SHA256


def test_render_cli_fail_closed_matches_baseline(baseline, tmp_path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    refactored = _run_cli("--root", str(empty), "render", "--check")
    oracle = _run_baseline_cli(["--root", str(empty), "render", "--check"])
    assert refactored.returncode == oracle.returncode != 0
    assert refactored.stdout == oracle.stdout == b""
    # The argparse usage banner names the launcher (``python -m ...`` vs a
    # ``-c`` runner), so compare the project-owned error line, not the banner.
    refactored_error = [line for line in refactored.stderr.splitlines() if line.startswith(b"project context error")]
    oracle_error = [line for line in oracle.stderr.splitlines() if line.startswith(b"project context error")]
    assert refactored_error == oracle_error
    assert refactored_error


# ---------------------------------------------------------------------------
# (6) module-boundary test: acyclic graph + bounded seam direction
# ---------------------------------------------------------------------------

def test_project_context_module_graph_is_acyclic() -> None:
    module_names = {Path(path).stem: path for path in SIX_MODULES}
    edges: dict[str, set[str]] = {}
    for stem, path in module_names.items():
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
        targets: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                if node.module.startswith("qntylab."):
                    candidate = node.module.split(".")[-1]
                    if candidate in module_names:
                        targets.add(candidate)
                elif node.module == "qntylab":
                    for alias in node.names:
                        if alias.name in module_names:
                            targets.add(alias.name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("qntylab."):
                        candidate = alias.name.split(".")[-1]
                        if candidate in module_names:
                            targets.add(candidate)
        edges[stem] = targets
    visited: dict[str, int] = {}

    def visit(stem: str) -> None:
        state = visited.get(stem, 0)
        assert state != 1, f"circular import edge through {stem!r}: {edges}"
        if state == 2:
            return
        visited[stem] = 1
        for target in edges[stem]:
            visit(target)
        visited[stem] = 2

    for stem in module_names:
        visit(stem)


def test_dsh_domain_module_is_importable_only_through_the_composition_root() -> None:
    for path in GENERIC_MODULES[1:]:  # all generic siblings except the composition root
        tree = ast.parse((ROOT / path).read_text(encoding="utf-8"), filename=path)
        for node in ast.walk(tree):
            imported = None
            if isinstance(node, ast.ImportFrom) and node.module:
                imported = node.module
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.startswith("qntylab"):
                        imported = alias.name
            if imported:
                assert "project_context_execution_authority" not in imported, (
                    f"{path} must not import the DSH domain module directly; "
                    "only the composition root may name the seam"
                )
    # The domain module must not import the composition root (no seam back-edge).
    tree = ast.parse((ROOT / DOMAIN_MODULE).read_text(encoding="utf-8"), filename=DOMAIN_MODULE)
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "qntylab.project_context":
            pytest.fail("the DSH domain module must not import the composition root")


# ---------------------------------------------------------------------------
# (7) canonical projects-registry validation semantics unchanged
# ---------------------------------------------------------------------------

def test_projects_registry_validation_matches_baseline_on_canonical_registry(baseline) -> None:
    config, adr_registry, projects_registry = project_context.load_context_sources(ROOT)
    baseline_config, baseline_adr, baseline_projects = baseline.load_context_sources(ROOT)
    assert config == baseline_config
    assert adr_registry == baseline_adr
    assert projects_registry == baseline_projects
    projects = project_context.validate_projects_registry(ROOT, projects_registry)
    baseline_result = baseline.validate_projects_registry(ROOT, baseline_projects)
    assert projects == baseline_result
    assert projects, "the canonical projects registry must validate to a non-empty projection"
    adrs = project_context.validate_adr_registry(ROOT, adr_registry)
    assert adrs == baseline.validate_adr_registry(ROOT, baseline_adr)


def test_projects_registry_validation_error_semantics_match_baseline(baseline, tmp_path) -> None:
    root = tmp_path / "registry_repo"
    (root / "docs/state").mkdir(parents=True)
    (root / "artifact.md").write_text("tracked\n", encoding="utf-8")
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    valid = {
        "schema_version": 1,
        "project": [
            {
                "project_id": "ONE",
                "state": "ACTIVE",
                "authority_level": "PROJECT_CONTEXT_IMPLEMENTATION",
                "authoritative_artifacts": ["artifact.md"],
                "next_action": "Implement only the authorized bounded work.",
                "implementation_authorized": True,
            }
        ],
    }
    assert project_context.validate_projects_registry(root, valid) == baseline.validate_projects_registry(root, valid)

    unknown_state = json.loads(json.dumps(valid))
    unknown_state["project"][0]["state"] = "NOT_A_STATE"
    with pytest.raises(project_context.ProjectContextError) as refactored_error:
        project_context.validate_projects_registry(root, unknown_state)
    with pytest.raises(baseline.ProjectContextError) as baseline_error:
        baseline.validate_projects_registry(root, unknown_state)
    assert str(refactored_error.value) == str(baseline_error.value)

    unauthorized = json.loads(json.dumps(valid))
    unauthorized["project"][0]["state"] = "PLANNED_NOT_AUTHORIZED"
    with pytest.raises(project_context.ProjectContextError) as refactored_error:
        project_context.validate_projects_registry(root, unauthorized)
    with pytest.raises(baseline.ProjectContextError) as baseline_error:
        baseline.validate_projects_registry(root, unauthorized)
    assert str(refactored_error.value) == str(baseline_error.value)
