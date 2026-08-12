import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
ARTIFACT_ROOT = ROOT / "experiments/research/jigsaw_funding_pressure_volatility_v0"
EXECUTION_RESULT_PATH = ARTIFACT_ROOT / "execution_result.json"
PIECE_PATH = ARTIFACT_ROOT / "result.json"
SOURCE_RECORD = Path(
    "/home/swirky/DevHub/executions/QntyLab/jigsaw_funding_pressure_volatility_v0/"
    "jigsaw-funding-pressure-v0-eea070f7fde033112ea94c277c5e9f91.execution.json"
)
EXPECTED_SOURCE_SHA256 = "e979a3b5e9e4adb85c11b2d04d9ced24729109ae9d3f7e400bd1c9602509fbf6"
EXPECTED_STATISTIC = "-0.0002003650803348647161725358990165653289511751324777"


def canonical_digest(payload):
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def without_digest(payload, field):
    result = dict(payload)
    result.pop(field)
    return result


def test_source_execution_record_is_bound_without_recomputation():
    artifact = load(EXECUTION_RESULT_PATH)
    assert SOURCE_RECORD.exists()
    assert hashlib.sha256(SOURCE_RECORD.read_bytes()).hexdigest() == EXPECTED_SOURCE_SHA256
    source = load(SOURCE_RECORD)
    assert artifact["source_execution_record"]["sha256"] == EXPECTED_SOURCE_SHA256
    assert artifact["authorization"]["authorization_id"] == source["provenance"]["authorization_id"]
    assert artifact["authorization"]["terminal_state"] == source["completion_state"] == "CONSUMED_COMPLETE"
    assert artifact["runtime"]["canonical_runtime_merge_sha"] == source["provenance"]["canonical_runtime_merge_sha"]
    assert artifact["result"]["result_digest"] == source["result_digest"]
    assert artifact["result"]["provenance_digest"] == source["provenance_digest"]
    assert artifact["result"]["primary_statistic"] == source["primary_statistic"] == EXPECTED_STATISTIC
    assert artifact["result"]["adjudication"] == source["adjudication"] == "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST"
    assert artifact["downstream_authorities"] == {
        "strategy": source["downstream_strategy_authority"],
        "router": source["downstream_router_authority"],
        "qnty": source["downstream_qnty_authority"],
    } == {"strategy": "NONE", "router": "NONE", "qnty": "NONE"}


def test_execution_record_artifact_has_deterministic_self_digest_and_lineage():
    artifact = load(EXECUTION_RESULT_PATH)
    assert artifact["record_digest"] == canonical_digest(without_digest(artifact, "record_digest"))
    assert artifact["historical_failed_authorization"] == {
        "authorization_id": "jigsaw-funding-pressure-v0-21299530daeea57ba2d1d2a900f5547c",
        "terminal_state": "CONSUMED_INCOMPLETE",
        "preserved_as_distinct_lineage": True,
    }
    assert artifact["real_experiment_recomputed"] is False
    assert artifact["executor_changed"] is False


def test_jigsaw_piece_is_bounded_non_inverse_evidence():
    piece = load(PIECE_PATH)
    assert piece["piece_digest"] == canonical_digest(without_digest(piece, "piece_digest"))
    assert piece["piece_type"] == "CONDITION_EFFECT"
    assert piece["primary"]["decision"] == "NOT_SUPPORTED_UNDER_FROZEN_SPECIFICATION"
    assert piece["primary"]["adjudication"] == "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST"
    assert piece["primary"]["observed_contrast"] == EXPECTED_STATISTIC
    assert piece["bound"] == {
        "panel_symbols": 20,
        "daily_decisions": 610,
        "funding_pressure_state": "frozen funding-pressure ECDF",
        "outcome": "frozen RV24 definition",
        "decision_window": "2023-10-19T00:00:00Z..2025-06-19T00:00:00Z",
    }
    assert "inverse effect" in piece["does_not_establish"]
    assert piece["follow_up"]["status"] == "UNTESTED_FOLLOW_UP"
    assert piece["promotion_eligible"] is False
    assert piece["authorities"] == {"strategy": "NONE", "router": "NONE", "qnty": "NONE"}
    assert "predicts lower" not in piece["interpretation"]
    assert "causal" not in piece["interpretation"].lower()
