"""Canonical Git provenance authentication for the Funding real-capable wrapper.

Phase ``FUNDING_INCREMENTAL_EXECUTOR_EVALUATION_PROVENANCE_REPAIR_V0``.

PR #233's hostile review (finding M-1) established that the REAL_CAPABLE
wrapper accepted a caller-supplied ``authorization_path`` and validated only
JSON field *values*, with no proof that the bytes came from canonical
QntyLab Git history.  A caller could therefore point the wrapper at an
arbitrary local JSON file.

This module is the repository-native repair.  It never trusts caller bytes,
the current ``HEAD``, a caller-provided commit, a mutable remote URL, or
self-attested JSON as the root of trust.  The root of trust is an explicitly
pinned immutable canonical commit, ``EXPECTED_CANONICAL_AUTHORIZATION_COMMIT``.
The authorization document is always read from the Git object database at
``EXPECTED_CANONICAL_AUTHORIZATION_COMMIT:<fixed path>`` -- never from ``HEAD``,
a descendant of the historical anchors, a different branch/tree, or a
worktree-local file.  A caller-supplied ``authorization_path`` is accepted
only as a redundant pointer that must ``realpath``-resolve to the exact
canonical artifact; it can never introduce bytes and can never select the
resolution commit.

The pinned commit must itself be present and resolvable, and -- when the
current checkout is newer -- an ancestor of the checked-out commit.  The two
historical QntyLab anchor commits are retained as a defence-in-depth lineage
check against the *pinned* commit, and the canonical remote URL is retained as
a contextual check only.

P1 repair (PR #238 targeted re-review): the previous revision resolved from
``HEAD:<path>`` and merely required the historical anchors to be ancestors of
``HEAD`` plus a canonical-looking ``origin`` URL.  A local clone that already
contains the old anchors could forge a descendant commit, set ``origin`` to
the expected URL, add an authorization artifact, and pass.  Pinning the
resolution commit closes that hole.

The canonical evaluation authorization artifact DOES NOT EXIST at this phase
and no commit is pinned (``EXPECTED_CANONICAL_AUTHORIZATION_COMMIT`` and
``EXPECTED_CANONICAL_AUTHORIZATION_SHA256`` are both ``None``), so
:func:`authenticate_canonical_evaluation_authorization` always fails closed
with :class:`UnauthorizedExecutionError` today for two independent reasons.
This phase creates no authorization and grants no scientific-execution
authority.

Repository-native mechanisms reused (no network service, registry, database,
or new dependency): ``git rev-parse --verify``, ``git cat-file``,
``git merge-base --is-ancestor``, ``git ls-files --error-unmatch`` and
``git config --get remote.origin.url`` -- the same plumbing already used by
``qntylab/jigsaw_funding_pressure_provenance_v0.py``,
``qntylab/qnty_context_adapter.py`` and ``qntylab/project_context.py``.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from qntylab.jigsaw_funding_pressure_incremental_forecast_value_core_v1 import (
    UnauthorizedExecutionError,
)
from qntylab.jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import (
    GOVERNING_PREREGISTRATION_DIGEST,
)

#: Canonical GitHub locator of QntyLab, in ``qnty_context_adapter`` form.
CANONICAL_REPOSITORY_LOCATOR = "github.com/CipherCuttle/QntyLab"

#: Fixed, tracked path of the canonical evaluation authorization artifact.
#: A caller cannot override which path the bytes are read from.
CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH = (
    "experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/"
    "evaluation_execution_authorization_v0/authorization.json"
)

REQUIRED_AUTHORIZATION_ARTIFACT_TYPE = (
    "FUNDING_INCREMENTAL_REAL_EVALUATION_EXECUTION_AUTHORIZATION"
)
REQUIRED_AUTHORIZATION_STATE = "CLOSED_PASS"

#: Identity of the real-capable wrapper the authorization must be bound to.
REAL_CAPABLE_WRAPPER_PROJECT_ID = (
    "JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_REAL_CAPABLE_WRAPPER_V1"
)

#: Immutable QntyLab anchor commits.  Retained as a defence-in-depth lineage
#: check: both must be ancestors of the *pinned* canonical authorization commit
#: (not merely of ``HEAD``).  An unrelated repository does not contain these
#: object IDs.  They are NOT, on their own, the root of trust any more.
PREREGISTRATION_ANCHOR_COMMIT = "d2f1839c286ec0407eefd02d878a1b16572bd902"
HISTORICAL_V0_ORACLE_ANCHOR_COMMIT = "f6f12994d65c3dfeaf7839de560e58ad99547c62"
CANONICAL_ANCHOR_COMMITS = (
    PREREGISTRATION_ANCHOR_COMMIT,
    HISTORICAL_V0_ORACLE_ANCHOR_COMMIT,
)

#: The exact immutable canonical commit the authorization artifact is resolved
#: from (``EXPECTED_CANONICAL_AUTHORIZATION_COMMIT:<fixed path>``).  This is the
#: root of trust.  It is ``None`` at this phase: no commit is pinned, so no
#: authorization -- however well formed, however canonically committed, and
#: whatever ``HEAD`` points at -- is ever accepted.  Pinning it is a reviewed
#: source change.  A caller cannot supply or override it.
EXPECTED_CANONICAL_AUTHORIZATION_COMMIT: str | None = None

#: SHA-256 of the exact canonical authorization blob bytes that a future
#: real-evaluation authorization phase will license.  It is ``None`` at this
#: phase: no digest is pinned, so no authorization -- however well formed and
#: however canonically committed -- is ever accepted.  Pinning this constant
#: is a reviewed source change and is the second key alongside the pinned
#: canonical commit.  It is what binds "the accepted bytes" to an expected
#: content digest (a file cannot carry its own hash).
EXPECTED_CANONICAL_AUTHORIZATION_SHA256: str | None = None

_FULL_SHA1 = re.compile(r"\A[0-9a-f]{40}\Z")
_REMOTE_PREFIXES = (
    "https://github.com/",
    "git@github.com:",
    "ssh://git@github.com/",
)


def _repository_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git(root: Path, *args: str, check: bool = True) -> bytes:
    """Read-only Git plumbing, failing closed on every error.

    An inherited ``GIT_DIR``/``GIT_WORK_TREE`` would silently redirect the
    read at another repository, so every ``GIT_*`` variable is dropped and
    ``-C`` is the only thing selecting the repository.  ``--no-optional-locks``
    keeps a read from rewriting ``.git/index``.
    """
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        completed = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *args],
            check=False,
            capture_output=True,
            env=environment,
        )
    except OSError as error:
        raise UnauthorizedExecutionError(
            f"git plumbing is unavailable while authenticating provenance ({args!r}): {error}"
        ) from error
    if check and completed.returncode:
        detail = completed.stderr.decode("utf-8", "replace").strip() or "git command failed"
        raise UnauthorizedExecutionError(
            f"canonical Git provenance could not be verified ({args!r}): {detail}"
        )
    return completed.stdout


def _git_text(root: Path, *args: str, check: bool = True) -> str:
    return _git(root, *args, check=check).decode("utf-8", "replace").strip()


def _git_ok(root: Path, *args: str) -> bool:
    environment = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        completed = subprocess.run(
            ["git", "--no-optional-locks", "-C", str(root), *args],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
            env=environment,
        )
    except OSError as error:
        raise UnauthorizedExecutionError(
            f"git plumbing is unavailable while authenticating provenance ({args!r}): {error}"
        ) from error
    return completed.returncode == 0


def _canonical_remote_locator(raw: str) -> str | None:
    value = raw.strip()
    suffix = next(
        (value[len(prefix):] for prefix in _REMOTE_PREFIXES if value.startswith(prefix)),
        None,
    )
    if suffix is None:
        return None
    if suffix.endswith("/"):
        suffix = suffix[:-1]
    if suffix.endswith(".git"):
        suffix = suffix[:-4]
    parts = suffix.split("/")
    if len(parts) != 2 or not all(parts):
        return None
    return f"github.com/{parts[0]}/{parts[1]}"


def _require_contextual_repository_locator(root: Path) -> None:
    """Contextual check only -- NOT the root of trust (that is the pinned commit).

    Confirms usable Git metadata and that ``origin`` looks like canonical
    QntyLab.  A mutable remote URL is deliberately not trusted to establish
    canonicality on its own; :func:`_resolve_pinned_canonical_commit` does that.
    """
    if not (root / ".git").exists():
        raise UnauthorizedExecutionError(
            f"no usable Git metadata at {root}: real evaluation provenance fails closed"
        )
    configured = _git_text(root, "config", "--get", "remote.origin.url", check=False)
    lines = [line for line in configured.splitlines() if line.strip()]
    if len(lines) != 1:
        raise UnauthorizedExecutionError(
            "canonical repository identity is unverifiable: remote.origin.url is absent or ambiguous"
        )
    if _canonical_remote_locator(lines[0]) != CANONICAL_REPOSITORY_LOCATOR:
        raise UnauthorizedExecutionError(
            "wrong repository identity: remote.origin.url does not resolve to "
            f"{CANONICAL_REPOSITORY_LOCATOR!r}"
        )


def _resolve_pinned_canonical_commit(root: Path) -> str:
    """Resolve, and fully validate, the pinned canonical resolution commit.

    The authorization is read from this commit and no other.  Fails closed
    when no commit is pinned, when the pinned object is absent or is not a
    commit, when it does not verify to an immutable object id, when it is
    neither the current checkout nor an ancestor of it, or when a historical
    anchor is not an ancestor of it.
    """
    pinned = EXPECTED_CANONICAL_AUTHORIZATION_COMMIT
    if pinned is None:
        raise UnauthorizedExecutionError(
            "no expected canonical authorization commit is pinned in the wrapper source; "
            "real execution fails closed"
        )
    if not isinstance(pinned, str) or not _FULL_SHA1.match(pinned):
        raise UnauthorizedExecutionError(
            "expected canonical authorization commit is not a full 40-hex commit id"
        )
    if _git_text(root, "cat-file", "-t", pinned, check=False) != "commit":
        raise UnauthorizedExecutionError(
            "pinned canonical authorization commit is not present or resolvable in this repository"
        )
    verified = _git_text(
        root, "rev-parse", "--verify", "--quiet", f"{pinned}^{{commit}}", check=False
    )
    if verified != pinned:
        raise UnauthorizedExecutionError(
            "pinned canonical authorization commit did not verify to an immutable commit object"
        )
    head = _git_text(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}", check=False)
    if not _FULL_SHA1.match(head):
        raise UnauthorizedExecutionError("HEAD does not resolve to a commit object")
    if head != pinned and not _git_ok(root, "merge-base", "--is-ancestor", pinned, head):
        raise UnauthorizedExecutionError(
            "pinned canonical authorization commit is neither the current checkout nor an "
            "ancestor of it; an unpinned, divergent, or forged descendant commit is refused"
        )
    for anchor in CANONICAL_ANCHOR_COMMITS:
        if _git_text(root, "cat-file", "-t", anchor, check=False) != "commit":
            raise UnauthorizedExecutionError(
                f"wrong repository identity: canonical anchor {anchor} is not a commit in this repository"
            )
        if not _git_ok(root, "merge-base", "--is-ancestor", anchor, pinned):
            raise UnauthorizedExecutionError(
                f"wrong repository identity: canonical anchor {anchor} is not an ancestor of the "
                "pinned canonical authorization commit"
            )
    return pinned


def _guard_caller_supplied_path(root: Path, authorization_path: str | Path | None) -> None:
    """Reject caller path substitution / symlink / traversal / worktree swaps.

    The parameter is redundant: it can only *point at* the canonical artifact,
    never introduce bytes.  It must ``realpath``-resolve to exactly the
    canonical tracked path.
    """
    if authorization_path is None:
        return
    expected = (root / CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH).resolve()
    try:
        supplied = Path(authorization_path).resolve()
    except OSError as error:
        raise UnauthorizedExecutionError(
            f"caller-supplied authorization_path could not be resolved: {error}"
        ) from error
    if supplied != expected:
        raise UnauthorizedExecutionError(
            "caller-supplied authorization_path does not resolve to the canonical "
            "Git-tracked evaluation authorization artifact; byte substitution is refused"
        )


def _canonical_blob(root: Path, resolution_commit: str) -> tuple[str, bytes]:
    """The authorization blob OID and bytes at the canonical path IN ``resolution_commit``.

    The tree entry is read from the pinned commit itself (``git ls-tree``), not
    from the worktree index, so a worktree-local file, a different branch, or a
    later ``HEAD`` tree cannot supply or hide it.  Fails closed when the
    artifact is absent from the pinned commit -- the permanent state today.
    """
    entry = _git_text(
        root,
        "ls-tree",
        "--full-tree",
        resolution_commit,
        "--",
        CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH,
        check=False,
    )
    if not entry:
        raise UnauthorizedExecutionError(
            "no canonical evaluation authorization exists at the pinned canonical commit "
            f"({CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH} at {resolution_commit}); "
            "real execution fails closed"
        )
    meta = entry.partition("\t")[0].split()
    if len(meta) != 3:
        raise UnauthorizedExecutionError("canonical evaluation authorization tree entry is unreadable")
    mode, kind, blob_oid = meta
    if kind != "blob" or not _FULL_SHA1.match(blob_oid):
        raise UnauthorizedExecutionError(
            "canonical evaluation authorization path does not resolve to a Git blob at the pinned commit"
        )
    if mode == "120000":
        raise UnauthorizedExecutionError(
            "canonical evaluation authorization path is a symlink in the pinned tree; "
            "a regular blob is required"
        )
    blob_bytes = _git(root, "cat-file", "blob", blob_oid, check=True)
    # The resolution is purely the pinned Git object; the worktree is never a
    # source.  As a defence-in-depth tamper signal, when the checkout is
    # exactly AT the pinned commit the on-disk copy must match it (a worktree
    # ahead of the pinned commit legitimately differs and is not checked).
    canonical_path = root / CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH
    head = _git_text(root, "rev-parse", "--verify", "--quiet", "HEAD^{commit}", check=False)
    if head == resolution_commit:
        if canonical_path.is_symlink():
            raise UnauthorizedExecutionError(
                "canonical evaluation authorization path is a symlink in the worktree; "
                "a regular tracked blob is required"
            )
        if canonical_path.is_file() and canonical_path.read_bytes() != blob_bytes:
            raise UnauthorizedExecutionError(
                "worktree copy of the canonical evaluation authorization diverges from the pinned "
                "canonical Git blob; worktree-local replacement is refused"
            )
    return blob_oid, blob_bytes


def _parse_authorization(blob_bytes: bytes) -> dict[str, Any]:
    try:
        document = json.loads(blob_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise UnauthorizedExecutionError(
            f"canonical evaluation authorization is malformed: {error}"
        ) from error
    if not isinstance(document, dict):
        raise UnauthorizedExecutionError(
            "canonical evaluation authorization must be a JSON object"
        )
    return document


def _require_field_bindings(document: dict[str, Any]) -> None:
    if document.get("artifact_type") != REQUIRED_AUTHORIZATION_ARTIFACT_TYPE:
        raise UnauthorizedExecutionError(
            "canonical evaluation authorization artifact_type mismatch: expected "
            f"{REQUIRED_AUTHORIZATION_ARTIFACT_TYPE!r}, got {document.get('artifact_type')!r}"
        )
    if document.get("state") != REQUIRED_AUTHORIZATION_STATE:
        raise UnauthorizedExecutionError(
            f"canonical evaluation authorization is not {REQUIRED_AUTHORIZATION_STATE}: "
            f"got {document.get('state')!r}"
        )
    if document.get("scientific_execution_authorized") is not True:
        raise UnauthorizedExecutionError(
            "canonical evaluation authorization does not grant scientific execution authority"
        )
    if document.get("governing_preregistration_digest") != GOVERNING_PREREGISTRATION_DIGEST:
        raise UnauthorizedExecutionError(
            "canonical evaluation authorization is not bound to the frozen preregistration digest"
        )
    if document.get("real_capable_wrapper_project_id") != REAL_CAPABLE_WRAPPER_PROJECT_ID:
        raise UnauthorizedExecutionError(
            "canonical evaluation authorization is not bound to this real-capable wrapper"
        )


def _require_self_attested_git_binding(document: dict[str, Any]) -> None:
    """The artifact must self-attest to the canonical identity it was authored for.

    The commit and blob digest are proven *independently* by the Git
    resolution above and cannot be restated by the artifact (a file cannot
    contain its own object hash).  What the artifact can and must carry is the
    repository locator, the fixed artifact path, and the immutable anchor
    commit set it was authored against -- so a document authored for a
    different repository, path, or anchor lineage is refused.
    """
    binding = document.get("canonical_git_binding")
    if not isinstance(binding, dict):
        raise UnauthorizedExecutionError(
            "canonical evaluation authorization is missing its canonical_git_binding"
        )
    expected = {
        "repository": CANONICAL_REPOSITORY_LOCATOR,
        "artifact_path": CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH,
        "preregistration_anchor_commit": PREREGISTRATION_ANCHOR_COMMIT,
        "historical_v0_oracle_anchor_commit": HISTORICAL_V0_ORACLE_ANCHOR_COMMIT,
    }
    for key, want in expected.items():
        if binding.get(key) != want:
            raise UnauthorizedExecutionError(
                f"canonical_git_binding.{key} mismatch: expected {want!r}, got {binding.get(key)!r}"
            )


def authenticate_canonical_evaluation_authorization(
    authorization_path: str | Path | None = None,
    *,
    root: Path | None = None,
) -> dict[str, Any]:
    """Authenticate the canonical evaluation authorization to QntyLab Git identity.

    Fails closed with :class:`UnauthorizedExecutionError` on: no pinned commit,
    a pinned commit that is absent / not a commit / not an ancestor of the
    current checkout, a forged or divergent descendant commit, caller path
    substitution, symlink/traversal, wrong repository, wrong tree/blob, wrong
    artifact path, modified bytes, worktree-local replacement, a missing
    canonical artifact at the pinned commit, malformed authorization, and a
    mismatched preregistration or wrapper identity.  No claim, evidence,
    ``ForecastRow``, shared core or result recording is touched here.

    Returns the parsed authorization document (augmented with an
    independently computed ``_canonical_git_provenance`` receipt) only when
    every check passes.  It never passes at this phase.
    """
    resolved_root = (root or _repository_root()).resolve()
    _guard_caller_supplied_path(resolved_root, authorization_path)
    _require_contextual_repository_locator(resolved_root)
    resolution_commit = _resolve_pinned_canonical_commit(resolved_root)
    blob_oid, blob_bytes = _canonical_blob(resolved_root, resolution_commit)
    blob_sha256 = hashlib.sha256(blob_bytes).hexdigest()
    if EXPECTED_CANONICAL_AUTHORIZATION_SHA256 is None:
        raise UnauthorizedExecutionError(
            "no expected canonical authorization digest is pinned in the wrapper source; "
            "real execution fails closed"
        )
    if blob_sha256 != EXPECTED_CANONICAL_AUTHORIZATION_SHA256:
        raise UnauthorizedExecutionError(
            "canonical evaluation authorization bytes do not match the pinned content digest; "
            "modified authorization bytes are refused"
        )
    document = _parse_authorization(blob_bytes)
    _require_field_bindings(document)
    _require_self_attested_git_binding(document)
    document["_canonical_git_provenance"] = {
        "authenticated": True,
        "repository": CANONICAL_REPOSITORY_LOCATOR,
        "resolution_commit": resolution_commit,
        "pinned_commit": resolution_commit,
        "artifact_path": CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH,
        "blob_sha1": blob_oid,
        "blob_sha256": blob_sha256,
        "anchor_commits": list(CANONICAL_ANCHOR_COMMITS),
    }
    return document


def canonical_authorization_exists(*, root: Path | None = None) -> bool:
    """True only when a canonical authorization blob is present at the pinned commit.

    Deterministic, offline, side-effect free.  ``False`` at this phase (no
    commit is pinned).
    """
    if EXPECTED_CANONICAL_AUTHORIZATION_COMMIT is None:
        return False
    resolved_root = (root or _repository_root()).resolve()
    try:
        _require_contextual_repository_locator(resolved_root)
        pinned = _resolve_pinned_canonical_commit(resolved_root)
        entry = _git_text(
            resolved_root,
            "ls-tree",
            "--full-tree",
            pinned,
            "--",
            CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH,
            check=False,
        )
    except UnauthorizedExecutionError:
        return False
    return bool(entry)


__all__ = [
    "CANONICAL_ANCHOR_COMMITS",
    "CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH",
    "CANONICAL_REPOSITORY_LOCATOR",
    "EXPECTED_CANONICAL_AUTHORIZATION_COMMIT",
    "EXPECTED_CANONICAL_AUTHORIZATION_SHA256",
    "HISTORICAL_V0_ORACLE_ANCHOR_COMMIT",
    "PREREGISTRATION_ANCHOR_COMMIT",
    "REAL_CAPABLE_WRAPPER_PROJECT_ID",
    "REQUIRED_AUTHORIZATION_ARTIFACT_TYPE",
    "REQUIRED_AUTHORIZATION_STATE",
    "authenticate_canonical_evaluation_authorization",
    "canonical_authorization_exists",
]
