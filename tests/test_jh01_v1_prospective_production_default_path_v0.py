"""Focused regression tests for the JH01 V1 production DEFAULT path.

These tests cover exactly the defaults used by the systemd ExecStart:

- unattended verifier resolution (no env var required; explicit path override);
- explicit Go toolchain resolution (pinned absolute go1.26.0 path, fail-closed);
- the EXACT current retention package is forwarded to
  ``recorder.offline_reverify_current_package`` with the expected policy
  derived from the SAME online attestation expectation (never the historical
  canary);
- dedicated canonical checkout synchronization (fast-forward/detach to
  origin/master on fixture repos; diverged/dirty fail closed BEFORE
  acquisition; frozen recorder/wrapper identity gates).

Fixture git repos live in ``tmp_path``; every campaign state directory is a
``tmp_path``.  The real development checkout and the real campaign ledger are
never written to; no real GitHub publication and no real market data access
happens here (all transport seams are fakes).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess

import pytest

from qntylab import jh01_v1_prospective_operation_v0 as operation
from qntylab import jh01_v1_prospective_production_caller_v0 as caller
from qntylab import jh01_v1_prospective_recorder_implementation_v0 as recorder
from qntylab import jh01_v1_prospective_runtime_defaults_v0 as defaults
from qntylab.jh01_v1_operational_checkout_v0 import (
    OperationalCheckoutBlocked,
    sync_operational_checkout,
    verify_frozen_identities,
)

from tests._jh01_v1_prospective_fixtures import (
    ORIGIN,
    archive_zip_bytes,
    synthetic_archive_provider,
    synthetic_fetch_klines,
)


ROOT = Path(__file__).resolve().parents[1]
PINNED = "c" * 40
QUALIFIED_SOURCE = ROOT / "qualifications" / "jh01_v0r3"
HISTORICAL_POLICY = QUALIFIED_SOURCE / "retention" / "historical_expected_policy.json"


def _noop_sync(root):
    return PINNED


class FakeTransport:
    def __init__(self, origin: datetime):
        self.origin = origin
        self.release: recorder.RemoteRelease | None = None
        self.create_calls = 0
        self.upload_calls = 0
        self.publish_calls = 0

    def find(self, origin_id: str):
        return () if self.release is None else (self.release,)

    def create(self, release: recorder.RemoteRelease):
        self.create_calls += 1
        self.release = recorder.RemoteRelease(release.origin_id, release.tag, release.artifact_digest, release.asset_name, None, None, target_commit=release.target_commit)
        return self.release

    def upload(self, tag: str, asset_name: str, content: bytes):
        self.upload_calls += 1
        assert self.release is not None
        self.release = recorder.RemoteRelease(self.release.origin_id, tag, self.release.artifact_digest, asset_name, sha256(content).hexdigest(), None, target_commit=self.release.target_commit)
        return self.release

    def publish(self, release: recorder.RemoteRelease):
        self.publish_calls += 1
        self.release = recorder.RemoteRelease(release.origin_id, release.tag, release.artifact_digest, release.asset_name, release.asset_sha256, self.origin + timedelta(minutes=10), target_commit=release.target_commit, immutable=True, repository_id="repo", owner_id="owner", release_id=7, purl=f"pkg:github/CipherCuttle/QntyLab@{release.tag}", package_id="repo")
        return self.release

    def acquire_attestation(self, release: recorder.RemoteRelease):
        return b"synthetic-bundle", b"synthetic-root\n"


class FakeVerifier:
    def __init__(self) -> None:
        self.expectations: list[recorder.AttestationExpectation] = []

    def verify(self, *, asset: bytes, bundle: bytes, trusted_root: bytes, expectation: recorder.AttestationExpectation):
        self.expectations.append(expectation)
        return recorder.VerifiedAttestation(expectation, ORIGIN + timedelta(minutes=20), bundle, trusted_root)


def activate_real_campaign(tmp_path: Path) -> None:
    operation.Operation(ROOT, tmp_path / "state").activate_real(activation_time=ORIGIN - timedelta(days=1))


def default_path_record_due(
    tmp_path: Path,
    *,
    now: datetime,
    transport: FakeTransport | None = None,
    verifier=None,
    go_binary: Path | None = None,
):
    """Run record_due with the production DEFAULT offline-reverify path.

    The git sync and Go resolution are stubbed (fixture checkout and pure
    unit seam); the expectation capture and the offline reverify default are
    the real production defaults.  The verifier is injected (synthetic
    bundles can never pass the real qualified verifier); unattended verifier
    resolution itself is proven separately.
    """
    return caller.record_due(
        ROOT,
        tmp_path / "state",
        now=now,
        run_git=_fake_run_git(),
        archive_provider=synthetic_archive_provider(),
        fetch_klines=synthetic_fetch_klines(),
        transport_factory=(lambda: transport) if transport is not None else None,
        verifier=verifier if verifier is not None else FakeVerifier(),
        go_binary=go_binary,
        sync_checkout=_noop_sync,
    )


def _fake_run_git(*, head: str = PINNED, remote: str = PINNED, porcelain: str = ""):
    def run_git(args):
        command = [str(part) for part in args]
        if command[0] == "fetch":
            return ""
        if command[:2] == ["rev-parse", "origin/master"]:
            return remote + "\n"
        if command[:2] == ["rev-parse", "HEAD"]:
            return head + "\n"
        if command[0] == "status":
            return porcelain
        raise AssertionError(f"unexpected git invocation: {command}")
    return run_git


# ---------------------------------------------------------------------------
# Proof 1: verifier resolution succeeds unattended (no env var needed)
# ---------------------------------------------------------------------------


def test_verifier_resolution_unattended_builds_persistent_binary(tmp_path, monkeypatch):
    monkeypatch.delenv("QNTYLAB_JH01_SIGSTORE_VERIFIER", raising=False)
    install_dir = tmp_path / "verifier-install"
    resolved = defaults.resolve_verifier(
        go_binary=Path("/home/swirky/.local/opt/go-1.26.0/bin/go"),
        qualified_source=QUALIFIED_SOURCE,
        install_dir=install_dir,
    )
    assert resolved.is_file()
    assert resolved == install_dir / "bin" / "verify-v0r3-generic"
    manifest = json.loads((install_dir / "build_identity.json").read_text())
    assert set(manifest["source_sha256"]) == {"main.go", "go.mod", "go.sum"}
    assert manifest["go_version"].startswith("go version go1.26.0")
    assert manifest["binary_sha256"] == sha256(resolved.read_bytes()).hexdigest()
    # Resolution is stable and fail-closed on identity mismatch.
    assert defaults.resolve_verifier(
        go_binary=Path("/home/swirky/.local/opt/go-1.26.0/bin/go"),
        qualified_source=QUALIFIED_SOURCE,
        install_dir=install_dir,
    ) == resolved
    tampered = install_dir / "bin" / "verify-v0r3-generic"
    tampered.write_bytes(b"tampered")
    with pytest.raises(defaults.RuntimeDefaultBlocked, match="binary identity mismatch"):
        defaults.resolve_verifier(
            go_binary=Path("/home/swirky/.local/opt/go-1.26.0/bin/go"),
            qualified_source=QUALIFIED_SOURCE,
            install_dir=install_dir,
        )


def test_verifier_resolution_explicit_env_override(tmp_path, monkeypatch):
    override = tmp_path / "custom-verifier"
    override.write_bytes(b"#!/bin/sh\nexit 0\n")
    override.chmod(0o755)
    monkeypatch.setenv("QNTYLAB_JH01_SIGSTORE_VERIFIER", str(override))
    assert defaults.resolve_verifier(install_dir=tmp_path / "unused") == override
    monkeypatch.setenv("QNTYLAB_JH01_SIGSTORE_VERIFIER", str(tmp_path / "missing"))
    with pytest.raises(defaults.RuntimeDefaultBlocked, match="missing executable"):
        defaults.resolve_verifier(install_dir=tmp_path / "unused")


# ---------------------------------------------------------------------------
# Proof 2: explicit Go path (exists, go1.26.0), fail-closed otherwise
# ---------------------------------------------------------------------------


def test_explicit_go_toolchain_resolution(tmp_path):
    resolved = defaults.resolve_go_binary(Path("/home/swirky/.local/opt/go-1.26.0/bin/go"))
    assert resolved == Path("/home/swirky/.local/opt/go-1.26.0/bin/go")
    with pytest.raises(defaults.RuntimeDefaultBlocked, match="go binary missing"):
        defaults.resolve_go_binary(tmp_path / "no-such-go")
    wrong = tmp_path / "wrong-go"
    wrong.write_text("#!/bin/sh\necho 'go version go1.21.3 linux/amd64'\n")
    wrong.chmod(0o755)
    with pytest.raises(defaults.RuntimeDefaultBlocked, match="expected go1.26.0"):
        defaults.resolve_go_binary(wrong)


# ---------------------------------------------------------------------------
# Proof 3: the CURRENT retention package is forwarded verbatim
# ---------------------------------------------------------------------------


def test_current_package_forwarded_to_offline_reverify_current_package(tmp_path, monkeypatch):
    activate_real_campaign(tmp_path)
    captured: dict = {}
    verifier = FakeVerifier()

    def fake_current_reverify(root, *, package, go_binary, expected_policy):
        captured["root"] = root
        captured["package"] = package
        captured["go_binary"] = go_binary
        captured["expected_policy"] = expected_policy.read_bytes()
        recorder.verify_retention_package(package)

    monkeypatch.setattr(recorder, "offline_reverify_current_package", fake_current_reverify)
    monkeypatch.setattr(defaults, "resolve_go_binary", lambda go_binary: go_binary)
    monkeypatch.setattr(
        recorder, "offline_reverify_v0r3_qualified_package",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("historical canary invoked")),
    )
    receipt = default_path_record_due(
        tmp_path, now=ORIGIN + timedelta(minutes=1), transport=FakeTransport(ORIGIN),
        verifier=verifier, go_binary=Path("/explicit/go"),
    )
    assert receipt["origin_state"] == "RECORDED"
    assert receipt["offline_reverification_status"] == "VERIFIED"
    retention_dirs = list((tmp_path / "state" / "retention").iterdir())
    assert len(retention_dirs) == 1
    # The exact package created by Operation._record_due is what the verifier
    # received, with the explicit go binary and the derived expected policy.
    assert captured["package"] == retention_dirs[0]
    assert captured["go_binary"] == Path("/explicit/go")
    assert captured["root"] == ROOT
    assert captured["expected_policy"] == defaults.expected_policy_bytes(verifier.expectations[-1])
    # The derived policy reflects the CURRENT origin publication facts, not
    # the historical canary policy.
    assert captured["expected_policy"] != HISTORICAL_POLICY.read_bytes()
    derived = json.loads(captured["expected_policy"])
    assert derived["target_commit"] == PINNED
    assert derived["tag"].startswith("jh01-v1-recorder-")


# ---------------------------------------------------------------------------
# Proof 4: historical canary cannot satisfy the current-origin check
# ---------------------------------------------------------------------------


def test_corrupted_current_package_fails_closed_without_origin_recorded(tmp_path, monkeypatch):
    activate_real_campaign(tmp_path)

    def rejecting_reverify(root, *, package, go_binary, expected_policy):
        # Simulate the isolated verifier rejecting a tampered current package.
        raise recorder.RecorderBlocked("current package offline Sigstore policy rejected retention package")

    monkeypatch.setattr(recorder, "offline_reverify_current_package", rejecting_reverify)
    monkeypatch.setattr(defaults, "resolve_go_binary", lambda go_binary: go_binary)
    monkeypatch.setattr(
        recorder, "offline_reverify_v0r3_qualified_package",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("historical canary invoked")),
    )
    with pytest.raises(recorder.RecorderBlocked, match="rejected retention package"):
        default_path_record_due(tmp_path, now=ORIGIN + timedelta(minutes=1), transport=FakeTransport(ORIGIN))
    events = (tmp_path / "state" / "jh01_v1_operation_events.jsonl").read_text()
    assert "ORIGIN_RECORDED" not in events
    # The historical canary policy can never stand in for the current policy.
    assert defaults.expected_policy_bytes(
        recorder.AttestationExpectation("CipherCuttle/QntyLab", "tag", PINNED, "forecast.json", "0" * 64)
    ) != HISTORICAL_POLICY.read_bytes()


# ---------------------------------------------------------------------------
# Proofs 5-8: canonical checkout synchronization on fixture repos
# ---------------------------------------------------------------------------

GIT_ENV = {
    **os.environ,
    "GIT_AUTHOR_NAME": "fixture",
    "GIT_AUTHOR_EMAIL": "fixture@example.com",
    "GIT_COMMITTER_NAME": "fixture",
    "GIT_COMMITTER_EMAIL": "fixture@example.com",
}


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False, env=GIT_ENV)
    if result.returncode:
        raise AssertionError(f"git {' '.join(args)} failed: {result.stderr}")
    return result.stdout


def _frozen_sources() -> dict[str, bytes]:
    return {
        "qntylab/jh01_v1_prospective_recorder_implementation_v0.py": (ROOT / "qntylab/jh01_v1_prospective_recorder_implementation_v0.py").read_bytes(),
        "qntylab/jh01_v1_prospective_operation_v0.py": (ROOT / "qntylab/jh01_v1_prospective_operation_v0.py").read_bytes(),
    }


def make_fixture_repo(tmp_path: Path) -> tuple[Path, Path]:
    """Bare origin + operational clone carrying the frozen source files."""
    origin = tmp_path / "origin.git"
    _git("init", "--bare", "--initial-branch=master", str(origin), cwd=tmp_path)
    seed = tmp_path / "seed"
    _git("init", "--initial-branch=master", str(seed), cwd=tmp_path)
    for relpath, content in _frozen_sources().items():
        path = seed / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)
    (seed / "README.md").write_text("fixture\n")
    _git("add", "-A", cwd=seed)
    _git("commit", "-m", "seed", cwd=seed)
    _git("remote", "add", "origin", str(origin), cwd=seed)
    _git("push", "-u", "origin", "master", cwd=seed)
    ops = tmp_path / "ops"
    _git("clone", str(origin), str(ops), cwd=tmp_path)
    return seed, ops


def test_checkout_sync_fast_forward_detaches_to_origin_master(tmp_path):
    seed, ops = make_fixture_repo(tmp_path)
    master = _git("rev-parse", "master", cwd=seed).strip()
    assert sync_operational_checkout(ops) == master
    assert _git("rev-parse", "HEAD", cwd=ops).strip() == master
    # A new origin/master commit is fast-forwarded via detached HEAD.
    (seed / "README.md").write_text("updated\n")
    _git("add", "-A", cwd=seed)
    _git("commit", "-m", "advance", cwd=seed)
    _git("push", "origin", "master", cwd=seed)
    advanced = _git("rev-parse", "master", cwd=seed).strip()
    assert sync_operational_checkout(ops) == advanced
    assert _git("rev-parse", "HEAD", cwd=ops).strip() == advanced
    symbolic = subprocess.run(["git", "symbolic-ref", "-q", "HEAD"], cwd=ops, capture_output=True, text=True)
    assert symbolic.returncode != 0  # detached HEAD, no arbitrary branch execution


def test_stale_diverged_checkout_fails_closed_before_any_effect(tmp_path):
    seed, ops = make_fixture_repo(tmp_path)
    before = _git("rev-parse", "HEAD", cwd=ops).strip()
    # Diverge the operational HEAD with a local commit.
    _git("checkout", "--detach", cwd=ops)
    (ops / "README.md").write_text("local divergence\n")
    _git("add", "-A", cwd=ops)
    _git("commit", "-m", "diverge", cwd=ops)
    diverged = _git("rev-parse", "HEAD", cwd=ops).strip()
    with pytest.raises(OperationalCheckoutBlocked, match="diverged"):
        sync_operational_checkout(ops)
    assert _git("rev-parse", "HEAD", cwd=ops).strip() == diverged
    assert before != diverged
    # A dirty tracked worktree also fails closed.
    _git("checkout", "master", cwd=ops)
    (ops / "README.md").write_text("dirty\n")
    with pytest.raises(OperationalCheckoutBlocked, match="dirty"):
        sync_operational_checkout(ops)


def test_frozen_recorder_identity_gate_fires_on_mismatch(tmp_path):
    seed, ops = make_fixture_repo(tmp_path)
    # Tamper with the frozen recorder in origin/master and advance.
    recorder_relpath = "qntylab/jh01_v1_prospective_recorder_implementation_v0.py"
    content = (seed / recorder_relpath).read_text()
    (seed / recorder_relpath).write_text(content + "\n# tampered\n")
    _git("add", "-A", cwd=seed)
    _git("commit", "-m", "tamper recorder", cwd=seed)
    _git("push", "origin", "master", cwd=seed)
    with pytest.raises(OperationalCheckoutBlocked, match="STOP_SOURCE_CONFLICT.*recorder_implementation"):
        sync_operational_checkout(ops)


def test_frozen_wrapper_identity_gate_fires_on_mismatch(tmp_path):
    seed, ops = make_fixture_repo(tmp_path)
    wrapper_relpath = "qntylab/jh01_v1_prospective_operation_v0.py"
    content = (seed / wrapper_relpath).read_text()
    (seed / wrapper_relpath).write_text(content + "\n# tampered\n")
    _git("add", "-A", cwd=seed)
    _git("commit", "-m", "tamper wrapper", cwd=seed)
    _git("push", "origin", "master", cwd=seed)
    with pytest.raises(OperationalCheckoutBlocked, match="STOP_SOURCE_CONFLICT.*prospective_operation"):
        sync_operational_checkout(ops)


def test_frozen_identity_gate_passes_on_real_repo_and_fails_on_fake_root(tmp_path):
    # The real development checkout still carries the exact frozen identities.
    observed = verify_frozen_identities(ROOT)
    assert set(observed.values()) == {
        "4f5e1791be9f17c1871f9b510329a1632412e028d2a84223fa59e83bbe95ec1a",
        "1176037ff0d3102afc67670202154970e4af1491cff1cd19bc9526c9c9d67c41",
    }
    # A root with wrong-content frozen files fails closed.
    fake = tmp_path / "root"
    (fake / "qntylab").mkdir(parents=True)
    for relpath in _frozen_sources():
        (fake / relpath).write_text("not the frozen source\n")
    with pytest.raises(OperationalCheckoutBlocked, match="STOP_SOURCE_CONFLICT"):
        verify_frozen_identities(fake)


# ---------------------------------------------------------------------------
# Proof 9: the real ledger is never referenced or written by these tests
# ---------------------------------------------------------------------------


def test_real_ledger_is_not_touched_by_default_path_runs(tmp_path, monkeypatch):
    real_state_dir = caller.default_state_dir()
    assert tmp_path / "state" != real_state_dir
    before = sorted(str(p) for p in real_state_dir.rglob("*")) if real_state_dir.exists() else []
    activate_real_campaign(tmp_path)
    receipt = default_path_record_due(tmp_path, now=ORIGIN - timedelta(minutes=1))
    assert receipt == {"origin_state": "NOT_DUE", "origin_utc": "2026-09-15T00:00:00Z"}
    after = sorted(str(p) for p in real_state_dir.rglob("*")) if real_state_dir.exists() else []
    assert before == after
    # All ledger writes stay inside the tmp campaign state directory.
    assert (tmp_path / "state" / "jh01_v1_operation_events.jsonl").is_file()


# ---------------------------------------------------------------------------
# Proof 10: no real GitHub publication in the default-path tests
# ---------------------------------------------------------------------------


def test_no_real_github_publication_in_default_path(tmp_path, monkeypatch):
    def _no_real_transport(*args, **kwargs):
        raise AssertionError("real GitHubReleaseTransport must never be constructed in tests")

    monkeypatch.setattr(recorder, "GitHubReleaseTransport", _no_real_transport)
    monkeypatch.setattr(recorder, "offline_reverify_current_package", lambda root, *, package, go_binary, expected_policy: recorder.verify_retention_package(package))
    monkeypatch.setattr(defaults, "resolve_go_binary", lambda go_binary: go_binary)
    activate_real_campaign(tmp_path)
    transport = FakeTransport(ORIGIN)
    receipt = default_path_record_due(tmp_path, now=ORIGIN + timedelta(minutes=1), transport=transport)
    assert receipt["origin_state"] == "RECORDED"
    # Every publication effect went through the injected fake seam only.
    assert transport.create_calls == 1
    assert transport.upload_calls == 1
    assert transport.publish_calls == 1
