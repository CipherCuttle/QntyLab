"""Narrow, read-only observation of Qnty's canonical control pointer.

This module deliberately does not import Qnty.  It validates only the active
task pointer and the receipt it names, then reports byte provenance without
interpreting continuity, authority, or next-action state.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any


QNTY_REPOSITORY_ID = "Qnty"
ACTIVE_TASK_PATH = "docs/control/active_task.json"
EXPECTED_CONTROL_KIND = "qnty_active_task_pointer"
EXPECTED_RECEIPT_KIND = "qnty_cross_agent_handoff_receipt"
RECEIPT_NAME = re.compile(r"^handoff_v[0-9]+\.json$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
REQUIRED_ACTIVE_FIELDS = (
    "task_id",
    "protocol_id",
    "phase",
    "handoff_receipt_path",
    "handoff_receipt_sha256",
)


class QntyAdapterError(ValueError):
    """A supplied Qnty root does not satisfy the narrow adapter contract."""


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _git_bytes(root: Path, *args: str, check: bool = True) -> bytes:
    environment = {key: value for key, value in os.environ.items() if not key.startswith("GIT_")}
    completed = subprocess.run(
        ["git", "--no-optional-locks", "-C", str(root), *args],
        check=False,
        capture_output=True,
        env=environment,
    )
    if check and completed.returncode:
        raise QntyAdapterError("GIT_READ_FAILED")
    return completed.stdout


def _tracked_regular_file(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts or candidate.as_posix() != relative:
        raise QntyAdapterError("PATH_NOT_REPOSITORY_RELATIVE")
    path = root / candidate
    if path.is_symlink() or not path.is_file():
        raise QntyAdapterError("PATH_NOT_REGULAR_NON_SYMLINK_FILE")
    try:
        path.resolve(strict=True).relative_to(root.resolve())
    except (OSError, ValueError) as exc:
        raise QntyAdapterError("PATH_ESCAPES_ROOT") from exc
    tracked = _git_bytes(root, "ls-files", "--error-unmatch", "--", relative, check=False).decode("utf-8", "replace").splitlines()
    if tracked != [relative]:
        raise QntyAdapterError("PATH_NOT_GIT_TRACKED")
    return path


def _load_canonical_object(path: Path, error_code: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = path.read_bytes()
        value = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QntyAdapterError(error_code) from exc
    if not isinstance(value, dict) or _canonical_json(value) != raw:
        raise QntyAdapterError(error_code)
    return value, raw


def _string_field(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise QntyAdapterError(f"ACTIVE_TASK_{field.upper()}_INVALID")
    return value


def _receipt_path(task_id: str, raw_path: Any) -> str:
    relative = _string_field(raw_path, "handoff_receipt_path")
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts or path.as_posix() != relative:
        raise QntyAdapterError("HANDOFF_PATH_NOT_REPOSITORY_RELATIVE")
    if len(path.parts) != 5 or path.parts[:3] != ("docs", "control", "tasks"):
        raise QntyAdapterError("HANDOFF_PATH_OUTSIDE_TASK_NAMESPACE")
    if path.parts[3] != task_id or not RECEIPT_NAME.fullmatch(path.name):
        raise QntyAdapterError("HANDOFF_PATH_OUTSIDE_TASK_NAMESPACE")
    return relative


def _head_binding(root: Path, compiled_inputs: list[str]) -> tuple[str, list[str]]:
    try:
        top = _git_bytes(root, "rev-parse", "--show-toplevel").decode().strip()
        head_sha = _git_bytes(root, "rev-parse", "HEAD").decode().strip()
    except (UnicodeDecodeError, QntyAdapterError) as exc:
        raise QntyAdapterError("GIT_READ_FAILED") from exc
    try:
        if Path(top).resolve() != root.resolve():
            raise QntyAdapterError("ROOT_IS_NOT_REPOSITORY_TOPLEVEL")
    except OSError as exc:
        raise QntyAdapterError("ROOT_IS_NOT_REPOSITORY_TOPLEVEL") from exc
    unbound: list[str] = []
    for relative in compiled_inputs:
        try:
            head_bytes = _git_bytes(root, "cat-file", "blob", f"HEAD:{relative}")
            worktree_bytes = (root / relative).read_bytes()
        except (OSError, QntyAdapterError) as exc:
            if isinstance(exc, QntyAdapterError) and str(exc) != "GIT_READ_FAILED":
                raise
            unbound.append(relative)
            continue
        if head_bytes != worktree_bytes:
            unbound.append(relative)
    return head_sha, unbound


def observe(root: Path) -> dict[str, Any]:
    """Return the bounded Qnty orientation packet for an explicit root."""
    root = root.resolve()
    if not root.is_dir():
        raise QntyAdapterError("ROOT_NOT_DIRECTORY")
    active_path = _tracked_regular_file(root, ACTIVE_TASK_PATH)
    active, _ = _load_canonical_object(active_path, "ACTIVE_TASK_MALFORMED")
    if active.get("control_kind") != EXPECTED_CONTROL_KIND:
        raise QntyAdapterError("ACTIVE_TASK_WRONG_CONTROL_KIND")
    for field in REQUIRED_ACTIVE_FIELDS:
        _string_field(active.get(field), field)
    task_id = active["task_id"]
    if "/" in task_id or "\\" in task_id or task_id in {".", ".."}:
        raise QntyAdapterError("ACTIVE_TASK_ID_INVALID")
    receipt_path = _receipt_path(task_id, active["handoff_receipt_path"])
    receipt_file = _tracked_regular_file(root, receipt_path)
    receipt, receipt_bytes = _load_canonical_object(receipt_file, "HANDOFF_RECEIPT_MALFORMED")
    if receipt.get("receipt_kind") != EXPECTED_RECEIPT_KIND:
        raise QntyAdapterError("HANDOFF_RECEIPT_WRONG_KIND")
    for field in ("task_id", "protocol_id", "phase"):
        if receipt.get(field) != active[field]:
            raise QntyAdapterError("HANDOFF_RECEIPT_POINTER_CONTRADICTION")
    declared_digest = active["handoff_receipt_sha256"]
    if not SHA256.fullmatch(declared_digest):
        raise QntyAdapterError("HANDOFF_DIGEST_INVALID")
    if hashlib.sha256(receipt_bytes).hexdigest() != declared_digest:
        raise QntyAdapterError("HANDOFF_DIGEST_MISMATCH")

    compiled_inputs = [ACTIVE_TASK_PATH, receipt_path]
    head_sha, unbound = _head_binding(root, compiled_inputs)
    return {
        "generated_from": {
            "canonical_git_identity": {
                "head_sha": head_sha,
                "compiled_bytes_bound_to_head_sha": not unbound,
                "compiled_inputs": compiled_inputs,
                "unbound_compiled_inputs": unbound,
            },
            "git_identity_semantics": "GIT_IDENTITY_SELECTS_BYTES_NOT_SEMANTIC_AUTHORITY",
        },
        "control_pointer": {
            "task_id": task_id,
            "protocol_id": active["protocol_id"],
            "phase": active["phase"],
            "handoff_receipt_path": receipt_path,
            "handoff_receipt_sha256": declared_digest,
        },
        "handoff_integrity": "POINTER_DIGEST_MATCH",
        "continuity_verifier_status": "NOT_EXECUTED",
        "next_action_authority": "NOT_ESTABLISHED",
    }
