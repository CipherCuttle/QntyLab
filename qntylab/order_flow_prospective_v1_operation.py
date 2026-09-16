"""Order Flow Prospective V1 canonical runtime shim.

This module preserves the previously qualified operation implementation as an
exact pinned Git blob and applies one bounded runtime repair: draft GitHub
release lookup falls back to the authenticated release listing when the
published-only tag endpoint returns 404.

All scientific/source/recorder semantics remain delegated to the frozen base
implementation.
"""
from __future__ import annotations

from hashlib import sha1
from pathlib import Path
import sys

_BASE_BLOB_SHA = "554319c26b9cae1f09b3d8ca107ca9f46ebf0720"
_BASE_PATH = Path(__file__).with_name("order_flow_prospective_v1_operation_base.py")


def _git_blob_sha(path: Path) -> str:
    payload = path.read_bytes()
    header = f"blob {len(payload)}\0".encode("ascii")
    return sha1(header + payload).hexdigest()


actual_base_sha = _git_blob_sha(_BASE_PATH)
if actual_base_sha != _BASE_BLOB_SHA:
    raise RuntimeError(
        "pinned Order Flow V1 operation base blob mismatch: "
        f"{actual_base_sha} != {_BASE_BLOB_SHA}"
    )

from . import order_flow_prospective_v1_operation_base as _base


_original_release_snapshot = _base._release_snapshot


def _release_snapshot(tag: str):
    release = _original_release_snapshot(tag)
    if release is not None:
        return release

    matches = [
        candidate
        for candidate in _base._list_evidence_releases()
        if candidate.get("tag_name") == tag
    ]
    if len(matches) > 1:
        raise _base.OperationBlocked("multiple evidence releases exist for one tag")
    return matches[0] if matches else None


_base._release_snapshot = _release_snapshot

if __name__ == "__main__":
    raise SystemExit(_base.main())

# Preserve import compatibility and monkeypatch behavior for the existing test
# suite by returning the patched base module object to normal importers.
sys.modules[__name__] = _base
