import hashlib
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLARIFICATION_PATH = ROOT / (
    "experiments/research/"
    "qntylab_repository_ergonomics_and_modularity_cleanup_v0/"
    "c1_agent_context_packet_v0/schema_clarification.json"
)
UMBRELLA_DECISION_PATH = ROOT / (
    "experiments/research/qntylab_repository_ergonomics_and_modularity_cleanup_v0/decision.json"
)
FORENSIC_PATH = ROOT / (
    "docs/forensics/"
    "QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0/"
    "agent_context_target.md"
)
PROJECTS_PATH = ROOT / "docs/state/projects.toml"
RECEIPT_PATH = ROOT / (
    "experiments/research/"
    "qntylab_repository_ergonomics_and_modularity_cleanup_v0/"
    "c1_agent_context_packet_v0/schema_clarification_review_receipt.json"
)

CLARIFICATION_ID = "QNTYLAB_AGENT_CONTEXT_PACKET_SCHEMA_CLARIFICATION_V0"
UMBRELLA_ID = "QNTYLAB_REPOSITORY_ERGONOMICS_AND_MODULARITY_CLEANUP_V0"
AFFECTED_PHASE = "QNTYLAB_AGENT_CONTEXT_PACKET_V0"
AFFECTED_INCREMENT = "C1"
REVIEWED_CANDIDATE = "a3a22df3604d58671ec7c4b2fd4e90b4c5b7b67a"

EXPECTED_FIELD_ORDER = [
    "REPOSITORY",
    "HEAD",
    "WORKTREE",
    "PHASE_ID",
    "STATE",
    "OBJECTIVE",
    "AUTHORITY_SOURCE",
    "ALLOWED_OPERATIONS",
    "FORBIDDEN_OPERATIONS",
    "INPUT_CONTRACTS",
    "OUTPUT_CONTRACTS",
    "LOAD_BEARING_INVARIANTS",
    "RELEVANT_CODE",
    "RELEVANT_TESTS",
    "IMMUTABLE_PATHS",
    "OPEN_BLOCKERS",
    "REVIEW_LIFECYCLE",
    "NEXT_ACTION",
    "VERIFY_COMMAND",
]
FORBIDDEN_FIELD_NAMES = {"ENVELOPE", "SCHEMA", "SCHEMA_VERSION", "PACKET_VERSION", "METADATA"}
EXPECTED_INCREMENT_IDS = {"C1", "C2", "C3", "C4", "C5", "C6"}
AUTHORITY_NONE_FIELDS = (
    "scientific_evaluation_authority",
    "scientific_execution_authority",
    "real_data_authority",
    "provider_authority",
    "claim_authority",
    "router_authority",
    "qnty_authority",
    "qntyspot_authority",
    "trading_authority",
    "capital_authority",
    "downstream_authority",
)
FORBIDDEN_EPHEMERAL_SUBSTRINGS = ("conversation", "attempt_completion", "this chat", "chat history")


def _clarification() -> dict[str, object]:
    return json.loads(CLARIFICATION_PATH.read_text(encoding="utf-8"))


def _umbrella_decision() -> dict[str, object]:
    return json.loads(UMBRELLA_DECISION_PATH.read_text(encoding="utf-8"))


def _record(project_id: str) -> dict[str, object]:
    registry = tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8"))
    return next(row for row in registry["project"] if row["project_id"] == project_id)


def test_1_schema_field_count_is_19() -> None:
    resolution = _clarification()["resolution"]
    assert resolution["schema_field_count"] == 19
    assert len(resolution["field_order"]) == 19


def test_2_field_order_is_exact_19_name_sequence() -> None:
    resolution = _clarification()["resolution"]
    assert resolution["field_order"] == EXPECTED_FIELD_ORDER


def test_3_envelope_is_not_a_schema_field() -> None:
    resolution = _clarification()["resolution"]
    assert resolution["envelope_is_schema_field"] is False
    assert resolution["envelope_disposition"] == "BYTE_BUDGET_ACCOUNTING_ONLY"


def test_4_no_twentieth_field_invented_and_no_forbidden_names() -> None:
    resolution = _clarification()["resolution"]
    assert resolution["no_twentieth_field_invented"] is True
    field_set = set(resolution["field_order"])
    assert len(field_set) == 19
    assert field_set == set(EXPECTED_FIELD_ORDER)
    assert field_set.isdisjoint(FORBIDDEN_FIELD_NAMES)
    assert set(resolution["forbidden_field_names"]) == FORBIDDEN_FIELD_NAMES


def test_5_fixed_20_field_text_superseded_and_forensic_untouched() -> None:
    resolution = _clarification()["resolution"]
    assert (
        resolution["forensic_fixed_20_field_text_disposition"]
        == "COUNTING_ERROR_SUPERSEDED_FOR_C1_IMPLEMENTATION_BY_THIS_CLARIFICATION"
    )
    assert resolution["forensic_artifact_disposition"] == "IMMUTABLE_HISTORICAL_DESIGN_EVIDENCE"
    # The forensic artifact still contains the original section 4 sentence:
    # proof that the forensic artifact was not modified by this clarification.
    forensic_text = FORENSIC_PATH.read_text(encoding="utf-8")
    assert "Fixed 20-field schema; renderer rejects unknown/missing fields." in forensic_text
    # The original conflict evidence is still present verbatim.
    assert "| *(envelope: keys, newlines, escaping)* | | | ~1,000 |" in forensic_text
    # The section 3 phrase wraps across source lines; normalize whitespace first.
    forensic_normalized = " ".join(forensic_text.split())
    assert "exactly these fields, in this order" in forensic_normalized


def test_6_c1_review_count_remains_one() -> None:
    lifecycle = _clarification()["c1_review_lifecycle"]
    assert lifecycle["independent_hostile_review_count"] == 1
    assert lifecycle["no_review_loop_reset"] is True
    assert lifecycle["no_second_unrestricted_review"] is True


def test_7_c1_bounded_repair_and_rereview_not_consumed() -> None:
    lifecycle = _clarification()["c1_review_lifecycle"]
    assert lifecycle["bounded_repair_used"] is False
    assert lifecycle["targeted_rereview_used"] is False
    assert lifecycle["does_not_consume_bounded_repair"] is True
    assert (
        lifecycle["post_clarification_repair_authorization"]
        == "EXACTLY_ONE_BOUNDED_REPAIR_COVERING_ALL_THREE_P1S"
    )
    assert lifecycle["post_repair_rereview"] == "AT_MOST_ONE_TARGETED_REREVIEW"


def test_8_new_increment_count_is_zero() -> None:
    clarification = _clarification()
    umbrella = _umbrella_decision()

    umbrella_relation = clarification["umbrella_relation"]
    assert umbrella_relation["new_increment_authorized"] is False
    assert umbrella_relation["authorized_implementation_increment_count_change"] == 0

    increments = umbrella["authorized_implementation_increments"]
    assert len(increments) == 6
    assert {inc["increment_id"] for inc in increments} == EXPECTED_INCREMENT_IDS
    assert umbrella["authorized_implementation_increment_count"] == 6


def test_9_c2_through_c6_unchanged() -> None:
    umbrella_relation = _clarification()["umbrella_relation"]
    for key in ("c2_changed", "c3_changed", "c4_changed", "c5_changed", "c6_changed"):
        assert umbrella_relation[key] is False
    assert umbrella_relation["c1_same_increment_and_review_lifecycle"] is True
    assert umbrella_relation["umbrella_state_unchanged"] == "CLOSED_PASS"


def test_10_scientific_authority_is_none() -> None:
    firewall = _clarification()["authority_firewall"]
    for field in AUTHORITY_NONE_FIELDS:
        assert firewall[field] in ("NONE", False)
    assert firewall["scientific_question_answered"] is False
    assert firewall["historical_result_changed"] is False
    assert firewall["frozen_evidence_deleted"] is False


def test_11_p1_dispositions_and_repair_semantics_not_implemented() -> None:
    clarification = _clarification()
    findings = clarification["review_findings"]["findings"]
    by_id = {finding["finding_id"]: finding for finding in findings}

    assert by_id["P1_SCHEMA_CONFLICT"]["thread_id"] == "PRRT_kwDOTo27Xs6fe8He"
    assert by_id["P1_SCHEMA_CONFLICT"]["disposition"] == "RESOLVED_BY_CANONICAL_SCHEMA_CLARIFICATION"
    assert by_id["P1_OUTPUT_CONTRACT_TRUNCATION"]["thread_id"] == "PRRT_kwDOTo27Xs6fe8Hh"
    assert by_id["P1_OUTPUT_CONTRACT_TRUNCATION"]["disposition"] == "OPEN_IMPLEMENTATION_HIGH"
    assert by_id["P1_DECISION_DIGEST_MISMATCH"]["thread_id"] == "PRRT_kwDOTo27Xs6fe8Hj"
    assert by_id["P1_DECISION_DIGEST_MISMATCH"]["disposition"] == "OPEN_IMPLEMENTATION_HIGH"

    repair_semantics = clarification["expected_repair_semantics_informational_not_implemented"]
    assert repair_semantics["status"] == "NOT_IMPLEMENTED_IN_THIS_CLARIFICATION_TASK"
    assert "authoritative_artifacts[:4]" in repair_semantics["P1_OUTPUT_CONTRACT_TRUNCATION"]
    assert "FAIL CLOSED" in repair_semantics["P1_OUTPUT_CONTRACT_TRUNCATION"]
    assert "sha256(actual bytes) == decision_artifact_sha256" in repair_semantics[
        "P1_DECISION_DIGEST_MISMATCH"
    ]
    assert "FAIL CLOSED" in repair_semantics["P1_DECISION_DIGEST_MISMATCH"]


def test_12_binding_to_c1_phase_and_umbrella() -> None:
    clarification = _clarification()
    umbrella = _umbrella_decision()
    umbrella_relation = clarification["umbrella_relation"]

    assert umbrella_relation["affected_phase"] == AFFECTED_PHASE
    assert umbrella_relation["affected_increment"] == AFFECTED_INCREMENT
    assert umbrella_relation["governing_umbrella"] == umbrella["project_id"] == UMBRELLA_ID
    assert clarification["c1_review_lifecycle"]["reviewed_candidate"] == REVIEWED_CANDIDATE
    assert clarification["resolution"]["byte_cap_unchanged"] == 8192


def test_13_closed_pass_self_lifecycle() -> None:
    clarification = _clarification()
    self_lifecycle = clarification["self_review_lifecycle"]

    assert clarification["state"] == "CLOSED_PASS"
    assert clarification["decision_state"] == "CLOSED_PASS"
    assert clarification["review_lifecycle_current_stage"] == "CLOSED"
    assert clarification["unresolved_critical"] == 0
    assert clarification["unresolved_high"] == 0
    assert self_lifecycle["state"] == "CLOSED_PASS"
    assert self_lifecycle["decision_state"] == "CLOSED_PASS"
    assert self_lifecycle["independent_hostile_governance_review_count"] == 1
    assert self_lifecycle["required_independent_hostile_governance_reviews"] == 1
    assert self_lifecycle["bounded_clarification_repair_used"] is False
    assert self_lifecycle["targeted_rereview_required"] is False
    assert self_lifecycle["targeted_rereview_used"] is False
    assert (
        self_lifecycle["next_action"]
        == "PERFORM_SINGLE_BOUNDED_C1_REPAIR_FOR_ORIGINAL_THREE_P1_FINDINGS"
    )
    assert self_lifecycle["target_state_after_review_success"] == "CLOSED_PASS"
    assert self_lifecycle["target_decision_state_after_review_success"] == "CLOSED_PASS"
    assert len(self_lifecycle["review_focus"]) == 5

    review_evidence = self_lifecycle["review_evidence"]
    assert review_evidence["evidence_type"] == "CODEX_NO_SUGGESTIONS_PR_REACTION"
    assert review_evidence["reviewed_candidate"] == "63d588b31da9c5a409c2ecf0f2ae765cfd88b908"
    assert review_evidence["request_comment_id"] == 5548485113
    assert review_evidence["formal_review_id"] is None
    assert review_evidence["reaction_id"] == 489707669
    assert review_evidence["reaction"] == "+1"
    assert review_evidence["reaction_created_at"] == "2026-09-05T01:42:41Z"
    assert review_evidence["reaction_actor"] == "chatgpt-codex-connector[bot]"
    assert review_evidence["critical"] == 0
    assert review_evidence["high"] == 0


def test_13b_review_receipt_file_matches_truthful_receipt() -> None:
    receipt = json.loads(RECEIPT_PATH.read_text(encoding="utf-8"))
    assert receipt["REVIEW_TYPE"] == "INDEPENDENT_HOSTILE_GOVERNANCE_REVIEW"
    assert receipt["REVIEWED_CANDIDATE"] == "63d588b31da9c5a409c2ecf0f2ae765cfd88b908"
    assert receipt["REQUEST_COMMENT_ID"] == 5548485113
    assert receipt["EVIDENCE_TYPE"] == "CODEX_NO_SUGGESTIONS_PR_REACTION"
    assert receipt["FORMAL_REVIEW_ID"] is None
    assert receipt["REACTION_ID"] == 489707669
    assert receipt["REACTION"] == "+1"
    assert receipt["REACTION_CREATED_AT"] == "2026-09-05T01:42:41Z"
    assert receipt["REACTION_ACTOR"] == "chatgpt-codex-connector[bot]"
    assert receipt["CRITICAL"] == 0
    assert receipt["HIGH"] == 0
    assert receipt["BOUNDED_REPAIR_USED"] is False
    assert receipt["TARGETED_REREVIEW_REQUIRED"] is False
    assert receipt["TARGETED_REREVIEW_USED"] is False
    assert receipt["FINAL_DISPOSITION"] == "CLOSED_PASS"


def test_13c_registry_row_closed_pass_state() -> None:
    record = _record(CLARIFICATION_ID)
    assert record["state"] == "CLOSED_PASS"
    assert record["decision_state"] == "CLOSED_PASS"
    assert record["review_lifecycle_current_stage"] == "CLOSED"
    assert record["hostile_review_count"] == 1
    assert record["bounded_repair_used"] is False
    assert record["targeted_rereview_required"] is False
    assert record["targeted_rereview_used"] is False
    assert record["unresolved_critical"] == 0
    assert record["unresolved_high"] == 0
    assert (
        record["next_action"]
        == "PERFORM_SINGLE_BOUNDED_C1_REPAIR_FOR_ORIGINAL_THREE_P1_FINDINGS"
    )
    assert record["authorized_implementation_increment_count_change"] == 0
    receipt_relpath = (
        "experiments/research/"
        "qntylab_repository_ergonomics_and_modularity_cleanup_v0/"
        "c1_agent_context_packet_v0/schema_clarification_review_receipt.json"
    )
    assert receipt_relpath in record["authoritative_artifacts"]


def test_14_registry_row_sha256_binding() -> None:
    record = _record(CLARIFICATION_ID)
    live_sha256 = hashlib.sha256(CLARIFICATION_PATH.read_bytes()).hexdigest()
    assert record["decision_artifact"] == str(CLARIFICATION_PATH.relative_to(ROOT))
    assert record["decision_artifact_sha256"] == live_sha256


def test_15_no_ephemeral_references() -> None:
    serialized = CLARIFICATION_PATH.read_bytes().decode("utf-8").lower()
    for forbidden in FORBIDDEN_EPHEMERAL_SUBSTRINGS:
        assert forbidden not in serialized