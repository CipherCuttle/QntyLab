import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
ARTIFACT_ROOT = ROOT / "experiments/research/jigsaw_harvest_v0"
EXECUTION_RESULT_PATH = ARTIFACT_ROOT / "execution_result.json"
PIECE_PATH = ARTIFACT_ROOT / "result.json"
SOURCE_RECORD = Path(
    "/home/swirky/DevHub/executions/QntyLab/jigsaw_harvest_v0/"
    "jigsaw-harvest-v0-a00f3015a58cddc663bcbc0651391b95.execution.json"
)
EXPECTED_SOURCE_SHA256 = "c6533ed3911bc00e29b153c604113bb6c71119d03d8df3287680e549a42e2fce"
EXPECTED_INNER_RESULT_DIGEST = "df362e058f20a79d7ade636c9a37ecd5c5674f8e19f1c6204915c03c6c84f83f"
ORDER = [
    "JH01_RV_PERSISTENCE",
    "JH02_DISPERSION_TO_RV",
    "JH03_BREADTH_TO_RETURN",
    "JH04_DRAWDOWN_TO_RETURN",
]
IMMUTABLE = {
    "JH01_RV_PERSISTENCE": {
        "beta": 0.5047974226484947,
        "hac_standard_error": 0.0400690156731937,
        "hac_confidence_interval_95": [0.4262635950330641, 0.5833312502639253],
        "raw_p_value_two_sided": 2.1602157776846238e-36,
        "holm_adjusted_p_value": 8.640863110738495e-36,
        "classification": "SUPPORTED_WITHIN_FROZEN_SCOPE",
    },
    "JH02_DISPERSION_TO_RV": {
        "beta": 0.16046158927398263,
        "hac_standard_error": 0.06333979405307211,
        "hac_confidence_interval_95": [0.03631787414177701, 0.28460530440618825],
        "raw_p_value_two_sided": 0.01129794973383219,
        "holm_adjusted_p_value": 0.033893849201496566,
        "classification": "SUPPORTED_WITHIN_FROZEN_SCOPE",
    },
    "JH03_BREADTH_TO_RETURN": {
        "beta": -7.294932254197117e-05,
        "hac_standard_error": 0.00453103510880285,
        "hac_confidence_interval_95": [-0.008953614948482081, 0.008807716303398138],
        "raw_p_value_two_sided": 0.9871546738566194,
        "holm_adjusted_p_value": 1.0,
        "classification": "INCONCLUSIVE",
    },
    "JH04_DRAWDOWN_TO_RETURN": {
        "beta": 0.00098684696068798,
        "hac_standard_error": 0.015520696956340764,
        "hac_confidence_interval_95": [-0.029433160088700352, 0.03140685401007631],
        "raw_p_value_two_sided": 0.9493025512677574,
        "holm_adjusted_p_value": 1.0,
        "classification": "INCONCLUSIVE",
    },
}


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
    source = load(SOURCE_RECORD)["receipt"]
    assert artifact["source_execution_record"]["sha256"] == EXPECTED_SOURCE_SHA256
    assert artifact["source_execution_record"]["execution_id"] == "jigsaw-harvest-v0-a00f3015a58cddc663bcbc0651391b95"
    assert artifact["runtime"]["canonical_execution_sha"] == "a2ece4b94e94e026b14631dcf8f0ef080c1452c6"
    assert artifact["preregistration_identity"]["contract_digest"] == "sha256:" + source["preregistration_digest"]
    assert artifact["implementation_identities"]["harvest_scientific_implementation_sha"] == source["reviewed_harvest_implementation_sha"]
    assert artifact["implementation_identities"]["execution_bridge_sha"] == source["execution_bridge_sha"]
    assert artifact["snapshot"]["snapshot_id"] == source["snapshot_id"]
    assert artifact["snapshot"]["snapshot_digest"] == source["snapshot_digest"]
    assert artifact["execution"]["execution_mode"] == source["execution_mode"] == "REAL_FROZEN_SNAPSHOT"
    assert artifact["execution"]["observation_count"] == source["observation_count"] == 580
    assert artifact["execution"]["hac_lag"] == source["hac_lag"] == 5
    assert artifact["result"]["inner_result_digest"] == source["result_digest"] == EXPECTED_INNER_RESULT_DIGEST
    assert artifact["real_experiment_recomputed"] is False


def test_every_recorded_value_matches_the_frozen_receipt_exactly():
    artifact = load(EXECUTION_RESULT_PATH)
    source = load(SOURCE_RECORD)["receipt"]
    assert artifact["result"]["result_order"] == source["result_order"] == ORDER
    assert [row["proposition_id"] for row in artifact["result"]["results"]] == ORDER
    assert len(artifact["result"]["results"]) == 4
    for recorded, original in zip(artifact["result"]["results"], source["results"], strict=True):
        expected = IMMUTABLE[recorded["proposition_id"]]
        for field, value in expected.items():
            assert recorded[field] == original[field] == value
            # Exact float identity, not approximate equality.
            assert repr(recorded[field]) == repr(original[field])


def test_execution_record_artifact_has_deterministic_self_digest_and_closure_counts():
    artifact = load(EXECUTION_RESULT_PATH)
    assert artifact["record_digest"] == canonical_digest(without_digest(artifact, "record_digest"))
    assert artifact["status"] == "RECORDED_IMMUTABLE"
    assert artifact["throughput"] == {
        "snapshot_reused": True,
        "new_data_acquisitions": 0,
        "new_data_qualification_phases": 0,
        "data_infrastructure_changes": 0,
        "propositions_registered": 4,
        "propositions_executed": 4,
    }
    closure = artifact["closure"]
    assert closure["project_state"] == "CLOSED_PASS"
    assert closure["implementation_authorized"] is False
    assert (closure["propositions_registered"], closure["propositions_executed"]) == (4, 4)
    assert closure["supported_within_frozen_scope"] == 2
    assert closure["not_supported"] == 0
    assert closure["inconclusive"] == 2
    assert closure["blocked"] == 0
    assert "does not mean every hypothesis was supported" in closure["closed_pass_meaning"]
    assert artifact["scientific_authority"] == "EXPLORATORY_ASSOCIATION_ONLY"
    assert artifact["downstream_authorities"] == {
        "causal": "NONE",
        "strategy": "NONE",
        "router": "NONE",
        "state_snapshot": "NONE",
        "qnty": "NONE",
        "trading": "NONE",
    }


def test_four_distinct_bounded_pieces_are_preserved_in_order():
    piece_file = load(PIECE_PATH)
    assert piece_file["piece_digest"] == canonical_digest(without_digest(piece_file, "piece_digest"))
    assert piece_file["piece_count"] == 4
    assert piece_file["piece_order"] == ORDER
    assert [piece["proposition_id"] for piece in piece_file["pieces"]] == ORDER
    assert piece_file["promotion_eligible"] is False
    assert piece_file["family_summary"]["supported_within_frozen_scope"] == 2
    assert piece_file["family_summary"]["inconclusive"] == 2
    for piece in piece_file["pieces"]:
        expected = IMMUTABLE[piece["proposition_id"]]
        for field, value in expected.items():
            assert piece[field] == value
        assert piece["sample"] == 580
        assert piece["hac_lag"] == 5
        assert piece["piece_type"] == "PREDICTIVE_ASSOCIATION"
        assert piece["feature"] and piece["outcome"]
        assert piece["direction"]["preregistered_predicted_beta_sign"] == "POSITIVE"
        assert piece["snapshot_binding"]["snapshot_digest"] == "c0fa7dc0e51c7680fccbd7e7cdd0945fcd63af3e8c75809a24aa3b216868b9ac"
        assert piece["limitations"]
        assert piece["promotion_eligible"] is False
        assert "causal" in piece["does_not_establish"] or "causality" in piece["does_not_establish"]
        assert "inverse effect" in piece["does_not_establish"]
        assert piece["authorities"] == {
            "causal": "NONE",
            "strategy": "NONE",
            "router": "NONE",
            "state_snapshot": "NONE",
            "qnty": "NONE",
            "trading": "NONE",
        }
        assert "State Snapshot" in piece["non_escalation"]


def test_pieces_make_no_causal_or_escalating_claim():
    pieces = {piece["proposition_id"]: piece for piece in load(PIECE_PATH)["pieces"]}
    for piece in pieces.values():
        text = piece["interpretation"].lower()
        assert "causes" not in text
        assert "causal" not in text
        assert "edge" not in text
        assert "authorized" not in text

    persistence = pieces["JH01_RV_PERSISTENCE"]["interpretation"]
    assert persistence.startswith("Within this exact frozen panel, sample, and specification,")
    assert "positively associated with" in persistence
    assert "50.5" not in persistence and "%" not in persistence
    assert "that volatility causes volatility" in pieces["JH01_RV_PERSISTENCE"]["does_not_establish"]
    assert "that RV24 is an authorized State Snapshot feature" in pieces["JH01_RV_PERSISTENCE"]["does_not_establish"]


def test_jh02_preserves_prior_feature_exposure_and_is_not_a_rescue():
    piece = {row["proposition_id"]: row for row in load(PIECE_PATH)["pieces"]}["JH02_DISPERSION_TO_RV"]
    assert piece["prior_feature_exposure"] == "YES"
    assert "not pristine first exposure" in piece["prior_exposure_note"]
    assert "does not rescue or reverse" in piece["prior_exposure_note"]
    assert "different outcome" in piece["prior_exposure_note"]
    assert "a rescue or reversal of the earlier cross-sectional dispersion result" in piece["does_not_establish"]
    assert piece["interpretation"].startswith("Within this exact frozen panel, sample, and specification,")


def test_inconclusive_pieces_do_not_claim_absence_of_effect():
    pieces = {row["proposition_id"]: row for row in load(PIECE_PATH)["pieces"]}
    breadth = pieces["JH03_BREADTH_TO_RETURN"]
    drawdown = pieces["JH04_DRAWDOWN_TO_RETURN"]
    assert breadth["classification"] == drawdown["classification"] == "INCONCLUSIVE"
    for piece in (breadth, drawdown):
        assert piece["interpretation"].startswith("No support was established for the preregistered positive")
        assert "INCONCLUSIVE" in piece["interpretation"]
        assert "absence of an effect" in piece["does_not_establish"]
        assert any("not evidence of absence" in item for item in piece["limitations"])
    assert "that breadth has no predictive value" in breadth["does_not_establish"]
    assert "that drawdowns do not rebound" in drawdown["does_not_establish"]


def test_recorded_project_state_closes_harvest_without_authorizing_anything():
    registry = (ROOT / "docs/state/projects.toml").read_text(encoding="utf-8")
    assert 'project_id = "JIGSAW_HARVEST_V0"\nstate = "CLOSED_PASS"' in registry
    assert "experiments/research/jigsaw_harvest_v0/execution_result.json" in registry
    assert "experiments/research/jigsaw_harvest_v0/result.json" in registry
    assert 'project_id = "STATE_SNAPSHOT_V0"\nstate = "PLANNED_NOT_AUTHORIZED"' in registry


def test_ledger_decision_preserves_all_four_outcomes_and_receipt_binding():
    decisions = [
        json.loads(line)
        for line in (ROOT / "experiments/research/decisions.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    event = next(item for item in decisions if item["event_id"] == "event_decision_jigsaw_harvest_v0_recorded_complete")
    assert event["family_id"] == "FAMILY_JIGSAW_HARVEST_V0"
    assert event["candidate_id"] == "CANDIDATE_JIGSAW_HARVEST_V0"
    assert event["registered_variant_denominator"] == 4
    note = event["decision_note"]
    for proposition_id in ORDER:
        assert proposition_id in note
    assert EXPECTED_SOURCE_SHA256 in note
    assert EXPECTED_INNER_RESULT_DIGEST in note
    assert "a1271c3330956e7c6a61a2d6dade71858581b69c" in note
    assert "d3a7e2da4cdaedb33c51f21f952f1181954c8650" in note
    assert "rds-v0-c0fa7dc0e51c7680fccbd7e7cdd0945fcd63af3e8c75809a24aa3b216868b9ac" in note
    assert "SUPPORTED_WITHIN_FROZEN_SCOPE" in note and "INCONCLUSIVE" in note
    assert "not an economic failure" in note
    assert "not evidence of absence" in note
    for path, digest in event["evidence_sha256"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest
