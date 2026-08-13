"""One-shot JFP03 V0R3 prefix input materialization.

This module is deliberately limited to source authentication and structural input
qualification.  It does not calculate any scientific feature, target, or result.
"""
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import io
import json
import os
import subprocess
import tomllib
import urllib.error
import urllib.request
import uuid
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Protocol


BASE_REL = Path("experiments/research/jigsaw_fast_prospective_signal_discovery_v0")
OUT_REL = BASE_REL / "materialization"
CLOSE_REPAIR_REL = BASE_REL / "close_boundary_repair_v0/close_boundary_source_contract_repair.json"
PREFIX_CONTRACT_REL = BASE_REL / "close_boundary_repair_v0/prefix_source_contract.json"
AUTH_REL = OUT_REL / "v0r3_prefix_materialization_authorization.json"
V0R2_MANIFEST_REL = OUT_REL / "v0r2_repaired_source_manifest.json"
V0R2_SNAPSHOT_REL = OUT_REL / "v0r2_input_snapshot.json"
V0R2_QUALIFICATION_REL = OUT_REL / "v0r2_input_qualification.json"
V0R2_RECEIPT_REL = OUT_REL / "v0r2_repaired_source_materialization_receipt.json"
V0R3_MANIFEST_REL = OUT_REL / "v0r3_source_manifest.json"
V0R3_SNAPSHOT_REL = OUT_REL / "v0r3_input_snapshot.json"
V0R3_QUALIFICATION_REL = OUT_REL / "v0r3_input_qualification.json"
V0R3_RECEIPT_REL = OUT_REL / "v0r3_materialization_receipt.json"
PROJECTS_REL = Path("docs/state/projects.toml")
CACHE_REL = Path("data/archive/binance_jfp_v0")

PROJECT_ID = "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_JFP03_V0R3_PREFIX_MATERIALIZATION_V0"
AUTH_PROJECT_ID = "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_JFP03_V0R3_PREFIX_MATERIALIZATION_AUTHORIZATION_V0"
CLOSE_REPAIR_PROJECT_ID = "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_JFP03_V0R2_CLOSE_BOUNDARY_SOURCE_CONTRACT_REPAIR_V0"
EXPECTED_MASTER = "5d2007b4a7ede300293c1ccecea7ed4957e8fa54"
AUTHORIZATION_BASE = "888e40ebd5adf77c56ede2f08a12791948132121"
DESIGN_DIGEST = "a52d4999038e0be814ee8770322303fce84bed9ec8941b812748a18867633736"
V0R2_SNAPSHOT_ID = "jfp-input-v0r2-0d28756edca8e24060f32a217362cb886c8b5eebd506293c32058cd59a617852"
V0R2_SNAPSHOT_DIGEST = "0d28756edca8e24060f32a217362cb886c8b5eebd506293c32058cd59a617852"
V0R2_QUALIFICATION_DIGEST = "bf5b474d371f931f02f18a3c7faac75f08eadac4b7f8b3e7cd2ec913cefc715f"
V0R2_RECEIPT_DIGEST = "8fffad3a525623ccd0bd2bcd698403575eda573706b0213d16fd108f37b9601d"
V0R2_REST_SHA256 = "ef2d114a512d1d2905ccd335b3a53d9601b59b2877d31af3dd2dd7dc3fe0c70a"
TAIL_SHA256 = "9ebc05c9b3d5ab3591edf65bc5c7e5dbc2f96c1efc4adc4ea198c651a99a41b1"
FEASIBILITY_SHA256 = "d8f1b085643cf14025cf611e9c96c4742d0ec3b3a6fdbba88c6bc71eb3f711ed"
PREFIX_ENDPOINT = "https://fapi.binance.com/fapi/v1/klines"
PREFIX_QUERY = "symbol=BTCUSDT&interval=1h&startTime=1575241200000&endTime=1575244799999&limit=1"
PREFIX_URL = f"{PREFIX_ENDPOINT}?{PREFIX_QUERY}"
REMOTE_CLAIM_REF = "refs/heads/qntylab-claims/jfp03-v0r3-prefix-materialization-v0"

EXPECTED_SCHEMA = [
    "open_time",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "close_time",
    "quote_asset_volume",
    "number_of_trades",
    "taker_buy_base_asset_volume",
    "taker_buy_quote_asset_volume",
    "ignore",
]


class MaterializationError(RuntimeError):
    """Base class for bounded materialization failures."""


class AuthorizationError(MaterializationError):
    """Raised before a claim when authority cannot be established."""


class AuthorizationAlreadyConsumed(AuthorizationError):
    """Raised before source access when a claim or output already exists."""


class ValidationError(MaterializationError):
    """Raised after claim when a frozen input requirement fails."""


@dataclass(frozen=True)
class FrozenContract:
    expected_master: str = EXPECTED_MASTER
    authorization_base: str = AUTHORIZATION_BASE
    design_digest: str = DESIGN_DIGEST
    v0r2_snapshot_id: str = V0R2_SNAPSHOT_ID
    v0r2_snapshot_digest: str = V0R2_SNAPSHOT_DIGEST
    v0r2_qualification_digest: str = V0R2_QUALIFICATION_DIGEST
    v0r2_receipt_digest: str = V0R2_RECEIPT_DIGEST
    v0r2_rest_sha256: str = V0R2_REST_SHA256
    tail_sha256: str = TAIL_SHA256
    feasibility_sha256: str = FEASIBILITY_SHA256
    endpoint: str = PREFIX_ENDPOINT
    query: str = PREFIX_QUERY
    prefix_open_time_ms: int = 1_575_241_200_000
    prefix_close_time_ms: int = 1_575_244_799_999
    logical_close_boundary_ms: int = 1_575_244_800_000
    old_rest_first_open_ms: int = 1_575_244_800_000
    old_rest_last_open_ms: int = 1_577_833_200_000


@dataclass(frozen=True)
class FetchResponse:
    status: int
    body: bytes


@dataclass(frozen=True)
class Claim:
    mechanism: str
    token: str
    remote_ref: str | None = None
    remote_commit: str | None = None


class ClaimBackend(Protocol):
    def claim(self, root: Path, contract: FrozenContract) -> Claim: ...


Fetcher = Callable[[str], FetchResponse]
GitVerifier = Callable[[Path, FrozenContract], None]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        allow_nan=False,
    ).encode("utf-8")


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _load_json(path: Path) -> Any:
    return json.loads(path.read_bytes())


def _sha256_path(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def _write_exclusive(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        with os.fdopen(descriptor, "wb", closefd=False) as handle:
            handle.write(body)
            handle.flush()
            os.fsync(handle.fileno())
    finally:
        os.close(descriptor)


def _write_json_exclusive(path: Path, value: Any) -> None:
    _write_exclusive(path, canonical_bytes(value) + b"\n")


def _replace_json(path: Path, value: Any) -> None:
    temporary = path.with_name(f".{path.name}.final-{os.getpid()}-{uuid.uuid4().hex}")
    _write_json_exclusive(temporary, value)
    os.replace(temporary, path)
    directory = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def _git(root: Path, *args: str, check: bool = True, input_text: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        check=check,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def verify_git(root: Path, contract: FrozenContract) -> None:
    observed = _git(root, "rev-parse", "origin/master").stdout.strip()
    if observed != contract.expected_master:
        raise AuthorizationError(f"EXPECTED_MASTER_MISMATCH:{observed}")
    parents = _git(root, "rev-list", "--parents", "-n", "1", "origin/master").stdout.split()
    if len(parents) < 3 or parents[1] != contract.authorization_base:
        raise AuthorizationError("AUTHORIZATION_BASE_NOT_CANONICAL_FIRST_PARENT")
    ancestor = _git(root, "merge-base", "--is-ancestor", contract.expected_master, "HEAD", check=False)
    if ancestor.returncode != 0:
        raise AuthorizationError("LOCAL_HEAD_NOT_DESCENDED_FROM_EXPECTED_MASTER")


class LocalReceiptClaim:
    """Atomic filesystem claim used by isolated tests and local crash checks."""

    def claim(self, root: Path, contract: FrozenContract) -> Claim:
        claim = Claim(mechanism="O_EXCL_RECEIPT", token=uuid.uuid4().hex)
        _write_claim_receipt(root, contract, claim)
        return claim


class RemoteGitClaim:
    """Repository-wide claim that is atomic across worktrees and clones."""

    def __init__(
        self,
        remote: str = "origin",
        remote_ref: str = REMOTE_CLAIM_REF,
        git_runner: Callable[..., subprocess.CompletedProcess[str]] = _git,
    ) -> None:
        self.remote = remote
        self.remote_ref = remote_ref
        self.git_runner = git_runner

    def claim(self, root: Path, contract: FrozenContract) -> Claim:
        existing = self.git_runner(
            root, "ls-remote", "--exit-code", "--heads", self.remote, self.remote_ref, check=False
        )
        if existing.returncode == 0 and existing.stdout.strip():
            raise AuthorizationAlreadyConsumed("REMOTE_CLAIM_ALREADY_EXISTS")
        if existing.returncode not in (0, 2):
            raise AuthorizationError(f"REMOTE_CLAIM_LOOKUP_FAILED:{existing.stderr.strip()}")

        token = uuid.uuid4().hex
        tree = self.git_runner(root, "rev-parse", f"{contract.expected_master}^{{tree}}").stdout.strip()
        message = canonical_bytes(
            {
                "artifact_type": "JFP03_V0R3_PREFIX_MATERIALIZATION_REMOTE_CLAIM",
                "project_id": PROJECT_ID,
                "authorization_project": AUTH_PROJECT_ID,
                "expected_master": contract.expected_master,
                "authorized_runs_consumed": 1,
                "claim_token": token,
            }
        ).decode("utf-8")
        commit = self.git_runner(
            root, "commit-tree", tree, "-p", contract.expected_master, input_text=message + "\n"
        ).stdout.strip()
        pushed = self.git_runner(
            root,
            "push",
            "--porcelain",
            self.remote,
            f"{commit}:{self.remote_ref}",
            check=False,
        )
        if pushed.returncode != 0:
            raise AuthorizationAlreadyConsumed(f"REMOTE_CLAIM_REJECTED:{pushed.stderr.strip()}")
        claim = Claim(
            mechanism="REMOTE_GIT_REF_PLUS_O_EXCL_RECEIPT",
            token=token,
            remote_ref=self.remote_ref,
            remote_commit=commit,
        )
        _write_claim_receipt(root, contract, claim)
        return claim


def _write_claim_receipt(root: Path, contract: FrozenContract, claim: Claim) -> None:
    value = {
        "artifact_type": "JFP03_V0R3_PREFIX_MATERIALIZATION_RECEIPT",
        "schema_version": "jfp03-v0r3-prefix-materialization-receipt-v1",
        "project_id": PROJECT_ID,
        "bound_authorization_project": AUTH_PROJECT_ID,
        "state": "CLAIMED",
        "input_qualification": "PENDING",
        "expected_master": contract.expected_master,
        "authorized_runs_allowed": 1,
        "authorized_runs_consumed_before": 0,
        "authorized_runs_consumed_after": 1,
        "claim": claim.__dict__,
        "source_access_performed": False,
        "scientific_computation_performed": False,
        "scientific_execution_authorized": False,
        "downstream_authority": "NONE",
    }
    try:
        _write_json_exclusive(root / V0R3_RECEIPT_REL, value)
    except FileExistsError as exc:
        raise AuthorizationAlreadyConsumed("LOCAL_CLAIM_ALREADY_EXISTS") from exc


def fetch_prefix_once(url: str) -> FetchResponse:
    if url != PREFIX_URL:
        raise AuthorizationError("PREFIX_URL_DRIFT")

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
            return None

    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/json",
            "Accept-Encoding": "identity",
            "User-Agent": "QntyLab-JFP03-V0R3-Prefix-Materializer/1",
        },
        method="GET",
    )
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(request, timeout=30) as response:
            return FetchResponse(status=int(response.status), body=response.read())
    except urllib.error.HTTPError as error:
        return FetchResponse(status=int(error.code), body=error.read())


def _assert_no_existing_outputs(root: Path) -> None:
    for relative in (V0R3_MANIFEST_REL, V0R3_SNAPSHOT_REL, V0R3_QUALIFICATION_REL, V0R3_RECEIPT_REL):
        if (root / relative).exists():
            raise AuthorizationAlreadyConsumed(f"V0R3_OUTPUT_ALREADY_EXISTS:{relative.name}")


def _project(registry: dict[str, Any], project_id: str) -> dict[str, Any]:
    matches = [row for row in registry.get("project", []) if row.get("project_id") == project_id]
    if len(matches) != 1:
        raise AuthorizationError(f"PROJECT_IDENTITY_COUNT_INVALID:{project_id}:{len(matches)}")
    return matches[0]


def verify_authorization(root: Path, contract: FrozenContract) -> dict[str, Any]:
    _assert_no_existing_outputs(root)
    registry = tomllib.loads((root / PROJECTS_REL).read_text(encoding="utf-8"))
    project = _project(registry, AUTH_PROJECT_ID)
    if project.get("state") != "CLOSED_PASS" or project.get("authority_level") != "PREFIX_MATERIALIZATION_AUTHORIZATION_ONLY":
        raise AuthorizationError("AUTHORIZATION_PROJECT_NOT_CLOSED_PASS")
    if project.get("prefix_materialization_runs_allowed") != 1:
        raise AuthorizationError("AUTHORIZED_RUNS_ALLOWED_INVALID")
    if project.get("authorized_runs_consumed") != 0 or project.get("prefix_materialization_performed") is not False:
        raise AuthorizationAlreadyConsumed("CANONICAL_AUTHORIZATION_ALREADY_CONSUMED")
    if project.get("scientific_execution_authorized") is not False:
        raise AuthorizationError("SCIENTIFIC_AUTHORITY_ESCALATION")

    auth = _load_json(root / AUTH_REL)
    if auth.get("project_id") != AUTH_PROJECT_ID or auth.get("bound_design_digest") != contract.design_digest:
        raise AuthorizationError("AUTHORIZATION_IDENTITY_INVALID")
    if auth.get("expected_master") != contract.authorization_base:
        raise AuthorizationError("AUTHORIZATION_BASE_BINDING_INVALID")
    future = auth.get("future_materialization_contract", {})
    boundary = auth.get("authority_boundary", {})
    if future.get("authorized_runs_allowed") != 1 or future.get("authorized_runs_consumed_before_run") != 0:
        raise AuthorizationError("AUTHORIZATION_RUN_COUNT_INVALID")
    if future.get("expected_master") != contract.authorization_base:
        raise AuthorizationError("FUTURE_CONTRACT_BASE_BINDING_INVALID")
    if future.get("atomic_pre_access_consumption_claim_required") is not True:
        raise AuthorizationError("ATOMIC_CLAIM_NOT_AUTHORIZED")
    if boundary.get("prefix_materialization_authorized") is not True:
        raise AuthorizationError("PREFIX_MATERIALIZATION_NOT_AUTHORIZED")
    prohibited = (
        "scientific_execution_authorized",
        "historical_execution_authorized",
        "feature_computation_authorized",
        "target_computation_authorized",
        "regression_authorized",
        "hac_authorized",
        "p_values_authorized",
        "qnty_authorized",
        "trading_authorized",
    )
    if any(boundary.get(field) is not False for field in prohibited):
        raise AuthorizationError("AUTHORITY_BOUNDARY_INVALID")

    source = auth.get("prefix_source_contract", {})
    expected_source = {
        "endpoint": contract.endpoint,
        "canonical_query": contract.query,
        "expected_rows": 1,
        "expected_open_time_ms": contract.prefix_open_time_ms,
        "expected_close_time_ms": contract.prefix_close_time_ms,
        "expected_logical_close_boundary_ms": contract.logical_close_boundary_ms,
        "expected_field_count": 12,
        "feasibility_response_sha256": contract.feasibility_sha256,
    }
    for key, expected in expected_source.items():
        if source.get(key) != expected:
            raise AuthorizationError(f"PREFIX_CONTRACT_DRIFT:{key}")
    if source.get("feasibility_sha_authoritative_for_future_run") is not False:
        raise AuthorizationError("FEASIBILITY_HASH_GATE_INVALID")
    reuse = auth.get("reuse_contract", {})
    expected_reuse = {
        "original_authenticated_monthly_objects": 60,
        "original_60_reuse_required": True,
        "original_60_reacquisition_authorized": False,
        "authenticated_2025_01_sha256": contract.tail_sha256,
        "2025_01_reuse_required": True,
        "2025_01_reacquisition_authorized": False,
        "existing_720_rest_sha256": contract.v0r2_rest_sha256,
        "existing_720_rest_rows": 720,
        "v0r2_720_rest_reuse_required": True,
        "v0r2_720_rest_reacquisition_authorized": False,
        "expected_v0r3_source_objects": 63,
        "expected_logical_warmup_rows": 721,
    }
    for key, expected in expected_reuse.items():
        if reuse.get(key) != expected:
            raise AuthorizationError(f"REUSE_CONTRACT_DRIFT:{key}")
    return auth


def _assert_self_digest(value: dict[str, Any], field: str, expected: str) -> None:
    if value.get(field) != expected:
        raise ValidationError(f"{field.upper()}_IDENTITY_MISMATCH")
    body = {key: item for key, item in value.items() if key != field}
    if digest(body) != expected:
        raise ValidationError(f"{field.upper()}_SELF_DIGEST_MISMATCH")


def _assert_snapshot_digest(value: dict[str, Any], contract: FrozenContract) -> None:
    if value.get("snapshot_id") != contract.v0r2_snapshot_id or value.get("snapshot_digest") != contract.v0r2_snapshot_digest:
        raise ValidationError("V0R2_SNAPSHOT_IDENTITY_MISMATCH")
    body = {key: item for key, item in value.items() if key not in {"snapshot_id", "snapshot_digest"}}
    if digest(body) != contract.v0r2_snapshot_digest:
        raise ValidationError("V0R2_SNAPSHOT_SELF_DIGEST_MISMATCH")


def _assert_file_sha(path: Path, expected: str, code: str) -> None:
    if not path.is_file() or _sha256_path(path) != expected:
        raise ValidationError(code)


def _assert_kline_row(row: Any, open_time: int | None = None, close_time: int | None = None) -> None:
    if not isinstance(row, list) or len(row) != 12:
        raise ValidationError("PREFIX_FIELD_COUNT_INVALID")
    try:
        integer_fields = [int(row[index]) for index in (0, 6, 8)]
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValidationError("KLINE_INTEGER_FIELD_INVALID") from exc
    if open_time is not None and integer_fields[0] != open_time:
        raise ValidationError("PREFIX_OPEN_TIME_INVALID")
    if close_time is not None and integer_fields[1] != close_time:
        raise ValidationError("PREFIX_CLOSE_TIME_INVALID")
    if integer_fields[1] != integer_fields[0] + 3_599_999:
        raise ValidationError("KLINE_CLOSE_RULE_INVALID")
    if integer_fields[2] < 0:
        raise ValidationError("KLINE_TRADE_COUNT_INVALID")
    for index in (1, 2, 3, 4, 5, 7, 9, 10, 11):
        try:
            number = Decimal(str(row[index]))
        except (InvalidOperation, TypeError, ValueError) as exc:
            raise ValidationError("KLINE_NUMERIC_FIELD_INVALID") from exc
        if not number.is_finite():
            raise ValidationError("KLINE_NONFINITE_FIELD")


def _validate_old_rest(raw: bytes, contract: FrozenContract) -> tuple[list[list[Any]], list[int]]:
    try:
        rows = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValidationError("V0R2_REST_JSON_INVALID") from exc
    if not isinstance(rows, list) or len(rows) != 720:
        raise ValidationError("V0R2_REST_ROWS_NOT_720")
    for row in rows:
        _assert_kline_row(row)
    opens = [int(row[0]) for row in rows]
    if opens[0] != contract.old_rest_first_open_ms or opens[-1] != contract.old_rest_last_open_ms:
        raise ValidationError("V0R2_REST_BOUNDARY_INVALID")
    if len(set(opens)) != 720 or any(right - left != 3_600_000 for left, right in zip(opens, opens[1:])):
        raise ValidationError("V0R2_REST_CONTINUITY_INVALID")
    return rows, opens


def _zip_open_times(path: Path, expected_member: str) -> list[int]:
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.namelist() != [expected_member]:
                raise ValidationError(f"ARCHIVE_MEMBER_IDENTITY_INVALID:{expected_member}")
            with archive.open(expected_member) as source:
                reader = csv.reader(io.TextIOWrapper(source, encoding="utf-8", newline=""))
                opens: list[int] = []
                for row in reader:
                    if not row:
                        continue
                    try:
                        opens.append(int(row[0]))
                    except ValueError:
                        if row[0] != "open_time":
                            raise ValidationError(f"ARCHIVE_OPEN_TIME_INVALID:{expected_member}")
                return opens
    except zipfile.BadZipFile as exc:
        raise ValidationError(f"ARCHIVE_ZIP_INVALID:{expected_member}") from exc


def verify_reuse(root: Path, contract: FrozenContract) -> dict[str, Any]:
    tracked = [V0R2_MANIFEST_REL, V0R2_SNAPSHOT_REL, V0R2_QUALIFICATION_REL, V0R2_RECEIPT_REL]
    old_file_hashes = {str(relative): _sha256_path(root / relative) for relative in tracked}
    snapshot = _load_json(root / V0R2_SNAPSHOT_REL)
    qualification = _load_json(root / V0R2_QUALIFICATION_REL)
    receipt = _load_json(root / V0R2_RECEIPT_REL)
    manifest = _load_json(root / V0R2_MANIFEST_REL)
    _assert_snapshot_digest(snapshot, contract)
    _assert_self_digest(qualification, "qualification_digest", contract.v0r2_qualification_digest)
    _assert_self_digest(receipt, "receipt_digest", contract.v0r2_receipt_digest)
    if snapshot.get("design_digest") != contract.design_digest:
        raise ValidationError("DESIGN_DIGEST_MISMATCH")
    if receipt.get("authoritative_response_sha256") != contract.v0r2_rest_sha256:
        raise ValidationError("V0R2_RECEIPT_REST_SHA_MISMATCH")

    identity = snapshot.get("identity", {})
    original = identity.get("reused_original_60")
    tail = identity.get("reused_2025_01")
    old_rest = identity.get("new_2019_12")
    if not isinstance(original, list) or len(original) != 60:
        raise ValidationError("ORIGINAL_60_IDENTITY_MISSING")
    periods = [f"{year}-{month:02d}" for year in range(2020, 2025) for month in range(1, 13)]
    if [row.get("calendar_period") for row in original] != periods:
        raise ValidationError("ORIGINAL_60_PERIODS_INVALID")
    if manifest.get("sources", {}).get("reused_original_60") != original:
        raise ValidationError("V0R2_MANIFEST_ORIGINAL_60_MISMATCH")

    cache = root / CACHE_REL
    cache_file_hashes: dict[str, str] = {}
    for row in original:
        local_sha = row.get("local_sha256")
        if row.get("status") != "MATERIALIZED_VERIFIED" or local_sha != row.get("official_checksum"):
            raise ValidationError("ORIGINAL_60_AUTHENTICATION_INVALID")
        archive_path = cache / f"{local_sha}.zip"
        _assert_file_sha(archive_path, str(local_sha), "ORIGINAL_60_CACHE_IDENTITY_INVALID")
        cache_file_hashes[str(archive_path.relative_to(root))] = str(local_sha)
    if not isinstance(tail, dict) or tail.get("local_sha256") != contract.tail_sha256:
        raise ValidationError("2025_01_IDENTITY_INVALID")
    if tail.get("official_checksum") != contract.tail_sha256 or tail.get("status") != "MATERIALIZED_VERIFIED":
        raise ValidationError("2025_01_AUTHENTICATION_INVALID")
    tail_path = cache / f"{contract.tail_sha256}.zip"
    _assert_file_sha(tail_path, contract.tail_sha256, "2025_01_CACHE_IDENTITY_INVALID")
    cache_file_hashes[str(tail_path.relative_to(root))] = contract.tail_sha256
    if not isinstance(old_rest, dict) or old_rest.get("response_sha256") != contract.v0r2_rest_sha256:
        raise ValidationError("V0R2_REST_IDENTITY_INVALID")
    if old_rest.get("row_count") != 720 or old_rest.get("status") != "MATERIALIZED_VERIFIED":
        raise ValidationError("V0R2_REST_METADATA_INVALID")
    old_rest_path = cache / f"{contract.v0r2_rest_sha256}.json"
    _assert_file_sha(old_rest_path, contract.v0r2_rest_sha256, "V0R2_REST_CACHE_IDENTITY_INVALID")
    cache_file_hashes[str(old_rest_path.relative_to(root))] = contract.v0r2_rest_sha256
    old_rows, old_opens = _validate_old_rest(old_rest_path.read_bytes(), contract)

    december = original[-1]
    december_member = december.get("archive_member_names", [None])
    tail_member = tail.get("archive_member_names", [None])
    if len(december_member) != 1 or len(tail_member) != 1:
        raise ValidationError("TARGET_ARCHIVE_MEMBER_COUNT_INVALID")
    december_opens = _zip_open_times(cache / f"{december['local_sha256']}.zip", december_member[0])
    january_opens = _zip_open_times(tail_path, tail_member[0])
    last_target_opens = [1_735_686_000_000 + index * 3_600_000 for index in range(24)]
    available = set(december_opens) | set(january_opens)
    if any(open_time not in available for open_time in last_target_opens):
        raise ValidationError("LAST_TARGET_24H_INCOMPLETE")

    return {
        "snapshot": snapshot,
        "qualification": qualification,
        "receipt": receipt,
        "manifest": manifest,
        "original": original,
        "tail": tail,
        "old_rest": old_rest,
        "old_rows": old_rows,
        "old_opens": old_opens,
        "old_file_hashes": old_file_hashes,
        "cache_file_hashes": cache_file_hashes,
        "last_target_24h_complete": True,
    }


def revalidate_reuse(root: Path, reuse: dict[str, Any]) -> None:
    """Close the post-request TOCTOU window before READY publication."""
    for relative, expected in reuse["cache_file_hashes"].items():
        _assert_file_sha(root / relative, expected, "REUSED_CACHE_CHANGED_AFTER_VERIFICATION")
    for relative, expected in reuse["old_file_hashes"].items():
        _assert_file_sha(root / relative, expected, "OLD_V0R2_MUTATED")


def _validate_prefix(response: FetchResponse, contract: FrozenContract) -> tuple[list[Any], str]:
    if response.status < 200 or response.status >= 300:
        raise ValidationError(f"PREFIX_HTTP_STATUS_INVALID:{response.status}")
    actual_sha = hashlib.sha256(response.body).hexdigest()
    try:
        rows = json.loads(response.body)
    except json.JSONDecodeError as exc:
        raise ValidationError("PREFIX_JSON_INVALID") from exc
    if not isinstance(rows, list):
        raise ValidationError("PREFIX_RESPONSE_NOT_ARRAY")
    if len(rows) != 1:
        raise ValidationError("PREFIX_ROW_COUNT_INVALID")
    row = rows[0]
    _assert_kline_row(row, contract.prefix_open_time_ms, contract.prefix_close_time_ms)
    return row, actual_sha


def _source_artifacts(
    contract: FrozenContract,
    claim: Claim,
    response: FetchResponse,
    prefix: list[Any],
    actual_sha: str,
    reuse: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    prefix_identity = {
        "source_role": "PREFIX_REST_OBJECT",
        "calendar_period": "2019-12-prefix",
        "purpose": "WARMUP_PREFIX",
        "endpoint": contract.endpoint,
        "canonical_query": contract.query,
        "http_status": response.status,
        "response_sha256": actual_sha,
        "cache_path": str(CACHE_REL / f"{actual_sha}.json"),
        "authoritative_response_bytes_location": "EMBEDDED_IN_THIS_SOURCE_IDENTITY",
        "authoritative_response_bytes_encoding": "base64",
        "authoritative_response_bytes_base64": base64.b64encode(response.body).decode("ascii"),
        "row_count": 1,
        "field_count": 12,
        "open_time_ms": int(prefix[0]),
        "close_time_ms": int(prefix[6]),
        "logical_close_boundary_ms": int(prefix[6]) + 1,
        "schema_identity": EXPECTED_SCHEMA,
        "product_identity": "Binance USD-M BTCUSDT",
        "interval_identity": "1h",
        "authentication": "PASS",
        "status": "MATERIALIZED_VERIFIED",
    }
    old_rest_identity = {
        **reuse["old_rest"],
        "source_role": "EXISTING_720_ROW_REST_OBJECT",
        "reused": True,
        "reacquired": False,
    }
    original = [{**row, "source_role": "ORIGINAL_MONTHLY_OBJECT", "reused": True, "reacquired": False} for row in reuse["original"]]
    tail = {**reuse["tail"], "source_role": "EXISTING_2025_01_OBJECT", "reused": True, "reacquired": False}
    source_objects = [prefix_identity, old_rest_identity, *original, tail]
    manifest_body = {
        "artifact_type": "JFP03_V0R3_SOURCE_MANIFEST",
        "schema_version": "jfp03-v0r3-source-manifest-v1",
        "project_id": PROJECT_ID,
        "design_digest": contract.design_digest,
        "predecessor_v0r2_snapshot_id": contract.v0r2_snapshot_id,
        "predecessor_v0r2_snapshot_digest": contract.v0r2_snapshot_digest,
        "source_object_count": 63,
        "source_objects": source_objects,
        "provenance": {
            "prefix_rest_object_separate": True,
            "existing_720_row_rest_object_separate": True,
            "original_60_reused": True,
            "original_60_reacquired": False,
            "2025_01_reused": True,
            "2025_01_reacquired": False,
            "v0r2_720_rest_reused": True,
            "v0r2_720_rest_reacquired": False,
        },
    }
    manifest = {**manifest_body, "source_manifest_digest": digest(manifest_body)}
    original_digest = digest(reuse["original"])
    snapshot_body = {
        "artifact_type": "JFP03_V0R3_IMMUTABLE_INPUT_SNAPSHOT",
        "schema_version": "jfp03-v0r3-input-snapshot-v1",
        "project_id": PROJECT_ID,
        "authority_level": "INPUT_MATERIALIZATION_ONLY",
        "design_digest": contract.design_digest,
        "predecessors": {
            "v0r2_snapshot_id": contract.v0r2_snapshot_id,
            "v0r2_snapshot_digest": contract.v0r2_snapshot_digest,
            "v0r2_qualification_digest": contract.v0r2_qualification_digest,
            "v0r2_materialization_receipt_digest": contract.v0r2_receipt_digest,
            "close_boundary_repair_project": CLOSE_REPAIR_PROJECT_ID,
            "prefix_authorization_project": AUTH_PROJECT_ID,
        },
        "source_manifest_digest": manifest["source_manifest_digest"],
        "source_bindings": {
            "original_60_identities_digest": original_digest,
            "original_60_count": 60,
            "authenticated_2025_01_sha256": contract.tail_sha256,
            "existing_720_row_rest_sha256": contract.v0r2_rest_sha256,
            "new_prefix_actual_response_sha256": actual_sha,
        },
        "source_object_count": 63,
        "logical_warmup": {
            "open_time_first_ms": contract.prefix_open_time_ms,
            "open_time_last_ms": contract.old_rest_last_open_ms,
            "logical_close_boundary_first_ms": contract.logical_close_boundary_ms,
            "logical_close_boundary_last_ms": contract.old_rest_last_open_ms + 3_600_000,
            "rows": 721,
            "gaps": 0,
            "duplicates": 0,
            "first_required_close_present": True,
            "first_har720_complete": True,
        },
        "last_target_24h_complete": True,
        "old_snapshots_mutated": False,
        "scientific_features_computed": False,
        "afi_computed": False,
        "har_computed": False,
        "targets_computed": False,
        "regression_executed": False,
        "hac_computed": False,
        "p_values_computed": False,
        "scientific_execution_authorized": False,
        "historical_execution_authorized": False,
        "jigsaw_evidence_authorized": False,
        "qnty_authorized": False,
        "trading_authorized": False,
        "capital_authority": "NONE",
    }
    snapshot_digest = digest(snapshot_body)
    snapshot = {
        **snapshot_body,
        "snapshot_id": f"jfp-input-v0r3-{snapshot_digest}",
        "snapshot_digest": snapshot_digest,
    }
    qualification_body = {
        "artifact_type": "JFP03_V0R3_INPUT_QUALIFICATION",
        "schema_version": "jfp03-v0r3-input-qualification-v1",
        "project_id": PROJECT_ID,
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_digest": snapshot_digest,
        "input_qualification": "READY",
        "authorization_claimed": True,
        "prefix_authenticated": True,
        "prefix_rows": 1,
        "prefix_schema": "PASS",
        "original_60_reused": True,
        "original_60_reacquired": False,
        "2025_01_reused": True,
        "2025_01_reacquired": False,
        "v0r2_720_rest_reused": True,
        "v0r2_720_rest_reacquired": False,
        "source_object_count": 63,
        "logical_warmup_rows": 721,
        "warmup_gaps": 0,
        "warmup_duplicates": 0,
        "first_required_close_present": True,
        "first_har720_complete": True,
        "last_target_24h_complete": True,
        "design_digest_match": True,
        "scientific_features_computed": False,
        "afi_computed": False,
        "har_computed": False,
        "targets_computed": False,
        "regression_executed": False,
        "hac_computed": False,
        "p_values_computed": False,
        "scientific_execution_authorized": False,
        "historical_execution_authorized": False,
        "jigsaw_evidence_authorized": False,
        "qnty_authorized": False,
        "trading_authorized": False,
        "capital_authority": "NONE",
    }
    qualification = {**qualification_body, "qualification_digest": digest(qualification_body)}
    receipt_body = {
        "artifact_type": "JFP03_V0R3_PREFIX_MATERIALIZATION_RECEIPT",
        "schema_version": "jfp03-v0r3-prefix-materialization-receipt-v1",
        "project_id": PROJECT_ID,
        "bound_authorization_project": AUTH_PROJECT_ID,
        "state": "CONSUMED_COMPLETE",
        "input_qualification": "READY",
        "expected_master": contract.expected_master,
        "claim": claim.__dict__,
        "atomic_claim": "PASS",
        "authorized_runs_allowed": 1,
        "authorized_runs_consumed_before": 0,
        "authorized_runs_consumed_after": 1,
        "prefix_endpoint": contract.endpoint,
        "prefix_query": contract.query,
        "prefix_http_status": response.status,
        "prefix_rows": 1,
        "prefix_open_time_ms": int(prefix[0]),
        "prefix_close_time_ms": int(prefix[6]),
        "prefix_field_count": len(prefix),
        "prefix_actual_response_sha256": actual_sha,
        "prefix_feasibility_response_sha256": contract.feasibility_sha256,
        "feasibility_hash_equal": actual_sha == contract.feasibility_sha256,
        "feasibility_hash_used_as_acceptance_gate": False,
        "original_60_reused": True,
        "original_60_reacquired": False,
        "2025_01_reused": True,
        "2025_01_sha256": contract.tail_sha256,
        "2025_01_reacquired": False,
        "v0r2_720_rest_reused": True,
        "v0r2_720_rest_sha256": contract.v0r2_rest_sha256,
        "v0r2_720_rest_reacquired": False,
        "total_source_objects": 63,
        "logical_warmup_rows": 721,
        "warmup_gaps": 0,
        "warmup_duplicates": 0,
        "first_required_close_present": True,
        "first_har720_complete": True,
        "last_target_24h_complete": True,
        "source_manifest_digest": manifest["source_manifest_digest"],
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_digest": snapshot_digest,
        "qualification_digest": qualification["qualification_digest"],
        "old_v0r2_mutated": False,
        "scientific_features_computed": False,
        "afi_computed": False,
        "har_computed": False,
        "targets_computed": False,
        "regression_executed": False,
        "hac_computed": False,
        "p_values_computed": False,
        "scientific_execution_authorized": False,
        "historical_execution_authorized": False,
        "jigsaw_evidence_authorized": False,
        "qnty_authorized": False,
        "trading_authorized": False,
        "capital_authority": "NONE",
        "downstream_authority": "NONE",
    }
    receipt = {**receipt_body, "receipt_digest": digest(receipt_body)}
    return manifest, snapshot, qualification, receipt


def _blocked_after_claim(root: Path, contract: FrozenContract, claim: Claim, error: Exception) -> dict[str, Any]:
    failure = f"{type(error).__name__}:{error}"
    qualification_body = {
        "artifact_type": "JFP03_V0R3_INPUT_QUALIFICATION",
        "schema_version": "jfp03-v0r3-input-qualification-v1",
        "project_id": PROJECT_ID,
        "input_qualification": "BLOCKED",
        "authorization_claimed": True,
        "failure": failure,
        "scientific_features_computed": False,
        "afi_computed": False,
        "har_computed": False,
        "targets_computed": False,
        "regression_executed": False,
        "hac_computed": False,
        "p_values_computed": False,
        "scientific_execution_authorized": False,
        "historical_execution_authorized": False,
        "jigsaw_evidence_authorized": False,
        "qnty_authorized": False,
        "trading_authorized": False,
        "capital_authority": "NONE",
    }
    qualification = {**qualification_body, "qualification_digest": digest(qualification_body)}
    _replace_json(root / V0R3_QUALIFICATION_REL, qualification)
    receipt_body = {
        "artifact_type": "JFP03_V0R3_PREFIX_MATERIALIZATION_RECEIPT",
        "schema_version": "jfp03-v0r3-prefix-materialization-receipt-v1",
        "project_id": PROJECT_ID,
        "bound_authorization_project": AUTH_PROJECT_ID,
        "state": "CONSUMED_BLOCKED",
        "input_qualification": "BLOCKED",
        "expected_master": contract.expected_master,
        "claim": claim.__dict__,
        "atomic_claim": "PASS",
        "authorized_runs_allowed": 1,
        "authorized_runs_consumed_before": 0,
        "authorized_runs_consumed_after": 1,
        "failure": failure,
        "qualification_digest": qualification["qualification_digest"],
        "scientific_computation_performed": False,
        "scientific_execution_authorized": False,
        "downstream_authority": "NONE",
    }
    receipt = {**receipt_body, "receipt_digest": digest(receipt_body)}
    _replace_json(root / V0R3_RECEIPT_REL, receipt)
    return {"qualification": qualification, "receipt": receipt}


def materialize(
    root: Path,
    *,
    contract: FrozenContract = FrozenContract(),
    fetcher: Fetcher = fetch_prefix_once,
    claim_backend: ClaimBackend | None = None,
    git_verifier: GitVerifier = verify_git,
) -> dict[str, Any]:
    root = root.resolve()
    git_verifier(root, contract)
    verify_authorization(root, contract)
    backend = claim_backend or RemoteGitClaim()
    claim = backend.claim(root, contract)
    try:
        reuse = verify_reuse(root, contract)
        response = fetcher(f"{contract.endpoint}?{contract.query}")
        prefix, actual_sha = _validate_prefix(response, contract)
        cache_path = root / CACHE_REL / f"{actual_sha}.json"
        try:
            _write_exclusive(cache_path, response.body)
        except FileExistsError as exc:
            raise ValidationError("PREFIX_CACHE_IDENTITY_ALREADY_EXISTS") from exc

        opens = [int(prefix[0]), *reuse["old_opens"]]
        if len(opens) != 721:
            raise ValidationError("LOGICAL_WARMUP_ROWS_NOT_721")
        if len(set(opens)) != 721:
            raise ValidationError("LOGICAL_WARMUP_DUPLICATES")
        if any(right - left != 3_600_000 for left, right in zip(opens, opens[1:])):
            raise ValidationError("LOGICAL_WARMUP_GAPS")
        if opens[0] != contract.prefix_open_time_ms or opens[-1] != contract.old_rest_last_open_ms:
            raise ValidationError("LOGICAL_WARMUP_BOUNDARY_INVALID")
        if opens[0] + 3_600_000 != contract.logical_close_boundary_ms:
            raise ValidationError("FIRST_REQUIRED_CLOSE_MISSING")

        manifest, snapshot, qualification, receipt = _source_artifacts(
            contract, claim, response, prefix, actual_sha, reuse
        )
        revalidate_reuse(root, reuse)
        _write_json_exclusive(root / V0R3_MANIFEST_REL, manifest)
        _write_json_exclusive(root / V0R3_SNAPSHOT_REL, snapshot)
        _write_json_exclusive(root / V0R3_QUALIFICATION_REL, qualification)
        _replace_json(root / V0R3_RECEIPT_REL, receipt)
        return {
            "manifest": manifest,
            "snapshot": snapshot,
            "qualification": qualification,
            "receipt": receipt,
        }
    except Exception as error:
        return _blocked_after_claim(root, contract, claim, error)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    args = parser.parse_args()
    result = materialize(args.root)
    print(json.dumps(result, sort_keys=True))
    return 0 if result["qualification"]["input_qualification"] == "READY" else 2


if __name__ == "__main__":
    raise SystemExit(main())
