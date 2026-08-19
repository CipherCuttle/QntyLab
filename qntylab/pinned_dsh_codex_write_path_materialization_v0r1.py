"""Evidence-integrity repair for the one-shot pinned DSH Codex D4 route.

This module is additive: V0 remains immutable history.  V0R1 repairs only the
runtime-byte gate, materialization binding, receipt validation, crash-safe
episode consumption, and receipt provenance.  It deliberately makes no claim
about filesystem mutation after the final byte gate has completed.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from qntylab.pinned_dsh_codex_write_path_materialization_v0 import (
    ALLOWED_CHANGED_PATHS,
    CODEX_BINARY,
    CODEX_HOME,
    CODEX_VERSION,
    D4_DRIVER_RELPATH,
    D4_DRIVER_SHA256,
    D4_DRIVER_TIMEOUT_SECONDS,
    D4_ROUTE_MARKER,
    D4_TURN_TIMEOUT_SECONDS,
    DSH_BUILD_TARGET,
    DSH_COMMIT,
    DSH_NODE_ENGINES,
    DSH_PACKAGE_MANAGER,
    DSH_REPOSITORY,
    DSH_TAG,
    DSH_TREE,
    LOCKFILE_SHA256,
    PR134_HEAD,
    PR135_HEAD,
    REQUIRED_RUNTIME_ARTIFACTS,
    SUBSCRIPTION_AUTH_MODE,
    codex_child_spawned,
    codex_identity,
    driver_identity,
    dsh_identity,
    identity_gate,
    node_version_satisfies,
    pnpm_version_satisfies,
)
from qntylab.subscription_backed_product_execution_plumbing_v0 import (
    API_KEY_NAMES,
    QualificationError,
    sha256_file,
)

PHASE_ID = "PINNED_DSH_CODEX_WRITE_PATH_MATERIALIZATION_V0R1"
FROZEN_DSH_ROOT = Path("/home/swirky/DevHub/dsh-pinned-materialization-v0")
MATERIALIZATION_SCHEMA = "pinned-dsh-materialization-record-v0r1"
RUNTIME_CLOSURE_SCHEMA = "pinned-dsh-generated-runtime-closure-v0r1"
RECEIPT_SCHEMA = "pinned-dsh-codex-write-path-d4-receipt-v0r1"
MAX_LIVE_ATTEMPTS = 1

# Filled from the exact pinned checkout after the resolver itself is tested.
# The materialization record carries the same mapping and is independently
# checked; neither declaration can make differing live bytes pass.
FROZEN_RUNTIME_CLOSURE_FILES: Mapping[str, str] = {
    "packages/core/agent/lib/index.js": "e7e40c5ca66d9827a5084c5c0c68983f9685842bb9b6d604803d4cb4642bb263",
    "packages/core/scope/lib/index.js": "2829df71d76e08941457d4dd173eac60783e55354921137c8b75e8b5c0d2ecca",
    "packages/core/session/lib/index.js": "9270186b579bc8a4c6c53c256e4471d3f134e94308462c6a413a722e9c7556fb",
    "packages/core/tools/lib/index.js": "47de95d14493dbd22d1a3ade14890fc99d7232db4e363f2190c9063b030dd029",
    "packages/llm/llm/lib/index.js": "66ef669901973863a474e7bfc172d7cdc9cb13420f92c74104730dd6858afc1d",
    "packages/sdk/protocol/lib/index.js": "371c38ca3514797d86df5f4bb78a56c40a2637294b83aababe8145bec6a20253",
    "packages/subagent/subagent-codex/lib/index.js": "2b65fd97f345d346319423a40cb285026c263be565e29e5dce0872e4aa5aa72a",
    "packages/subagent/subagent/lib/index.js": "510aba14f13d1a9deccf3d81d790be3e7ebcdc4797fcfa584908350d07c529c6",
    "packages/subprocess/subprocess-local/lib/index.js": "e16ecbcce0fa3d60234a8a1ca3de80fa29d850ba1513bf9e8e6daa186e526ce4",
    "packages/subprocess/subprocess/lib/index.js": "679e514028454cdef67adeb362e99a18e8efb7ca281857cf7868fc26d4821f6c",
    "packages/util/timeout/lib/index.js": "744fdb4f79c8d513c6d4014a018949cfb2f02f4dde4621167302c5467c3994ec",
    "vendor/cordis/lib/index.js": "1729cdbf8ee40b17c8839e06bf96491490548559e11ef7e411271e0754e751c5",
    "vendor/cosmokit/lib/index.js": "a024ad32ead85dd6708cedd5b56acacb578e048e8f71e78b20ed56053ac7beb4",
    "vendor/schemastery/lib/index.mjs": "d23d1f48ea69800c68fc8be592f5d1074c9c764b22f35a1d40b84f5eab39ac00",
}
FROZEN_RUNTIME_CLOSURE_DIGEST = "d354fd326bfba5fd51e4a6076a7573223224628c1d89266ecc66168742d30ec8"
SOURCE_MATERIALIZATION_RECORD_SHA256 = "5ff19d10774c28d813c0f90d4daf26d15724f6f68e61eb03bcefdebb739bd3bc"

_IMPORT_PATTERNS = (
    re.compile(r"(?:^|\s)(?:import|export)\s+(?:[^;]*?\s+from\s+)?[\"']([^\"']+)[\"']", re.MULTILINE),
    re.compile(r"\b(?:import|require)\s*\(\s*[\"']([^\"']+)[\"']\s*\)"),
)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")


class RuntimeClosureError(QualificationError):
    """A path or dependency cannot safely join the generated runtime closure."""


def api_key_gate(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Observe credential *name presence* only; never inspect values."""

    source = os.environ if environ is None else environ
    presence = {name: name in source for name in API_KEY_NAMES}
    return {"presence": presence, "passed": not any(presence.values())}


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def _lexists(path: Path) -> bool:
    return os.path.lexists(path)


def resolve_dsh_root(root: Path, *, expected_root: Path | None = None) -> Path:
    """Resolve one non-symlink DSH root and optionally bind its exact location."""

    lexical = Path(root)
    if lexical.is_symlink():
        raise RuntimeClosureError(f"DSH root may not be a symlink: {lexical}")
    try:
        resolved = lexical.resolve(strict=True)
    except OSError as exc:
        raise RuntimeClosureError(f"DSH root is unavailable: {lexical}") from exc
    if not resolved.is_dir():
        raise RuntimeClosureError(f"DSH root is not a directory: {resolved}")
    if expected_root is not None:
        expected = Path(expected_root).resolve(strict=True)
        if resolved != expected:
            raise RuntimeClosureError(f"wrong DSH root: {resolved} != {expected}")
    return resolved


def _safe_regular_file(root: Path, relpath: str) -> Path:
    """Return a regular non-symlink file strictly below ``root``."""

    relative = Path(relpath)
    if relative.is_absolute() or not relative.parts or ".." in relative.parts:
        raise RuntimeClosureError(f"runtime path escapes DSH root: {relpath}")
    candidate = root / relative
    cursor = root
    for part in relative.parts:
        cursor = cursor / part
        try:
            mode = cursor.lstat().st_mode
        except OSError as exc:
            raise RuntimeClosureError(f"runtime path is missing: {relpath}") from exc
        if stat.S_ISLNK(mode):
            raise RuntimeClosureError(f"runtime path contains a symlink: {relpath}")
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(root)
    except (OSError, ValueError) as exc:
        raise RuntimeClosureError(f"runtime path escapes DSH root: {relpath}") from exc
    if not stat.S_ISREG(candidate.stat().st_mode):
        raise RuntimeClosureError(f"runtime artifact is not a regular file: {relpath}")
    return candidate


def _walk_package_json(root: Path) -> dict[str, tuple[Path, Mapping[str, Any]]]:
    """Index local workspace packages without following directory symlinks."""

    packages: dict[str, tuple[Path, Mapping[str, Any]]] = {}
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames[:] = sorted(
            name
            for name in dirnames
            if name not in {".git", "node_modules"}
            and not (Path(directory) / name).is_symlink()
        )
        if "package.json" not in filenames:
            continue
        manifest = Path(directory) / "package.json"
        relpath = manifest.relative_to(root).as_posix()
        _safe_regular_file(root, relpath)
        try:
            value = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RuntimeClosureError(f"malformed local package manifest: {relpath}") from exc
        if not isinstance(value, Mapping):
            raise RuntimeClosureError(f"local package manifest is not an object: {relpath}")
        name = value.get("name")
        if isinstance(name, str) and name.startswith("@deepseek-ai/"):
            if name in packages:
                raise RuntimeClosureError(f"duplicate local package name: {name}")
            packages[name] = (manifest.parent, value)
    return packages


def _package_parts(specifier: str) -> tuple[str, str] | None:
    if not specifier.startswith("@deepseek-ai/"):
        return None
    parts = specifier.split("/")
    if len(parts) < 2:
        return None
    name = "/".join(parts[:2])
    subpath = "." if len(parts) == 2 else "./" + "/".join(parts[2:])
    return name, subpath


def _export_target(manifest: Mapping[str, Any], subpath: str) -> str | None:
    exports = manifest.get("exports")
    target: Any = None
    if isinstance(exports, str) and subpath == ".":
        target = exports
    elif isinstance(exports, Mapping):
        target = exports.get(subpath)
        if isinstance(target, Mapping):
            for condition in ("import", "default", "node"):
                if isinstance(target.get(condition), str):
                    target = target[condition]
                    break
    if not isinstance(target, str) and subpath == ".":
        for key in ("module", "main"):
            if isinstance(manifest.get(key), str):
                target = manifest[key]
                break
    return target if isinstance(target, str) else None


def _resolve_local_import(
    root: Path,
    importer: Path,
    specifier: str,
    packages: Mapping[str, tuple[Path, Mapping[str, Any]]],
) -> Path | None:
    if specifier.startswith("."):
        raw = importer.parent / specifier
    else:
        parsed = _package_parts(specifier)
        if parsed is None or parsed[0] not in packages:
            return None
        package_root, manifest = packages[parsed[0]]
        target = _export_target(manifest, parsed[1])
        if target is None:
            raise RuntimeClosureError(f"unresolved local package export: {specifier}")
        raw = package_root / target

    candidates = [raw]
    if raw.suffix == "":
        candidates.extend((raw.with_suffix(".js"), raw / "index.js"))
    for candidate in candidates:
        try:
            relpath = candidate.relative_to(root).as_posix()
        except ValueError as exc:
            raise RuntimeClosureError(f"local import escapes DSH root: {specifier}") from exc
        if _lexists(candidate):
            return _safe_regular_file(root, relpath)
    raise RuntimeClosureError(f"local generated import is missing: {specifier}")


def _import_specifiers(path: Path) -> list[str]:
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeClosureError(f"cannot read generated runtime artifact: {path}") from exc
    return sorted({match.group(1) for pattern in _IMPORT_PATTERNS for match in pattern.finditer(text)})


def runtime_closure(root: Path, *, entrypoints: Sequence[str] = REQUIRED_RUNTIME_ARTIFACTS) -> dict[str, Any]:
    """Hash the transitive local generated-JS closure of the D4 entrypoints.

    Static/dynamic relative imports and local ``@deepseek-ai/*`` workspace
    package imports are followed.  Third-party and ``node:`` imports are not
    local generated artifacts and are intentionally outside this manifest.
    """

    resolved_root = resolve_dsh_root(root)
    packages = _walk_package_json(resolved_root)
    queue = [_safe_regular_file(resolved_root, relpath) for relpath in entrypoints]
    seen: set[str] = set()
    files: dict[str, str] = {}
    while queue:
        path = queue.pop(0)
        relpath = path.relative_to(resolved_root).as_posix()
        if relpath in seen:
            continue
        seen.add(relpath)
        files[relpath] = sha256_file(path)
        for specifier in _import_specifiers(path):
            dependency = _resolve_local_import(resolved_root, path, specifier, packages)
            if dependency is not None:
                queue.append(dependency)
    payload = {
        "schema_version": RUNTIME_CLOSURE_SCHEMA,
        "entrypoints": list(entrypoints),
        "files": dict(sorted(files.items())),
    }
    return {
        **payload,
        "root": str(resolved_root),
        "digest": hashlib.sha256(_canonical_json(payload)).hexdigest(),
    }


def closure_matches(observed: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    return (
        observed.get("schema_version") == RUNTIME_CLOSURE_SCHEMA
        and observed.get("entrypoints") == list(REQUIRED_RUNTIME_ARTIFACTS)
        and observed.get("files") == expected.get("files")
        and observed.get("digest") == expected.get("digest")
        and observed.get("root") == expected.get("root")
    )


_RECORD_KEYS = {
    "schema_version",
    "phase_id",
    "dsh",
    "lockfile_sha256",
    "node",
    "pnpm",
    "build",
    "install",
    "runtime_closure",
    "source_record_sha256",
}


def _record_shape_reasons(record: Any) -> list[str]:
    if not isinstance(record, Mapping):
        return ["MATERIALIZATION_RECORD_NOT_OBJECT"]
    reasons: list[str] = []
    if set(record) != _RECORD_KEYS:
        reasons.append("MATERIALIZATION_RECORD_TOP_LEVEL_SCHEMA_MISMATCH")
    exact_nested = {
        "dsh": {"repository", "commit", "tree", "tag"},
        "node": {"version", "range"},
        "pnpm": {"version"},
        "build": {"target", "success"},
        "install": {"success", "frozen_lockfile"},
        "runtime_closure": {"schema_version", "entrypoints", "files", "digest"},
    }
    for key, keys in exact_nested.items():
        value = record.get(key)
        if not isinstance(value, Mapping) or set(value) != keys:
            reasons.append(f"MATERIALIZATION_RECORD_{key.upper()}_SCHEMA_MISMATCH")
    return reasons


def validate_materialization_record(
    record_path: Path,
    *,
    source_record_path: Path,
    dsh_root: Path,
    closure: Mapping[str, Any],
    identity: Mapping[str, Any],
    node_version: str,
    pnpm_version: str,
) -> dict[str, Any]:
    """Validate record claims against live checkout, toolchain, and bytes."""

    result: dict[str, Any] = {"passed": False, "reasons": [], "record_sha256": None}
    if not Path(record_path).is_file() or Path(record_path).is_symlink():
        result["reasons"] = ["MATERIALIZATION_RECORD_MISSING_OR_SYMLINK"]
        return result
    try:
        raw = Path(record_path).read_bytes()
        record = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        result["reasons"] = ["MATERIALIZATION_RECORD_MALFORMED"]
        return result
    result["record_sha256"] = hashlib.sha256(raw).hexdigest()
    reasons = _record_shape_reasons(record)
    if reasons:
        result["reasons"] = reasons
        return result

    expected_dsh = {
        "repository": DSH_REPOSITORY,
        "commit": DSH_COMMIT,
        "tree": DSH_TREE,
        "tag": DSH_TAG,
    }
    if record.get("schema_version") != MATERIALIZATION_SCHEMA:
        reasons.append("MATERIALIZATION_RECORD_SCHEMA_VERSION_MISMATCH")
    if record.get("phase_id") != PHASE_ID:
        reasons.append("MATERIALIZATION_RECORD_PHASE_MISMATCH")
    if record.get("dsh") != expected_dsh:
        reasons.append("MATERIALIZATION_RECORD_DSH_IDENTITY_MISMATCH")
    if any(identity.get(key) != expected_dsh[key] for key in ("commit", "tree", "tag")):
        reasons.append("LIVE_DSH_IDENTITY_MISMATCH")
    if not identity.get("matches") or Path(identity.get("root", "")).resolve() != Path(dsh_root).resolve():
        reasons.append("LIVE_DSH_CHECKOUT_MISMATCH")

    try:
        lockfile = _safe_regular_file(resolve_dsh_root(dsh_root), "pnpm-lock.yaml")
        observed_lockfile = sha256_file(lockfile)
    except RuntimeClosureError:
        observed_lockfile = None
    result["lockfile_sha256_observed"] = observed_lockfile
    if observed_lockfile != LOCKFILE_SHA256:
        reasons.append("LIVE_LOCKFILE_DIGEST_MISMATCH")
    if record.get("lockfile_sha256") != LOCKFILE_SHA256:
        reasons.append("RECORDED_LOCKFILE_DIGEST_MISMATCH")

    node = record["node"]
    pnpm = record["pnpm"]
    if node.get("range") != DSH_NODE_ENGINES or node.get("version") != node_version:
        reasons.append("RECORDED_NODE_MISMATCH")
    if not node_version_satisfies(node_version):
        reasons.append("LIVE_NODE_MISMATCH")
    if pnpm.get("version") != pnpm_version or not pnpm_version_satisfies(pnpm_version):
        reasons.append("RECORDED_OR_LIVE_PNPM_MISMATCH")
    if record["build"].get("target") != DSH_BUILD_TARGET:
        reasons.append("BUILD_TARGET_MISMATCH")
    if record["install"].get("success") is not True or record["install"].get("frozen_lockfile") is not True:
        reasons.append("INSTALL_NOT_SUCCESSFUL")
    if record["build"].get("success") is not True:
        reasons.append("BUILD_NOT_SUCCESSFUL")

    recorded_closure = record["runtime_closure"]
    expected_closure = {
        "schema_version": RUNTIME_CLOSURE_SCHEMA,
        "entrypoints": list(REQUIRED_RUNTIME_ARTIFACTS),
        "files": dict(FROZEN_RUNTIME_CLOSURE_FILES),
        "digest": FROZEN_RUNTIME_CLOSURE_DIGEST,
    }
    if recorded_closure != expected_closure:
        reasons.append("RECORDED_RUNTIME_CLOSURE_MISMATCH")
    if closure.get("files") != expected_closure["files"] or closure.get("digest") != expected_closure["digest"]:
        reasons.append("LIVE_RUNTIME_CLOSURE_MISMATCH")
    if record.get("source_record_sha256") != SOURCE_MATERIALIZATION_RECORD_SHA256:
        reasons.append("SOURCE_RECORD_DIGEST_MISMATCH")
    if (
        not Path(source_record_path).is_file()
        or Path(source_record_path).is_symlink()
        or sha256_file(Path(source_record_path)) != SOURCE_MATERIALIZATION_RECORD_SHA256
    ):
        reasons.append("SOURCE_MATERIALIZATION_RECORD_BYTES_MISMATCH")

    result["reasons"] = reasons
    result["passed"] = not reasons
    return result


def final_execution_gate(
    *,
    dsh_root: Path,
    expected_root: Path,
    expected_closure: Mapping[str, Any],
    record_path: Path,
    source_record_path: Path,
    node_version: str,
    pnpm_version: str,
) -> dict[str, Any]:
    """Recompute all execution-binding evidence at the final pre-spawn gate."""

    try:
        root = resolve_dsh_root(dsh_root, expected_root=expected_root)
        closure = runtime_closure(root)
    except RuntimeClosureError as exc:
        return {"passed": False, "reason": str(exc), "runtime_closure_match": False}
    identity = dsh_identity(root)
    closure_match = closure_matches(closure, expected_closure)
    binding = validate_materialization_record(
        record_path,
        source_record_path=source_record_path,
        dsh_root=root,
        closure=closure,
        identity=identity,
        node_version=node_version,
        pnpm_version=pnpm_version,
    )
    return {
        "passed": closure_match and binding["passed"],
        "root": str(root),
        "runtime_closure": closure,
        "runtime_closure_match": closure_match,
        "materialization_binding": binding,
    }


def acquire_episode_marker(
    marker_path: Path,
    *,
    attempt_path: Path,
    receipt_path: Path,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    """Durably and exclusively consume V0R1 before a product process starts."""

    for path, label in (
        (marker_path, "CONSUMED_MARKER"),
        (attempt_path, "PRIOR_ATTEMPT"),
        (receipt_path, "PRIOR_RECEIPT"),
    ):
        if _lexists(Path(path)):
            raise QualificationError(f"V0R1 live episode already consumed: {label}:{path}")
    Path(marker_path).parent.mkdir(parents=True, exist_ok=True)
    data = _canonical_json(dict(payload)) + b"\n"
    try:
        descriptor = os.open(marker_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise QualificationError(f"V0R1 live episode already consumed: CONSUMED_MARKER:{marker_path}") from exc
    try:
        offset = 0
        while offset < len(data):
            offset += os.write(descriptor, data[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    try:
        parent_fd = os.open(Path(marker_path).parent, os.O_RDONLY)
        try:
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
    except OSError:
        # File fsync is authoritative.  Directory fsync is best-effort on
        # platforms/filesystems that do not support it.
        pass
    return {"acquired": True, "path": str(marker_path), "sha256": hashlib.sha256(data).hexdigest()}


def _receipt_shape_reasons(receipt: Any, *, expected_dsh_root: Path | None = None) -> list[str]:
    """Validate exact final-driver receipt provenance before product claims."""

    if not isinstance(receipt, Mapping):
        return ["D4_RECEIPT_NOT_OBJECT"]
    required = {
        "status", "output", "lifecycle", "processes", "parentLlmProvider",
        "parentLlmRequestCount", "route", "startedAt", "endedAt", "timedOut",
        "observed", "outputPartCount", "stdoutSha256", "stderrSha256",
        "apiKeyPresence", "bridgeExitCode",
    }
    reasons: list[str] = []
    if set(receipt) not in (required, required | {"error"}):
        reasons.append("D4_RECEIPT_EXACT_SCHEMA_MISMATCH")
    if receipt.get("route") != D4_ROUTE_MARKER:
        reasons.append("D4_RECEIPT_ROUTE_MISMATCH")
    if not isinstance(receipt.get("status"), str):
        reasons.append("D4_RECEIPT_STATUS_MALFORMED")
    if not isinstance(receipt.get("output"), str):
        reasons.append("D4_RECEIPT_OUTPUT_MALFORMED")
    if not isinstance(receipt.get("processes"), list) or any(
        not isinstance(item, Mapping) for item in receipt.get("processes", [])
    ):
        reasons.append("D4_RECEIPT_PROCESSES_MALFORMED")
    if not isinstance(receipt.get("startedAt"), str) or not isinstance(receipt.get("endedAt"), str):
        reasons.append("D4_RECEIPT_TIMESTAMPS_MALFORMED")
    part_count = receipt.get("outputPartCount")
    if isinstance(part_count, bool) or not isinstance(part_count, int) or part_count < 0:
        reasons.append("D4_RECEIPT_OUTPUT_PART_COUNT_MALFORMED")
    exit_code = receipt.get("bridgeExitCode")
    if isinstance(exit_code, bool) or not isinstance(exit_code, int):
        reasons.append("D4_RECEIPT_BRIDGE_EXIT_CODE_MALFORMED")
    if receipt.get("error") is not None and not isinstance(receipt.get("error"), str):
        reasons.append("D4_RECEIPT_ERROR_MALFORMED")
    if not isinstance(receipt.get("timedOut"), bool):
        reasons.append("D4_RECEIPT_TIMEOUT_MALFORMED")
    if not isinstance(receipt.get("parentLlmProvider"), str):
        reasons.append("D4_RECEIPT_PARENT_PROVIDER_MALFORMED")
    count = receipt.get("parentLlmRequestCount")
    if isinstance(count, bool) or not isinstance(count, int):
        reasons.append("D4_RECEIPT_PARENT_COUNT_MALFORMED")
    lifecycle = receipt.get("lifecycle")
    ends = lifecycle.get("ends") if isinstance(lifecycle, Mapping) else None
    if not isinstance(lifecycle, Mapping) or set(lifecycle) != {"ends"}:
        reasons.append("D4_RECEIPT_LIFECYCLE_SCHEMA_MISMATCH")
    if not isinstance(ends, list) or not ends:
        reasons.append("D4_RECEIPT_LIFECYCLE_ENDS_MALFORMED")
    elif any(
        not isinstance(end, Mapping)
        or set(end) != {"stopReason"}
        or not isinstance(end.get("stopReason"), str)
        for end in ends
    ):
        reasons.append("D4_RECEIPT_LIFECYCLE_ELEMENT_MALFORMED")
    presence = receipt.get("apiKeyPresence")
    if not isinstance(presence, Mapping) or set(presence) != set(API_KEY_NAMES) or any(
        not isinstance(value, bool) for value in presence.values()
    ):
        reasons.append("D4_RECEIPT_CREDENTIAL_GATE_MALFORMED")
    observed = receipt.get("observed")
    observed_keys = {
        "requestedCwd", "codexHome", "pathPrefix", "dshRoot", "childEnvKeys",
        "providerName", "promptSha256",
    }
    if not isinstance(observed, Mapping) or set(observed) != observed_keys:
        reasons.append("D4_RECEIPT_PROVIDER_OBSERVATION_MALFORMED")
    elif (
        observed.get("providerName") != "codex"
        or observed.get("codexHome") != CODEX_HOME
        or observed.get("pathPrefix") != str(Path(CODEX_BINARY).parent)
        or observed.get("childEnvKeys") != ["CODEX_HOME", "PATH"]
        or not isinstance(observed.get("requestedCwd"), str)
        or not isinstance(observed.get("promptSha256"), str)
        or not _DIGEST.fullmatch(observed["promptSha256"])
    ):
        reasons.append("D4_RECEIPT_PROVIDER_OBSERVATION_MALFORMED")
    elif expected_dsh_root is not None:
        try:
            observed_root = Path(observed.get("dshRoot", "")).resolve(strict=True)
            expected = Path(expected_dsh_root).resolve(strict=True)
        except (OSError, TypeError):
            reasons.append("D4_RECEIPT_DSH_ROOT_OBSERVATION_MALFORMED")
        else:
            if observed_root != expected:
                reasons.append("D4_RECEIPT_DSH_ROOT_OBSERVATION_MISMATCH")
    for key in ("stdoutSha256", "stderrSha256"):
        if not isinstance(receipt.get(key), str) or not _DIGEST.fullmatch(receipt[key]):
            reasons.append(f"D4_RECEIPT_{key.upper()}_MALFORMED")
    return reasons


def parse_d4_stdout(stdout: bytes) -> dict[str, Any]:
    """Return one exact-route object, never promote unrelated JSON."""

    candidates: list[dict[str, Any]] = []
    try:
        lines = stdout.decode("utf-8").splitlines()
    except UnicodeDecodeError:
        return {"receipt": None, "state": "NO_VALID_D4_RECEIPT", "reason": "STDOUT_NOT_UTF8"}
    for line in lines:
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict) and value.get("route") == D4_ROUTE_MARKER:
            candidates.append(value)
    if len(candidates) != 1:
        reason = "MULTIPLE_D4_ROUTE_OBJECTS" if len(candidates) > 1 else "NO_D4_ROUTE_OBJECT"
        return {"receipt": None, "state": "NO_VALID_D4_RECEIPT", "reason": reason}
    return {"receipt": candidates[0], "state": "D4_ROUTE_OBJECT_FOUND", "reason": None}


def receipt_pass_reasons(receipt: Mapping[str, Any], *, expected_dsh_root: Path | None = None) -> list[str]:
    reasons = _receipt_shape_reasons(receipt, expected_dsh_root=expected_dsh_root)
    if reasons:
        return reasons
    if receipt["status"] != "COMPLETED":
        reasons.append("RECEIPT_STATUS_NOT_COMPLETED")
    if receipt["bridgeExitCode"] != 0:
        reasons.append("DRIVER_EXIT_CODE_NONZERO")
    if receipt.get("error") is not None:
        reasons.append("RECEIPT_CARRIES_ERROR")
    if receipt["parentLlmProvider"] != "NONE":
        reasons.append("DSH_PARENT_LLM_ACTIVE")
    if receipt["parentLlmRequestCount"] != 0:
        reasons.append("DSH_PARENT_LLM_REQUESTS_NONZERO")
    if any(receipt["apiKeyPresence"].values()):
        reasons.append("PAY_PER_TOKEN_CREDENTIAL_PRESENT_IN_DRIVER_ENV")
    if any(end["stopReason"] != "completed" for end in receipt["lifecycle"]["ends"]):
        reasons.append("LIFECYCLE_NOT_ALL_COMPLETED")
    return reasons


def classify_d4(
    *,
    gates_passed: bool,
    gate_reason: str | None,
    receipt: Mapping[str, Any] | None,
    descendants: Sequence[Mapping[str, Any]],
    fixture_before_class: str,
    fixture_after_class: str,
    changed: Sequence[str],
    marker_acquired: bool,
    expected_dsh_root: Path,
    profile: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Classify only provenance-valid product evidence as D4 PASS/FAIL."""

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
        "target_mechanism_exercised": False,
    }
    if not gates_passed or not marker_acquired:
        return {**evidence, "d4": "INCONCLUSIVE_INFRA", "reason": gate_reason or "PRELIVE_GATE_FAILED", "failure_mechanism": None}
    if receipt is None:
        return {**evidence, "d4": "INCONCLUSIVE_INFRA", "reason": "NO_VALID_D4_RECEIPT", "failure_mechanism": None}
    shape = _receipt_shape_reasons(receipt, expected_dsh_root=expected_dsh_root)
    if shape:
        return {
            **evidence,
            "d4": "INCONCLUSIVE_INFRA",
            "reason": "NO_VALID_D4_RECEIPT:" + ",".join(shape),
            "failure_mechanism": None,
            "receipt_integrity_reasons": shape,
        }

    ends = receipt["lifecycle"]["ends"]
    stop_reasons = [end["stopReason"] for end in ends]
    timed_out = receipt["timedOut"]
    spawned = codex_child_spawned(descendants)
    target = spawned
    terminal = bool(stop_reasons) and not timed_out
    integrity = receipt_pass_reasons(receipt, expected_dsh_root=expected_dsh_root)
    evidence.update(
        {
            "dsh_provider_entered": True,
            "codex_child_spawned": spawned,
            "turn_started": spawned or bool(stop_reasons),
            "turn_terminal_observed": terminal,
            "dsh_stop_reason": stop_reasons[0],
            "all_stop_reasons": stop_reasons,
            "timed_out": timed_out,
            "target_mechanism_exercised": target,
            "receipt_integrity_reasons": integrity,
            "profile_observation": dict(profile or {}),
        }
    )
    clean_write = (
        evidence["fixture_target_match"]
        and list(changed) == list(ALLOWED_CHANGED_PATHS)
        and not evidence["unauthorized_writes"]
    )
    if target and not integrity and clean_write:
        return {**evidence, "d4": "PASS", "reason": "PINNED_DSH_CODEX_PROVIDER_PERFORMED_BOUNDED_WRITE", "failure_mechanism": None}

    error_text = str(receipt.get("error") or "").lower()
    if timed_out:
        mechanism = "DSH_CODEX_TURN_TIMEOUT"
    elif not spawned:
        mechanism = "DSH_CODEX_STARTUP_FAILURE"
    elif "DSH_PARENT_LLM_ACTIVE" in integrity or "DSH_PARENT_LLM_REQUESTS_NONZERO" in integrity:
        mechanism = "DSH_EFFECTIVE_CONFIG_DIVERGENCE"
    elif (profile or {}).get("workspace_trusted") is False and not evidence["fixture_target_match"]:
        mechanism = "DSH_EFFECTIVE_CONFIG_DIVERGENCE"
    elif any(word in error_text for word in ("protocol", "jsonrpc", "malformed", "handshake")):
        mechanism = "DSH_CODEX_PROTOCOL_FAILURE"
    elif not integrity and not clean_write:
        mechanism = "DSH_CODEX_WRITE_ATTEMPT_FAILED" if fixture_after_class == "AFTER" else "DSH_CODEX_COMPLETED_NO_WRITE"
    else:
        mechanism = "DSH_CODEX_TURN_ERROR"
    return {**evidence, "d4": "FAIL", "reason": mechanism, "failure_mechanism": mechanism}


def phase_verdict(classification: Mapping[str, Any]) -> str:
    if classification.get("d4") == "PASS":
        return "PINNED_DSH_CODEX_WRITE_PATH_V0R1_PASS"
    if classification.get("d4") == "FAIL":
        return "PINNED_DSH_CODEX_WRITE_PATH_V0R1_FAIL"
    if classification.get("d4") == "INCONCLUSIVE_INFRA":
        return "PINNED_DSH_CODEX_WRITE_PATH_V0R1_BLOCKED"
    raise QualificationError("unknown or missing V0R1 D4 classification")


def downstream_authority(_classification: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "scientific_authority": "NONE",
        "runtime_authority": "NONE",
        "qnty_next_action_authority": "NONE",
        "trading_authority": "NONE",
        "capital_authority": "NONE",
        "stage_a_v1_rerun_authorized": False,
        "v2_created": False,
        "v2_authorized": False,
        "merge_authorized": False,
    }
