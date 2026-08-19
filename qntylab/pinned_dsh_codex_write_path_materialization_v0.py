"""Bounded contract for PINNED_DSH_CODEX_WRITE_PATH_MATERIALIZATION_V0.

This phase resolves exactly one missing observation left by the predecessor
diagnostic (PR #135): whether the *exact pinned* DeepSeek Harness Codex
provider can mechanically perform a bounded synthetic workspace write with
subscription-backed Codex Profile A.

The predecessor recorded ``D4 = INCONCLUSIVE_INFRA`` for the single reason
``PINNED_DSH_BUILD_OUTPUT_UNAVAILABLE``: the pinned DSH worktree was never
built, so ``lib/`` (gitignored) did not exist and module resolution failed
before the target mechanism was reached.

Everything here is deterministic and byte-driven.  Assistant prose never
decides a gate.  There is exactly one live attempt and no retry construct.
"""

from __future__ import annotations

import os
import re
import subprocess
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from qntylab.subscription_backed_product_execution_plumbing_v0 import (
    API_KEY_NAMES,
    QualificationError,
    sha256_file,
)

PHASE_ID = "PINNED_DSH_CODEX_WRITE_PATH_MATERIALIZATION_V0"

# ---------------------------------------------------------------------------
# Pinned upstream DSH identity.  These are the phase contract, not defaults.
# ---------------------------------------------------------------------------

DSH_REPOSITORY = "deepseek-ai/deepseek-harness"
DSH_COMMIT = "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
DSH_TREE = "3bc8f89fe494a4755c188be354add4e8b1e7b188"
DSH_TAG = "dsh-v0.1.0-rc.7"
DSH_PACKAGE_VERSION = "0.1.0-rc.7"
DSH_PACKAGE_MANAGER = "pnpm@11.7.0"
DSH_BUILD_TARGET = "build:lib"

#: Node engine range declared by the pinned ``package.json``.
DSH_NODE_ENGINES = "^22.19.0 || >=24.0.0"

#: Exactly the generated runtime entrypoints the frozen D4 driver imports.
REQUIRED_RUNTIME_ARTIFACTS: tuple[str, ...] = (
    "vendor/cordis/lib/index.js",
    "packages/subagent/subagent/lib/index.js",
    "packages/subprocess/subprocess-local/lib/index.js",
    "packages/subagent/subagent-codex/lib/index.js",
)

#: SHA-256 of the artifacts produced by the recorded reproducible build of the
#: pinned source.  These bind *execution* to *verification*: `lib/` is
#: gitignored, so the clean-tracked-tree check cannot see these bytes and a
#: stale or tampered `lib/` would otherwise satisfy a mere existence test.
#: They are this phase's own build attestation, not an upstream-published one.
REQUIRED_ARTIFACT_SHA256: Mapping[str, str] = {
    "vendor/cordis/lib/index.js": "1729cdbf8ee40b17c8839e06bf96491490548559e11ef7e411271e0754e751c5",
    "packages/subagent/subagent/lib/index.js": "510aba14f13d1a9deccf3d81d790be3e7ebcdc4797fcfa584908350d07c529c6",
    "packages/subprocess/subprocess-local/lib/index.js": "e16ecbcce0fa3d60234a8a1ca3de80fa29d850ba1513bf9e8e6daa186e526ce4",
    "packages/subagent/subagent-codex/lib/index.js": "2b65fd97f345d346319423a40cb285026c263be565e29e5dce0872e4aa5aa72a",
}

#: SHA-256 of the pinned ``pnpm-lock.yaml``, re-verified at live-run time.
LOCKFILE_SHA256 = "f517dc3978d57531cda747df62a2abdde1df5b9f25415fcf1fc5d51f8b7547ea"

ARTIFACT_HASH_KEYS: Mapping[str, str] = {
    "vendor/cordis/lib/index.js": "CORDIS_LIB_SHA256",
    "packages/subagent/subagent/lib/index.js": "SUBAGENT_LIB_SHA256",
    "packages/subprocess/subprocess-local/lib/index.js": "SUBPROCESS_LOCAL_LIB_SHA256",
    "packages/subagent/subagent-codex/lib/index.js": "SUBAGENT_CODEX_LIB_SHA256",
}

# ---------------------------------------------------------------------------
# Frozen predecessor driver identity (PR #135).  Reused, never edited.
# ---------------------------------------------------------------------------

D4_DRIVER_RELPATH = (
    "experiments/research/qnty_agent_orchestration_control_contract_v0/"
    "subscription_backed_codex_app_server_write_path_diagnostic_v0/"
    "pinned_dsh_codex_route_driver_v0.mjs"
)
D4_DRIVER_BLOB = "64336748769ed8a4a4bf8a1f2f44d6e493568ab5"
D4_DRIVER_SHA256 = "e29c1bb891e6ae2040dff1ac240e33dd84f1da34b5fdaa68dd437c097ced5b94"

# ---------------------------------------------------------------------------
# Product identity.
# ---------------------------------------------------------------------------

CODEX_BINARY = "/home/swirky/.local/bin/codex"
CODEX_VERSION = "codex-cli 0.147.0"
CODEX_HOME = "/home/swirky/.codex"

PREDECESSOR_MASTER_SHA = "b909bb7dddebb17247ac3101e045387f9ecd69e9"
PR134_HEAD = "e24b540900ef9fcf48e24e8e53dbf2b18028f5d9"
PR135_HEAD = "d104342a62bc3e315d3434d16013862de529ca70"

#: One live attempt, hard-bounded.  No retry construct exists in this phase.
D4_TURN_TIMEOUT_SECONDS = 300.0
D4_DRIVER_TIMEOUT_SECONDS = D4_TURN_TIMEOUT_SECONDS + 60.0
MAX_LIVE_ATTEMPTS = 1

# ---------------------------------------------------------------------------
# Closed classification vocabularies.
# ---------------------------------------------------------------------------

MATERIALIZATION_FAILURE_CLASSES: tuple[str, ...] = (
    "PINNED_DSH_DEPENDENCY_INSTALL_FAILURE",
    "PINNED_DSH_NODE_VERSION_MISMATCH",
    "PINNED_DSH_PACKAGE_MANAGER_MISMATCH",
    "PINNED_DSH_BUILD_FAILURE",
    "PINNED_DSH_RUNTIME_ARTIFACT_MISSING",
    "PINNED_DSH_RUNTIME_ARTIFACT_DRIFT",
    "PINNED_DSH_SOURCE_MUTATION_REQUIRED",
    "PINNED_DSH_OTHER_MATERIALIZATION_FAILURE",
)

D4_FAILURE_MECHANISMS: tuple[str, ...] = (
    "DSH_CODEX_STARTUP_FAILURE",
    "DSH_CODEX_PROTOCOL_FAILURE",
    "DSH_CODEX_TURN_TIMEOUT",
    "DSH_CODEX_TURN_ERROR",
    "DSH_CODEX_COMPLETED_NO_WRITE",
    "DSH_CODEX_WRITE_ATTEMPT_FAILED",
    "DSH_EFFECTIVE_CONFIG_DIVERGENCE",
    "DSH_OTHER_OBSERVED_PRODUCT_DIVERGENCE",
    "UNKNOWN_WITH_TRACE",
)

D4_RESULTS: tuple[str, ...] = ("PASS", "FAIL", "INCONCLUSIVE_INFRA")

ALLOWED_VERDICTS: tuple[str, ...] = (
    "PINNED_DSH_CODEX_WRITE_PATH_PASS",
    "PINNED_DSH_CODEX_WRITE_PATH_FAIL",
    "PINNED_DSH_MATERIALIZATION_BLOCKED",
    "BLOCKED_BY_IDENTITY_DRIFT",
    "BLOCKED_BY_AUTHORITY_CONFLICT",
)

#: The one path the live write is permitted to change.
ALLOWED_CHANGED_PATHS: tuple[str, ...] = ("fixture.txt",)


# ---------------------------------------------------------------------------
# Toolchain gates.
# ---------------------------------------------------------------------------


def _semver(text: str) -> tuple[int, int, int] | None:
    match = re.match(r"^v?(\d+)\.(\d+)\.(\d+)", text.strip())
    if match is None:
        return None
    return (int(match.group(1)), int(match.group(2)), int(match.group(3)))


def node_version_satisfies(version: str) -> bool:
    """Honour the pinned ``^22.19.0 || >=24.0.0`` engine range exactly."""

    parsed = _semver(version)
    if parsed is None:
        return False
    major, minor, patch = parsed
    if major == 22:
        return (minor, patch) >= (19, 0)
    return major >= 24


def pnpm_version_satisfies(version: str) -> bool:
    """The pinned ``packageManager`` is exact; a newer pnpm is a mismatch."""

    return version.strip() == DSH_PACKAGE_MANAGER.split("@", 1)[1]


# ---------------------------------------------------------------------------
# DSH build identity.
# ---------------------------------------------------------------------------


def _git(root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    return completed.stdout.strip()


def dsh_identity(root: Path) -> dict[str, Any]:
    """Observe the DSH checkout identity; never assert it from a declaration."""

    root = Path(root)
    if not (root / ".git").exists():
        return {
            "root": str(root),
            "present": False,
            "commit": "",
            "tree": "",
            "tag": "",
            "tracked_modified_count": None,
            "matches": False,
        }
    commit = _git(root, "rev-parse", "HEAD")
    tree = _git(root, "rev-parse", "HEAD^{tree}")
    tag = _git(root, "tag", "--points-at", "HEAD")
    dirty = _git(root, "status", "--porcelain", "--untracked-files=no")
    tracked_modified = [line for line in dirty.splitlines() if line.strip()]
    return {
        "root": str(root),
        "present": True,
        "commit": commit,
        "tree": tree,
        "tag": tag,
        "tracked_modified_count": len(tracked_modified),
        "tracked_modified_paths": [line[3:] for line in tracked_modified[:20]],
        "matches": (
            commit == DSH_COMMIT
            and tree == DSH_TREE
            and tag == DSH_TAG
            and not tracked_modified
        ),
    }


def runtime_artifact_hashes(root: Path) -> dict[str, str | None]:
    """SHA-256 of each generated runtime entrypoint, or ``None`` when absent."""

    root = Path(root)
    result: dict[str, str | None] = {}
    for relpath in REQUIRED_RUNTIME_ARTIFACTS:
        path = root / relpath
        result[relpath] = sha256_file(path) if path.is_file() else None
    return result


def runtime_artifacts_present(hashes: Mapping[str, str | None]) -> bool:
    return all(hashes.get(relpath) for relpath in REQUIRED_RUNTIME_ARTIFACTS)


def runtime_artifact_drift(hashes: Mapping[str, str | None]) -> list[str]:
    """Paths whose present bytes differ from the pinned build attestation."""

    return sorted(
        relpath
        for relpath, expected in REQUIRED_ARTIFACT_SHA256.items()
        if hashes.get(relpath) is not None and hashes.get(relpath) != expected
    )


def classify_materialization(
    identity: Mapping[str, Any],
    hashes: Mapping[str, str | None],
    *,
    node_version: str,
    pnpm_version: str,
    install_ok: bool,
    build_ok: bool,
    lockfile_unchanged: bool,
) -> dict[str, Any]:
    """Fail closed with exactly one taxonomy class, or report materialized.

    Order matters: a toolchain mismatch is reported ahead of the build failure
    it would have caused, so a build failure is never misattributed.
    """

    failure: str | None = None
    if not node_version_satisfies(node_version):
        failure = "PINNED_DSH_NODE_VERSION_MISMATCH"
    elif not pnpm_version_satisfies(pnpm_version):
        failure = "PINNED_DSH_PACKAGE_MANAGER_MISMATCH"
    elif not install_ok or not lockfile_unchanged:
        failure = "PINNED_DSH_DEPENDENCY_INSTALL_FAILURE"
    elif identity.get("tracked_modified_count"):
        failure = "PINNED_DSH_SOURCE_MUTATION_REQUIRED"
    elif not build_ok:
        failure = "PINNED_DSH_BUILD_FAILURE"
    elif not runtime_artifacts_present(hashes):
        failure = "PINNED_DSH_RUNTIME_ARTIFACT_MISSING"
    elif runtime_artifact_drift(hashes):
        failure = "PINNED_DSH_RUNTIME_ARTIFACT_DRIFT"
    elif not identity.get("matches"):
        failure = "PINNED_DSH_OTHER_MATERIALIZATION_FAILURE"

    return {
        "materialized": failure is None,
        "failure_class": failure,
        "node_version": node_version,
        "pnpm_version": pnpm_version,
        "dependency_install": "FROZEN_LOCKFILE_OK" if install_ok else "FAILED",
        "lockfile_unchanged": bool(lockfile_unchanged),
        "build": "OK" if build_ok else "FAILED",
        "build_target": DSH_BUILD_TARGET,
        "tracked_source_mutation": bool(identity.get("tracked_modified_count")),
        "runtime_artifacts_present": runtime_artifacts_present(hashes),
        "runtime_artifact_drift": runtime_artifact_drift(hashes),
        "runtime_artifact_hashes": dict(hashes),
        "runtime_artifact_expected_hashes": dict(REQUIRED_ARTIFACT_SHA256),
    }


# ---------------------------------------------------------------------------
# Frozen driver + product identity gates.
# ---------------------------------------------------------------------------


def driver_identity(path: Path) -> dict[str, Any]:
    path = Path(path)
    if not path.is_file():
        return {"path": str(path), "present": False, "sha256": None, "matches": False}
    digest = sha256_file(path)
    return {
        "path": str(path),
        "present": True,
        "sha256": digest,
        "expected_sha256": D4_DRIVER_SHA256,
        "expected_blob": D4_DRIVER_BLOB,
        "matches": digest == D4_DRIVER_SHA256,
    }


def codex_identity(binary: str = CODEX_BINARY) -> dict[str, Any]:
    if not Path(binary).exists():
        return {
            "binary": binary,
            "present": False,
            "version_observed": "",
            "version_expected": CODEX_VERSION,
            "matches": False,
            "codex_home": CODEX_HOME,
            "codex_home_present": Path(CODEX_HOME).is_dir(),
        }
    observed = subprocess.run(
        [binary, "--version"], capture_output=True, text=True, check=False
    ).stdout.strip()
    return {
        "binary": binary,
        "present": True,
        "version_observed": observed,
        "version_expected": CODEX_VERSION,
        "matches": observed == CODEX_VERSION,
        "codex_home": CODEX_HOME,
        "codex_home_present": Path(CODEX_HOME).is_dir(),
    }


def api_key_gate(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Presence only.  Values are never read, compared, or recorded."""

    source = os.environ if environ is None else environ
    presence = {name: bool(source.get(name)) for name in API_KEY_NAMES}
    return {"presence": presence, "passed": not any(presence.values())}


def identity_gate(
    *,
    dsh: Mapping[str, Any],
    driver: Mapping[str, Any],
    codex: Mapping[str, Any],
    keys: Mapping[str, Any],
) -> dict[str, Any]:
    """Every identity binding must hold before any live product call."""

    reasons: list[str] = []
    if not dsh.get("matches"):
        reasons.append("DSH_IDENTITY_DRIFT")
    if not driver.get("matches"):
        reasons.append("D4_DRIVER_DRIFT")
    if not codex.get("matches"):
        reasons.append("CODEX_IDENTITY_DRIFT")
    if not codex.get("codex_home_present"):
        reasons.append("CODEX_HOME_ABSENT")
    if not keys.get("passed"):
        reasons.append("PAY_PER_TOKEN_CREDENTIAL_PRESENT")
    return {"passed": not reasons, "reasons": reasons}


# ---------------------------------------------------------------------------
# Live D4 classification.
# ---------------------------------------------------------------------------

_TERMINAL_ABSENT = {None, "", "missing"}
D4_ROUTE_MARKER = "D4_PINNED_DSH_CODEX_PROVIDER"
#: Codex `auth.json` mode that means the turn is billed to the subscription.
SUBSCRIPTION_AUTH_MODE = "chatgpt"
_PROTOCOL_MARKERS = ("protocol", "jsonrpc", "json-rpc", "malformed", "handshake", "initialize")
_STARTUP_MARKERS = ("spawn", "enoent", "not found", "start failed", "exited", "launch")


def codex_child_spawned(descendants: Sequence[Mapping[str, Any]]) -> bool:
    """True only when a real ``codex app-server`` descendant process was seen."""

    for entry in descendants:
        argv = entry.get("argv") or []
        if not argv:
            continue
        if Path(str(argv[0])).name != "codex":
            continue
        if "app-server" in [str(part) for part in argv[1:]]:
            return True
    return False


def receipt_integrity(receipt: Mapping[str, Any]) -> list[str]:
    """Fail-closed reasons a receipt cannot support a PASS, whatever it says.

    A `completed` stop reason is necessary but never sufficient: the driver
    can report a completed turn alongside a disposal error, a non-zero exit,
    or -- the load-bearing one -- a parent LLM that was supposed to be absent.
    """

    reasons: list[str] = []
    if receipt.get("route") != D4_ROUTE_MARKER:
        reasons.append("RECEIPT_IS_NOT_A_D4_ROUTE_RECEIPT")
    if receipt.get("parentLlmProvider", "NONE") != "NONE":
        reasons.append("DSH_PARENT_LLM_ACTIVE")
    if receipt.get("parentLlmRequestCount", 0) != 0:
        reasons.append("DSH_PARENT_LLM_REQUESTS_NONZERO")
    if receipt.get("status") != "COMPLETED":
        reasons.append("RECEIPT_STATUS_NOT_COMPLETED")
    if receipt.get("error"):
        reasons.append("RECEIPT_CARRIES_ERROR")
    if receipt.get("bridgeExitCode") not in (0, None):
        reasons.append("DRIVER_EXIT_CODE_NONZERO")
    presence = receipt.get("apiKeyPresence")
    if isinstance(presence, Mapping) and any(presence.values()):
        reasons.append("PAY_PER_TOKEN_CREDENTIAL_PRESENT_IN_DRIVER_ENV")
    return reasons


def _stop_reasons(receipt: Mapping[str, Any]) -> list[Any]:
    lifecycle = receipt.get("lifecycle")
    ends = lifecycle.get("ends") if isinstance(lifecycle, Mapping) else None
    if not isinstance(ends, list):
        return []
    return [end.get("stopReason") for end in ends if isinstance(end, Mapping)]


def classify_d4(
    *,
    materialization: Mapping[str, Any],
    identity: Mapping[str, Any],
    receipt: Mapping[str, Any] | None,
    descendants: Sequence[Mapping[str, Any]],
    fixture_before_class: str,
    fixture_after_class: str,
    changed: Sequence[str],
    profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the single machine classification for the one live D4 attempt.

    A filesystem effect never upgrades a lifecycle that did not complete, and
    a completed lifecycle never substitutes for the byte evidence.
    """

    evidence: dict[str, Any] = {
        "dsh_provider_entered": False,
        "codex_child_spawned": False,
        "turn_started": False,
        "turn_terminal_observed": False,
        "dsh_stop_reason": None,
        "timed_out": False,
        "changed_paths": list(changed),
        "fixture_target_match": fixture_before_class == "BEFORE" and fixture_after_class == "AFTER",
        "unauthorized_writes": sorted(set(changed) - set(ALLOWED_CHANGED_PATHS)),
        "filesystem_effect_observed": fixture_after_class == "AFTER",
    }

    if not materialization.get("materialized"):
        return {
            **evidence,
            "d4": "INCONCLUSIVE_INFRA",
            "target_mechanism_exercised": False,
            "reason": materialization.get("failure_class")
            or "PINNED_DSH_OTHER_MATERIALIZATION_FAILURE",
            "failure_mechanism": None,
        }
    if not identity.get("passed"):
        return {
            **evidence,
            "d4": "INCONCLUSIVE_INFRA",
            "target_mechanism_exercised": False,
            "reason": "IDENTITY_GATE_FAILED:" + ",".join(identity.get("reasons") or []),
            "failure_mechanism": None,
        }
    if receipt is None:
        return {
            **evidence,
            "d4": "INCONCLUSIVE_INFRA",
            "target_mechanism_exercised": False,
            "reason": "D4_DRIVER_PRODUCED_NO_RECEIPT",
            "failure_mechanism": None,
        }

    infra = receipt.get("inconclusiveInfra")
    if infra:
        return {
            **evidence,
            "d4": "INCONCLUSIVE_INFRA",
            "target_mechanism_exercised": False,
            "reason": str(infra),
            "failure_mechanism": None,
        }

    stop_reasons = _stop_reasons(receipt)
    stop_reason = stop_reasons[0] if stop_reasons else None
    timed_out = bool(receipt.get("timedOut"))
    spawned = codex_child_spawned(descendants)
    terminal = stop_reason not in _TERMINAL_ABSENT and not timed_out
    error_text = str(receipt.get("error") or "").lower()
    integrity = receipt_integrity(receipt)
    profile = dict(profile or {})

    evidence.update(
        {
            # Only a genuine D4 route receipt proves the pinned modules
            # resolved; a receipt synthesized by the harness does not.
            "dsh_provider_entered": receipt.get("route") == D4_ROUTE_MARKER,
            "codex_child_spawned": spawned,
            "turn_started": spawned or stop_reason not in _TERMINAL_ABSENT,
            "turn_terminal_observed": terminal,
            "dsh_stop_reason": stop_reason,
            "all_stop_reasons": stop_reasons,
            "timed_out": timed_out,
            "receipt_integrity_reasons": integrity,
            "profile_observation": profile,
        }
    )

    # Every recorded end must be `completed`; a trailing error end never
    # inherits the first end's success.
    completed = (
        bool(stop_reasons)
        and all(reason == "completed" for reason in stop_reasons)
        and not timed_out
        and not integrity
    )
    clean_write = (
        evidence["fixture_target_match"]
        and list(changed) == list(ALLOWED_CHANGED_PATHS)
        and not evidence["unauthorized_writes"]
    )

    if spawned and completed and clean_write:
        return {
            **evidence,
            "d4": "PASS",
            "target_mechanism_exercised": True,
            "reason": "PINNED_DSH_CODEX_PROVIDER_PERFORMED_BOUNDED_WRITE",
            "failure_mechanism": None,
        }

    if integrity and evidence["dsh_provider_entered"]:
        # A receipt that cannot support a PASS is classified by *why*.
        if "DSH_PARENT_LLM_ACTIVE" in integrity or "DSH_PARENT_LLM_REQUESTS_NONZERO" in integrity:
            mechanism = "DSH_EFFECTIVE_CONFIG_DIVERGENCE"
        elif not spawned:
            mechanism = "DSH_CODEX_STARTUP_FAILURE"
        elif timed_out:
            mechanism = "DSH_CODEX_TURN_TIMEOUT"
        elif any(marker in error_text for marker in _PROTOCOL_MARKERS):
            mechanism = "DSH_CODEX_PROTOCOL_FAILURE"
        elif profile.get("workspace_trusted") is False and not evidence["filesystem_effect_observed"]:
            # DSH's provider sends no approval/sandbox policy on `thread/start`,
            # unlike the D2/D3 routes.  An untrusted workspace plus no write is
            # a configuration divergence, not an unexplained product error.
            mechanism = "DSH_EFFECTIVE_CONFIG_DIVERGENCE"
        elif any(marker in error_text for marker in _STARTUP_MARKERS):
            mechanism = "DSH_CODEX_STARTUP_FAILURE"
        else:
            mechanism = "DSH_CODEX_TURN_ERROR"
    elif not spawned:
        mechanism = (
            "DSH_CODEX_STARTUP_FAILURE"
            if error_text or not terminal
            else "UNKNOWN_WITH_TRACE"
        )
    elif timed_out:
        mechanism = "DSH_CODEX_TURN_TIMEOUT"
    elif completed and not evidence["filesystem_effect_observed"]:
        mechanism = (
            "DSH_EFFECTIVE_CONFIG_DIVERGENCE"
            if profile.get("workspace_trusted") is False
            else "DSH_CODEX_COMPLETED_NO_WRITE"
        )
    elif completed and not clean_write:
        mechanism = "DSH_CODEX_WRITE_ATTEMPT_FAILED"
    elif any(marker in error_text for marker in _PROTOCOL_MARKERS):
        mechanism = "DSH_CODEX_PROTOCOL_FAILURE"
    elif any(marker in error_text for marker in _STARTUP_MARKERS):
        mechanism = "DSH_CODEX_STARTUP_FAILURE"
    elif error_text or stop_reason not in _TERMINAL_ABSENT:
        # A terminal stop reason that is not `completed` is a turn error, and
        # a driver-reported error is one even when a stop reason is missing.
        mechanism = "DSH_CODEX_TURN_ERROR"
    else:
        mechanism = "UNKNOWN_WITH_TRACE"

    return {
        **evidence,
        "d4": "FAIL",
        # DSH's own provider code ran; the mechanism was exercised and lost.
        "target_mechanism_exercised": True,
        "reason": mechanism,
        "failure_mechanism": mechanism,
    }


def phase_verdict(classification: Mapping[str, Any]) -> str:
    result = classification.get("d4")
    if result == "PASS":
        return "PINNED_DSH_CODEX_WRITE_PATH_PASS"
    if result == "FAIL":
        return "PINNED_DSH_CODEX_WRITE_PATH_FAIL"
    if result == "INCONCLUSIVE_INFRA":
        reason = str(classification.get("reason") or "")
        if reason.startswith("IDENTITY_GATE_FAILED"):
            return "BLOCKED_BY_IDENTITY_DRIFT"
        return "PINNED_DSH_MATERIALIZATION_BLOCKED"
    if result is None:
        raise QualificationError("classification is missing a D4 result")
    raise QualificationError(f"unknown D4 result: {result!r}")


def downstream_authority(classification: Mapping[str, Any]) -> dict[str, Any]:
    """A PASS is execution plumbing evidence only.  It authorizes nothing."""

    passed = classification.get("d4") == "PASS"
    return {
        "v2_authorized": False,
        "v2_created": False,
        "stage_a_v1_rerun_authorized": False,
        "scientific_authority": "NONE",
        "runtime_authority": "NONE",
        "trading_authority": "NONE",
        "capital_authority": "NONE",
        "merge_authorized": False,
        "dsh_scientific_superiority_proven": False,
        "eligibility": (
            "ELIGIBLE_FOR_SEPARATE_EXECUTION_PLUMBING_QUALIFICATION_CONSIDERATION"
            if passed
            else "NONE"
        ),
    }
