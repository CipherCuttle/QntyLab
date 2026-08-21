import hashlib
import json
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_multi_agent_orchestration_stage_a_authorization_v0"


def auth():
    return json.loads((ARTIFACT / "authorization.json").read_text(encoding="utf-8"))


def test_exact_predecessor_master_and_pr164_binding():
    value = auth()
    gate = value["canonical_merge_gate"]
    assert gate["predecessor_project_id"] == "PINNED_DSH_CODEX_PROVIDER_BOUNDARY_FINAL_CLOSEOUT_V0"
    assert gate["predecessor_pr"] == 164
    assert gate["predecessor_canonical_master"] == "0424212f922d4028527025b77be6a96cb3adf3c3"
    assert gate["predecessor_outcome"] == "CLOSED_PASS_CONSERVATIVE_REPAIR"
    assert gate["reopens_predecessor_permission_phase"] is False


def test_exact_pinned_dsh_commit_tree_tag_are_bound():
    identities = auth()["frozen_product_identities"]
    assert identities["dsh_repository"] == "deepseek-ai/deepseek-harness"
    assert identities["dsh_commit"] == "99f6f02fecdb7dff40c3fbc9470f5907c29f74ca"
    assert identities["dsh_tree"] == "3bc8f89fe494a4755c188be354add4e8b1e7b188"
    assert identities["dsh_tag"] == "dsh-v0.1.0-rc.7"


def test_canonical_repaired_provider_path_and_contract_are_bound():
    identities = auth()["frozen_product_identities"]
    assert identities["repaired_provider_materializer"] == "qntylab/pinned_dsh_provider_boundary_repair_v0.py"
    assert (ROOT / identities["repaired_provider_materializer"]).is_file()
    assert identities["repaired_thread_start_required"] == {"approvalPolicy": "never", "sandbox": "workspace-write"}
    assert identities["repaired_thread_start_preserved"] == ["cwd", "ephemeral"]
    assert identities["repair_semantic_delta_count"] == 2


def test_profile_composition_is_frozen_not_deferred_to_the_later_phase():
    composition = auth()["runnable_profile_composition"]
    assert composition["frozen"] is True
    assert composition["raw_upstream_fallback_prohibited"] is True
    assert "later_phase_must_establish" not in composition
    steps = composition["later_phase_must_materialize_and_verify"]
    assert "materialize_provider_boundary" in steps["step_3_materialize"]
    assert "captured_thread_start_contract" in steps["step_6a_provider_identity_gate"]
    assert "--dump-config" in steps["step_6b_composition_identity_gate"]


def test_frozen_profile_files_exist_and_match_digests():
    composition = auth()["runnable_profile_composition"]
    profile_root = ROOT / composition["profile_files_root"]
    for relative, expected_digest in composition["profile_files_sha256"].items():
        path = profile_root / Path(relative).relative_to("profile")
        assert path.is_file(), f"missing profile file: {relative}"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected_digest, f"profile file digest drift: {relative}"


def _load_patch():
    composition = auth()["runnable_profile_composition"]
    profile_root = ROOT / composition["profile_files_root"]
    return yaml.safe_load((profile_root / "cordis.patch.yml").read_text(encoding="utf-8"))


def test_llm_pi_ai_is_patched_by_id_not_reinserted():
    # dsh-base already inserts a dormant `id: llm-pi-ai` row; a second insert
    # of the same id would collide with it rather than configure it.
    patch = _load_patch()
    inserted_ids = {entry["id"] for item in patch if "insert" in item for entry in item["insert"]}
    assert "llm-pi-ai" not in inserted_ids

    id_patches = {item["id"]: item for item in patch if "id" in item and "insert" not in item}
    assert "name" not in id_patches["llm-pi-ai"]  # a bare id+config patches the existing row
    openai_route = id_patches["llm-pi-ai"]["config"]["providers"]["openai"]
    assert set(id_patches["llm-pi-ai"]["config"]["providers"]) == {"openai"}
    assert openai_route["apiKeyEnv"] == "OPENAI_API_KEY"
    # H-04: retries are disabled, not merely counted -- step/start fires once
    # per step before step()'s own internal retry loop, so a retry never
    # produces a new step/start event and a step-count-only guard can't see it.
    assert openai_route["retryPolicy"]["maxRetries"] == 0
    assert openai_route["models"] == [{"id": "gpt-5-mini", "maxTokens": 4096}]

    assert "name" not in id_patches["agent-default-model"]
    assert id_patches["agent-default-model"]["config"] == {"provider": "openai", "model": "gpt-5-mini"}


def test_both_child_delegation_tools_are_inserted_with_correct_provider_binding():
    patch = _load_patch()
    inserted = {entry["id"]: entry for item in patch if "insert" in item for entry in item["insert"]}
    assert set(inserted) == {"subagent-codex", "subagent-claude-code", "tool-subagent-codex", "tool-subagent-claude-code"}

    assert inserted["subagent-codex"]["name"] == "@deepseek-ai/dsh-subagent-codex"
    assert inserted["subagent-claude-code"]["name"] == "@deepseek-ai/dsh-subagent-claude-code"

    codex_tool = inserted["tool-subagent-codex"]
    assert codex_tool["name"] == "@deepseek-ai/dsh-tool-subagent"
    assert codex_tool["config"]["provider"] == "codex"
    assert codex_tool["config"]["toolName"] == "subagent_codex"
    assert codex_tool["config"]["backgroundMode"] == "one-shot"

    claude_tool = inserted["tool-subagent-claude-code"]
    assert claude_tool["name"] == "@deepseek-ai/dsh-tool-subagent"
    assert claude_tool["config"]["provider"] == "claude-code"
    assert claude_tool["config"]["toolName"] == "subagent_claude_code"
    assert claude_tool["config"]["backgroundMode"] == "one-shot"


def test_frozen_profile_package_json_declares_exactly_the_headless_bundles():
    composition = auth()["runnable_profile_composition"]
    profile_root = ROOT / composition["profile_files_root"]
    manifest = json.loads((profile_root / "package.json").read_text(encoding="utf-8"))
    assert manifest["dsh"]["profile"]["bundles"] == ["@deepseek-ai/dsh-base", "@deepseek-ai/dsh-headless"]


def test_frozen_profile_matches_h01_spend_controls_exactly():
    value = auth()
    route = value["parent_model_route"]
    patch = _load_patch()
    id_patches = {item["id"]: item for item in patch if "id" in item and "insert" not in item}
    model_override = id_patches["llm-pi-ai"]["config"]["providers"]["openai"]["models"][0]
    assert model_override["id"] == route["model_id"]
    assert model_override["maxTokens"] == route["max_output_tokens_per_call_override"]


def test_provider_packages_resolve_via_link_not_registry():
    composition = auth()["runnable_profile_composition"]
    profile_root = ROOT / composition["profile_files_root"]
    manifest = json.loads((profile_root / "package.json").read_text(encoding="utf-8"))
    deps = manifest["dependencies"]
    assert deps["@deepseek-ai/dsh-subagent-codex"].startswith("link:")
    assert deps["@deepseek-ai/dsh-subagent-claude-code"].startswith("link:")
    assert "packages/subagent/subagent-codex" in deps["@deepseek-ai/dsh-subagent-codex"]
    assert "packages/subagent/subagent-claude-code" in deps["@deepseek-ai/dsh-subagent-claude-code"]
    resolution = composition["provider_package_resolution"]
    assert resolution["registry_fetch_excluded"]


def test_dedicated_dsh_home_is_not_ambient():
    composition = auth()["runnable_profile_composition"]
    dsh_home = composition["dedicated_dsh_home"]
    assert "build_root" in dsh_home
    assert "~/.dsh" in dsh_home  # documents that it is explicitly NOT the ambient host DSH_HOME


def test_authorization_has_exactly_one_synthetic_fixture():
    fixture = auth()["synthetic_fixture"]
    assert fixture["fixture_id"] == "STAGE_A_BOUNDED_RETRY_V0"
    assert fixture["single_fixture_only"] is True
    assert fixture["disposable"] is True
    assert fixture["isolated_from_qntylab_scientific_state"] is True
    assert fixture["isolated_from_qnty_runtime"] is True
    assert fixture["no_market_data"] is True
    assert fixture["no_credentials_required"] is True
    assert fixture["solved_copy_must_not_be_committed_to_qntylab_or_qnty"] is True


def test_fixture_files_exist_and_match_frozen_digests():
    fixture = auth()["synthetic_fixture"]
    fixture_root = ROOT / fixture["fixture_root"]
    for relative, expected_digest in fixture["initial_file_digests_sha256"].items():
        path = fixture_root / Path(relative).relative_to("fixture")
        assert path.is_file(), f"missing fixture file: {relative}"
        actual = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual == expected_digest, f"fixture digest drift: {relative}"


def test_fixture_stub_is_unimplemented_and_tests_are_present():
    fixture = auth()["synthetic_fixture"]
    fixture_root = ROOT / fixture["fixture_root"]
    stub = (fixture_root / "retry.py").read_text(encoding="utf-8")
    assert "NotImplementedError" in stub
    tests = (fixture_root / "tests" / "test_retry.py").read_text(encoding="utf-8")
    assert "def test_" in tests
    assert fixture["verified_at_authorization_time"]["stub_raises_not_implemented_and_all_tests_fail"] is True
    assert fixture["verified_at_authorization_time"]["reference_implementation_passes_all_tests"] is True


def test_both_intended_child_roles_are_present_with_native_routes():
    routes = auth()["child_routes"]
    assert routes["codex"]["role"] == "bounded implementation"
    assert "codex app-server" in routes["codex"]["product_route"]
    assert routes["codex"]["api_key_override_prohibited"] is True
    assert routes["claude_code"]["role"] == "independent hostile review"
    assert "claude" in routes["claude_code"]["product_route"]
    assert routes["claude_code"]["api_key_override_prohibited"] is True


def test_child_invocation_budgets_are_finite():
    routes = auth()["child_routes"]
    codex_budget = routes["codex"]["call_budget"]
    assert codex_budget["initial_implementation_calls"] == 1
    assert codex_budget["repair_calls"] == 1
    claude_budget = routes["claude_code"]["call_budget"]
    assert claude_budget["initial_review_calls"] == 1
    assert claude_budget["targeted_rereview_calls"] == 1


def test_parent_spend_authority_is_explicit_bounded_and_scoped_to_later_phase():
    route = auth()["parent_model_route"]
    assert route["spend_authority"] == "YES"
    assert isinstance(route.get("spend_authority_source"), str) and route["spend_authority_source"]
    assert route["spend_ceiling_usd"] == 1.00
    assert route["spend_ceiling_applies_to"] == "later_execution_phase_only"
    assert route["authorization_phase_parent_api_spend_usd"] == 0
    assert route["authorization_phase_parent_api_calls"] == 0


def test_parent_model_is_confirmed_compatible_with_pinned_adapter_not_asserted():
    route = auth()["parent_model_route"]
    assert route["model_id"] == "gpt-5-mini"
    assert route["model_compatibility"] == "CONFIRMED_IN_PINNED_VENDORED_CATALOG"
    catalog = route["model_catalog_entry"]
    assert catalog["id"] == "gpt-5-mini"
    assert catalog["cost_usd_per_million_tokens"]["output"] == 2
    assert route["credential_present_in_this_environment_at_authorization_time"] is False
    assert route["absent_credential_is_not_grounds_for_a_test_call"] is True


def test_parent_spend_boundedness_uses_step_ceiling_not_turn_ceiling():
    budget = auth()["parent_lifecycle_budget"]
    assert budget["budget_unit_that_actually_bounds_spend"] == "STEPS_NOT_TURNS"
    assert isinstance(budget["parent_max_total_steps"], int) and budget["parent_max_total_steps"] > 0
    assert budget["no_autonomous_indefinite_loop"] is True


def test_h04_retries_are_disabled_not_merely_counted():
    value = auth()
    budget = value["parent_lifecycle_budget"]
    route = value["parent_model_route"]

    assert budget["internal_parent_retries_disabled"] is True
    assert budget["max_parent_request_attempts"] == budget["parent_max_total_steps"]
    assert route["retry_policy"] == {"mode": "normal", "maxRetries": 0}

    # The frozen profile file must encode the same maxRetries=0, cross-checked
    # against the JSON contract rather than trusted in isolation.
    patch = _load_patch()
    id_patches = {item["id"]: item for item in patch if "id" in item and "insert" not in item}
    assert id_patches["llm-pi-ai"]["config"]["providers"]["openai"]["retryPolicy"]["maxRetries"] == route["retry_policy"]["maxRetries"]


def test_worst_case_episode_cost_stays_under_the_dollar_ceiling():
    value = auth()
    route = value["parent_model_route"]
    budget = value["parent_lifecycle_budget"]
    worst_case_total = route["worst_case_single_call_cost_usd"] * budget["parent_max_total_steps"]
    assert worst_case_total == budget["worst_case_episode_cost_usd"]
    assert worst_case_total < route["spend_ceiling_usd"]


def test_output_token_override_is_narrower_than_raw_model_catalog_max():
    route = auth()["parent_model_route"]
    assert route["max_output_tokens_per_call_override"] < route["model_catalog_entry"]["maxTokens"]


def test_openai_api_key_is_scoped_to_parent_only():
    policy = auth()["auth_secret_policy"]
    assert policy["openai_api_key_scope"] == "DSH_PARENT_PROCESS_ENVIRONMENT_ONLY"
    assert policy["openai_api_key_must_not_reach_codex_child"] is True
    assert policy["openai_api_key_must_not_reach_claude_child"] is True
    assert policy["authorization_artifact_records_mechanism_only_not_value"] is True
    text = (ARTIFACT / "authorization.json").read_text(encoding="utf-8")
    assert "sk-" not in text


def test_zero_live_authority_in_the_authorization_phase_itself():
    boundary = auth()["governance_boundary"]
    assert boundary["authorization_phase_dsh_invocations"] == 0
    assert boundary["authorization_phase_codex_invocations"] == 0
    assert boundary["authorization_phase_claude_invocations"] == 0
    assert boundary["authorization_phase_parent_api_calls"] == 0
    assert boundary["authorization_phase_parent_api_spend_usd"] == 0


def test_downstream_and_scientific_authorities_are_all_denied():
    boundary = auth()["governance_boundary"]
    for key in (
        "scientific_execution_authorized",
        "market_data_access_authorized",
        "jigsaw_mutation_authorized",
        "state_snapshot_mutation_authorized",
        "router_mutation_authorized",
        "qnty_mutation_authorized",
        "qnty_agent_eval_mutation_authorized",
        "upstream_dsh_mutation_authorized",
        "mcp_integration_authorized",
        "benchmark_suite_authority",
        "permission_forensics_reopening_authorized",
    ):
        assert boundary[key] is False, key
    for key in ("qnty_runtime_authority", "trading_authority", "promotion_authority", "capital_authority", "downstream_authority"):
        assert boundary[key] == "NONE", key


def test_only_one_later_execution_closure_phase_is_authorized():
    value = auth()
    budget = value["hard_pr_budget"]
    assert budget["later_execution_prs_authorized"] == 1
    assert budget["later_separate_forensic_prs_authorized"] == 0
    assert budget["later_additional_authorization_prs_authorized"] == 0
    assert budget["later_benchmark_prs_authorized"] == 0
    assert value["governance_boundary"]["later_execution_closure_prs"] == 1
    assert value["active_project_after_closure"] == "NONE"


def test_evaluator_is_not_applicable():
    value = auth()
    assert value["qnty_agent_eval"] == "NOT_APPLICABLE"


def test_review_policy_is_frozen_and_hostile_review_artifact_exists():
    value = auth()
    assert value["review_policy"] == {
        "authorization_hostile_review_count": 1,
        "later_hostile_review_count": 1,
        "targeted_rereview_only_if_critical_or_high_repair": True,
        "medium_low_do_not_restart": True,
    }
    review_text = (ARTIFACT / "hostile_governance_review.md").read_text(encoding="utf-8")
    assert "Critical: 0" in review_text
    assert "High: 1" in review_text


def test_authorization_effective_only_after_canonical_merge():
    value = auth()
    assert value["authorization_effective"] == "AFTER_CANONICAL_MERGE_ONLY"
    assert value["canonical_merge_gate"]["effective_only_after_authorization_merge"] is True
    assert value["canonical_merge_gate"]["noncanonical_action"] == "PRELIVE_BLOCKED"
