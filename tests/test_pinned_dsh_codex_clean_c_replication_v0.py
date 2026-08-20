import json
import inspect
from pathlib import Path

import pytest

from qntylab import pinned_dsh_codex_clean_c_replication_v0 as d


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/pinned_dsh_codex_clean_c_replication_v0"


def _clean_receipt(**overrides):
    value = {
        "prelive_gate": "PASS",
        "product_invocation_count": 1,
        "identity_gate": "PASS",
        "credential_gate": "PASS",
        "request_equivalence_gate": "PASS",
        "fixture_before_digest": d.FIXTURE_BEFORE_SHA256,
        "fixture_after_digest": d.FIXTURE_AFTER_SHA256,
        "changed_paths": ["fixture.txt"],
        "unauthorized_writes": [],
        "turn_started": True,
        "terminal_status": "completed",
        "read_only_message_observed": False,
        "sandbox_denial_observed": False,
        "approval_request_observed": False,
        "expected_write_occurred": True,
        "profile_hash_before": "same",
        "profile_hash_after": "same",
        "profile_bytes_changed": False,
        "timeout": False,
        "infrastructure_failure": None,
    }
    value.update(overrides)
    return value


def test_authorization_161_is_canonical_and_budgets_are_exact():
    auth = d.authorization()
    gate = d.canonical_authorization_gate()
    assert gate["authorization_pr"] == 161
    assert gate["authorization_merge_sha"] == "e0c74578d86816d6edd7afd5d60b099bbd7d4fc1"
    assert gate["canonical_master_match"] is True
    assert gate["authorization_head_ancestor"] is True
    assert gate["pass"] is True
    assert auth["later_live_budget"]["d_live_exposures_authorized"] == 1
    assert auth["later_live_budget"]["d_retries_authorized"] == 0


def test_c_and_d_request_comparison_covers_all_protocol_stages_and_is_zero_delta():
    comparison = d.request_equivalence()
    assert comparison["comparison_stages"] == ["initialize", "thread/start", "turn/start"]
    assert comparison["semantic_diff"] == []
    assert comparison["c_to_d_product_request_delta_count"] == 0
    assert comparison["c_request_digest"] == comparison["d_request_digest"]
    assert comparison["c_request"][1]["params"]["approvalPolicy"] == "never"
    assert comparison["c_request"][1]["params"]["sandbox"] == "workspace-write"


def test_exact_pinned_identities_prompt_and_fixture_are_frozen():
    identity = d.product_identity_gate()
    assert identity["dsh_commit"] == d.DSH_COMMIT
    assert identity["dsh_tree"] == d.DSH_TREE
    assert identity["dsh_tag"] == d.DSH_TAG
    assert identity["codex_version"] == "codex-cli 0.147.0"
    assert identity["codex_binary_sha256"] == d.CODEX_BINARY_SHA256
    assert identity["prompt_sha256"] == d.PROMPT_SHA256
    assert d.sha256_bytes(d.BEFORE) == d.FIXTURE_BEFORE_SHA256
    assert d.sha256_bytes(d.AFTER) == d.FIXTURE_AFTER_SHA256


def test_profile_baseline_is_authorization_hash_and_no_mutation_authority_exists():
    auth = d.authorization()
    assert auth["authorization_profile_baseline"]["authorization_profile_hash"] == d.AUTHORIZATION_PROFILE_HASH
    assert auth["authorization_profile_baseline"]["profile_baseline_match"] is True
    boundary = auth["governance_boundary"]
    assert boundary["profile_a_mutation_authorized"] is False
    assert boundary["profile_restoration_authorized"] is False
    assert boundary["codex_home_mutation_authorized"] is False


def test_profile_baseline_mismatch_is_a_prelive_block():
    assert d.AUTHORIZATION_PROFILE_HASH != "different"
    assert d.AUTHORIZATION_PROFILE_HASH == d.authorization()["authorization_profile_baseline"]["authorization_profile_hash"]
    assert d.profile_hash() == d.AUTHORIZATION_PROFILE_HASH


def test_credential_gate_uses_presence_only_and_empty_value_is_present():
    class PresenceOnly(dict):
        def __getitem__(self, key):
            raise AssertionError("credential values must not be read")

    env = PresenceOnly({"OPENAI_API_KEY": "", "ANTHROPIC_API_KEY": "", "DEEPSEEK_API_KEY": ""})
    presence = d.credential_presence(env)
    assert set(presence) == set(d.FORBIDDEN_API_ENV)
    assert all(type(value) is bool for value in presence.values())
    assert all(presence.values())
    assert d.credential_gate(presence) == "BLOCK"


def test_raw_profile_snapshots_are_private_ephemeral_and_not_artifacts():
    auth = d.authorization()
    observation = auth["observation_only_delta"]
    assert observation["raw_snapshot_policy"] == "EPHEMERAL_LOCAL_ONLY"
    assert observation["raw_bytes_may_be_committed"] is False
    assert observation["raw_bytes_may_be_serialized"] is False
    assert observation["raw_bytes_may_be_sent_to_model"] is False
    assert not any(path.name.endswith(".config.toml") for path in ARTIFACT.iterdir() if path.is_file())


def test_redacted_semantic_diff_never_serializes_secret_value():
    before = b'[profile]\ntrust_level = "trusted"\napi_key = "before-secret"\n'
    after = b'[profile]\ntrust_level = "trusted"\napi_key = "after-secret"\n'
    diff = d.redacted_profile_diff(before, after)
    encoded = json.dumps(diff, sort_keys=True)
    assert diff["profile_bytes_changed"] is True
    assert diff["semantic_config_changed"] == "YES"
    assert "before-secret" not in encoded
    assert "after-secret" not in encoded
    key = next(item for item in diff["changed_keys"] if item["key_path"] == "profile.api_key")
    assert key["secret_redacted"] == "YES"
    assert key["load_bearing_classification"] == "AUTHENTICATION_ONLY"


def test_profile_restoration_paths_are_absent_from_controller():
    source = inspect.getsource(d)
    assert "PROFILE_PATH.write" not in source
    assert "PROFILE_PATH.unlink" not in source
    assert "shutil.copyfile(PROFILE_PATH" not in source
    assert "CODEX_HOME.write" not in source


def test_consumed_marker_is_irrevocable_and_second_write_fails(tmp_path):
    marker = tmp_path / "live_canary_consumed.marker"
    d.write_consumed_marker(marker, {"phase_id": d.PHASE_ID, "irrevocable": True})
    assert marker.exists()
    with pytest.raises(FileExistsError):
        d.write_consumed_marker(marker, {"phase_id": d.PHASE_ID, "irrevocable": True})


def test_clean_pass_requires_stable_profile_and_exact_fixture_write():
    assert d.classify_result(_clean_receipt()) == "CLEAN_CONFIRMATION_PASS"
    assert d.classify_result(_clean_receipt(profile_bytes_changed=True)) == "PROFILE_MUTATED_RECORDED"
    assert d.classify_result(_clean_receipt(profile_hash_after="changed")) == "INCONCLUSIVE_INFRA"
    assert d.classify_result(_clean_receipt(expected_write_occurred=False)) == "WRITE_FAILURE_WITH_STABLE_PROFILE"
    assert d.classify_result(_clean_receipt(unauthorized_writes=["other.txt"])) == "WRITE_FAILURE_WITH_STABLE_PROFILE"


def test_timeout_or_crash_after_marker_is_consumed_and_not_clean():
    receipt = _clean_receipt(timeout=True, terminal_status=None, expected_write_occurred=False)
    assert receipt["product_invocation_count"] == 1
    assert d.classify_result(receipt) == "INCONCLUSIVE_INFRA"
    assert d.authorization()["later_live_budget"]["d_retries_authorized"] == 0


def test_jsonrpc_32600_presence_does_not_override_success_classification():
    receipt = _clean_receipt(jsonrpc_32600_observed=True, jsonrpc_32600_fatal="NO")
    assert d.classify_result(receipt) == "CLEAN_CONFIRMATION_PASS"


def test_effective_sandbox_is_only_claimed_when_observed():
    assert d._effective_sandbox([]) == "NOT_OBSERVABLE"
    events = [{"direction": "event", "effective": {"sandbox": "workspaceWrite"}}]
    assert d._effective_sandbox(events) == "workspaceWrite"


def test_no_additional_authority_and_no_historical_reclassification():
    auth = d.authorization()
    boundary = auth["governance_boundary"]
    assert boundary["historical_reclassification_authorized"] is False
    assert boundary["scientific_execution_authorized"] is False
    assert boundary["qnty_runtime_authority"] == "NONE"
    assert boundary["trading_authority"] == "NONE"
    assert boundary["capital_authority"] == "NONE"
    assert boundary["parent_model_requests"] == 0
    assert boundary["pay_per_token_authorized"] is False


def test_live_controller_has_single_product_boundary_and_no_retry_branch():
    source = inspect.getsource(d.run_live)
    assert source.count('subprocess.run(["node", str(DRIVER)]') == 1
    assert d.AUTHORIZATION_MERGE_SHA == "e0c74578d86816d6edd7afd5d60b099bbd7d4fc1"
    assert d.authorization()["later_live_budget"]["d_retries_authorized"] == 0
