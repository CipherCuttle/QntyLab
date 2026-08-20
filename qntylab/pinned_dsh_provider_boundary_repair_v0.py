"""Fail-closed, source-controlled repair for the pinned DSH Codex provider.

This module materializes only the provider source boundary.  It never runs
DSH/Codex, never edits the upstream checkout, and never guesses at an
unrecognized source revision.  The generated file is the durable QntyLab
owned input to a later pinned DSH build/materialization step.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Mapping


DSH_REPOSITORY = "deepseek-ai/deepseek-harness"
DSH_COMMIT = "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
DSH_TREE = "3bc8f89fe494a4755c188be354add4e8b1e7b188"
DSH_TAG = "dsh-v0.1.0-rc.7"

PROVIDER_SOURCE_PATH = "packages/subagent/subagent-codex/src/wire.ts"
PREIMAGE_METHOD_START = "  async startThread(cwd: string, signal: AbortSignal): Promise<void> {"
PREIMAGE_METHOD_END = "\n  /**"
OLD_POLICY_LINES = "      cwd,\n      ephemeral: true,\n"
NEW_POLICY_LINES = (
    "      cwd,\n"
    "      ephemeral: true,\n"
    "      approvalPolicy: 'never',\n"
    "      sandbox: 'workspace-write',\n"
)

# These hashes bind the exact pinned source span, not merely a method name.
# The whole-file hash is also recorded in the evidence artifact.
UPSTREAM_SOURCE_SHA256 = "9d94284e578ff2253f09e10130cac4aa977e8f3e9e64d442f1ca005cb207fdbd"
UPSTREAM_PREIMAGE_SHA256 = "d3b8c0f7083c7d00b75c60c97e9353c735f1e6818495d92c1a6dcb2c9b64f4c8"
REPAIRED_POSTIMAGE_SHA256 = "4b6f9bcca0d1940085a978d7f413f456fb030f303704061e1d1a682b460ff716"

REQUIRED_THREAD_START = {
    "approvalPolicy": "never",
    "sandbox": "workspace-write",
}
PRESERVED_THREAD_START = ("cwd", "ephemeral")
FORBIDDEN_PROVIDER_FIELDS = (
    "sandboxPolicy",
    "writableRoots",
    "runtimeWorkspaceRoots",
    "networkAccess",
    "requestAttestation",
)


class ProviderBoundaryError(ValueError):
    """A pinned provider source or policy construction failed closed."""


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise ProviderBoundaryError(f"git identity query failed: {' '.join(args)}")
    return completed.stdout.strip()


def inspect_pinned_identity(root: Path) -> dict[str, Any]:
    """Read and verify the exact upstream Git identity without modifying it."""

    root = Path(root)
    if root.is_symlink() or not (root / ".git").exists():
        raise ProviderBoundaryError("pinned DSH root is missing or a symlink")
    identity = {
        "repository": DSH_REPOSITORY,
        "commit": _git(root, "rev-parse", "HEAD"),
        "tree": _git(root, "rev-parse", "HEAD^{tree}"),
        "tag": _git(root, "tag", "--points-at", "HEAD"),
        "tracked_status": _git(root, "status", "--porcelain", "--untracked-files=no"),
    }
    expected = {
        "repository": DSH_REPOSITORY,
        "commit": DSH_COMMIT,
        "tree": DSH_TREE,
        "tag": DSH_TAG,
        "tracked_status": "",
    }
    identity["matches"] = identity == expected
    if not identity["matches"]:
        raise ProviderBoundaryError("pinned DSH identity or tracked source drift")
    return identity


def _provider_path(root: Path) -> Path:
    path = Path(root) / PROVIDER_SOURCE_PATH
    if path.is_symlink() or not path.is_file():
        raise ProviderBoundaryError("provider source is missing or a symlink")
    return path


def _method_span(source: str) -> tuple[int, int, str]:
    start = source.find(PREIMAGE_METHOD_START)
    if start < 0:
        raise ProviderBoundaryError("provider startThread preimage is missing")
    end = source.find(PREIMAGE_METHOD_END, start)
    if end < 0:
        raise ProviderBoundaryError("provider startThread boundary is missing")
    span = source[start:end]
    if source.find(PREIMAGE_METHOD_START, start + 1) >= 0:
        raise ProviderBoundaryError("duplicate startThread preimage")
    return start, end, span


def _repaired_source(source: str) -> tuple[str, dict[str, Any]]:
    start, end, span = _method_span(source)
    if _sha256(span.encode("utf-8")) != UPSTREAM_PREIMAGE_SHA256:
        raise ProviderBoundaryError("provider startThread preimage digest mismatch")
    if span.count(OLD_POLICY_LINES) != 1:
        raise ProviderBoundaryError("provider policy insertion preimage is not unique")
    if any(field in span for field in REQUIRED_THREAD_START):
        raise ProviderBoundaryError("provider already contains an unexpected policy field")
    repaired_span = span.replace(OLD_POLICY_LINES, NEW_POLICY_LINES, 1)
    if _sha256(repaired_span.encode("utf-8")) != REPAIRED_POSTIMAGE_SHA256:
        raise ProviderBoundaryError("repaired provider postimage digest mismatch")
    repaired = source[:start] + repaired_span + source[end:]
    delta = [
        {"path": "thread/start.params.approvalPolicy", "before": "<ABSENT>", "after": "never"},
        {"path": "thread/start.params.sandbox", "before": "<ABSENT>", "after": "workspace-write"},
    ]
    return repaired, {
        "upstream_preimage_sha256": UPSTREAM_PREIMAGE_SHA256,
        "repaired_postimage_sha256": REPAIRED_POSTIMAGE_SHA256,
        "semantic_delta": delta,
        "semantic_delta_count": len(delta),
    }


def materialize_provider_boundary(source_root: Path, output_root: Path) -> dict[str, Any]:
    """Emit the repaired provider source into a new QntyLab-owned root."""

    source_root = Path(source_root)
    output_root = Path(output_root)
    identity = inspect_pinned_identity(source_root)
    source_path = _provider_path(source_root)
    source_bytes = source_path.read_bytes()
    if _sha256(source_bytes) != UPSTREAM_SOURCE_SHA256:
        raise ProviderBoundaryError("provider source whole-file preimage digest mismatch")
    source = source_bytes.decode("utf-8")
    repaired, patch = _repaired_source(source)
    output_path = output_root / PROVIDER_SOURCE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(repaired, encoding="utf-8", newline="")
    return {
        "schema_version": "pinned-dsh-provider-boundary-materialization-v0",
        "dsh": identity,
        "provider_source_path": PROVIDER_SOURCE_PATH,
        "upstream_source_sha256": UPSTREAM_SOURCE_SHA256,
        **patch,
        "postimage_path": str(output_path),
        "postimage_source_sha256": _sha256(output_path.read_bytes()),
        "output_is_outside_upstream": output_path.resolve() != source_path.resolve(),
    }


def captured_thread_start_contract(provider_source: Path) -> dict[str, Any]:
    """Capture the serialized permission fields from materialized source bytes."""

    source = Path(provider_source).read_text(encoding="utf-8")
    _, _, span = _method_span(source)
    if _sha256(span.encode("utf-8")) != REPAIRED_POSTIMAGE_SHA256:
        raise ProviderBoundaryError("captured provider is not the repaired postimage")
    return {
        "cwd": "<runtime cwd>",
        "ephemeral": True,
        "approvalPolicy": "never",
        "sandbox": "workspace-write",
    }


def validate_thread_start_contract(contract: Mapping[str, Any], cwd: str) -> dict[str, Any]:
    """Validate runtime policy construction and fail closed on extra/malformed fields."""

    expected = {"cwd": cwd, "ephemeral": True, **REQUIRED_THREAD_START}
    if dict(contract) != expected:
        raise ProviderBoundaryError("malformed or broadened thread/start provider contract")
    if any(field in contract for field in FORBIDDEN_PROVIDER_FIELDS):
        raise ProviderBoundaryError("forbidden provider field present")
    return dict(contract)


def semantic_repair_delta() -> list[dict[str, str]]:
    return [
        {"path": "thread/start.params.approvalPolicy", "before": "<ABSENT>", "after": "never"},
        {"path": "thread/start.params.sandbox", "before": "<ABSENT>", "after": "workspace-write"},
    ]
