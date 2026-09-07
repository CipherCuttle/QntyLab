"""C5 structural assertions for PROVEN_DELETE_SAFE_SLIMMING_V0.

Pins the proven delete-safe slimming increment C5 of the umbrella
QNTYLAB_REPOSITORY_ERGONOMICS_AND_MODULARITY_CLEANUP_V0 (canonical parent
``e826dcb9cc264d1280c91c0bec01e23488fbb9e1``).

The exact deleted set and the blocked-36 retained set are NOT hardcoded here:
both are read from the authoritative forensic deletion matrix
``docs/forensics/QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0/deletion_matrix.json``
and cross-bound against the C5 implementation manifest. This test grants no
authority; it only pins structural post-conditions of the six deletions.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CANONICAL_PARENT = "e826dcb9cc264d1280c91c0bec01e23488fbb9e1"
FORENSIC_ANCHOR = "be291300abb70f3ffc6ba0dd8b1bea570daf5377"
DELETION_MATRIX = (
    ROOT
    / "docs/forensics/QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0/deletion_matrix.json"
)
C5_DIR = (
    ROOT
    / "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0/c5_proven_delete_safe_slimming_v0"
)
UMBRELLA_DECISION = (
    ROOT
    / "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0/decision.json"
)


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    )
    return result.stdout


def _deletion_matrix() -> dict:
    return json.loads(DELETION_MATRIX.read_text(encoding="utf-8"))


def _deleted_safe_list() -> list[str]:
    matrix = _deletion_matrix()
    assert matrix["repo_head"] == FORENSIC_ANCHOR
    safe = matrix["delete_safe_list"]
    assert len(safe) == 6
    return safe


def _manifest() -> dict:
    return json.loads((C5_DIR / "implementation_manifest.json").read_text(encoding="utf-8"))


def test_deleted_set_matches_manifest_and_matrix() -> None:
    manifest = _manifest()
    assert manifest["increment_id"] == "C5"
    assert manifest["phase_id"] == "PROVEN_DELETE_SAFE_SLIMMING_V0"
    assert manifest["canonical_parent"] == CANONICAL_PARENT
    assert manifest["forensic_audit_commit"] == FORENSIC_ANCHOR
    assert manifest["deleted_set_count"] == 6
    assert manifest["load_blocking_reference_count"] == 0
    assert manifest["blocked_retained"] == 36
    assert manifest["deleted_paths"] == _deleted_safe_list()


def test_six_deleted_paths_absent_from_index_and_filesystem() -> None:
    tracked = set(_git("ls-files").splitlines())
    for path in _deleted_safe_list():
        assert path not in tracked, f"still tracked: {path}"
        assert not (ROOT / path).exists(), f"still on filesystem: {path}"


def test_blocked_36_candidates_all_retained() -> None:
    matrix = _deletion_matrix()
    blocked = [row["candidate_path"] for row in matrix["rows"] if row["classification"] != "DELETE_SAFE"]
    assert len(blocked) == 36
    frozen = [r for r in matrix["rows"] if r["classification"] == "DELETE_BLOCKED_BY_FROZEN_BINDING"]
    active = [r for r in matrix["rows"] if r["classification"] == "DELETE_BLOCKED_BY_ACTIVE_USE"]
    assert len(frozen) == 28
    assert len(active) == 8
    tracked = set(_git("ls-files").splitlines())
    for path in blocked:
        assert (ROOT / path).exists(), f"blocked candidate missing from filesystem: {path}"
        assert path in tracked, f"blocked candidate missing from index: {path}"


def test_qntylab_module_count_is_135() -> None:
    modules = sorted((ROOT / "qntylab").glob("*.py"))
    assert len(modules) == 135


def test_deleted_module_stems_have_zero_reference_hits() -> None:
    stems = [Path(p).name[:-3] for p in _deleted_safe_list() if p.endswith(".py")]
    assert len(stems) == 4
    sources: list[Path] = sorted((ROOT / "qntylab").glob("*.py")) + sorted((ROOT / "tests").glob("*.py"))
    for source in sources:
        text = source.read_text(encoding="utf-8", errors="replace")
        for stem in stems:
            assert stem not in text, f"deleted stem {stem!r} referenced by {source.relative_to(ROOT)}"


def test_forbidden_surfaces_unchanged_vs_canonical_parent() -> None:
    changed = _git("diff", "--name-only", CANONICAL_PARENT, "--", "docs/forensics/", ".github/", "pyproject.toml")
    assert changed.strip() == "", f"forbidden surfaces changed vs parent:\n{changed}"


def test_umbrella_decision_unmodified_vs_canonical_parent() -> None:
    changed = _git(
        "diff",
        "--name-only",
        CANONICAL_PARENT,
        "--",
        "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0/decision.json",
    )
    assert changed.strip() == "", "umbrella decision.json changed vs parent"
    decision = json.loads(UMBRELLA_DECISION.read_text(encoding="utf-8"))
    assert decision["state"] == "CLOSED_PASS"


def test_qntylab_diff_vs_parent_is_exactly_four_deletions() -> None:
    name_status = _git("diff", "--name-status", CANONICAL_PARENT, "--", "qntylab/").strip().splitlines()
    expected = {"D\t" + p for p in _deleted_safe_list() if p.startswith("qntylab/")}
    assert set(name_status) == expected, f"qntylab/ diff vs parent not exactly the four deletions: {name_status}"


def test_reference_reproof_artifact_records_gate_pass() -> None:
    reproof = json.loads((C5_DIR / "reference_reproof.json").read_text(encoding="utf-8"))
    assert reproof["canonical_head"] == CANONICAL_PARENT
    assert reproof["verdict"] == "GATE_PASS"
    assert reproof["total_load_bearing"] == 0
    assert len(reproof["cells"]) == 6
    for candidate, cells in reproof["cells"].items():
        assert candidate in _deleted_safe_list()
        assert cells["_load_bearing_cells"] == []
        assert cells["_load_bearing_sweep_paths"] == []
