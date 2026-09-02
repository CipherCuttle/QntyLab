"""Adversarial tests for canonical Git provenance of the Funding real-capable wrapper.

Phase ``FUNDING_INCREMENTAL_EXECUTOR_EVALUATION_PROVENANCE_REPAIR_V0``.

Repairs PR #233 hostile-review finding M-1: the real-capable wrapper accepted
a caller-supplied ``authorization_path`` and validated JSON field *values*
only, with no binding to canonical QntyLab Git provenance.

Every fixture repository here is a throwaway clone under ``tmp_path``.  NO
canonical evaluation authorization is created in canonical QntyLab history, no
claim is consumed, no evidence is read, no real ``ForecastRow`` is built, and
the shared scientific core is never invoked.  The positive-control test proves
the verifier is not vacuously failing; it operates entirely inside a disposable
clone.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from qntylab import jigsaw_funding_pressure_incremental_forecast_value_executor_v0 as executor
from qntylab import (
    jigsaw_funding_pressure_incremental_forecast_value_evaluation_authorization_provenance_v1 as provenance,
)
from qntylab import jigsaw_funding_pressure_incremental_forecast_value_real_capable_wrapper_v1 as real_capable

ROOT = Path(__file__).resolve().parents[1]
CANON_REL = provenance.CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH
CANONICAL_REMOTE_URL = "https://github.com/CipherCuttle/QntyLab.git"
UnauthorizedExecutionError = executor.UnauthorizedExecutionError


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args], check=True, capture_output=True, text=True
    )
    return completed.stdout.strip()


def _canonical_bytes(document: dict) -> bytes:
    return (json.dumps(document, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _good_document() -> dict:
    return {
        "artifact_type": provenance.REQUIRED_AUTHORIZATION_ARTIFACT_TYPE,
        "state": provenance.REQUIRED_AUTHORIZATION_STATE,
        "scientific_execution_authorized": True,
        "governing_preregistration_digest": executor.GOVERNING_PREREGISTRATION_DIGEST,
        "real_capable_wrapper_project_id": provenance.REAL_CAPABLE_WRAPPER_PROJECT_ID,
        "execution_mode": "REAL_SCIENTIFIC_EXECUTION",
        "canonical_git_binding": {
            "repository": provenance.CANONICAL_REPOSITORY_LOCATOR,
            "artifact_path": CANON_REL,
            "preregistration_anchor_commit": provenance.PREREGISTRATION_ANCHOR_COMMIT,
            "historical_v0_oracle_anchor_commit": provenance.HISTORICAL_V0_ORACLE_ANCHOR_COMMIT,
        },
    }


def _commit_file(root: Path, relative: str, payload: bytes, message: str) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    _git(root, "add", "--", relative)
    _git(root, "commit", "--quiet", "-m", message)


def _pin_digest(monkeypatch, payload: bytes) -> str:
    digest = hashlib.sha256(payload).hexdigest()
    monkeypatch.setattr(provenance, "EXPECTED_CANONICAL_AUTHORIZATION_SHA256", digest)
    return digest


@pytest.fixture(scope="session")
def _base_clone(tmp_path_factory) -> Path:
    base = tmp_path_factory.mktemp("provenance-base") / "qntylab"
    subprocess.run(
        ["git", "clone", "--quiet", "--no-hardlinks", str(ROOT), str(base)],
        check=True,
        capture_output=True,
    )
    return base


@pytest.fixture
def canonical_repo(_base_clone: Path, tmp_path: Path) -> Path:
    """A disposable clone that carries canonical QntyLab history + remote identity."""
    repo = tmp_path / "canonical"
    subprocess.run(
        ["git", "clone", "--quiet", "--local", str(_base_clone), str(repo)],
        check=True,
        capture_output=True,
    )
    _git(repo, "remote", "set-url", "origin", CANONICAL_REMOTE_URL)
    _git(repo, "config", "user.email", "provenance-test@example.invalid")
    _git(repo, "config", "user.name", "provenance test")
    _git(repo, "checkout", "--quiet", "--detach", "HEAD")
    return repo


# --------------------------------------------------------------------------
# 1 -- the permanent fail-closed state (no canonical authorization exists)
# --------------------------------------------------------------------------


def test_real_repo_has_no_canonical_authorization_and_fails_closed():
    assert provenance.canonical_authorization_exists() is False
    assert not (ROOT / CANON_REL).exists()
    with pytest.raises(UnauthorizedExecutionError):
        provenance.authenticate_canonical_evaluation_authorization()
    with pytest.raises(UnauthorizedExecutionError):
        real_capable.run_real_capable_evaluation()


def test_pinned_digest_is_absent_at_this_phase():
    """This phase creates no authorization: no content digest may be pinned."""
    assert provenance.EXPECTED_CANONICAL_AUTHORIZATION_SHA256 is None


def test_missing_canonical_artifact_in_canonical_clone(canonical_repo):
    with pytest.raises(UnauthorizedExecutionError, match="no canonical evaluation authorization exists"):
        provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)


# --------------------------------------------------------------------------
# 2 -- caller-supplied path substitution / symlink / traversal
# --------------------------------------------------------------------------


def test_caller_supplied_arbitrary_path_is_refused(tmp_path):
    forged = tmp_path / "authorization.json"
    forged.write_bytes(_canonical_bytes(_good_document()))
    with pytest.raises(UnauthorizedExecutionError, match="does not resolve to the canonical"):
        provenance.authenticate_canonical_evaluation_authorization(forged)
    with pytest.raises(UnauthorizedExecutionError):
        real_capable.run_real_capable_evaluation(authorization_path=str(forged))


def test_caller_supplied_valid_json_at_the_wrong_path_is_refused(canonical_repo):
    wrong = "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/wrong_authorization.json"
    _commit_file(canonical_repo, wrong, _canonical_bytes(_good_document()), "wrong path")
    with pytest.raises(UnauthorizedExecutionError, match="does not resolve to the canonical"):
        provenance.authenticate_canonical_evaluation_authorization(
            canonical_repo / wrong, root=canonical_repo
        )
    # ...and with no override the canonical path is still empty => fail closed.
    with pytest.raises(UnauthorizedExecutionError, match="no canonical evaluation authorization exists"):
        provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)


def test_symlink_authorization_path_pointing_elsewhere_is_refused(tmp_path):
    real_file = tmp_path / "elsewhere.json"
    real_file.write_bytes(_canonical_bytes(_good_document()))
    link = tmp_path / "authorization.json"
    link.symlink_to(real_file)
    with pytest.raises(UnauthorizedExecutionError, match="does not resolve to the canonical"):
        provenance.authenticate_canonical_evaluation_authorization(link)


def test_path_traversal_authorization_path_is_refused(canonical_repo):
    traversal = canonical_repo / "experiments" / ".." / "etc" / "authorization.json"
    with pytest.raises(UnauthorizedExecutionError, match="does not resolve to the canonical"):
        provenance.authenticate_canonical_evaluation_authorization(traversal, root=canonical_repo)


def test_canonical_path_committed_as_symlink_is_refused(canonical_repo, monkeypatch):
    target = canonical_repo / CANON_REL
    target.parent.mkdir(parents=True, exist_ok=True)
    (canonical_repo / "real_auth_payload.json").write_bytes(_canonical_bytes(_good_document()))
    target.symlink_to(canonical_repo / "real_auth_payload.json")
    _git(canonical_repo, "add", "--", CANON_REL, "real_auth_payload.json")
    _git(canonical_repo, "commit", "--quiet", "-m", "symlink at canonical path")
    _pin_digest(monkeypatch, _canonical_bytes(_good_document()))
    with pytest.raises(UnauthorizedExecutionError, match="symlink"):
        provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)


# --------------------------------------------------------------------------
# 3 -- wrong repository identity
# --------------------------------------------------------------------------


def test_wrong_repository_identity_is_refused(tmp_path, monkeypatch):
    alien = tmp_path / "alien"
    alien.mkdir()
    _git(alien, "init", "--quiet")
    _git(alien, "config", "user.email", "a@b.invalid")
    _git(alien, "config", "user.name", "alien")
    _git(alien, "remote", "add", "origin", CANONICAL_REMOTE_URL)
    _commit_file(alien, CANON_REL, _canonical_bytes(_good_document()), "alien authorization")
    _pin_digest(monkeypatch, _canonical_bytes(_good_document()))
    with pytest.raises(UnauthorizedExecutionError, match="wrong repository identity"):
        provenance.authenticate_canonical_evaluation_authorization(root=alien)


def test_non_canonical_remote_origin_is_refused(canonical_repo, monkeypatch):
    _git(canonical_repo, "remote", "set-url", "origin", "https://github.com/attacker/QntyLab.git")
    _commit_file(canonical_repo, CANON_REL, _canonical_bytes(_good_document()), "auth")
    _pin_digest(monkeypatch, _canonical_bytes(_good_document()))
    with pytest.raises(UnauthorizedExecutionError, match="wrong repository identity"):
        provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)


# --------------------------------------------------------------------------
# 4 -- wrong commit / changed blob bytes / wrong tree
# --------------------------------------------------------------------------


def test_authorization_only_in_a_non_head_commit_is_refused(canonical_repo, monkeypatch):
    payload = _canonical_bytes(_good_document())
    _commit_file(canonical_repo, CANON_REL, payload, "add canonical authorization")
    with_auth = _git(canonical_repo, "rev-parse", "HEAD")
    _git(canonical_repo, "rm", "--quiet", "--", CANON_REL)
    _git(canonical_repo, "commit", "--quiet", "-m", "remove authorization")
    _pin_digest(monkeypatch, payload)
    # HEAD no longer carries the artifact even though a prior commit did.
    with pytest.raises(UnauthorizedExecutionError, match="no canonical evaluation authorization exists"):
        provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)
    # Proof the artifact really was valid at the earlier commit.
    assert _git(canonical_repo, "cat-file", "-t", f"{with_auth}:{CANON_REL}") == "blob"


def test_changed_blob_bytes_break_the_pinned_digest(canonical_repo, monkeypatch):
    good = _good_document()
    good_payload = _canonical_bytes(good)
    tampered = dict(good)
    tampered["note"] = "cosmetically altered but still valid JSON with the right fields"
    _commit_file(canonical_repo, CANON_REL, _canonical_bytes(tampered), "tampered authorization")
    _pin_digest(monkeypatch, good_payload)  # pin the digest of the *unmodified* bytes
    with pytest.raises(UnauthorizedExecutionError, match="do not match the pinned content digest"):
        provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)


def test_well_formed_authorization_without_a_pinned_digest_still_fails_closed(canonical_repo):
    _commit_file(canonical_repo, CANON_REL, _canonical_bytes(_good_document()), "auth, no pin")
    assert provenance.EXPECTED_CANONICAL_AUTHORIZATION_SHA256 is None
    with pytest.raises(UnauthorizedExecutionError, match="no expected canonical authorization digest is pinned"):
        provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)


# --------------------------------------------------------------------------
# 5 -- malformed / mismatched identity
# --------------------------------------------------------------------------


def test_malformed_authorization_bytes_are_refused(canonical_repo, monkeypatch):
    payload = b'{"artifact_type": "FUNDING_INCREMENTAL_REAL_EVALUATION_EXECUTION_AUTHORIZATION"'  # truncated
    _commit_file(canonical_repo, CANON_REL, payload, "malformed authorization")
    _pin_digest(monkeypatch, payload)
    with pytest.raises(UnauthorizedExecutionError, match="malformed"):
        provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)


@pytest.mark.parametrize(
    "mutation, expected",
    [
        ({"real_capable_wrapper_project_id": "SOME_OTHER_WRAPPER"}, "not bound to this real-capable wrapper"),
        ({"governing_preregistration_digest": "0" * 64}, "not bound to the frozen preregistration digest"),
        ({"state": "OPEN"}, "is not CLOSED_PASS"),
        ({"scientific_execution_authorized": False}, "does not grant scientific execution authority"),
        ({"artifact_type": "WRONG"}, "artifact_type mismatch"),
    ],
)
def test_mismatched_identity_fields_are_refused(canonical_repo, monkeypatch, mutation, expected):
    document = _good_document()
    document.update(mutation)
    payload = _canonical_bytes(document)
    _commit_file(canonical_repo, CANON_REL, payload, "mismatched authorization")
    _pin_digest(monkeypatch, payload)
    with pytest.raises(UnauthorizedExecutionError, match=expected):
        provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)


@pytest.mark.parametrize(
    "binding_key",
    ["repository", "artifact_path", "preregistration_anchor_commit", "historical_v0_oracle_anchor_commit"],
)
def test_mismatched_self_attested_git_binding_is_refused(canonical_repo, monkeypatch, binding_key):
    document = _good_document()
    document["canonical_git_binding"][binding_key] = "NOT_THE_CANONICAL_VALUE"
    payload = _canonical_bytes(document)
    _commit_file(canonical_repo, CANON_REL, payload, "bad git binding")
    _pin_digest(monkeypatch, payload)
    with pytest.raises(UnauthorizedExecutionError, match=f"canonical_git_binding.{binding_key} mismatch"):
        provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)


def test_absent_self_attested_git_binding_is_refused(canonical_repo, monkeypatch):
    document = _good_document()
    document.pop("canonical_git_binding")
    payload = _canonical_bytes(document)
    _commit_file(canonical_repo, CANON_REL, payload, "no git binding")
    _pin_digest(monkeypatch, payload)
    with pytest.raises(UnauthorizedExecutionError, match="missing its canonical_git_binding"):
        provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)


# --------------------------------------------------------------------------
# 6 -- positive control: the verifier is not vacuously failing
# --------------------------------------------------------------------------


def test_positive_control_authenticates_inside_a_disposable_clone(canonical_repo, monkeypatch):
    """A fully canonical artifact authenticates -- proving deterministic verification.

    This happens only inside a throwaway ``tmp_path`` clone; canonical QntyLab
    history is untouched and no authorization is created there.
    """
    payload = _canonical_bytes(_good_document())
    _commit_file(canonical_repo, CANON_REL, payload, "canonical authorization")
    resolution_commit = _git(canonical_repo, "rev-parse", "HEAD")
    blob_oid = _git(canonical_repo, "rev-parse", "--verify", f"HEAD:{CANON_REL}")
    digest = _pin_digest(monkeypatch, payload)

    receipt = provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)
    provenance_block = receipt["_canonical_git_provenance"]
    assert provenance_block == {
        "authenticated": True,
        "repository": provenance.CANONICAL_REPOSITORY_LOCATOR,
        "resolution_commit": resolution_commit,
        "artifact_path": CANON_REL,
        "blob_sha1": blob_oid,
        "blob_sha256": digest,
        "anchor_commits": list(provenance.CANONICAL_ANCHOR_COMMITS),
    }
    # An accepted path override that DOES resolve to the canonical artifact is fine.
    receipt_again = provenance.authenticate_canonical_evaluation_authorization(
        canonical_repo / CANON_REL, root=canonical_repo
    )
    assert receipt_again["_canonical_git_provenance"]["authenticated"] is True


def test_positive_control_then_worktree_replacement_is_refused(canonical_repo, monkeypatch):
    payload = _canonical_bytes(_good_document())
    _commit_file(canonical_repo, CANON_REL, payload, "canonical authorization")
    _pin_digest(monkeypatch, payload)
    assert provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)["_canonical_git_provenance"]["authenticated"]
    # Replace the worktree copy without committing: worktree-local swap.
    (canonical_repo / CANON_REL).write_bytes(payload + b"  \n")
    with pytest.raises(UnauthorizedExecutionError, match="worktree-local replacement is refused"):
        provenance.authenticate_canonical_evaluation_authorization(root=canonical_repo)


# --------------------------------------------------------------------------
# 7 -- authorization failure happens BEFORE every downstream effect
# --------------------------------------------------------------------------


def _wire_downstream_spies(monkeypatch) -> dict:
    calls = {"claim": 0, "evidence": 0, "rows": 0, "core": 0, "record": 0}

    def spy(name):
        def _spy(*_args, **_kwargs):
            calls[name] += 1
            raise AssertionError(f"{name} must not run when authorization provenance fails")
        return _spy

    monkeypatch.setattr(real_capable, "_consume_irreversible_one_shot_claim", spy("claim"))
    monkeypatch.setattr(real_capable, "_authenticate_frozen_evidence", spy("evidence"))
    monkeypatch.setattr(real_capable, "_construct_real_forecast_rows", spy("rows"))
    monkeypatch.setattr(real_capable, "_invoke_successor_shared_core", spy("core"))
    monkeypatch.setattr(real_capable, "_record_exactly_one_result", spy("record"))
    return calls


def test_provenance_failure_precedes_claim_evidence_rows_core_and_recording(monkeypatch):
    calls = _wire_downstream_spies(monkeypatch)
    with pytest.raises(UnauthorizedExecutionError):
        real_capable.run_real_capable_evaluation(claim_transport=object(), frozen_evidence=object())
    assert calls == {"claim": 0, "evidence": 0, "rows": 0, "core": 0, "record": 0}


@pytest.mark.parametrize(
    "scenario",
    ["missing_artifact", "wrong_path_override", "no_pinned_digest", "identity_mismatch"],
)
def test_downstream_never_runs_for_any_provenance_rejection(canonical_repo, monkeypatch, scenario):
    monkeypatch.setattr(real_capable, "_repository_root", lambda: canonical_repo)
    calls = _wire_downstream_spies(monkeypatch)
    kwargs: dict = {"claim_transport": object(), "frozen_evidence": object()}

    if scenario == "missing_artifact":
        pass
    elif scenario == "wrong_path_override":
        wrong = canonical_repo / "experiments" / "wrong.json"
        wrong.parent.mkdir(parents=True, exist_ok=True)
        wrong.write_bytes(_canonical_bytes(_good_document()))
        kwargs["authorization_path"] = str(wrong)
    elif scenario == "no_pinned_digest":
        _commit_file(canonical_repo, CANON_REL, _canonical_bytes(_good_document()), "auth")
    elif scenario == "identity_mismatch":
        document = _good_document()
        document["real_capable_wrapper_project_id"] = "OTHER"
        payload = _canonical_bytes(document)
        _commit_file(canonical_repo, CANON_REL, payload, "auth")
        _pin_digest(monkeypatch, payload)

    with pytest.raises(UnauthorizedExecutionError):
        real_capable.run_real_capable_evaluation(**kwargs)
    assert calls == {"claim": 0, "evidence": 0, "rows": 0, "core": 0, "record": 0}


def test_phase_attestation_and_firewall_remain_all_negative():
    attestation = dict(real_capable.REAL_CAPABLE_PHASE_ATTESTATION)
    assert attestation["REAL_ROWS_CONSTRUCTED"] == 0
    assert attestation["REAL_OUTCOMES_ACCESSED"] is False
    assert attestation["SCIENTIFIC_CORE_INVOCATIONS"] == 0
    assert attestation["EVALUATION_ORIGINS_CONSUMED"] == 0
    assert attestation["AUTHORIZATION_CLAIM_CONSUMED"] is False
    assert attestation["CANONICAL_EVALUATION_AUTHORIZATION_EXISTS"] is False
    assert attestation["CALLER_SUPPLIED_AUTHORIZATION_BYTES_TRUSTED"] is False
    assert attestation["AUTHORIZATION_PROVENANCE_BINDING"] == "CANONICAL_QNTYLAB_GIT_IDENTITY"
    assert attestation["DOWNSTREAM_AUTHORITY"] == "NONE"
    assert attestation["CAPITAL_AUTHORITY"] == "NONE"
