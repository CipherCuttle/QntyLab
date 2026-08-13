from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from qntylab.jfp03_repaired_source_materialization import (
    HISTORICAL_FEASIBILITY_SHA256,
    run,
)


def _fixture(tmp_path: Path) -> tuple[Path, Path, list[dict]]:
    root = tmp_path / "repo"
    out = root / "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/materialization"
    out.mkdir(parents=True)
    periods = [f"{year}-{month:02d}" for year in range(2020, 2025) for month in range(1, 13)]
    identities = [
        {"calendar_period": period, "status": "MATERIALIZED_VERIFIED", "local_sha256": f"{index:064x}", "official_checksum": f"{index:064x}"}
        for index, period in enumerate(periods, 1)
    ]
    identities += [{"calendar_period": "2019-12", "status": "SOURCE_OBJECT_NOT_PUBLISHED", "local_sha256": None, "official_checksum": None}]
    identities += [{"calendar_period": "2025-01", "status": "MATERIALIZED_VERIFIED", "local_sha256": "9ebc05c9b3d5ab3591edf65bc5c7e5dbc2f96c1efc4adc4ea198c651a99a41b1", "official_checksum": "9ebc05c9b3d5ab3591edf65bc5c7e5dbc2f96c1efc4adc4ea198c651a99a41b1"}]
    prior = {"snapshot_id": "prior", "snapshot_digest": "ffd6711cbc443507190a29004dad73324866c017fe440301b7fd99cd9110db5e", "identity_semantics": {"ordered_authenticated_object_identities": identities}}
    auth = {"project_id": "JIGSAW_FAST_PROSPECTIVE_SIGNAL_DISCOVERY_JFP03_V0R1_REPAIRED_SOURCE_MATERIALIZATION_AUTHORIZATION_V0", "bound_design_digest": "a52d4999038e0be814ee8770322303fce84bed9ec8941b812748a18867633736", "authorization": {"materialization_performed": False, "exactly_one_future_materialization_run": True}}
    (out / "v0r1_snapshot_manifest.json").write_text(json.dumps(prior))
    (out / "v0r1_repaired_source_materialization_authorization.json").write_text(json.dumps(auth))
    (out / "v0r1_supplemental_source_census.json").write_text("{}")
    captured = tmp_path / "captured"
    captured.mkdir()
    rows = [[1575244800000 + index * 3600000, "1", "1", "1", str(index), "1", 1575248399999 + index * 3600000, "1", 1, "1", "1", "0"] for index in range(720)]
    (captured / "rest.json").write_text(json.dumps(rows, separators=(",", ":")))
    return root, captured, identities


def test_actual_response_sha_is_authoritative_and_feasibility_sha_is_informational(tmp_path: Path) -> None:
    root, captured, _ = _fixture(tmp_path)
    result = run(root, captured)
    actual = hashlib.sha256((captured / "rest.json").read_bytes()).hexdigest()
    assert actual != HISTORICAL_FEASIBILITY_SHA256
    assert result["receipt"]["authoritative_response_sha256"] == actual
    assert result["receipt"]["historical_feasibility_sha256_equal"] is False


def test_second_invocation_fails_closed_without_writing(tmp_path: Path) -> None:
    root, captured, _ = _fixture(tmp_path)
    run(root, captured)
    output = root / "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/materialization/v0r2_repaired_source_materialization_receipt.json"
    before = output.read_bytes()
    with pytest.raises(ValueError, match="AUTHORIZATION_ALREADY_CONSUMED"):
        run(root, captured)
    assert output.read_bytes() == before


@pytest.mark.parametrize("mutation", ["snapshot", "placeholder"])
def test_prior_identity_bindings_fail_closed(tmp_path: Path, mutation: str) -> None:
    root, captured, identities = _fixture(tmp_path)
    path = root / "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/materialization/v0r1_snapshot_manifest.json"
    prior = json.loads(path.read_text())
    if mutation == "snapshot":
        prior["snapshot_digest"] = "wrong"
    else:
        identities[60]["status"] = "MATERIALIZED_VERIFIED"
        prior["identity_semantics"]["ordered_authenticated_object_identities"] = identities
    path.write_text(json.dumps(prior))
    with pytest.raises(ValueError, match="(PRIOR_SNAPSHOT_DIGEST_MISMATCH|MISSING_2019_12_PLACEHOLDER_BINDING)"):
        run(root, captured)
    assert not list((root / "experiments/research/jigsaw_fast_prospective_signal_discovery_v0/materialization").glob("v0r2_*"))
