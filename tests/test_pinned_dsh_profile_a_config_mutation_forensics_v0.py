import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_profile_a_config_mutation_forensics_v0"
AUTH = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_profile_a_config_mutation_authorization_v0"
AUTH_FALLBACK = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_profile_a_config_mutation_forensics_authorization_v0"
PREDECESSOR = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_sandbox_policy_ownership_forensics_v0"
PROFILE = Path("/home/swirky/.codex/config.toml")


def load(name):
    return json.loads((ARTIFACT / name).read_text(encoding="utf-8"))


def load_auth():
    path = AUTH / "authorization.json"
    if not path.is_file():
        path = AUTH_FALLBACK / "authorization.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_canonical_authorization_and_immutable_predecessor_binding():
    evidence = load("evidence_inventory.json")
    auth = load_auth()
    assert evidence["governing_authorization"]["pr"] == 159
    assert evidence["governing_authorization"]["merge_sha"] == "3901dc113ca736da821db14b0fcb1f083c84578e"
    assert auth["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
    assert evidence["canonical_predecessor"]["pr"] == 158
    assert evidence["canonical_predecessor"]["merge_sha"] == "89952634622f2480eebb8f695360379272bd01ea"
    assert evidence["canonical_predecessor"]["classification"] == "INCONCLUSIVE_INFRA"
    assert evidence["canonical_predecessor"]["classification_changed"] is False


def test_predecessor_c_is_consumed_and_write_succeeded():
    evidence = load("evidence_inventory.json")["canonical_predecessor"]
    receipt = json.loads((PREDECESSOR / "live_canary_receipt.json").read_text(encoding="utf-8"))
    assert evidence["c_consumed"] is True
    assert evidence["expected_write_occurred"] is True
    assert receipt["classification"] == "INCONCLUSIVE_INFRA"
    assert receipt["product_invocation_count"] == 1
    assert receipt["changed_paths"] == ["fixture.txt"]
    assert (PREDECESSOR / "live_canary_consumed.marker").is_file()


def test_hash_implementation_is_single_file_raw_bytes():
    value = load("hash_reconstruction.json")
    assert value["hash_input_type"] == "FILE"
    assert value["hash_input_path_logical"] == "~/.codex/config.toml"
    assert value["hash_mode"] == "RAW_BYTES"
    behavior = value["normalization_behavior"]
    assert behavior["raw_bytes_only"] is True
    assert behavior["newline_normalization"] is False
    assert behavior["encoding_conversion"] is False
    assert behavior["toml_parsing"] is False
    assert behavior["toml_canonicalization"] is False
    assert value["implementation"]["source_file"].endswith("pinned_dsh_codex_terminal_error_permission_policy_forensics_v0.py")


def test_exact_hashes_and_current_hash_relations_are_preserved():
    value = load("hash_reconstruction.json")
    assert value["canonical_hashes"]["before"] == "955cec088237c2ca3f2a704ab67ad2d805c0916feb74dec6fec0eb6c5b04eef0"
    assert value["canonical_hashes"]["after"] == "cb07d9468bb9f7e21b3cc507b20f31a6bffbc8328ef5b250bd7f9a12141ab6c7"
    assert value["current_hash"] == value["canonical_hashes"]["after"]
    assert value["current_equals_before"] is False
    assert value["current_equals_after"] is True
    assert value["current_equals_neither"] is False


def test_profile_was_not_mutated_by_forensic_phase():
    closure = load("closure.json")
    temporal = load("temporal_analysis.json")
    assert closure["profile_mutated_by_forensic_phase"] is False
    assert closure["profile_hash_forensic_start"] == closure["profile_hash_forensic_end"]
    assert temporal["profile_hash_forensic_start"] == temporal["profile_hash_forensic_end"]
    if PROFILE.is_file():
        assert hashlib.sha256(PROFILE.read_bytes()).hexdigest() == closure["profile_hash_forensic_end"]


def test_no_live_execution_or_downstream_authority():
    closure = load("closure.json")
    live = load("evidence_inventory.json")["live_execution_attestation"]
    assert live["dsh_invoked"] is False
    assert live["codex_invoked"] is False
    assert live["canary_run"] is False
    assert live["product_invocations"] == 0
    assert closure["qnty_agent_eval"] == "NO_MATCH"
    assert closure["scientific_execution"] is False
    assert closure["qnty_runtime_authority"] == "NONE"
    assert closure["trading_authority"] == "NONE"
    assert closure["capital_authority"] == "NONE"


def test_secret_values_and_raw_profile_bytes_are_not_recorded():
    evidence = load("evidence_inventory.json")
    diff = load("redacted_config_diff.json")
    assert evidence["secret_safety"]["raw_profile_bytes_recorded"] is False
    assert evidence["secret_safety"]["config_values_recorded"] is False
    assert evidence["secret_safety"]["secret_values_recorded"] is False
    assert diff["before"]["safe_semantic_values"] == "UNAVAILABLE"
    assert diff["after"]["safe_semantic_values"] == "NOT_SERIALIZED"
    assert all(item["secret_redacted"] == "YES" for item in diff["candidate_current_fields_not_proven_changed"])


def test_partial_recovery_does_not_claim_exact_semantic_diff():
    diff = load("redacted_config_diff.json")
    causal = load("causal_analysis.json")
    assert diff["content_recovery"] == "PARTIAL_DIFF_RECOVERED"
    assert diff["changed_config_keys"] == "UNKNOWN"
    assert diff["semantic_config_changed"] == "UNKNOWN"
    assert causal["profile_a_mutation_causal_relevance"] == "UNKNOWN"


def test_frozen_outcome_set_and_exclusion_gates():
    causal = load("causal_analysis.json")
    assert causal["classification"] in {
        "CONFOUNDER_EXCLUDED",
        "LOAD_BEARING_CONFOUNDER",
        "PARTIAL_CONFOUNDER",
        "HASH_ONLY_INCONCLUSIVE",
        "FORENSIC_CONTRADICTION",
    }
    gate = causal["classification_gate"]
    assert gate["confounder_excluded_requires_positive_mechanical_exclusion"] is True
    assert gate["hash_only_or_missing_before_prohibits_confounder_excluded"] is True
    assert gate["load_bearing_confounder_requires_changed_setting_and_relevant_timing"] is True
    assert gate["current_phase_has_positive_exclusion"] is False
    assert causal["classification"] != "CONFOUNDER_EXCLUDED"


def test_temporal_ordering_does_not_overclaim_event_resolution():
    temporal = load("temporal_analysis.json")
    ordering = temporal["ordering"]
    assert ordering["mutation_before_product_launch"] == "NO"
    assert ordering["mutation_after_turn_completed"] == "NO"
    assert ordering["mutation_before_thread_start"] == "UNKNOWN"
    assert ordering["mutation_before_turn_started"] == "UNKNOWN"
    assert ordering["mutation_before_fixture_write"] == "UNKNOWN"
    assert ordering["mutation_after_fixture_write"] == "UNKNOWN"
    assert temporal["profile_metadata_evidence"]["metadata_is_not_writer_proof"] is True


def test_writer_attribution_is_uncertain_and_concurrent_writers_remain_open():
    writer = load("writer_analysis.json")
    assert writer["mutation_writer"] == "UNKNOWN"
    assert writer["writer_confidence"] == "LOW"
    assert "UNRELATED_CONCURRENT_PROCESS_OR_MANUAL_CHANGE" in {x["candidate"] for x in writer["candidate_mechanisms"]}
    assert writer["writer_attribution_from_mtime_alone"] == "PROHIBITED"


def test_closure_keeps_historical_result_immutable_and_no_canary_authority():
    closure = load("closure.json")
    assert closure["predecessor_classification"] == "INCONCLUSIVE_INFRA"
    assert closure["predecessor_classification_changed"] is False
    assert closure["classification"] == "PARTIAL_CONFOUNDER"
    assert closure["additional_canary_authorized"] is False
    assert closure["historical_reclassification_authorized"] is False
    assert closure["active_project_after_closure"] == "NONE"


def test_causal_matrix_preserves_d3_b_c_comparison():
    matrix = load("causal_analysis.json")["causal_matrix"]
    assert matrix["known_good_d3"]["approval_policy"] == "never"
    assert matrix["known_good_d3"]["sandbox"] == "workspace-write"
    assert matrix["b_pr156"]["approval_policy"] == "never"
    assert matrix["b_pr156"]["sandbox_explicit"] is False
    assert matrix["c_pr158"]["approval_policy"] == "never"
    assert matrix["c_pr158"]["sandbox"] == "workspace-write"
    assert matrix["c_pr158"]["profile_a_hash_mutation"] is True
