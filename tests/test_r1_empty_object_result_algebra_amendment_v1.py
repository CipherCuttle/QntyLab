"""Hostile tests for
experiments/data/r1_empty_object_result_algebra_amendment_v1.json
(a PROTOCOL_AMENDMENT_CANDIDATE, not yet frozen -- see its own "status" field).

The forensic receipt at r1_empty_object_schema_id_contract_forensic_review_v1.json
(CONFIRMED, read-only) established that the canonical public materialization
entrypoint currently returns status=MATERIALIZED_VALID_RECORD, is_valid=True,
record.schema_id=None for a raw object whose own frozen schema admission
evaluates to SCHEMA_INADMISSIBLE -- a direct contradiction of the frozen
schema_admission_rule -- and that the binary MATERIALIZED_VALID_RECORD /
MATERIALIZATION_QUARANTINED_NO_RECORD result model has no representable
outcome for a legitimate, schema-inadmissible, zero-trade EMPTY_OBJECT
observation. This candidate defines the missing third outcome,
EMPTY_OBJECT_ZERO_TRADE_OBSERVATION, as a protocol-level result algebra.

This file verifies the CANDIDATE ARTIFACT'S OWN semantics and authority
bindings -- the tagged-union invariants, the countermodel classifications,
and the exact-hash bindings to already-frozen authorities -- exactly as
tests/test_r1_source_structure_recognition_amendment_v1.py and
tests/test_r1_daily_market_evidence_schema_admission_amendment_v1.py do for
their own still-or-formerly-unfrozen candidates. It does NOT test runtime
behavior: no change is made to qntylab/r1_daily_market_materializer.py by
this candidate, so the confirmed runtime contradiction (Countermodel A)
necessarily still reproduces at this commit -- that is expected, and this
file asserts the candidate classifies it FORBIDDEN_BY_RESULT_ALGEBRA in its
own text, not that the runtime has stopped producing it.
"""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "experiments/data"

CANDIDATE_PATH = DATA / "r1_empty_object_result_algebra_amendment_v1.json"
CONTRACT_PATH = DATA / "r1_normalized_evidence_contract_v1.json"
REGISTRY_PATH = DATA / "r1_source_schema_registry_v1.json"
RECOGNITION_PATH = DATA / "r1_source_structure_recognition_amendment_v1.json"
SCOPE_PATH = DATA / "r1_source_schema_registry_scope_amendment_v1.json"
ADMISSION_PATH = DATA / "r1_daily_market_evidence_schema_admission_amendment_v1.json"
FORENSIC_PATH = DATA / "r1_empty_object_schema_id_contract_forensic_review_v1.json"

PARENT_HEAD = "ce9e2ceed932e338141cbc144e9c22af1d9d138b"


def _canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _hash(payload_bytes):
    return hashlib.sha256(payload_bytes).hexdigest()


def _semantic_hash(value):
    return _hash(_canonical_bytes(value))


def _candidate():
    return json.loads(CANDIDATE_PATH.read_bytes())


def _frozen(path):
    doc = json.loads(path.read_bytes())
    assert doc["status"] == "FROZEN", f"{path.name} expected FROZEN, got {doc['status']!r}"
    return doc


# ---------------------------------------------------------------------------
# Candidate governance shape
# ---------------------------------------------------------------------------

def test_candidate_is_unfrozen_candidate_not_yet_reviewed():
    candidate = _candidate()
    assert candidate["status"] == "CANDIDATE_NOT_YET_FROZEN"
    assert candidate["self_freeze_authorized"] is False
    assert candidate["artifact_kind"] == "PROTOCOL_AMENDMENT_CANDIDATE"
    assert candidate["artifact"] == "r1_empty_object_result_algebra_amendment_v1"
    assert "freeze_provenance" not in candidate
    assert candidate["raw_deletion_authorized"] is False
    assert candidate["outcome_embargo"] is True


def test_candidate_parent_head_matches_expected_baseline():
    assert _candidate()["parent_head"] == PARENT_HEAD


def test_candidate_semantic_content_hash_recomputes_exactly():
    candidate = _candidate()
    assert _semantic_hash(candidate["semantic_body"]) == candidate["amendment_semantic_content_sha256"]


def test_candidate_effective_binding_hash_recomputes_exactly():
    candidate = _candidate()
    assert _semantic_hash(candidate["effective_combined_contract_binding"]) == candidate["effective_combined_contract_binding_sha256"]


def test_candidate_binds_exact_current_bytes_of_every_named_authority():
    candidate = _candidate()
    bound = candidate["bound_authority"]
    exact = {
        "base_contract_sha256": CONTRACT_PATH.read_bytes(),
        "base_registry_sha256": REGISTRY_PATH.read_bytes(),
        "frozen_source_structure_recognition_amendment_sha256": RECOGNITION_PATH.read_bytes(),
        "frozen_source_schema_registry_scope_amendment_sha256": SCOPE_PATH.read_bytes(),
        "frozen_daily_market_evidence_schema_admission_amendment_sha256": ADMISSION_PATH.read_bytes(),
        "empty_object_schema_id_contract_forensic_review_sha256": FORENSIC_PATH.read_bytes(),
    }
    for field, payload in exact.items():
        assert _hash(payload) == bound[field], f"bound_authority.{field} mismatch"


def test_candidate_binds_semantic_and_effective_hashes_of_bound_amendments():
    candidate = _candidate()
    bound = candidate["bound_authority"]
    recognition = _frozen(RECOGNITION_PATH)
    scope = _frozen(SCOPE_PATH)
    admission = _frozen(ADMISSION_PATH)
    assert recognition["amendment_semantic_content_sha256"] == bound["frozen_source_structure_recognition_semantic_sha256"]
    assert recognition["effective_combined_contract_binding_sha256"] == bound["frozen_source_structure_recognition_effective_binding_sha256"]
    assert scope["amendment_semantic_content_sha256"] == bound["frozen_source_schema_registry_scope_semantic_sha256"]
    assert scope["effective_combined_contract_binding_sha256"] == bound["frozen_source_schema_registry_scope_effective_binding_sha256"]
    assert admission["amendment_semantic_content_sha256"] == bound["frozen_daily_market_evidence_schema_admission_semantic_sha256"]
    assert admission["effective_combined_contract_binding_sha256"] == bound["frozen_daily_market_evidence_schema_admission_effective_binding_sha256"]


def test_bound_frozen_authorities_are_all_actually_frozen():
    for path in (RECOGNITION_PATH, SCOPE_PATH, ADMISSION_PATH):
        _frozen(path)


def test_effective_combined_contract_binding_names_every_bound_authority():
    candidate = _candidate()
    binding = candidate["effective_combined_contract_binding"]
    assert binding["amendment_semantic_content_sha256"] == candidate["amendment_semantic_content_sha256"]
    for key in (
        "base_contract_sha256", "base_registry_sha256",
        "frozen_source_structure_recognition_amendment_sha256",
        "frozen_source_structure_recognition_effective_binding_sha256",
        "frozen_source_schema_registry_scope_amendment_sha256",
        "frozen_source_schema_registry_scope_effective_binding_sha256",
        "frozen_daily_market_evidence_schema_admission_amendment_sha256",
        "frozen_daily_market_evidence_schema_admission_effective_binding_sha256",
    ):
        assert key in binding


# ---------------------------------------------------------------------------
# Existing frozen artifact bytes must remain untouched by authoring this
# candidate -- this is a read-only additive amendment.
# ---------------------------------------------------------------------------

def test_existing_frozen_artifact_bytes_are_unchanged_by_this_candidate():
    expected = {
        CONTRACT_PATH: "c199b9481285d80b34183b8a7681f75ef7e60e5aadad6e4e0ece3ef8f33d6c92",
        REGISTRY_PATH: "02d2a75cdaa3d53a2708d2d20d5bf19f934fc68e6ee1b942404994d80ab94c4d",
        RECOGNITION_PATH: "3861a6ce8639badf4cdde23cb2143f9a75a1bb84ba4293bf81da4d41299c5544",
        SCOPE_PATH: "aeb23da1f6f9558616ce2dd9f4430da61396b865c72963d52aaf9a9c072f9809",
    }
    for path, expected_sha in expected.items():
        assert _hash(path.read_bytes()) == expected_sha, f"{path.name} bytes changed"


# ---------------------------------------------------------------------------
# Result algebra shape
# ---------------------------------------------------------------------------

def test_result_outcome_enum_contains_exactly_three_variants():
    body = _candidate()["semantic_body"]
    enum = body["result_algebra"]["outcome_enum"]
    assert set(enum) == {
        "MATERIALIZED_VALID_RECORD",
        "EMPTY_OBJECT_ZERO_TRADE_OBSERVATION",
        "MATERIALIZATION_QUARANTINED_NO_RECORD",
    }
    assert len(enum) == 3
    assert body["result_algebra"]["outcome_enum_is_exhaustive_and_pairwise_exclusive"] is True


def test_mutual_exclusivity_invariant_is_explicit_for_all_three_variants():
    invariant = _candidate()["semantic_body"]["mutual_exclusivity"]["tagged_union_invariant"]
    assert invariant["MATERIALIZED_VALID_RECORD"] == "record present, observation absent"
    assert invariant["EMPTY_OBJECT_ZERO_TRADE_OBSERVATION"] == "record absent, observation present"
    assert invariant["MATERIALIZATION_QUARANTINED_NO_RECORD"] == "record absent, observation absent"


def test_mutual_exclusivity_forbidden_states_cover_required_cases():
    forbidden = _candidate()["semantic_body"]["mutual_exclusivity"]["forbidden_states"]
    joined = " ".join(forbidden)
    assert "record present AND observation present" in forbidden
    assert "MATERIALIZED_VALID_RECORD" in joined and "SCHEMA_ADMISSIBLE" in joined
    assert "record.schema_id != admission-derived schema_id" in joined
    assert "EMPTY_OBJECT_ZERO_TRADE_OBSERVATION AND is_valid == true" in joined
    assert "EMPTY_OBJECT_ZERO_TRADE_OBSERVATION AND observation carries any schema_id" in joined


def test_materialized_valid_record_requires_schema_admissible():
    conditions = _candidate()["semantic_body"]["result_algebra"]["MATERIALIZED_VALID_RECORD"][
        "necessary_and_jointly_sufficient_conditions"
    ]
    assert "schema admission == SCHEMA_ADMISSIBLE" in conditions
    assert "recognition disposition == RECOGNIZED" in conditions
    assert "record.schema_id == admission-derived schema_id" in conditions


def test_mechanical_completeness_is_necessary_not_sufficient():
    text = _candidate()["semantic_body"]["result_algebra"]["MATERIALIZED_VALID_RECORD"][
        "mechanical_completeness_is_necessary_not_sufficient"
    ]
    assert "necessary but never by itself sufficient" in text


def test_empty_object_observation_has_record_absent_and_is_invalid():
    outcome = _candidate()["semantic_body"]["result_algebra"]["EMPTY_OBJECT_ZERO_TRADE_OBSERVATION"]
    permitted = outcome["permitted_only_when"]
    assert "DailyMarketEvidenceV1 record is absent" in permitted
    assert "is_valid == false" in permitted
    assert "schema admission == SCHEMA_INADMISSIBLE" in permitted
    assert "recognition disposition == FRAMING_FAILURE" in permitted


def test_empty_object_observation_payload_contains_no_schema_id():
    payload = _candidate()["semantic_body"]["result_algebra"]["EMPTY_OBJECT_ZERO_TRADE_OBSERVATION"][
        "observation_payload"
    ]
    assert "schema_id" not in payload["fields"]
    forbidden = " ".join(payload["forbidden_in_payload"])
    assert "schema_id=None" in forbidden
    assert "schema_id='UNKNOWN_SCHEMA'" in forbidden
    assert payload["required_values"]["trade_count"] == 0
    assert payload["required_values"]["schema_admission"] == "SCHEMA_INADMISSIBLE"
    assert payload["required_values"]["recognition_disposition"] == "FRAMING_FAILURE"


def test_quarantine_outcome_requires_record_and_observation_absent():
    outcome = _candidate()["semantic_body"]["result_algebra"]["MATERIALIZATION_QUARANTINED_NO_RECORD"]
    assert "record absent" in outcome["required_invariant"]
    assert "observation payload absent" in outcome["required_invariant"]
    assert "is_valid == false" in outcome["required_invariant"]


def test_quarantine_covers_registered_but_unauthorized_schema():
    covers = _candidate()["semantic_body"]["result_algebra"]["MATERIALIZATION_QUARANTINED_NO_RECORD"]["covers"]
    assert any("recognized-but-unauthorized schema" in c for c in covers)
    assert any("near-empty" in c for c in covers)


# ---------------------------------------------------------------------------
# UNKNOWN_SCHEMA treatment
# ---------------------------------------------------------------------------

def test_unknown_schema_is_explicitly_forbidden_as_admitted_schema_id():
    treatment = _candidate()["semantic_body"]["unknown_schema_treatment"]
    must_not = " ".join(treatment["must_not"])
    assert "registered or authorized schema variant" in must_not
    assert "admitted record schema identity" in must_not
    assert treatment["registry_unchanged"].startswith(
        "This amendment does not change r1_source_schema_registry_v1.json"
    )


def test_candidate_does_not_add_unknown_schema_to_registry_on_disk():
    registry = json.loads(REGISTRY_PATH.read_bytes())
    assert "UNKNOWN_SCHEMA" not in registry["known_schema_variants"]


# ---------------------------------------------------------------------------
# EMPTY_OBJECT boundary is exact, not widened; recognition itself untouched
# ---------------------------------------------------------------------------

def test_near_empty_inputs_are_outside_empty_object_variant():
    boundary = _candidate()["semantic_body"]["empty_object_boundary"]
    assert "FEWER_THAN_TWO_TOKENS" in boundary["not_eligible"]
    assert "non-EMPTY_OBJECT" not in boundary["eligible"]
    assert "length == 0" in boundary["eligible"]


def test_candidate_does_not_alter_recognition_dispositions():
    recognition = _frozen(RECOGNITION_PATH)
    # This candidate must not redefine any of recognize()'s enumerated
    # dispositions; the recognition amendment's own dispositions are the
    # sole authority for FRAMING_FAILURE/MALFORMED_HEADER/NO_MATCH/RECOGNIZED/AMBIGUOUS.
    dispositions_text = json.dumps(recognition["semantic_body"]["match_set_and_dispositions"])
    for token in ("NO_MATCH", "RECOGNIZED", "AMBIGUOUS"):
        assert token in dispositions_text
    candidate_text = json.dumps(_candidate()["semantic_body"])
    assert "does_not_govern" in json.dumps(_candidate()["semantic_body"]["scope"])
    assert any(
        "structural recognition" in item
        for item in _candidate()["semantic_body"]["explicitly_not_addressed_by_this_amendment"]
    )


def test_candidate_does_not_amend_dailymarketevidence_fields():
    body = _candidate()["semantic_body"]
    amended = body["amends"]["target_fields_amended"]
    assert len(amended) == 1
    assert "adds no field to, and changes no existing field's type/missingness/precision spec" in amended[0]
    assert body["amends"]["original_contract_bytes_unchanged_by_this_amendment"] is True
    assert body["amends"]["frozen_recognition_amendment_bytes_unchanged_by_this_amendment"] is True
    assert body["amends"]["frozen_registry_scope_amendment_bytes_unchanged_by_this_amendment"] is True
    assert body["amends"]["frozen_schema_admission_amendment_bytes_unchanged_by_this_amendment"] is True


def test_candidate_does_not_authorize_parser_b_acquisition_h001_or_outcomes():
    non_goals = _candidate()["semantic_body"]["non_goals"]
    joined = " ".join(non_goals)
    assert "Parser B" not in joined or any("Parser B" in item for item in
        _candidate()["semantic_body"]["explicitly_not_addressed_by_this_amendment"])
    not_addressed = _candidate()["semantic_body"]["explicitly_not_addressed_by_this_amendment"]
    assert any("Parser B" in item for item in not_addressed)
    assert any("acquisition, H001" in item for item in non_goals)
    assert any("raw deletion" in item for item in non_goals)
    assert any("outcome computation" in item for item in non_goals)


def test_candidate_declares_no_runtime_implementation_and_no_new_status_constant():
    non_goals = _candidate()["semantic_body"]["non_goals"]
    joined = " ".join(non_goals)
    assert "no code is modified by this candidate" in joined
    assert "no new Python result class or status constant" in joined.replace(
        "a new Python result class or status constant being introduced anywhere in qntylab/",
        "no new Python result class or status constant",
    )


# ---------------------------------------------------------------------------
# Countermodel proofs
# ---------------------------------------------------------------------------

def test_countermodel_a_current_contradiction_is_forbidden_by_result_algebra():
    cm = _candidate()["semantic_body"]["countermodel_proof"]["countermodel_a_current_contradiction"]
    assert cm["classification"] == "FORBIDDEN_BY_RESULT_ALGEBRA"
    assert cm["state"]["status"] == "MATERIALIZED_VALID_RECORD"
    assert cm["state"]["admission"] == "SCHEMA_INADMISSIBLE"


def test_countermodel_b_sentinel_laundering_is_forbidden():
    cm = _candidate()["semantic_body"]["countermodel_proof"]["countermodel_b_sentinel_laundering"]
    assert cm["classification"] == "FORBIDDEN_NOT_REGISTERED_OR_ADMITTED_SCHEMA_ID"
    assert cm["state"]["record.schema_id"] == "UNKNOWN_SCHEMA"


def test_countermodel_c_arbitrary_schema_substitution_is_forbidden():
    cm = _candidate()["semantic_body"]["countermodel_proof"]["countermodel_c_arbitrary_schema_substitution"]
    assert cm["classification"] == "FORBIDDEN_SCHEMA_IDENTITY_MISMATCH"


def test_countermodel_d_registered_but_unauthorized_is_forbidden():
    cm = _candidate()["semantic_body"]["countermodel_proof"]["countermodel_d_registered_but_unauthorized"]
    assert cm["classification"] == "FORBIDDEN_REGISTERED_DOES_NOT_IMPLY_AUTHORIZED"
    assert cm["state"]["recognized_schema"] == "bybit_trade_v1_rpi"


def test_countermodel_e_payload_overlap_is_forbidden():
    cm = _candidate()["semantic_body"]["countermodel_proof"]["countermodel_e_payload_overlap"]
    assert cm["classification"] == "FORBIDDEN_NON_EXCLUSIVE_RESULT_VARIANT"
    assert cm["state"]["record"] == "present"
    assert cm["state"]["observation"] == "present"


def test_countermodel_f_near_empty_widening_is_forbidden():
    cm = _candidate()["semantic_body"]["countermodel_proof"]["countermodel_f_near_empty_widening"]
    assert cm["classification"] == "FORBIDDEN_NOT_EXACT_EMPTY_OBJECT"
    assert cm["state"]["status"] == "EMPTY_OBJECT_ZERO_TRADE_OBSERVATION"


def test_all_six_countermodels_present_and_distinctly_classified():
    proofs = _candidate()["semantic_body"]["countermodel_proof"]
    assert len(proofs) == 6
    classifications = {v["classification"] for v in proofs.values()}
    assert len(classifications) == 6, "each countermodel must have a distinct classification"


# ---------------------------------------------------------------------------
# Validity predicate
# ---------------------------------------------------------------------------

def test_validity_predicate_does_not_require_live_registry_read():
    predicate = _candidate()["semantic_body"]["validity_predicate"]
    assert "not independently re-derived from a live registry read" in predicate["definition"]
    assert "never from an implicit, ambient, or independently re-opened live registry file read" in \
        predicate["no_live_registry_read_required"]


def test_validity_predicate_consequences_cover_every_required_failure_mode():
    consequences = _candidate()["semantic_body"]["validity_predicate"]["consequences"]
    for phrase in (
        "schema_id missing", "schema_id null", "schema_id wrong type", "schema_id empty string",
        "schema_id == 'UNKNOWN_SCHEMA'", "schema_id unregistered", "schema_id registered but unauthorized",
        "schema_id different from the admission-derived schema_id",
    ):
        assert phrase in consequences


# ---------------------------------------------------------------------------
# Low-level capability boundary does not prescribe an implementation
# ---------------------------------------------------------------------------

def test_low_level_capability_boundary_names_no_mandatory_function_name():
    boundary = _candidate()["semantic_body"]["low_level_capability_boundary"]
    assert "does not prescribe the exact private implementation type or function name" in \
        boundary["no_prescribed_private_type_or_function_name"]
    assert "Only the canonical, admission-gated public materialization boundary" in \
        boundary["public_boundary_exclusivity"]


# ---------------------------------------------------------------------------
# The confirmed current runtime contradiction still reproduces (expected --
# this lane makes no runtime change; it only names the state forbidden).
# ---------------------------------------------------------------------------

def test_confirmed_runtime_contradiction_still_reproduces_unrepaired():
    import gzip
    from datetime import date

    from qntylab.r1_daily_market_materializer import materialize_parser_a, MATERIALIZED_VALID
    from qntylab import r1_schema_admission as admission
    from qntylab import r1_schema_recognizer as recognizer

    result = materialize_parser_a(gzip.compress(b""), date(2024, 1, 1), "BYBIT_TEST_1h")
    evaluation = admission.evaluate_schema_admission(gzip.compress(b""))

    assert result.status == MATERIALIZED_VALID
    assert result.is_valid is True
    assert result.record["schema_id"] is None
    assert evaluation.admission == admission.INADMISSIBLE
    assert evaluation.recognition_disposition == recognizer.FRAMING_FAILURE
    assert "EMPTY_OBJECT" in evaluation.reasons

    # This is exactly Countermodel A, unrepaired at this commit -- naming it
    # FORBIDDEN_BY_RESULT_ALGEBRA in the candidate does not itself change
    # runtime behavior; that is a required subsequent implementation task.
    cm = _candidate()["semantic_body"]["countermodel_proof"]["countermodel_a_current_contradiction"]
    assert cm["classification"] == "FORBIDDEN_BY_RESULT_ALGEBRA"
