from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

import pytest

from qntylab import jh01_v1_prospective_operation_v0 as operation
from qntylab import jh01_v1_prospective_recorder_implementation_v0 as recorder


ROOT = Path(__file__).resolve().parents[1]
PANEL = tuple(json.loads((ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/preregistration.json").read_text())["frozen_target"]["ordered_20_symbol_panel"])
FIRST = recorder.FIRST_LIVE_ORIGIN


def fixture_bars() -> tuple[recorder.Bar, ...]:
    start, end = datetime(2025, 8, 15, tzinfo=UTC), FIRST
    values: list[recorder.Bar] = []
    hours = int((end - start).total_seconds() // 3600)
    for offset in range(hours + 1):
        close = start + timedelta(hours=offset)
        for index, symbol in enumerate(PANEL):
            price = 100 + index + 0.01 * offset + 0.1 * ((offset + index) % 7)
            raw = (int((close - timedelta(hours=1)).timestamp() * 1000), str(price), str(price), str(price), str(price), "1", int((close - timedelta(milliseconds=1)).timestamp() * 1000), "1", 1, "1", "1", "0")
            values.append(recorder.Bar(symbol, close, price, raw))
    return tuple(values)


@pytest.fixture(scope="module")
def bars() -> tuple[recorder.Bar, ...]:
    return fixture_bars()


class FakeTransport:
    def __init__(self, origin: datetime):
        self.origin = origin
        self.release: recorder.RemoteRelease | None = None
        self.create_calls = 0
        self.upload_calls = 0

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
        self.release = recorder.RemoteRelease(release.origin_id, release.tag, release.artifact_digest, release.asset_name, release.asset_sha256, self.origin + timedelta(minutes=10), target_commit=release.target_commit, immutable=True, repository_id="repo", owner_id="owner", release_id=7, purl=f"pkg:github/CipherCuttle/QntyLab@{release.tag}", package_id="repo")
        return self.release

    def acquire_attestation(self, release: recorder.RemoteRelease):
        return b"synthetic-bundle", b"synthetic-root\n"


class FakeVerifier:
    def verify(self, *, asset: bytes, bundle: bytes, trusted_root: bytes, expectation: recorder.AttestationExpectation):
        assert bundle == b"synthetic-bundle"
        assert trusted_root == b"synthetic-root\n"
        return recorder.VerifiedAttestation(expectation, FIRST + timedelta(minutes=20), bundle, trusted_root)


def make_operation(tmp_path: Path) -> operation.Operation:
    return operation.Operation(ROOT, tmp_path / "state")


def test_authority_binding_schedule_and_recorder_identity(tmp_path):
    contract = operation.build_activation_contract(ROOT)
    assert contract["canonical_authorization_identity"]["canonical_merge"] == operation.AUTHORIZATION_CANONICAL_MERGE
    assert contract["qualified_recorder_implementation_identity"] == recorder.implementation_identity()
    assert contract["qualified_recorder_implementation_identity"] == operation.EXPECTED_RECORDER_SOURCE_DIGEST
    assert operation.required_origins()[0] == datetime(2026, 9, 15, tzinfo=UTC)
    assert operation.required_origins()[-1] == datetime(2027, 9, 14, tzinfo=UTC)
    assert len(operation.required_origins()) == 365
    assert operation.schedule_digest() == contract["schedule_digest"]


def test_synthetic_activation_is_one_campaign_and_no_peek_status(tmp_path):
    op = make_operation(tmp_path)
    before = op.status(now=FIRST - timedelta(hours=2))
    assert before["campaign_state"] == "UNARMED"
    assert before["next_origin_due_state"] == "NOT_DUE"
    activated = op.activate(activation_time=FIRST - timedelta(days=1), synthetic=True)
    assert activated["campaign_state"] == "ARMED_BUT_INACTIVE"
    assert activated["next_required_origin"] == "2026-09-15T00:00:00Z"
    assert "MSE" not in json.dumps(activated).upper()
    assert "P_VALUE" not in json.dumps(activated).upper()
    with pytest.raises(operation.OperationBlocked, match="second activation"):
        op.activate(activation_time=FIRST - timedelta(days=1), synthetic=True)
    with pytest.raises(operation.OperationBlocked, match="NOT_AUTHORIZED"):
        op.activate(activation_time=FIRST - timedelta(days=1), synthetic=False)


def test_exact_next_origin_due_and_missed_window_blocks_without_skip(tmp_path):
    op = make_operation(tmp_path)
    op.activate(activation_time=FIRST - timedelta(days=1), synthetic=True)
    assert op.status(now=FIRST - timedelta(minutes=1))["next_origin_due_state"] == "NOT_DUE"
    assert op.status(now=FIRST + timedelta(minutes=1))["next_origin_due_state"] == "DUE"
    missed = op.record_due(now=FIRST + timedelta(hours=1), bars=(), runtime=None, target_commit="a" * 40, offline_reverify=None)  # type: ignore[arg-type]
    assert missed["origin_state"] == "BLOCKED_MISSED_WINDOW"
    assert missed["origin_utc"] == "2026-09-15T00:00:00Z"
    assert op.status(now=FIRST + timedelta(days=2))["blocked_origin_count"] == 1
    assert op.status(now=FIRST + timedelta(days=2))["next_required_origin"] == "2026-09-15T00:00:00Z"


def test_full_synthetic_due_path_reuses_qualified_primitives_and_retention(tmp_path, bars):
    op = make_operation(tmp_path)
    op.activate(activation_time=FIRST - timedelta(days=1), synthetic=True)
    transport = FakeTransport(FIRST)
    runtime = recorder.PublicationRuntime(transport, FakeVerifier())
    verified_packages: list[Path] = []

    def offline(package: Path) -> None:
        recorder.verify_retention_package(package)
        verified_packages.append(package)

    receipt = op.record_due(now=FIRST + timedelta(minutes=1), bars=bars, runtime=runtime, target_commit="a" * 40, offline_reverify=offline)
    assert receipt["origin_state"] == "RECORDED"
    assert receipt["publication_state"] == "ORIGIN_COMPLETE"
    assert receipt["attestation_status"] == "VERIFIED"
    assert receipt["offline_reverification_status"] == "VERIFIED"
    assert len(verified_packages) == 1
    status = op.status(now=FIRST + timedelta(minutes=2))
    assert status["completed_origin_count"] == 1
    assert status["next_required_origin"] == "2026-09-16T00:00:00Z"
    assert status["next_origin_due_state"] == "NOT_DUE"
    assert all(metric not in status for metric in ("mse", "mae", "p_value", "relative_mse_reduction", "clark_west_statistic", "candidate_ranking", "scientific_classification"))


def test_wrapper_model_values_match_qualified_builder_without_mutating_recorder(bars):
    qualification_origin = FIRST + timedelta(hours=1)
    qualified = recorder.build_forecast_artifact(ROOT, bars + tuple(
        recorder.Bar(symbol, qualification_origin, 200.0 + index, (int((qualification_origin - timedelta(hours=1)).timestamp() * 1000), "1", "1", "1", str(200.0 + index), "1", int((qualification_origin - timedelta(milliseconds=1)).timestamp() * 1000), "1", 1, "1", "1", "0"))
        for index, symbol in enumerate(PANEL)
    ), origin=qualification_origin, qualification_mode=True)
    qualified_bars = bars + tuple(
        recorder.Bar(symbol, qualification_origin, 200.0 + index, (int((qualification_origin - timedelta(hours=1)).timestamp() * 1000), "1", "1", "1", str(200.0 + index), "1", int((qualification_origin - timedelta(milliseconds=1)).timestamp() * 1000), "1", 1, "1", "1", "0"))
        for index, symbol in enumerate(PANEL)
    )
    operational = operation._operational_artifact(ROOT, qualified_bars, origin=qualification_origin)
    for key in ("C_JH01", "B0", "B1", "B3", "training_origin_count", "training_first_origin", "training_last_origin"):
        assert operational[key] == qualified[key]
    assert operational["qualification_mode"] is False
    assert sha256((ROOT / "qntylab/jh01_v1_prospective_recorder_implementation_v0.py").read_bytes()).hexdigest() == operation.EXPECTED_RECORDER_SOURCE_DIGEST
