"""Unattended runtime defaults for the JH01 V1 production caller (H-01, C-01).

Owns the deterministic, fail-closed resolution of the non-secret runtime
prerequisites the systemd invocation needs:

- explicit Go toolchain (existence + exact version check at resolution time);
- a persistent, identity-proved V0R3 Sigstore verifier executable built from
  the already-qualified frozen source ``qualifications/jh01_v0r3`` at a
  deterministic absolute location (no network: GOPROXY=off);
- the current-package offline reverification default, which forwards the
  EXACT current retention package created by ``Operation._record_due`` to
  ``recorder.offline_reverify_current_package`` together with an
  expected_policy deterministically derived from the SAME
  ``AttestationExpectation`` facts used for the online attestation
  verification.  The historical canary package is never consulted.

This module owns no recorder logic and no science; the frozen recorder is
never modified and its functions are only called.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Callable

from . import jh01_v1_prospective_recorder_implementation_v0 as recorder
from .jh01_v1_operational_checkout_v0 import OperationalCheckoutBlocked

DEFAULT_GO_BINARY = Path("/home/swirky/.local/opt/go-1.26.0/bin/go")
EXPECTED_GO_VERSION_PREFIX = "go version go1.26.0"

VERIFIER_INSTALL_DIR = Path.home() / ".local" / "opt" / "jh01-v0r3-verifier"
VERIFIER_BIN_RELPATH = Path("bin") / "verify-v0r3-generic"
VERIFIER_IDENTITY_RELPATH = Path("build_identity.json")

VERIFIER_SOURCE_FILES = ("main.go", "go.mod", "go.sum")

OfflineReverify = Callable[[Path], None]


class RuntimeDefaultBlocked(RuntimeError):
    """An unattended runtime prerequisite failed its fail-closed check."""


def resolve_go_binary(go_binary: Path | None = None) -> Path:
    """Resolve the Go toolchain, failing closed unless it is exactly go1.26.0."""
    resolved = Path(go_binary) if go_binary is not None else DEFAULT_GO_BINARY
    if not resolved.is_file():
        raise RuntimeDefaultBlocked(f"EXPLICIT_GO_TOOLCHAIN_REQUIRED: go binary missing at {resolved}")
    run = subprocess.run([str(resolved), "version"], capture_output=True, text=True, check=False)
    if run.returncode or not run.stdout.startswith(EXPECTED_GO_VERSION_PREFIX):
        raise RuntimeDefaultBlocked(
            "EXPLICIT_GO_TOOLCHAIN_REQUIRED: expected go1.26.0, "
            f"observed {run.stdout.strip() or run.stderr.strip()}"
        )
    return resolved


@dataclass(frozen=True)
class VerifierIdentity:
    source_sha256: dict[str, str]
    go_version: str
    binary_sha256: str


def _source_identities(qualified_source: Path) -> dict[str, str]:
    identities: dict[str, str] = {}
    for name in VERIFIER_SOURCE_FILES:
        path = qualified_source / name
        if not path.is_file():
            raise RuntimeDefaultBlocked(f"verifier source file missing: {path}")
        identities[name] = sha256(path.read_bytes()).hexdigest()
    return identities


def _binary_sha256(binary: Path) -> str:
    return sha256(binary.read_bytes()).hexdigest()


def _go_version(go_binary: Path) -> str:
    run = subprocess.run([str(go_binary), "version"], capture_output=True, text=True, check=False)
    if run.returncode:
        raise RuntimeDefaultBlocked("go version invocation failed")
    return run.stdout.strip()


def build_persistent_verifier(go_binary: Path, *, qualified_source: Path, install_dir: Path) -> VerifierIdentity:
    """Build the persistent verifier from the frozen qualified V0R3 source.

    Deterministic build: explicit Go, GOPROXY=off (no network), -trimpath and
    -buildvcs=false so the binary identity depends only on the module source
    and the pinned toolchain.  Records the build identity manifest and fails
    closed on any build failure.
    """
    install_bin = install_dir / VERIFIER_BIN_RELPATH
    install_bin.parent.mkdir(parents=True, exist_ok=True)
    staged = install_bin.parent / (install_bin.name + ".building")
    env = {**os.environ, "GOPROXY": "off", "GOFLAGS": "-mod=mod"}
    build = subprocess.run(
        [str(go_binary), "build", "-trimpath", "-buildvcs=false", "-o", str(staged), "."],
        cwd=qualified_source, capture_output=True, text=True, check=False, env=env,
    )
    if build.returncode:
        raise RuntimeDefaultBlocked(f"persistent V0R3 verifier build failed: {build.stderr.strip()}")
    identity = VerifierIdentity(
        source_sha256=_source_identities(qualified_source),
        go_version=_go_version(go_binary),
        binary_sha256=_binary_sha256(staged),
    )
    (install_dir / VERIFIER_IDENTITY_RELPATH).write_text(
        json.dumps(
            {
                "source_sha256": identity.source_sha256,
                "go_version": identity.go_version,
                "binary_sha256": identity.binary_sha256,
            },
            sort_keys=True,
            indent=2,
        )
        + "\n"
    )
    staged.replace(install_bin)
    return identity


def verify_persistent_verifier_identity(
    *, qualified_source: Path, install_dir: Path
) -> VerifierIdentity:
    """Verify the persistent binary against its recorded build identity.

    Fails closed when the binary or manifest is missing, the qualified source
    files changed since the build, or the binary bytes no longer match the
    recorded build output.
    """
    binary = install_dir / VERIFIER_BIN_RELPATH
    manifest_path = install_dir / VERIFIER_IDENTITY_RELPATH
    if not binary.is_file() or not manifest_path.is_file():
        raise RuntimeDefaultBlocked(
            f"persistent V0R3 verifier or identity manifest missing under {install_dir}"
        )
    manifest = json.loads(manifest_path.read_text())
    identity = VerifierIdentity(
        source_sha256=dict(manifest["source_sha256"]),
        go_version=str(manifest["go_version"]),
        binary_sha256=str(manifest["binary_sha256"]),
    )
    if _source_identities(qualified_source) != identity.source_sha256:
        raise RuntimeDefaultBlocked(
            "persistent V0R3 verifier source identity mismatch: qualified source "
            "changed since the recorded build"
        )
    if _binary_sha256(binary) != identity.binary_sha256:
        raise RuntimeDefaultBlocked(
            "persistent V0R3 verifier binary identity mismatch: executable does not "
            "match the recorded build output"
        )
    return identity


def resolve_verifier(
    *,
    go_binary: Path | None = None,
    qualified_source: Path | None = None,
    install_dir: Path | None = None,
) -> Path:
    """Deterministic unattended verifier resolution.

    Order: explicit ``QNTYLAB_JH01_SIGSTORE_VERIFIER`` env override (must
    exist on disk), otherwise the persistent identity-proved binary under the
    deterministic install dir (built on demand from the frozen qualified
    source with GOPROXY=off).  Fails closed on any missing/mismatched
    identity or build failure.
    """
    override = os.environ.get("QNTYLAB_JH01_SIGSTORE_VERIFIER")
    if override:
        path = Path(override)
        if not path.is_file():
            raise RuntimeDefaultBlocked(
                f"QNTYLAB_JH01_SIGSTORE_VERIFIER points to a missing executable: {path}"
            )
        return path
    source = Path(qualified_source) if qualified_source is not None else Path(__file__).resolve().parent.parent / "qualifications" / "jh01_v0r3"
    directory = Path(install_dir) if install_dir is not None else VERIFIER_INSTALL_DIR
    binary = directory / VERIFIER_BIN_RELPATH
    manifest_path = directory / VERIFIER_IDENTITY_RELPATH
    if not (binary.is_file() and manifest_path.is_file()):
        build_persistent_verifier(
            resolve_go_binary(go_binary), qualified_source=source, install_dir=directory
        )
    # Always fail closed on any identity mismatch (source drift or binary
    # tampering); a present-but-mismatched binary is never rebuilt over.
    verify_persistent_verifier_identity(qualified_source=source, install_dir=directory)
    return binary


def expected_policy_bytes(expectation: recorder.AttestationExpectation) -> bytes:
    """Derive the current-origin expected policy from the online expectation.

    Exact same field mapping the frozen ``ExternalSigstoreVerifier`` writes
    for its policy file (recorder implementation, ``verify``): the policy is
    derived from the SAME publication/attestation facts used to verify the
    current release online — never from the historical canary.
    """
    return recorder.canonical_bytes(
        {
            "repository": expectation.repository,
            "repository_id": expectation.repository_id,
            "owner_id": expectation.owner_id,
            "release_id": expectation.release_id,
            "tag": expectation.tag,
            "purl": expectation.purl,
            "package_id": expectation.package_id,
            "target_commit": expectation.target_commit,
            "asset_name": expectation.asset_name,
            "asset_sha256": expectation.asset_sha256,
            "predicate_type": expectation.predicate_type,
            "signer_uri": expectation.signer_uri,
        }
    )


class ExpectationCell:
    """Captures the AttestationExpectation observed during online verify."""

    def __init__(self) -> None:
        self.captured: list[recorder.AttestationExpectation] = []


class ExpectationCapturingVerifier:
    """Passive verifier wrapper recording the expectation used online."""

    def __init__(self, delegate: recorder.AttestationVerifier, cell: ExpectationCell):
        self._delegate = delegate
        self._cell = cell

    def verify(
        self,
        *,
        asset: bytes,
        bundle: bytes,
        trusted_root: bytes,
        expectation: recorder.AttestationExpectation,
    ) -> recorder.VerifiedAttestation:
        verified = self._delegate.verify(
            asset=asset, bundle=bundle, trusted_root=trusted_root, expectation=expectation
        )
        self._cell.captured.append(expectation)
        return verified


def current_package_offline_reverify(
    root: Path,
    *,
    go_binary: Path,
    cell: ExpectationCell,
) -> OfflineReverify:
    """C-01 default: reverify the EXACT current retention package.

    The callable receives the package path handed over by
    ``Operation._record_due`` and forwards it verbatim to
    ``recorder.offline_reverify_current_package`` together with the
    expected_policy derived from the online attestation expectation.  The
    historical qualified canary is never invoked.
    """

    def offline_reverify(package: Path) -> None:
        if not cell.captured:
            raise RuntimeDefaultBlocked(
                "CURRENT_PACKAGE_OFFLINE_REVERIFY_REQUIRED: no online attestation "
                "expectation was captured for the current origin"
            )
        policy_bytes = expected_policy_bytes(cell.captured[-1])
        with tempfile.TemporaryDirectory(prefix="qntylab-jh01-expected-policy-") as temporary:
            policy_path = Path(temporary) / "expected_policy.json"
            policy_path.write_bytes(policy_bytes)
            recorder.offline_reverify_current_package(
                root, package=package, go_binary=go_binary, expected_policy=policy_path
            )

    return offline_reverify


__all__ = [
    "DEFAULT_GO_BINARY",
    "ExpectationCapturingVerifier",
    "ExpectationCell",
    "RuntimeDefaultBlocked",
    "VerifierIdentity",
    "build_persistent_verifier",
    "current_package_offline_reverify",
    "expected_policy_bytes",
    "resolve_go_binary",
    "resolve_verifier",
    "verify_persistent_verifier_identity",
]
