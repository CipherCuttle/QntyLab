import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_profile_a_config_mutation_forensics_authorization_v0"
PREDECESSOR = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_sandbox_policy_ownership_forensics_v0"


def load_auth():
    return json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))


def test_exact_pr_merge_binding_and_immutable_predecessor_classification():
    auth = load_auth()
    predecessor = auth["predecessor"]
    assert predecessor["pr"] == 158
    assert predecessor["merge_sha"] == "89952634622f2480eebb8f695360379272bd01ea"
    assert predecessor["classification"] == "INCONCLUSIVE_INFRA"
    assert predecessor["classification_immutable"] is True
    assert auth["governance_boundary"]["historical_reclassification_authorized"] is False


def test_c_consumption_and_write_success_are_preserved():
    predecessor = load_auth()["predecessor"]
    assert predecessor["c_consumed"] is True
    assert predecessor["c_product_invocations"] == 1
    assert predecessor["c_retries"] == 0
    assert predecessor["write_attempt"] is True
    assert predecessor["write_success"] is True
    assert predecessor["changed_paths"] == ["fixture.txt"]
    assert predecessor["unauthorized_writes"] == []
    assert (PREDECESSOR / "live_canary_consumed.marker").is_file()


def test_effective_treatment_and_non_write_observations_are_exact():
    predecessor = load_auth()["predecessor"]
    assert predecessor["approval_policy_requested"] == "never"
    assert predecessor["sandbox_requested"] == "workspace-write"
    assert predecessor["effective_sandbox"] == "workspaceWrite"
    assert predecessor["read_only_message_observed"] is False
    assert predecessor["sandbox_denial_observed"] is False
    assert predecessor["approval_request_observed"] is False
    assert predecessor["turn_started"] is True
    assert predecessor["terminal_status"] == "completed"
    assert predecessor["child_exit"] == 0
    assert predecessor["timeout"] is False


def test_fixture_digests_and_jsonrpc_error_are_preserved_without_overclaiming():
    predecessor = load_auth()["predecessor"]
    assert predecessor["fixture_before_sha256"] == "be9351741a8155d01fd028d158546f1005e73ce0bb2d093335feac4144e450"
    assert predecessor["fixture_after_sha256"] == "f72c713b7b432dd18949ca10f1be6dbcf493479945653609d1c715b2d8d74356"
    assert predecessor["jsonrpc_32600"] == {
        "code": -32600,
        "message": "no active turn to interrupt",
        "event_ordinal": 93,
        "stage": "terminal/other",
        "fatal": "NO",
        "causal_explanation_for_failed_B": "NOT_ADEQUATE",
    }


def test_exact_profile_hashes_and_hash_input_contract_are_frozen():
    mutation = load_auth()["profile_a_mutation"]
    assert mutation["mutated"] is True
    assert mutation["hash_before"] == "955cec088237c2ca3f2a704ab67ad2d805c0916feb74dec6fec0eb6c5b04eef0"
    assert mutation["hash_after"] == "cb07d9468bb9f7e21b3cc507b20f31a6bffbc8328ef5b250bd7f9a12141ab6c7"
    source = mutation["hash_source_evidence"]
    assert source["input_type"] == "FILE"
    assert source["input_paths"] == ["~/.codex/config.toml"]
    assert source["normalization"] == "raw bytes"
    assert source["secret_material_included"] == "UNKNOWN"


def test_authorization_is_read_only_and_has_zero_live_authority():
    auth = load_auth()
    boundary = auth["governance_boundary"]
    assert auth["authorized_operation"] == "READ_ONLY_FORENSIC_DIAGNOSIS"
    assert boundary["live_product_invocations_authorized"] == 0
    assert boundary["dsh_invocations_authorized"] == 0
    assert boundary["codex_invocations_authorized"] == 0
    assert boundary["canaries_authorized"] == 0
    assert boundary["fixture_mutation_authorized"] is False
    assert boundary["profile_a_mutation_authorized"] is False
    assert boundary["treatment_mutation_authorized"] is False


def test_profile_and_treatment_mutation_surfaces_are_explicitly_prohibited():
    boundary = load_auth()["governance_boundary"]
    assert boundary["sandbox_mutation_authorized"] is False
    assert boundary["approval_policy_mutation_authorized"] is False
    assert boundary["trust_mutation_authorized"] is False
    assert boundary["writable_roots_mutation_authorized"] is False
    assert boundary["runtime_workspace_roots_mutation_authorized"] is False
    prohibited = " ".join(boundary["prohibited_operations"])
    assert "~/.codex/config.toml" in prohibited
    assert "changing the sandbox treatment" in prohibited


def test_no_reruns_and_no_historical_reclassification_are_authorized():
    boundary = load_auth()["governance_boundary"]
    assert boundary["rerun_b_authorized"] is False
    assert boundary["rerun_c_authorized"] is False
    assert boundary["historical_reclassification_authorized"] is False
    assert load_auth()["predecessor"]["classification"] == "INCONCLUSIVE_INFRA"


def test_secret_and_paid_service_authority_is_absent():
    auth = load_auth()
    safety = auth["secret_safety"]
    assert all(value is False for key, value in safety.items() if key.endswith("_authorized"))
    assert safety["redaction_required_before_serialization"] is True
    boundary = auth["governance_boundary"]
    assert boundary["pay_per_token_authorized"] is False
    assert boundary["parent_model_requests"] == 0


def test_no_science_qnty_trading_or_capital_authority():
    boundary = load_auth()["governance_boundary"]
    assert boundary["scientific_execution_authorized"] is False
    assert boundary["qnty_runtime_authority"] == "NONE"
    assert boundary["trading_authority"] == "NONE"
    assert boundary["capital_authority"] == "NONE"


def test_forensic_surface_and_outcomes_are_diagnostic_only():
    auth = load_auth()
    assert "canonical Git-tracked repository evidence" in auth["authorized_read_surface"]
    assert "Profile A configuration file content only as necessary for safe semantic identification" in auth["authorized_read_surface"]
    assert auth["profile_a_mutation"]["content_recovery_status"] == "NOT_YET_DETERMINED"
    assert set(auth["later_outcome_classes"]) == {
        "CONFOUNDER_EXCLUDED",
        "LOAD_BEARING_CONFOUNDER",
        "PARTIAL_CONFOUNDER",
        "HASH_ONLY_INCONCLUSIVE",
        "FORENSIC_CONTRADICTION",
    }
    assert auth["counterfactual_scope"]["causal_relevance_initial_status"] == "UNKNOWN"
    assert auth["new_sanitized_forensic_artifacts_authorized"] is True
    assert auth["existing_canonical_artifact_mutation_authorized"] is False


def test_temporal_and_writer_uncertainty_must_be_evidence_bound():
    requirements = load_auth()["forensic_requirements"]
    assert requirements["tri_state_values"] == ["YES", "NO", "UNKNOWN"]
    assert set(requirements["temporal_outputs"]) == {
        "MUTATION_BEFORE_EFFECTIVE_SANDBOX",
        "MUTATION_BEFORE_WRITE",
        "MUTATION_AFTER_WRITE",
        "MUTATION_AFTER_TURN_COMPLETED",
    }
    assert "UNKNOWN" in requirements["writer_classes"]


def test_authorization_is_merge_gated_and_closes_with_no_active_project():
    auth = load_auth()
    assert auth["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
    assert auth["phase_state"] == "CLOSED_PASS"
    assert auth["active_project_after_closure"] == "NONE"
    assert auth["qnty_agent_eval"] == "NO_MATCH"


def test_review_policy_and_later_project_identity_are_bound():
    auth = load_auth()
    assert auth["later_forensic_project_id"] == "PINNED_DSH_PROFILE_A_CONFIG_MUTATION_FORENSICS_V0"
    assert auth["review"] == {
        "independent_hostile_review_required": True,
        "targeted_rereview_only_if_critical_or_high_repair": True,
    }
