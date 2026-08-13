from __future__ import annotations

import hashlib
import json
from pathlib import Path

from qntylab import project_context


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "experiments/research/jigsaw_fast_prospective_signal_discovery_v0"
CENSUS = BASE / "materialization/v0r1_supplemental_source_census.json"
AUTH = BASE / "materialization/v0r1_input_materialization_authorization.json"
ORIGINAL = BASE / "materialization/per_source_manifest.json"


def digest_without(value: dict, field: str) -> str:
    body = {key: item for key, item in value.items() if key != field}
    encoded = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_exact_v0r1_census_and_immutable_bindings() -> None:
    census = json.loads(CENSUS.read_text())
    original = json.loads(ORIGINAL.read_text())
    existing = [row["calendar_period"] for row in original["source_objects"] if row["candidate_id"] == "JFP03"]
    assert len(existing) == 60
    assert census["object_classifications"]["reuse_existing_authenticated"]["calendar_periods"] == existing
    assert census["object_classifications"]["reuse_existing_authenticated"]["count"] == 60
    supplemental = census["object_classifications"]["new_supplemental_objects"]
    assert [(row["calendar_period"], row["purpose"]) for row in supplemental] == [("2019-12", "WARMUP"), ("2025-01", "FUTURE_TAIL")]
    assert census["required_support_interval"] == {
        "earliest_required_close": "2019-12-02T00:00:00Z",
        "latest_required_close": "2025-01-01T23:00:00Z",
        "derivation": census["required_support_interval"]["derivation"],
        "market_values_inspected": False,
        "scientific_computation_performed": False,
    }
    assert census["census_digest"] == digest_without(census, "census_digest")


def test_authorization_is_materialization_only_and_sole_active_project() -> None:
    auth = json.loads(AUTH.read_text())
    assert auth["authorization_digest"] == digest_without(auth, "authorization_digest")
    assert auth["bound_design_digest"] == "a52d4999038e0be814ee8770322303fce84bed9ec8941b812748a18867633736"
    assert auth["bound_original_authenticated_object_count"] == 60
    assert auth["prohibitions"]["input_reacquisition_of_existing_60"] is False
    assert all(value is False for key, value in auth["prohibitions"].items() if key not in {"capital", "downstream_authority"})
    _, _, registry = project_context.load_context_sources(ROOT)
    active = [row for row in registry["project"] if row["state"] == "ACTIVE"]
    assert [row["project_id"] for row in active] == [auth["project_id"]]
    assert active[0]["authority_level"] == "INPUT_MATERIALIZATION_ONLY"
    assert active[0]["historical_execution_authorized"] is False
    assert active[0]["jigsaw_authorized"] is False
    assert active[0]["capital_authority"] == "NONE"
