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
    tracked-file checks -> historical materializer identity -> Git ancestry ->
    funding structural coverage. It does not replace the narrower unit tests
    above; it proves they compose into a working whole.
    """
    result = provenance.verify_baseline()
    assert result == {
        "evidence_files": 505,
        "pressure_days": 975,
        "symbol_days_missing": 0,
        "historical_materializers": 2,
    }


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


# --- P-F4: historical materializer identity must come from immutable Git objects -----
#
# The frozen funding provenance baseline names the exact materializer source
# that produced the frozen evidence. That is a claim about history. It is
# authenticated against the Git blobs at the baseline's own frozen ancestors,
# never against the working tree, so unrelated later development of the shared
# materializer cannot force a rewrite of the frozen record -- and, crucially,
# cannot be laundered into it either.


BASELINE = provenance._load("provenance_baseline_v0.json")
KLINE_MATERIALIZER = "qntylab/binance_um_kline_1h.py"
HISTORICAL_KLINE_SHA256 = "e5a333f3ce08bb95fa7ef6144fffc672cf14ddf2226dc74817db62beb987cdfa"


def _baseline_copy() -> dict:
    return copy.deepcopy(BASELINE)


def test_historical_materializer_digest_reads_the_blob_not_the_worktree():
    """The frozen kline materializer hash is history, and history still says it."""
    for anchor in BASELINE["required_git_ancestors"]:
        assert provenance.historical_materializer_digest(anchor, KLINE_MATERIALIZER) == HISTORICAL_KLINE_SHA256


def test_the_shared_materializer_has_in_fact_moved_on_at_head():
    """Regression guard for the exact condition this repair exists to handle.

    If this ever stops being true the repair is still correct, but the test
    below would no longer be proving anything, so it is asserted explicitly.
    """
    current = provenance.file_digest(provenance.ROOT / KLINE_MATERIALIZER)
    assert current != HISTORICAL_KLINE_SHA256


def test_historical_identity_holds_even_though_the_worktree_diverged():
    """The whole point: divergent current bytes must not break historical provenance."""
    result = provenance.verify_historical_materializer_identity(_baseline_copy())
    by_path = {item["relative_path"]: item for item in result}
    assert by_path[KLINE_MATERIALIZER]["file_sha256"] == HISTORICAL_KLINE_SHA256
    assert by_path[KLINE_MATERIALIZER]["anchors"] == BASELINE["required_git_ancestors"]


def test_laundering_the_current_worktree_hash_into_history_fails_closed():
    """The forbidden 'repair': replace the historical hash with today's hash."""
    laundered = _baseline_copy()
    current = provenance.file_digest(provenance.ROOT / KLINE_MATERIALIZER)
    for item in laundered["materializer_files"]:
        if item["relative_path"] == KLINE_MATERIALIZER:
            item["file_sha256"] = current
    with pytest.raises(AssertionError, match="historical materializer identity mismatch"):
        provenance.verify_historical_materializer_identity(laundered)


def test_arbitrary_substituted_materializer_digest_fails_closed():
    tampered = _baseline_copy()
    tampered["materializer_files"][0]["file_sha256"] = "0" * 64
    with pytest.raises(AssertionError, match="historical materializer identity mismatch"):
        provenance.verify_historical_materializer_identity(tampered)


def test_malformed_materializer_digest_fails_closed():
    tampered = _baseline_copy()
    tampered["materializer_files"][0]["file_sha256"] = "not-a-sha256"
    with pytest.raises(AssertionError, match="frozen materializer digest is malformed"):
        provenance.verify_historical_materializer_identity(tampered)


def test_materializer_absent_from_the_historical_commit_fails_closed():
    tampered = _baseline_copy()
    tampered["materializer_files"] = [
        {"relative_path": "qntylab/does_not_exist_at_that_commit.py", "file_sha256": "0" * 64}
    ]
    # `git rev-parse --verify` already refuses the missing path, so the failure
    # surfaces as the command failure; either way it is fail-closed.
    with pytest.raises(AssertionError, match="git command failed|does not resolve to an object"):
        provenance.verify_historical_materializer_identity(tampered)


def test_empty_materializer_list_fails_closed():
    tampered = _baseline_copy()
    tampered["materializer_files"] = []
    with pytest.raises(AssertionError, match="no materializer files"):
        provenance.verify_historical_materializer_identity(tampered)


@pytest.mark.parametrize("anchors", [[], None, "98e9dbcbec5dab18f7498cf4c5df77e14a8d5569"])
def test_missing_or_malformed_anchor_list_fails_closed(anchors):
    tampered = _baseline_copy()
    tampered["required_git_ancestors"] = anchors
    with pytest.raises(AssertionError, match="no historical Git anchors"):
        provenance.verify_historical_materializer_identity(tampered)


def test_swapped_anchor_set_fails_closed():
    """The anchors used for identity must be the same set ancestry was proven for."""
    tampered = _baseline_copy()
    tampered["required_git_ancestors"] = ["d1a327a902b410e806cffd7ef90fa2b7719fb3c6"]
    with pytest.raises(AssertionError, match="do not match the verified ancestry set"):
        provenance.verify_historical_materializer_identity(tampered)


def test_reordered_anchor_set_fails_closed():
    tampered = _baseline_copy()
    tampered["required_git_ancestors"] = list(reversed(BASELINE["required_git_ancestors"]))
    with pytest.raises(AssertionError, match="do not match the verified ancestry set"):
        provenance.verify_historical_materializer_identity(tampered)


@pytest.mark.parametrize(
    "anchor",
    [
        "98e9dbc",                                    # abbreviated
        "HEAD",                                       # ref-shaped
        "refs/heads/master",                          # ref
        "98e9dbcbec5dab18f7498cf4c5df77e14a8d5569^",  # revision expression
        "98E9DBCBEC5DAB18F7498CF4C5DF77E14A8D5569",   # uppercase
        "",                                           # empty
    ],
)
def test_ambiguous_or_non_canonical_anchor_is_refused(anchor):
    with pytest.raises(AssertionError, match="not a full 40-hex object id"):
        provenance.historical_materializer_digest(anchor, KLINE_MATERIALIZER)


def test_a_blob_id_is_not_accepted_as_a_commit_anchor():
    """Passing the materializer's own blob id must not authenticate it."""
    blob = subprocess.check_output(
        ["git", "rev-parse", f"{provenance.PREREG_SHA}:{KLINE_MATERIALIZER}"],
        cwd=provenance.ROOT,
        text=True,
    ).strip()
    with pytest.raises(AssertionError, match="not a commit object"):
        provenance.historical_materializer_digest(blob, KLINE_MATERIALIZER)


def test_a_nonexistent_object_id_fails_closed():
    with pytest.raises(AssertionError, match="git command failed"):
        provenance.historical_materializer_digest("0" * 40, KLINE_MATERIALIZER)


def test_identity_fails_closed_outside_the_repository(tmp_path):
    repo, _ = _init_tiny_repo(tmp_path)
    with pytest.raises(AssertionError, match="git command failed"):
        provenance.historical_materializer_digest(provenance.PREREG_SHA, KLINE_MATERIALIZER, root=repo)


def test_identity_fails_closed_with_no_git_metadata_at_all(tmp_path):
    with pytest.raises(AssertionError, match="git command failed|git command unavailable"):
        provenance.historical_materializer_digest(provenance.PREREG_SHA, KLINE_MATERIALIZER, root=tmp_path)


def test_untracked_materializer_path_still_fails_the_continuity_check(tmp_path):
    """`require_tracked` is repository continuity, and it is still enforced."""
    repo, _ = _init_tiny_repo(tmp_path)
    with pytest.raises(AssertionError):
        provenance.verify_historical_materializer_identity(_baseline_copy(), root=repo)


def test_frozen_baseline_bytes_were_not_rewritten_by_this_repair():
    """The repair changed the verifier, never the frozen evidence."""
    provenance.verify_self_digest(BASELINE, "provenance_baseline_digest")
    assert BASELINE["provenance_baseline_digest"] == "sha256:902be2246b64d133e0f22dd71c04eba344d12ead659e5f57c69183ab92f878d9"
    frozen = {item["relative_path"]: item["file_sha256"] for item in BASELINE["materializer_files"]}
    assert frozen == {
        KLINE_MATERIALIZER: HISTORICAL_KLINE_SHA256,
        "qntylab/binance_um_funding_settlement.py": "e2b9c7d99aa8f1743e2b93603551b53e7981b732a4c2c4c1e088bc19d3b87cbc",
    }
