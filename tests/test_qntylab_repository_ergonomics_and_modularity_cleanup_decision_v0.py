import hashlib
import json
import tomllib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DECISION_PATH = ROOT / (
    "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0/decision.json"
)
PROJECTS_PATH = ROOT / "docs/state/projects.toml"
PROJECT_ID = "QNTYLAB_REPOSITORY_ERGONOMICS_AND_MODULARITY_CLEANUP_V0"
PHASE_ID = "QNTYLAB_REPOSITORY_ERGONOMICS_AND_MODULARITY_CLEANUP_DECISION_V0"
CANONICAL_PARENT = "7b1f00d7ae975aa26029e70fab190ea2b16effdc"
FORENSIC_AUDIT_IDENTITY = "QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0"
FORENSIC_AUDIT_COMMIT = "be291300abb70f3ffc6ba0dd8b1bea570daf5377"
FIRST_IMPLEMENTATION = "QNTYLAB_AGENT_CONTEXT_PACKET_V0"
EXPECTED_INCREMENT_IDS = {"C1", "C2", "C3", "C4", "C5", "C6"}
EXPECTED_INCREMENT_PHASE_IDS = {
    "QNTYLAB_AGENT_CONTEXT_PACKET_V0",
    "PROJECT_CONTEXT_MODULARIZATION_V0",
    "DEV_LOOP_CI_SPLIT_V0",
    "PYTHON_TOOLING_NORMALIZATION_V0",
    "PROVEN_DELETE_SAFE_SLIMMING_V0",
    "REPOSITORY_ERGONOMICS_FITNESS_FUNCTIONS_V0",
}
EXPECTED_EDGES = {
    ("C1", "C2"),
    ("C1", "C3"),
    ("C2", "C6"),
    ("C3", "C6"),
    ("C4", "C6"),
    ("C5", "C6"),
}
EXPECTED_PRINCIPLES = {
    "CURRENT_STATE_IS_NOT_HISTORY",
    "SECURITY_BY_SMALL_TRUSTED_CORE",
    "INFORMATION_HIDING",
    "POINTERS_OVER_COPIES",
    "COLD_HISTORY",
    "EXECUTABLE_ARCHITECTURE",
    "SMALL_BOUNDED_CHANGES",
}
EXPECTED_LOW_RISK_LIFECYCLE = [
    "IMPLEMENT",
    "TEST",
    "ONE_INDEPENDENT_REVIEW",
    "BOUNDED_CRITICAL_HIGH_REPAIR",
    "AT_MOST_ONE_TARGETED_REREVIEW",
    "CLOSED_PASS_OR_CLOSED_BLOCKED",
]
FORBIDDEN_EPHEMERAL_SUBSTRINGS = ("conversation", "attempt_completion", "this chat", "chat history")


def _decision() -> dict[str, object]:
    return json.loads(DECISION_PATH.read_text(encoding="utf-8"))


def _record(project_id: str) -> dict[str, object]:
    registry = tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    return next(row for row in registry["project"] if row["project_id"] == project_id)


def test_decision_identity_and_open_review_state() -> None:
    decision = _decision()
    record = _record(PROJECT_ID)

    assert DECISION_PATH.is_file()
    assert record["project_id"] == decision["project_id"] == PROJECT_ID
    assert record["phase_id"] == decision["phase_id"] == PHASE_ID
    assert record["phase_type"] == decision["phase_type"] == "GOVERNANCE_ONLY"
    assert record["governance_only"] is True
    assert decision["governance_only"] is True
    # Registry `state` uses the canonical validator vocabulary (qntylab/project_context.py
    # PROJECT_STATES); the review lifecycle vocabulary lives in decision_state, which the
    # registry validator does not constrain.
    assert record["state"] == "PLANNED_NOT_AUTHORIZED"
    assert (
        record["decision_state"]
        == decision["decision_state"]
        == "READY_FOR_TARGETED_CRITICAL_HIGH_REREVIEW"
    )
    assert decision["decision_state"] == decision["state"] == "READY_FOR_TARGETED_CRITICAL_HIGH_REREVIEW"
    assert decision["state"] != "CLOSED_PASS"
    assert decision["authority"] == "CANONICAL_QNTYLAB_GIT_IDENTITY_GOVERNANCE_ONLY"
    assert decision["canonical_parent"] == CANONICAL_PARENT
    assert decision["forensic_audit_identity"] == FORENSIC_AUDIT_IDENTITY
    assert decision["forensic_audit_commit"] == FORENSIC_AUDIT_COMMIT


def test_decision_enumerates_exactly_six_increments() -> None:
    decision = _decision()

    assert decision["authorized_implementation_increment_count"] == 6
    increments = decision["authorized_implementation_increments"]
    assert len(increments) == 6
    assert {inc["increment_id"] for inc in increments} == EXPECTED_INCREMENT_IDS
    assert {inc["phase_id"] for inc in increments} == EXPECTED_INCREMENT_PHASE_IDS
    assert decision["scientific_evaluation_phase_count"] == 0
    assert decision["first_implementation_after_governance"] == FIRST_IMPLEMENTATION


def test_decision_grants_zero_scientific_and_downstream_authority() -> None:
    decision = _decision()
    out_of_scope = decision["out_of_scope"]

    assert out_of_scope["SCIENTIFIC_EVALUATION_PHASES_AUTHORIZED"] == 0
    for field in (
        "REAL_DATA_AUTHORITY",
        "PROVIDER_AUTHORITY",
        "CLAIM_AUTHORITY",
        "TRADING_AUTHORITY",
        "CAPITAL_AUTHORITY",
        "QNTY_AUTHORITY",
        "QNTYSPOT_AUTHORITY",
        "ROUTER_AUTHORITY",
    ):
        assert out_of_scope[field] == "NONE"
    for field in (
        "real_data_access_authorized",
        "outcome_access_authorized",
        "provider_access_authorized",
        "claim_consumption_authorized",
        "scientific_execution_authorized",
    ):
        assert out_of_scope[field] is False


def test_packet_byte_cap_constant() -> None:
    decision = _decision()
    metrics = decision["acceptance_metrics"]

    packet = metrics["packet"]
    assert packet["hard_cap_bytes"] == 8192
    assert packet["typical_target_bytes"] == 7000
    assert packet["no_silent_truncation"] is True
    assert packet["fail_closed_on_overflow"] is True
    assert metrics["DEFAULT_AGENT_CONTEXT_REDUCTION_PERCENT"]["minimum"] == 95


def test_dependency_graph() -> None:
    decision = _decision()
    graph = decision["increment_graph"]

    edges = set()
    for edge in graph["edges"]:
        src, dst = edge.split(" -> ")
        edges.add((src, dst))
    assert edges == EXPECTED_EDGES

    increments = {inc["increment_id"]: inc for inc in decision["authorized_implementation_increments"]}
    assert increments["C1"]["dependencies"] == []
    assert increments["C4"]["dependencies"] == []
    assert increments["C5"]["dependencies"] == []
    assert increments["C2"]["dependencies"] == ["C1"]
    assert increments["C3"]["dependencies"] == ["C1"]
    assert increments["C6"]["dependencies"] == ["C2", "C3", "C4", "C5"]

    # Acyclic: Kahn topological sort must consume all six nodes.
    indegree = {node: 0 for node in EXPECTED_INCREMENT_IDS}
    adjacency: dict[str, list[str]] = {node: [] for node in EXPECTED_INCREMENT_IDS}
    for src, dst in edges:
        adjacency[src].append(dst)
        indegree[dst] += 1
    queue = sorted(node for node, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while queue:
        node = queue.pop(0)
        order.append(node)
        for nxt in adjacency[node]:
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)
    assert len(order) == 6

    # C6 is the unique terminal node (no outgoing edges).
    assert {dst for _, dst in edges} - {src for src, _ in edges} == {"C6"}
    assert graph["terminal_increment"] == "C6"


def test_forbidden_operations_present() -> None:
    decision = _decision()
    out_of_scope = decision["out_of_scope"]

    forbidden = " ".join(out_of_scope["forbidden_operations"]).lower()
    assert "frozen output modification" in forbidden
    assert "oracle semantics change" in forbidden
    assert "git history rewrite" in forbidden
    assert "frozen/hash-bound deletion" in forbidden
    assert "pr #239" in forbidden and "pr #241" in forbidden
    assert "pr #245 revival" in forbidden
    assert "archive/lfs/dvc migration" in forbidden
    assert "render --check breakage" in forbidden
    assert "generated summary replacing canonical state" in forbidden
    assert "funding-contract successor" in forbidden
    assert "funding_incremental_contract_integrity_hardening_implementation_v0" in forbidden

    assert decision["out_of_scope"]["explicit_non_authorizations"]
    assert decision["kill_criteria"]


def test_open_pr_isolation() -> None:
    decision = _decision()
    isolation = decision["open_pr_isolation"]

    assert isolation["isolated_prs"] == [241, 239, 189, 6]
    assert isolation["merge_authority"] == "NONE"
    assert isolation["repair_authority"] == "NONE"
    assert isolation["rereview_authority"] == "NONE"
    assert isolation["cherrypick_authority"] == "NONE"
    assert CANONICAL_PARENT in isolation["lineage_rule"]


def test_review_tiers() -> None:
    decision = _decision()
    tiers = decision["review_tiers"]

    low_risk = tiers["LOW_RISK_ERGONOMIC_CHANGE"]
    assert low_risk["lifecycle"] == EXPECTED_LOW_RISK_LIFECYCLE

    authority_tier = tiers["AUTHORITY_OR_SECURITY_SEMANTIC_CHANGE"]
    assert authority_tier["action"] == "STOP"
    assert "separate governance decision" in authority_tier["rule"]


def test_frozen_first_principles() -> None:
    decision = _decision()
    principles = decision["frozen_first_principles"]

    assert set(principles.keys()) == EXPECTED_PRINCIPLES
    assert all(entry["required"] is True for entry in principles.values())


def test_safety_invariants_and_gates_declared() -> None:
    decision = _decision()
    metrics = decision["acceptance_metrics"]

    invariants = " ".join(metrics["safety_invariants"]).lower()
    assert "doctor --strict" in invariants
    assert "render --check" in invariants
    assert "research_ledger doctor" in invariants
    assert "scientific authority unchanged" in invariants
    assert "frozen bytes unchanged" in invariants

    gates = " ".join(decision["acceptance_gates"]).lower()
    assert "diff is limited to authorized surfaces" in gates


def test_registry_entry_consistency() -> None:
    decision = _decision()
    record = _record(PROJECT_ID)

    assert record["decision_artifact"] == (
        "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0/decision.json"
    )
    live_sha256 = hashlib.sha256(DECISION_PATH.read_bytes()).hexdigest()
    assert live_sha256 == record["decision_artifact_sha256"]
    assert record["candidate_state"] == "CANONICAL_GOVERNANCE_DECISION"
    assert record["canonicalization_status"] == "NOT_CANONICALIZED"
    assert record["authorized_implementation_increment_count"] == 6
    assert record["first_implementation_increment"] == FIRST_IMPLEMENTATION
    assert record["scientific_evaluation_phases_authorized"] == 0
    for field in (
        "real_data_access_authorized",
        "outcome_access_authorized",
        "provider_access_authorized",
        "claim_access_authorized",
        "claim_consumption_authorized",
    ):
        assert record[field] is False
    for field in (
        "router_authority",
        "qnty_authority",
        "qntyspot_authority",
        "trading_authority",
        "capital_authority",
        "downstream_authority",
    ):
        assert record[field] == "NONE"
    assert record["review_lifecycle_current_stage"] == "READY_FOR_TARGETED_CRITICAL_HIGH_REREVIEW"
    assert record["targeted_rereview_required"] is True
    assert record["critical_high_rereviews_used"] == 0
    assert record["next_action"] == "ONE_TARGETED_REREVIEW_OF_P1_A_AND_P1_B"
    assert record["canonical_parent"] == decision["canonical_parent"] == CANONICAL_PARENT


def test_no_ephemeral_references() -> None:
    serialized = DECISION_PATH.read_bytes().decode("utf-8").lower()
    for forbidden in FORBIDDEN_EPHEMERAL_SUBSTRINGS:
        assert forbidden not in serialized


def test_c5_pre_deletion_reference_reproof_gate() -> None:
    decision = _decision()
    c5 = next(
        increment
        for increment in decision["authorized_implementation_increments"]
        if increment["increment_id"] == "C5"
    )

    criteria = c5["acceptance_criteria"]
    assert any("PRE_DELETION_REFERENCE_REPROOF_GATE" in criterion for criterion in criteria)

    gate_criterion = next(
        criterion for criterion in criteria if "PRE_DELETION_REFERENCE_REPROOF_GATE" in criterion
    )
    for category in (
        "PYTHON_IMPORT_REFERENCES",
        "DOCSTRING_PROSE_REFERENCES",
        "TEST_REFERENCES",
        "PROJECT_REGISTRY_REFERENCES",
        "AUTHORITATIVE_ARTIFACT_REFERENCES",
        "HASH_BINDINGS",
        "PREREGISTRATION_BINDINGS",
        "CLOSURE_REFERENCES",
        "ADR_REFERENCES",
        "RESEARCH_LEDGER_REFERENCES",
        "CI_REFERENCES",
        "GENERATED_VIEW_REFERENCES",
    ):
        assert category in gate_criterion
    assert "CURRENT canonical master HEAD" in gate_criterion
    assert any(
        "necessary but NOT sufficient" in criterion for criterion in criteria
    )
    assert "PRE_DELETION_REFERENCE_REPROOF_GATE" in c5["objective"]


HOSTILE_REVIEW_PATH = ROOT / (
    "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0/hostile_review.json"
)
EXPECTED_HOSTILE_REVIEW = {
    "REVIEW_TYPE": "INDEPENDENT_HOSTILE_REVIEW",
    "REVIEW_ID": "PRR_kwDOTo27Xs8AAAABMRPxcA",
    "REVIEWED_COMMIT": "f1e7821b11fb87574771694c322ffb8442ebfccc",
    "CRITICAL": 0,
    "HIGH": 2,
    "P1_A_THREAD": "PRRT_kwDOTo27Xs6fdZ14",
    "P1_B_THREAD": "PRRT_kwDOTo27Xs6fdZ16",
    "BOUNDED_REPAIR_USED": True,
    "TARGETED_REREVIEW_REQUIRED": True,
    "TARGETED_REREVIEW_USED": False,
    "STATE": "REPAIR_COMPLETE_AWAITING_TARGETED_REREVIEW",
}


def test_governance_decision_lifecycle_not_gated_by_increments() -> None:
    decision = _decision()
    state_lifecycle = decision["state_lifecycle"]
    separation = decision["lifecycle_separation"]

    # The circular closure prerequisite is gone from state_lifecycle.
    assert "all six increments closed" not in state_lifecycle["closed_pass_rule"]
    assert "do not gate governance-decision closure" in state_lifecycle["closed_pass_rule"]
    assert "MUST NOT be prerequisites" in separation["rule"]
    assert "BETWEEN IMPLEMENTATION INCREMENTS" in separation["rule"]
    assert separation["governance_decision_lifecycle"][-1] == "CLOSED_PASS"
    assert "C1-C6 each execute independently" in separation["cleanup_program_increment_lifecycles"]

    # Increment graph edges are unchanged and remain between-increment dependencies.
    graph = decision["increment_graph"]
    edges = set()
    for edge in graph["edges"]:
        src, dst = edge.split(" -> ")
        edges.add((src, dst))
    assert edges == EXPECTED_EDGES


def test_c1_renderer_semantics_contract() -> None:
    decision = _decision()
    c1 = next(
        increment
        for increment in decision["authorized_implementation_increments"]
        if increment["increment_id"] == "C1"
    )
    criteria = c1["acceptance_criteria"]

    # No criterion requires global repository byte identity any more.
    for criterion in criteria:
        assert "outputs byte-unchanged" not in criterion
    contract = next(
        criterion for criterion in criteria if "SAME_INPUT -> SAME_OLD_RENDERER_OUTPUT" in criterion
    )
    # Fixed pre-C1 input gives byte-identical legacy renderer output.
    assert "identical canonical input tree / identical registry bytes" in contract
    assert "pre-existing brief and spine renderer outputs MUST remain byte-identical" in contract
    # The one authorized registration row and the generated roadmap delta are allowed.
    assert "explicitly authorized registration row" in contract
    assert "generated roadmap delta" in contract
    assert "explicitly excluded from repository-byte-identity comparisons" in contract
    # Renderer semantics are protected.
    assert "MUST NOT modify qntylab/project_context.py" in contract
    assert "brief rendering implementation" in contract
    assert "spine rendering implementation" in contract
    assert "projects.toml schema/rendering semantics" in contract
    # Packet generation must not mutate canonical state.
    assert "must not mutate canonical state" in contract


def test_c1_forbidden_paths_protect_renderers() -> None:
    decision = _decision()
    c1 = next(
        increment
        for increment in decision["authorized_implementation_increments"]
        if increment["increment_id"] == "C1"
    )

    forbidden = c1["forbidden_paths"]
    assert any("qntylab/project_context.py" in path for path in forbidden)
    assert any("brief/spine output bytes" in path for path in forbidden)
    assert any("projects.toml rendering semantics" in path for path in forbidden)


def test_hostile_review_receipt() -> None:
    assert HOSTILE_REVIEW_PATH.is_file()
    receipt = json.loads(HOSTILE_REVIEW_PATH.read_text(encoding="utf-8"))
    assert receipt == EXPECTED_HOSTILE_REVIEW


def test_decision_state_awaiting_rereview() -> None:
    decision = _decision()
    review_lifecycle = decision["review_lifecycle"]

    assert review_lifecycle["current_stage"] == "READY_FOR_TARGETED_CRITICAL_HIGH_REREVIEW"
    assert review_lifecycle["targeted_rereview_used"] is False
    assert review_lifecycle["bounded_repair_used"] is True
    assert review_lifecycle["hostile_review_count"] == 1
    assert review_lifecycle["original_critical_count"] == 0
    assert review_lifecycle["original_high_count"] == 2
    assert decision["next_action"] == "ONE_TARGETED_REREVIEW_OF_P1_A_AND_P1_B"
    assert decision["state"] != "CLOSED_PASS"
    assert decision["decision_state"] != "CLOSED_PASS"
    # No finding is marked fully resolved before the targeted rereview.
    for entry in review_lifecycle["repair_history"]:
        assert entry["status"] == "RESOLVED_PENDING_REREVIEW"


def test_registry_lifecycle_consistency() -> None:
    decision = _decision()
    record = _record(PROJECT_ID)

    assert record["review_lifecycle_current_stage"] == "READY_FOR_TARGETED_CRITICAL_HIGH_REREVIEW"
    assert record["targeted_rereview_required"] is True
    assert record["critical_high_rereviews_used"] == 0
    assert record["next_action"] == "ONE_TARGETED_REREVIEW_OF_P1_A_AND_P1_B"
    assert record["state"] == "PLANNED_NOT_AUTHORIZED"
    live_sha256 = hashlib.sha256(DECISION_PATH.read_bytes()).hexdigest()
    assert live_sha256 == record["decision_artifact_sha256"]
