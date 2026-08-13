from __future__ import annotations

import base64
import hashlib
import io
import json
import subprocess
import threading
import tomllib
import zipfile
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest

import qntylab.jfp03_v0r3_prefix_materialization as materializer
from qntylab.jfp03_v0r3_prefix_materialization import (
    AUTH_PROJECT_ID,
    AuthorizationAlreadyConsumed,
    BASE_REL,
    CACHE_REL,
    CLOSE_REPAIR_PROJECT_ID,
    EXPECTED_SCHEMA,
    FetchResponse,
    FrozenContract,
    LocalReceiptClaim,
    MaterializationError,
    PREFIX_URL,
    PROJECT_ID,
    RemoteGitClaim,
    V0R3_MANIFEST_REL,
    V0R3_QUALIFICATION_REL,
    V0R3_RECEIPT_REL,
    V0R3_SNAPSHOT_REL,
    canonical_bytes,
    digest,
    materialize,
)


ROOT = Path(__file__).resolve().parents[1]


def _zip_bytes(member: str, rows: list[list[Any]]) -> bytes:
    payload = io.StringIO(newline="")
    payload.write("open_time,open,high,low,close,volume,close_time,quote_volume,count,taker_buy_volume,taker_buy_quote_volume,ignore\n")
    for row in rows:
        payload.write(",".join(str(item) for item in row) + "\n")
    result = io.BytesIO()
    info = zipfile.ZipInfo(member, date_time=(2020, 1, 1, 0, 0, 0))
    info.compress_type = zipfile.ZIP_DEFLATED
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr(info, payload.getvalue())
    return result.getvalue()


def _row(open_time: int) -> list[Any]:
    return [open_time, "1", "2", "0.5", "1.5", "3", open_time + 3_599_999, "4", 5, "1", "2", "0"]


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value) + b"\n")


def _synthetic_repo(tmp_path: Path, *, old_rows: int = 720) -> tuple[Path, FrozenContract, bytes]:
    root = tmp_path / "repo"
    out = root / BASE_REL / "materialization"
    cache = root / CACHE_REL
    out.mkdir(parents=True)
    cache.mkdir(parents=True)

    placeholder_member = "placeholder.csv"
    placeholder_zip = _zip_bytes(placeholder_member, [_row(0)])
    placeholder_sha = hashlib.sha256(placeholder_zip).hexdigest()
    (cache / f"{placeholder_sha}.zip").write_bytes(placeholder_zip)
    december_member = "BTCUSDT-1h-2024-12.csv"
    december_zip = _zip_bytes(december_member, [_row(1_735_686_000_000)])
    december_sha = hashlib.sha256(december_zip).hexdigest()
    (cache / f"{december_sha}.zip").write_bytes(december_zip)
    january_member = "BTCUSDT-1h-2025-01.csv"
    january_zip = _zip_bytes(
        january_member,
        [_row(1_735_689_600_000 + index * 3_600_000) for index in range(23)],
    )
    january_sha = hashlib.sha256(january_zip).hexdigest()
    (cache / f"{january_sha}.zip").write_bytes(january_zip)

    periods = [f"{year}-{month:02d}" for year in range(2020, 2025) for month in range(1, 13)]
    original = []
    for period in periods:
        sha = december_sha if period == "2024-12" else placeholder_sha
        member = december_member if period == "2024-12" else placeholder_member
        original.append(
            {
                "calendar_period": period,
                "archive_member_names": [member],
                "local_sha256": sha,
                "official_checksum": sha,
                "status": "MATERIALIZED_VERIFIED",
            }
        )
    tail = {
        "calendar_period": "2025-01",
        "archive_member_names": [january_member],
        "local_sha256": january_sha,
        "official_checksum": january_sha,
        "status": "MATERIALIZED_VERIFIED",
    }
    old = [_row(1_575_244_800_000 + index * 3_600_000) for index in range(old_rows)]
    old_raw = canonical_bytes(old)
    old_sha = hashlib.sha256(old_raw).hexdigest()
    (cache / f"{old_sha}.json").write_bytes(old_raw)
    old_identity = {
        "calendar_period": "2019-12",
        "response_sha256": old_sha,
        "row_count": 720,
        "status": "MATERIALIZED_VERIFIED",
    }
    snapshot_body = {
        "artifact_type": "JFP03_V0R1_REPAIRED_SOURCE_IMMUTABLE_INPUT_SNAPSHOT",
        "project_id": "old",
        "design_digest": "synthetic-design",
        "identity": {
            "reused_original_60": original,
            "reused_2025_01": tail,
            "new_2019_12": old_identity,
        },
    }
    snapshot_digest = digest(snapshot_body)
    snapshot = {
        **snapshot_body,
        "snapshot_id": f"jfp-input-v0r2-{snapshot_digest}",
        "snapshot_digest": snapshot_digest,
    }
    qualification_body = {"artifact_type": "old-qualification", "snapshot_digest": snapshot_digest}
    qualification = {**qualification_body, "qualification_digest": digest(qualification_body)}
    receipt_body = {
        "artifact_type": "old-receipt",
        "authoritative_response_sha256": old_sha,
    }
    receipt = {**receipt_body, "receipt_digest": digest(receipt_body)}
    manifest = {
        "artifact_type": "old-manifest",
        "sources": {
            "reused_original_60": original,
            "reused_2025_01": tail,
            "new_2019_12": old_identity,
        },
    }
    _write_json(out / "v0r2_input_snapshot.json", snapshot)
    _write_json(out / "v0r2_input_qualification.json", qualification)
    _write_json(out / "v0r2_repaired_source_materialization_receipt.json", receipt)
    _write_json(out / "v0r2_repaired_source_manifest.json", manifest)

    contract = replace(
        FrozenContract(),
        expected_master="synthetic-master",
        authorization_base="synthetic-base",
        design_digest="synthetic-design",
        v0r2_snapshot_id=snapshot["snapshot_id"],
        v0r2_snapshot_digest=snapshot_digest,
        v0r2_qualification_digest=qualification["qualification_digest"],
        v0r2_receipt_digest=receipt["receipt_digest"],
        v0r2_rest_sha256=old_sha,
        tail_sha256=january_sha,
        feasibility_sha256="f" * 64,
        old_rest_last_open_ms=1_575_244_800_000 + (old_rows - 1) * 3_600_000,
    )
    auth = {
        "project_id": AUTH_PROJECT_ID,
        "expected_master": contract.authorization_base,
        "bound_design_digest": contract.design_digest,
        "future_materialization_contract": {
            "authorized_runs_allowed": 1,
            "authorized_runs_consumed_before_run": 0,
            "expected_master": contract.authorization_base,
            "atomic_pre_access_consumption_claim_required": True,
        },
        "authority_boundary": {
            "prefix_materialization_authorized": True,
            "scientific_execution_authorized": False,
            "historical_execution_authorized": False,
            "feature_computation_authorized": False,
            "target_computation_authorized": False,
            "regression_authorized": False,
            "hac_authorized": False,
            "p_values_authorized": False,
            "qnty_authorized": False,
            "trading_authorized": False,
        },
        "prefix_source_contract": {
            "endpoint": contract.endpoint,
            "canonical_query": contract.query,
            "expected_rows": 1,
            "expected_open_time_ms": contract.prefix_open_time_ms,
            "expected_close_time_ms": contract.prefix_close_time_ms,
            "expected_logical_close_boundary_ms": contract.logical_close_boundary_ms,
            "expected_field_count": 12,
            "feasibility_response_sha256": contract.feasibility_sha256,
            "feasibility_sha_authoritative_for_future_run": False,
        },
        "reuse_contract": {
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
        },
    }
    _write_json(out / "v0r3_prefix_materialization_authorization.json", auth)
    _write_json(
        root / BASE_REL / "close_boundary_repair_v0/close_boundary_source_contract_repair.json",
        {"project_id": CLOSE_REPAIR_PROJECT_ID},
    )
    _write_json(
        root / BASE_REL / "close_boundary_repair_v0/prefix_source_contract.json",
        {"source": {"endpoint": contract.endpoint, "canonical_query": contract.query}},
    )
    projects = root / "docs/state/projects.toml"
    projects.parent.mkdir(parents=True)
    projects.write_text(
        f'''schema_version = 1

[[project]]
project_id = "{AUTH_PROJECT_ID}"
state = "CLOSED_PASS"
authority_level = "PREFIX_MATERIALIZATION_AUTHORIZATION_ONLY"
prefix_materialization_runs_allowed = 1
prefix_materialization_performed = false
authorized_runs_consumed = 0
scientific_execution_authorized = false
'''
    )
    prefix_raw = canonical_bytes([_row(contract.prefix_open_time_ms)])
    return root, contract, prefix_raw


def _run(root: Path, contract: FrozenContract, body: bytes, calls: list[str]) -> dict[str, Any]:
    def fetcher(url: str) -> FetchResponse:
        receipt = json.loads((root / V0R3_RECEIPT_REL).read_text())
        assert receipt["state"] == "CLAIMED"
        calls.append(url)
        return FetchResponse(200, body)

    return materialize(
        root,
        contract=contract,
        fetcher=fetcher,
        claim_backend=LocalReceiptClaim(),
        git_verifier=lambda _root, _contract: None,
    )


def test_ready_claims_before_one_exact_request_and_hashes_actual_bytes(tmp_path: Path) -> None:
    root, contract, prefix_raw = _synthetic_repo(tmp_path)
    calls: list[str] = []
    result = _run(root, contract, prefix_raw, calls)
    assert calls == [PREFIX_URL]
    assert result["qualification"]["input_qualification"] == "READY"
    assert result["receipt"]["authorized_runs_consumed_after"] == 1
    assert result["receipt"]["prefix_actual_response_sha256"] == hashlib.sha256(prefix_raw).hexdigest()
    assert result["receipt"]["feasibility_hash_equal"] is False
    assert result["receipt"]["feasibility_hash_used_as_acceptance_gate"] is False
    assert result["snapshot"]["logical_warmup"]["rows"] == 721
    assert result["snapshot"]["source_object_count"] == 63
    assert len(result["manifest"]["source_objects"]) == 63
    assert result["manifest"]["source_objects"][0]["source_role"] == "PREFIX_REST_OBJECT"
    assert result["manifest"]["source_objects"][1]["source_role"] == "EXISTING_720_ROW_REST_OBJECT"
    assert all(result["qualification"][field] is False for field in ("afi_computed", "har_computed", "targets_computed", "regression_executed", "hac_computed", "p_values_computed"))


def test_second_invocation_fails_before_network(tmp_path: Path) -> None:
    root, contract, prefix_raw = _synthetic_repo(tmp_path)
    calls: list[str] = []
    _run(root, contract, prefix_raw, calls)
    with pytest.raises(MaterializationError, match="ALREADY_EXISTS"):
        _run(root, contract, prefix_raw, calls)
    assert calls == [PREFIX_URL]


def test_crash_after_claim_is_not_replayable(tmp_path: Path) -> None:
    root, contract, _ = _synthetic_repo(tmp_path)

    def crash(_url: str) -> FetchResponse:
        assert (root / V0R3_RECEIPT_REL).exists()
        raise SystemExit("synthetic crash")

    with pytest.raises(SystemExit):
        materialize(
            root,
            contract=contract,
            fetcher=crash,
            claim_backend=LocalReceiptClaim(),
            git_verifier=lambda _root, _contract: None,
        )
    with pytest.raises(MaterializationError, match="ALREADY_EXISTS"):
        materialize(
            root,
            contract=contract,
            fetcher=lambda _url: pytest.fail("network must not be reached"),
            claim_backend=LocalReceiptClaim(),
            git_verifier=lambda _root, _contract: None,
        )


@pytest.mark.parametrize(
    ("mutation", "failure"),
    [
        (lambda row, contract: row.__setitem__(0, contract.prefix_open_time_ms + 1), "PREFIX_OPEN_TIME_INVALID"),
        (lambda row, contract: row.__setitem__(6, contract.prefix_close_time_ms - 1), "PREFIX_CLOSE_TIME_INVALID"),
        (lambda row, contract: row.pop(), "PREFIX_FIELD_COUNT_INVALID"),
    ],
)
def test_wrong_prefix_shape_blocks_without_retry(tmp_path: Path, mutation: Any, failure: str) -> None:
    root, contract, _ = _synthetic_repo(tmp_path)
    row = _row(contract.prefix_open_time_ms)
    mutation(row, contract)
    calls: list[str] = []
    result = _run(root, contract, canonical_bytes([row]), calls)
    assert calls == [PREFIX_URL]
    assert result["qualification"]["input_qualification"] == "BLOCKED"
    assert failure in result["qualification"]["failure"]


def test_prefix_row_count_must_be_exactly_one(tmp_path: Path) -> None:
    root, contract, _ = _synthetic_repo(tmp_path)
    calls: list[str] = []
    result = _run(root, contract, canonical_bytes([]), calls)
    assert calls == [PREFIX_URL]
    assert result["qualification"]["input_qualification"] == "BLOCKED"
    assert "PREFIX_ROW_COUNT_INVALID" in result["qualification"]["failure"]


@pytest.mark.parametrize("kind", ["original", "tail", "rest"])
def test_frozen_reuse_identity_failure_blocks_without_reacquisition(tmp_path: Path, kind: str) -> None:
    root, contract, prefix_raw = _synthetic_repo(tmp_path)
    snapshot_path = root / BASE_REL / "materialization/v0r2_input_snapshot.json"
    snapshot = json.loads(snapshot_path.read_text())
    if kind == "original":
        path = root / CACHE_REL / f"{snapshot['identity']['reused_original_60'][0]['local_sha256']}.zip"
    elif kind == "tail":
        path = root / CACHE_REL / f"{contract.tail_sha256}.zip"
    else:
        path = root / CACHE_REL / f"{contract.v0r2_rest_sha256}.json"
    path.write_bytes(path.read_bytes() + b"tamper")
    calls: list[str] = []
    result = _run(root, contract, prefix_raw, calls)
    assert calls == []
    assert result["qualification"]["input_qualification"] == "BLOCKED"
    assert result["receipt"]["authorized_runs_consumed_after"] == 1


def test_720_row_existing_warmup_is_not_accepted_as_721(tmp_path: Path) -> None:
    root, contract, prefix_raw = _synthetic_repo(tmp_path, old_rows=719)
    calls: list[str] = []
    result = _run(root, contract, prefix_raw, calls)
    assert calls == []
    assert result["qualification"]["input_qualification"] == "BLOCKED"
    assert "V0R2_REST_ROWS_NOT_720" in result["qualification"]["failure"]


def test_concurrent_local_claim_has_exactly_one_winner(tmp_path: Path) -> None:
    root, contract, _ = _synthetic_repo(tmp_path)
    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def contender() -> None:
        barrier.wait()
        try:
            LocalReceiptClaim().claim(root, contract)
            outcomes.append("PASS")
        except FileExistsError:
            outcomes.append("FAIL")
        except MaterializationError:
            outcomes.append("FAIL")

    threads = [threading.Thread(target=contender) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(outcomes) == ["FAIL", "PASS"]


class _FakeRemoteGit:
    def __init__(self, *, existing: bool = False, reject_push: bool = False) -> None:
        self.existing = existing
        self.reject_push = reject_push
        self.calls: list[tuple[str, ...]] = []

    def __call__(
        self,
        _root: Path,
        *args: str,
        check: bool = True,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        del check, input_text
        self.calls.append(args)
        command = args[0]
        if command == "ls-remote":
            return subprocess.CompletedProcess(
                args,
                0 if self.existing else 2,
                "remote-commit\trefs/heads/claim\n" if self.existing else "",
                "",
            )
        if command == "rev-parse":
            return subprocess.CompletedProcess(args, 0, "tree-id\n", "")
        if command == "commit-tree":
            return subprocess.CompletedProcess(args, 0, "claim-commit\n", "")
        if command == "push":
            if self.existing or self.reject_push:
                return subprocess.CompletedProcess(args, 1, "", "non-fast-forward")
            self.existing = True
            return subprocess.CompletedProcess(args, 0, "ok\n", "")
        raise AssertionError(args)


def test_remote_git_claim_succeeds_once_then_replay_fails(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    fake = _FakeRemoteGit()
    backend = RemoteGitClaim(git_runner=fake)
    claim = backend.claim(root, FrozenContract())
    assert claim.mechanism == "REMOTE_GIT_REF_PLUS_O_EXCL_RECEIPT"
    assert claim.remote_commit == "claim-commit"
    assert json.loads((root / V0R3_RECEIPT_REL).read_text())["state"] == "CLAIMED"
    with pytest.raises(AuthorizationAlreadyConsumed, match="REMOTE_CLAIM_ALREADY_EXISTS"):
        backend.claim(root, FrozenContract())
    assert sum(call[0] == "push" for call in fake.calls) == 1


def test_remote_git_concurrent_push_rejection_fails_closed(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    fake = _FakeRemoteGit(reject_push=True)
    with pytest.raises(AuthorizationAlreadyConsumed, match="REMOTE_CLAIM_REJECTED"):
        RemoteGitClaim(git_runner=fake).claim(root, FrozenContract())
    assert not (root / V0R3_RECEIPT_REL).exists()


def test_remote_claim_survives_crash_before_local_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    fake = _FakeRemoteGit()

    def crash(*_args: Any, **_kwargs: Any) -> None:
        raise SystemExit("crash after remote push")

    monkeypatch.setattr(materializer, "_write_claim_receipt", crash)
    with pytest.raises(SystemExit):
        RemoteGitClaim(git_runner=fake).claim(root, FrozenContract())
    assert fake.existing is True
    with pytest.raises(AuthorizationAlreadyConsumed, match="REMOTE_CLAIM_ALREADY_EXISTS"):
        RemoteGitClaim(git_runner=fake).claim(root, FrozenContract())


@pytest.mark.parametrize("failure_point", ["manifest", "snapshot", "qualification", "receipt"])
def test_terminal_write_failure_leaves_blocked_qualification_and_receipt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failure_point: str,
) -> None:
    root, contract, prefix_raw = _synthetic_repo(tmp_path)
    target = {
        "manifest": root / V0R3_MANIFEST_REL,
        "snapshot": root / V0R3_SNAPSHOT_REL,
        "qualification": root / V0R3_QUALIFICATION_REL,
    }.get(failure_point)
    original_write = materializer._write_json_exclusive
    original_replace = materializer._replace_json

    def fail_write(path: Path, value: Any) -> None:
        original_write(path, value)
        if path == target:
            raise OSError(f"synthetic {failure_point} failure")

    def fail_replace(path: Path, value: Any) -> None:
        original_replace(path, value)
        if failure_point == "receipt" and path == root / V0R3_RECEIPT_REL and value.get("state") == "CONSUMED_COMPLETE":
            raise OSError("synthetic receipt failure")

    monkeypatch.setattr(materializer, "_write_json_exclusive", fail_write)
    monkeypatch.setattr(materializer, "_replace_json", fail_replace)
    result = _run(root, contract, prefix_raw, [])
    disk_qualification = json.loads((root / V0R3_QUALIFICATION_REL).read_text())
    disk_receipt = json.loads((root / V0R3_RECEIPT_REL).read_text())
    assert result["qualification"]["input_qualification"] == "BLOCKED"
    assert disk_qualification["input_qualification"] == "BLOCKED"
    assert disk_receipt["input_qualification"] == "BLOCKED"
    assert disk_receipt["qualification_digest"] == disk_qualification["qualification_digest"]


def test_post_request_reuse_mutation_blocks_before_ready_publication(tmp_path: Path) -> None:
    root, contract, prefix_raw = _synthetic_repo(tmp_path)
    old_rest = root / CACHE_REL / f"{contract.v0r2_rest_sha256}.json"

    def fetcher(_url: str) -> FetchResponse:
        old_rest.write_bytes(old_rest.read_bytes() + b"tamper")
        return FetchResponse(200, prefix_raw)

    result = materialize(
        root,
        contract=contract,
        fetcher=fetcher,
        claim_backend=LocalReceiptClaim(),
        git_verifier=lambda _root, _contract: None,
    )
    assert result["qualification"]["input_qualification"] == "BLOCKED"
    assert "REUSED_CACHE_CHANGED_AFTER_VERIFICATION" in result["qualification"]["failure"]
    assert not (root / V0R3_MANIFEST_REL).exists()
    assert not (root / V0R3_SNAPSHOT_REL).exists()


def test_schema_identity_is_frozen() -> None:
    assert EXPECTED_SCHEMA == [
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


def test_canonical_v0r3_artifacts_are_ready_and_self_authenticating() -> None:
    manifest = json.loads((ROOT / V0R3_MANIFEST_REL).read_text())
    snapshot = json.loads((ROOT / V0R3_SNAPSHOT_REL).read_text())
    qualification = json.loads((ROOT / V0R3_QUALIFICATION_REL).read_text())
    receipt = json.loads((ROOT / V0R3_RECEIPT_REL).read_text())
    assert manifest["source_manifest_digest"] == digest(
        {key: value for key, value in manifest.items() if key != "source_manifest_digest"}
    )
    snapshot_body = {key: value for key, value in snapshot.items() if key not in {"snapshot_id", "snapshot_digest"}}
    assert snapshot["snapshot_digest"] == digest(snapshot_body)
    assert snapshot["snapshot_id"] == f"jfp-input-v0r3-{snapshot['snapshot_digest']}"
    assert qualification["qualification_digest"] == digest(
        {key: value for key, value in qualification.items() if key != "qualification_digest"}
    )
    assert receipt["receipt_digest"] == digest(
        {key: value for key, value in receipt.items() if key != "receipt_digest"}
    )
    assert manifest["source_object_count"] == len(manifest["source_objects"]) == 63
    assert snapshot["logical_warmup"] == {
        "duplicates": 0,
        "first_har720_complete": True,
        "first_required_close_present": True,
        "gaps": 0,
        "logical_close_boundary_first_ms": 1_575_244_800_000,
        "logical_close_boundary_last_ms": 1_577_836_800_000,
        "open_time_first_ms": 1_575_241_200_000,
        "open_time_last_ms": 1_577_833_200_000,
        "rows": 721,
    }
    assert qualification["input_qualification"] == receipt["input_qualification"] == "READY"


def test_canonical_claim_and_response_bytes_are_frozen() -> None:
    manifest = json.loads((ROOT / V0R3_MANIFEST_REL).read_text())
    receipt = json.loads((ROOT / V0R3_RECEIPT_REL).read_text())
    prefix = manifest["source_objects"][0]
    raw = base64.b64decode(prefix["authoritative_response_bytes_base64"], validate=True)
    assert prefix["authoritative_response_bytes_location"] == "EMBEDDED_IN_THIS_SOURCE_IDENTITY"
    assert prefix["authoritative_response_bytes_encoding"] == "base64"
    assert hashlib.sha256(raw).hexdigest() == receipt["prefix_actual_response_sha256"]
    assert receipt["atomic_claim"] == "PASS"
    assert receipt["authorized_runs_consumed_before"] == 0
    assert receipt["authorized_runs_consumed_after"] == 1
    assert receipt["prefix_endpoint"] + "?" + receipt["prefix_query"] == PREFIX_URL
    assert receipt["prefix_rows"] == 1
    assert receipt["prefix_field_count"] == 12
    assert receipt["feasibility_hash_used_as_acceptance_gate"] is False


def test_canonical_consumption_closes_scientific_authority() -> None:
    registry = tomllib.loads((ROOT / "docs/state/projects.toml").read_text())
    authorization = next(row for row in registry["project"] if row["project_id"] == AUTH_PROJECT_ID)
    assert authorization["authorized_runs_consumed"] == 1
    assert authorization["prefix_materialization_performed"] is True
    snapshot = json.loads((ROOT / V0R3_SNAPSHOT_REL).read_text())
    assert snapshot["project_id"] == PROJECT_ID
    for field in (
        "scientific_features_computed",
        "afi_computed",
        "har_computed",
        "targets_computed",
        "regression_executed",
        "hac_computed",
        "p_values_computed",
        "scientific_execution_authorized",
        "historical_execution_authorized",
        "jigsaw_evidence_authorized",
        "qnty_authorized",
        "trading_authorized",
    ):
        assert snapshot[field] is False
