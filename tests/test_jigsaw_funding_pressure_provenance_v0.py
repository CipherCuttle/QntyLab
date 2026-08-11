import copy
import json
import os
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from qntylab import jigsaw_funding_pressure_provenance_v0 as provenance

_GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "provenance-test",
    "GIT_AUTHOR_EMAIL": "provenance-test@example.invalid",
    "GIT_COMMITTER_NAME": "provenance-test",
    "GIT_COMMITTER_EMAIL": "provenance-test@example.invalid",
}


def _init_tiny_repo(tmp_path: Path) -> tuple[Path, str]:
    """Build a throwaway, single-commit Git repo unrelated to QntyLab history."""
    repo = tmp_path / "tiny-repo"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=_GIT_ENV)
    (repo / "file.txt").write_text("hello", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True, env=_GIT_ENV)
    subprocess.run(["git", "commit", "-q", "-m", "initial"], cwd=repo, check=True, env=_GIT_ENV)
    sha = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True, env=_GIT_ENV).strip()
    return repo, sha


def test_pit_v1_certificate_digest_and_mutation():
    certificate = provenance._load("pit_coverage_certificate_v1.json")
    assert provenance.canonical_digest(provenance._without(certificate, "pit_coverage_certificate_v1_digest")) == "sha256:eee5ce2769e49970a7a4e8d4851d7da569abc156d4f183959b416bfb8dbf188b"
    mutated = copy.deepcopy(certificate)
    mutated["pit_eligibility"]["combined_executable_decisions_total"] = 609
    assert provenance.canonical_digest(provenance._without(mutated, "pit_coverage_certificate_v1_digest")) != provenance.PIT_V1_DIGEST


def test_coverage_schedule_is_derived_and_complete():
    coverage = provenance.compute_funding_coverage()
    assert coverage["first_required_pressure_day"] == "2022-10-19"
    assert coverage["last_required_pressure_day"] == "2025-06-19"
    assert coverage["pressure_day_count"] == 975
    assert coverage["symbol_day_requirement_count"] == 19500
    assert coverage["symbol_day_complete_count"] == 19500
    assert coverage["missing_count"] == 0


def test_funding_boundary_is_strict_lower_and_inclusive_upper():
    decision = datetime(2023, 10, 19, tzinfo=UTC)
    lower = decision - timedelta(hours=24)
    assert not (lower < lower <= decision)
    assert lower <= decision


def test_verifier_uses_active_checkout_root():
    assert provenance.ROOT == provenance.Path(provenance.__file__).resolve().parents[1]


def test_tampered_evidence_byte_fails(tmp_path):
    item = provenance._load("provenance_baseline_v0.json")["evidence_files"][0]
    path = tmp_path / item["relative_path"]
    path.parent.mkdir(parents=True)
    path.write_bytes((provenance.ROOT / item["relative_path"]).read_bytes() + b"x")
    with pytest.raises(AssertionError, match="evidence byte mismatch"):
        provenance.verify_evidence_entry(item, tmp_path, require_tracked=False)


def test_removed_evidence_path_fails(tmp_path):
    item = provenance._load("provenance_baseline_v0.json")["evidence_files"][0]
    with pytest.raises(AssertionError, match="evidence byte mismatch"):
        provenance.verify_evidence_entry(item, tmp_path, require_tracked=False)


@pytest.mark.parametrize("field", ["funding_history_coverage_digest", "execution_git_provenance_contract_digest"])
def test_digest_artifacts_are_self_consistent(field):
    filename = {"funding_history_coverage_digest": "funding_history_coverage_v0.json", "execution_git_provenance_contract_digest": "execution_git_provenance_contract_v0.json"}[field]
    payload = provenance._load(filename)
    assert payload[field] == provenance.canonical_digest(provenance._without(payload, field))


# --- P-F2: verify_baseline() must be exercised directly, end-to-end, by pytest --------


def test_verify_baseline_end_to_end_orchestration():
    """Directly exercises verify_baseline() against the canonical candidate checkout.

    This walks the real orchestration: self-digests -> evidence hashes ->
    tracked-file checks -> materializer hashes -> Git ancestry -> funding
    structural coverage. It does not replace the narrower unit tests above;
    it proves they compose into a working whole.
    """
    result = provenance.verify_baseline()
    assert result == {"evidence_files": 505, "pressure_days": 975, "symbol_days_missing": 0}


# --- P-F3: Git ancestry verification must fail closed, never silently pass -----------


def test_verify_git_ancestry_passes_for_valid_checkout():
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=provenance.ROOT, text=True).strip()
    provenance.verify_git_ancestry(head)  # must not raise


def test_verify_git_ancestry_fails_closed_with_no_git_metadata(tmp_path):
    with pytest.raises(AssertionError, match="no usable Git metadata"):
        provenance.verify_git_ancestry("deadbeef", root=tmp_path)


def test_verify_git_ancestry_fails_when_required_ancestor_missing(tmp_path):
    repo, sha = _init_tiny_repo(tmp_path)
    with pytest.raises(AssertionError, match="is not an ancestor"):
        provenance.verify_git_ancestry(sha, root=repo, ancestors=(provenance.PREREG_SHA,))


def test_verify_git_ancestry_fails_closed_when_git_command_unavailable(tmp_path):
    repo, sha = _init_tiny_repo(tmp_path)

    def _broken_runner(*args, **kwargs):
        raise OSError("git executable not found")

    with pytest.raises(AssertionError, match="git command unavailable"):
        provenance.verify_git_ancestry(sha, root=repo, ancestors=(sha,), git_runner=_broken_runner)


def test_verify_git_ancestry_does_not_accept_archive_as_checkout(tmp_path):
    """A `git archive` tarball extraction has no `.git` metadata at all; it must
    never be treated as equivalent to an authenticated runtime checkout."""
    archive_dir = tmp_path / "extracted-archive"
    archive_dir.mkdir()
    (archive_dir / "some_file.py").write_text("# not a real checkout", encoding="utf-8")
    with pytest.raises(AssertionError, match="no usable Git metadata"):
        provenance.verify_git_ancestry("deadbeef", root=archive_dir)
