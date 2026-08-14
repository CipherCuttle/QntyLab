from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
import json
import hashlib
import io
import zipfile
import pytest

from qntylab import jh01_v1_prospective_recorder_implementation_v0 as recorder


ROOT = Path(__file__).resolve().parents[1]
RESULT = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/prospective_recorder_and_input_materialization_implementation_v0.json"
GO = Path("/tmp/qntylab-go-toolchain/go/bin/go")
QUALIFICATION_ORIGIN = recorder.FIRST_LIVE_ORIGIN + timedelta(hours=1)
PANEL = json.loads((ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/preregistration.json").read_text())["frozen_target"]["ordered_20_symbol_panel"]


def fixture_bars() -> tuple[recorder.Bar, ...]:
    start, end = datetime(2025, 8, 15, tzinfo=UTC), datetime(2026, 9, 15, 1, tzinfo=UTC)
    values = []
    hours = int((end - start).total_seconds() // 3600)
    for offset in range(hours + 1):
        close = start + timedelta(hours=offset)
        for index, symbol in enumerate(PANEL):
            price = 100 + index + 0.01 * offset + 0.1 * ((offset + index) % 7)
            values.append(recorder.Bar(symbol, close, price, (int((close - timedelta(hours=1)).timestamp() * 1000), str(price), str(price), str(price), str(price), "1", int((close - timedelta(milliseconds=1)).timestamp() * 1000), "1", 1, "1", "1", "0")))
    return tuple(values)


@pytest.fixture(scope="module")
def bars() -> tuple[recorder.Bar, ...]: return fixture_bars()


def test_frozen_fixture_recorder_implements_source_range_models_and_artifact(bars):
    artifact = recorder.build_forecast_artifact(ROOT, bars, origin=QUALIFICATION_ORIGIN, qualification_mode=True)
    assert artifact["first_required_source_close"] == "2025-08-15T00:00:00Z"
    assert artifact["training_origin_count"] == 365
    assert artifact["training_first_origin"] == "2025-09-14T00:00:00Z"
    assert artifact["training_last_origin"] == "2026-09-13T00:00:00Z"
    assert set(("C_JH01", "B0", "B1", "B3")) <= artifact.keys()
    assert artifact["B3"]["monthly_coefficient"] == artifact["B3"]["monthly_coefficient"]
    assert artifact["forecast_artifact_canonical_digest"] == recorder.digest({key: value for key, value in artifact.items() if key != "forecast_artifact_canonical_digest"})
    assert "p_value" not in artifact and "realized_target" not in artifact


def test_determinism_activation_and_origin_recovery(bars):
    first = recorder.build_forecast_artifact(ROOT, bars, origin=QUALIFICATION_ORIGIN, qualification_mode=True)
    second = recorder.build_forecast_artifact(ROOT, bars, origin=QUALIFICATION_ORIGIN, qualification_mode=True)
    assert recorder.canonical_bytes(first) == recorder.canonical_bytes(second)
    with pytest.raises(recorder.RecorderBlocked, match="REAL_V1_ACTIVATION_REQUIRED"):
        recorder.build_forecast_artifact(ROOT, bars, origin=recorder.FIRST_LIVE_ORIGIN, qualification_mode=True)
    existing = {"origin_identity": recorder.origin_identity(QUALIFICATION_ORIGIN), "artifact_digest": first["forecast_artifact_canonical_digest"]}
    assert recorder.recover_publication(existing, first) == "IDEMPOTENT_AUTHORITATIVE_RECOVERY"
    with pytest.raises(recorder.RecorderBlocked, match="different digest"):
        recorder.recover_publication({**existing, "artifact_digest": "0" * 64}, first)


@pytest.mark.parametrize("mutation", ["future", "duplicate", "missing", "open", "wrong_symbol", "wrong_raw_close"])
def test_source_negative_matrix_fails_closed(bars, mutation):
    changed = list(bars)
    if mutation == "future": changed.append(recorder.Bar(PANEL[0], recorder.FIRST_LIVE_ORIGIN + timedelta(hours=1), 123.0, (0,) * 12))
    elif mutation == "duplicate": changed.append(changed[0])
    elif mutation == "missing": changed = [bar for bar in changed if not (bar.symbol == PANEL[0] and bar.logical_close == datetime(2025, 8, 20, tzinfo=UTC))]
    elif mutation == "open": changed[0] = recorder.Bar(changed[0].symbol, changed[0].logical_close, changed[0].close, changed[0].raw_row, False)
    elif mutation == "wrong_symbol": changed[0] = recorder.Bar("WRONG", changed[0].logical_close, changed[0].close, changed[0].raw_row)
    else: changed[0] = recorder.Bar(changed[0].symbol, changed[0].logical_close, changed[0].close, (0, *changed[0].raw_row[1:]))
    with pytest.raises(recorder.RecorderBlocked): recorder.build_forecast_artifact(ROOT, changed, origin=QUALIFICATION_ORIGIN, qualification_mode=True)


def test_retention_package_is_complete_and_tamper_fails(bars, tmp_path):
    forecast = recorder.build_forecast_artifact(ROOT, bars, origin=QUALIFICATION_ORIGIN, qualification_mode=True)
    manifest = recorder.retention_package(tmp_path, forecast=forecast, release_metadata={"informational": True}, bundle=b"fixture-bundle", trusted_root=b"fixture-root\n")
    assert set(manifest["files"]) == {"forecast.json", "release_metadata.json", "release_attestation.sigstore.json", "trusted_root.jsonl"}
    recorder.verify_retention_package(tmp_path)
    (tmp_path / "forecast.json").write_bytes(b"{}")
    with pytest.raises(recorder.RecorderBlocked): recorder.verify_retention_package(tmp_path)


def test_qualified_v0r3_offline_verifier_runs_with_no_network():
    recorder.offline_reverify_v0r3_qualified_package(ROOT, go_binary=GO)


def test_direct_source_seam_rejects_reordered_frozen_panel(bars):
    with pytest.raises(recorder.RecorderBlocked, match="wrong ordered panel"):
        recorder.source_manifest(bars, panel=list(reversed(PANEL)), origin=QUALIFICATION_ORIGIN, first_required_close=datetime(2025, 8, 15, tzinfo=UTC))


def test_qualification_receipt_preserves_frozen_inputs_and_blocks_real_v1():
    result = json.loads(RESULT.read_text())
    prereg = ROOT / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/preregistration.json"
    assert result["state"] == "CLOSED_BLOCKED"
    assert hashlib.sha256(prereg.read_bytes()).hexdigest() == result["frozen_inputs"]["v1_preregistration_bytes_sha256"]
    assert result["frozen_inputs"]["first_required_source_close"] == "2025-08-15T00:00:00Z"
    assert result["frozen_inputs"]["obsolete_historical_boundary_consumed"] is False
    assert result["qualification"]["synthetic_live_canary_used"] is False
    assert result["block_reason"].startswith("CURRENT_ORIGIN_GITHUB_SIGSTORE_ATTESTATION")
    assert result["authority"]["v0r3_implementation_authorization_consumed"] is True
    assert not any(value for key, value in result["authority"].items() if key != "v0r3_implementation_authorization_consumed")


class FakeTransport:
    def __init__(self, *, origin: datetime, fail_create=False, fail_upload=False, ambiguous=False):
        self.origin, self.fail_create, self.fail_upload, self.ambiguous = origin, fail_create, fail_upload, ambiguous
        self.release = None; self.create_calls = self.upload_calls = self.attestation_calls = 0
    def find(self, origin_id):
        if self.ambiguous and self.release: return (self.release, self.release)
        return () if self.release is None else (self.release,)
    def create(self, release):
        self.create_calls += 1; self.release = recorder.RemoteRelease(*release.__dict__.values())
        self.release = recorder.RemoteRelease(self.release.origin_id, self.release.tag, self.release.artifact_digest, self.release.asset_name, None, self.origin + timedelta(minutes=1))
        if self.fail_create and self.create_calls == 1: raise recorder.UnknownWrite()
        return self.release
    def upload(self, tag, asset_name, content):
        self.upload_calls += 1; self.release = recorder.RemoteRelease(self.release.origin_id, tag, self.release.artifact_digest, asset_name, hashlib.sha256(content).hexdigest(), self.release.published_at)
        if self.fail_upload and self.upload_calls == 1: raise recorder.UnknownWrite()
        return self.release
    def acquire_attestation(self, release):
        self.attestation_calls += 1; return b"current-fixture-bundle", b"current-fixture-root\n"


class FakeVerifier:
    def verify(self, *, asset, bundle, trusted_root, expectation):
        if bundle != b"current-fixture-bundle" or trusted_root != b"current-fixture-root\n": raise recorder.RecorderBlocked("invalid synthetic attestation")
        return recorder.VerifiedAttestation(expectation, QUALIFICATION_ORIGIN + timedelta(minutes=2), bundle, trusted_root)


def test_publication_runtime_crash_recovery_timing_and_concurrency(bars):
    artifact = recorder.build_forecast_artifact(ROOT, bars, origin=QUALIFICATION_ORIGIN, qualification_mode=True)
    transport = FakeTransport(origin=QUALIFICATION_ORIGIN, fail_create=True, fail_upload=True)
    states, release, verified = recorder.PublicationRuntime(transport, FakeVerifier()).publish(artifact, origin=QUALIFICATION_ORIGIN, target_commit="a" * 40)
    assert states[-1] is recorder.OriginState.ORIGIN_COMPLETE
    assert transport.create_calls == transport.upload_calls == 1
    assert release.asset_sha256 == hashlib.sha256(recorder.canonical_bytes(artifact)).hexdigest()
    assert verified.tsa_timestamp == QUALIFICATION_ORIGIN + timedelta(minutes=2)
    with pytest.raises(recorder.RecorderBlocked, match="outside"):
        recorder.PublicationRuntime(FakeTransport(origin=QUALIFICATION_ORIGIN - timedelta(hours=2)), FakeVerifier()).publish(artifact, origin=QUALIFICATION_ORIGIN, target_commit="a" * 40)


def test_canonical_binance_archive_seam_rejects_malformed_numeric_row():
    row = "1755212400000,100,101,99,100.5,1,1755215999999,0,1,0,0,0\n"
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive: archive.writestr("ALICEUSDT-1h-2025-08.csv", row)
    good = stream.getvalue(); checksum = f"{hashlib.sha256(good).hexdigest()} ALICEUSDT-1h-2025-08.zip"
    assert len(recorder.bars_from_authenticated_archive(symbol="ALICEUSDT", year=2025, month=8, zip_bytes=good, checksum_text=checksum)) == 1
    broken = io.BytesIO()
    with zipfile.ZipFile(broken, "w") as archive: archive.writestr("ALICEUSDT-1h-2025-08.csv", row.replace("100.5", "not-a-number"))
    payload = broken.getvalue()
    with pytest.raises(recorder.RecorderBlocked): recorder.bars_from_authenticated_archive(symbol="ALICEUSDT", year=2025, month=8, zip_bytes=payload, checksum_text=f"{hashlib.sha256(payload).hexdigest()} ALICEUSDT-1h-2025-08.zip")


def test_current_origin_crypto_verifier_has_no_unsafe_manifest_fallback(tmp_path):
    expectation = recorder.AttestationExpectation("CipherCuttle/QntyLab", "fixture-tag", "a" * 40, "forecast.json", "0" * 64)
    with pytest.raises(recorder.RecorderBlocked, match="generic per-origin Sigstore verifier unavailable"):
        recorder.ExternalSigstoreVerifier(tmp_path / "missing").verify(asset=b"fixture", bundle=b"bundle", trusted_root=b"root", expectation=expectation)


class _Response:
    def __init__(self, status, payload):
        self.status = status
        self._payload = payload
        self.headers = {"content-type": "application/json"}

    def read(self):
        return json.dumps(self._payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _ReleaseHTTP:
    def __init__(self, origin):
        self.origin = origin
        self.release = None
        self.asset = None

    def __call__(self, request, timeout):
        path = request.full_url.split("github.com", 1)[-1]
        if request.method == "GET" and path == "/repos/CipherCuttle/QntyLab":
            return _Response(200, {"id": 1317911390, "owner": {"id": 97258089}})
        if request.method == "GET" and "/releases/tags/" in path:
            return _Response(200, self.release) if self.release else _Response(404, {})
        if request.method == "POST" and path == "/repos/CipherCuttle/QntyLab/releases":
            body = json.loads(request.data)
            self.release = {"id": 991, "tag_name": body["tag_name"], "target_commitish": body["target_commitish"], "published_at": None, "immutable": False, "assets": []}
            return _Response(201, self.release)
        if request.method == "POST" and "/assets?name=forecast.json" in path:
            self.asset = {"name": "forecast.json", "digest": "sha256:" + hashlib.sha256(request.data).hexdigest()}
            self.release["assets"] = [self.asset]
            return _Response(201, self.asset)
        if request.method == "PATCH" and path.endswith("/releases/991"):
            self.release.update({"published_at": self.origin.isoformat().replace("+00:00", "Z"), "immutable": True})
            return _Response(200, self.release)
        raise AssertionError((request.method, path))


def test_concrete_github_transport_reads_back_publish_and_immutability():
    origin = QUALIFICATION_ORIGIN
    opener = _ReleaseHTTP(origin)
    transport = recorder.GitHubReleaseTransport(token="test-token", opener=opener)
    expected = recorder.RemoteRelease("o" * 64, "jh01-v1-recorder-" + "o" * 24, "a" * 64, "forecast.json", None, None, target_commit="b" * 40)
    created = transport.create(expected)
    assert created.release_id == 991 and created.published_at is None
    uploaded = transport.upload(expected.tag, "forecast.json", b"artifact")
    assert uploaded.asset_sha256 == hashlib.sha256(b"artifact").hexdigest()
    published = transport.publish(uploaded)
    assert published.immutable is True and published.published_at == origin
    assert published.repository_id == "1317911390" and published.owner_id == "97258089"
