import copy

from qntylab.r1_input_bom import (CUTOFF, availability_observation, canonical_bytes, canonical_hash,
                                  determine_verdict, funding_plan, identity_assignment, input_requirements,
                                  lifecycle_acquisition_audit, parse_archive_listing, required_domain)


def instance(instance_id, *, symbol="TESTUSDT", start="2021-01-01T00:00:00Z",
             end_state="OPEN_AT_HISTORICAL_CUTOFF", lifecycle="OPEN_AT_CUTOFF_CORROBORATED",
             identity="SINGLE_CANDIDATE_NO_REUSE_EVIDENCE", start_state="FIRST_CAUSAL_TRADABILITY_EVIDENCE"):
    return {"instrument_instance_id": instance_id, "symbol": symbol, "lineage": "primary", "start_time": start,
            "start_state": start_state, "end_state": end_state, "identity_state": identity,
            "lifecycle_state": lifecycle, "ambiguity_reasons": []}


def document(*rows):
    return {"compiled_instrument_instance_count": len(rows), "instances": list(rows)}


def test_all_instances_accounted_and_future_reservoir_is_explicitly_excluded():
    domain = required_domain(document(instance("a"), instance("b", start="2026-07-01T00:00:00Z",
        end_state="OUTSIDE_HISTORICAL_CUTOFF", lifecycle="FUTURE_RESERVOIR_EXCLUDED")))
    assert domain["instances_total"] == 2
    assert domain["instances_structurally_relevant_to_r1"] == 1
    assert domain["excluded_instances"] == [{"instrument_instance_id": "b", "frozen_reason": "FUTURE_RESERVOIR_STARTS_AFTER_2026_06_30_CUTOFF"}]


def test_required_domain_does_not_depend_on_availability_or_current_membership():
    required = required_domain(document(instance("a")))
    observed = availability_observation(required, {"TESTUSDT": set()})
    assert observed["counts"]["absent"] == required["determinate_market_object_count"]
    assert canonical_hash(required) == canonical_hash(copy.deepcopy(required))
    assert "current" not in canonical_bytes(required).decode().lower()


def test_frozen_warmups_and_cutoff_are_not_coverage_dependent():
    requirements = input_requirements()
    assert requirements["required_market_input_start"] == "2021-07-03"
    assert requirements["required_funding_input_start"] == "2021-09-25"
    assert requirements["historical_cutoff_utc"] == CUTOFF
    assert requirements["future_reservoir_start_utc"] > CUTOFF


def test_ambiguous_start_and_terminal_are_explicit_not_extended_to_cutoff():
    required = required_domain(document(instance("a", start="2023-01-01T00:00:00Z", start_state="START_AMBIGUOUS",
        end_state="AMBIGUOUS_TERMINAL", lifecycle="TERMINATED_AMBIGUOUS")))
    row = required["records"][0]
    assert row["market"]["interval_state"] == "UNRESOLVED_CAUSAL_CESSATION"
    assert row["market"]["required_end_utc"] is None
    assert row["funding"]["segments"] == []


def test_reuse_lineages_are_never_merged_and_assignment_is_ambiguous():
    required = required_domain(document(instance("old", identity="IDENTITY_AMBIGUOUS", end_state="AMBIGUOUS_TERMINAL", lifecycle="TERMINATED_AMBIGUOUS"),
                                        instance("new", identity="IDENTITY_AMBIGUOUS")))
    assignments = identity_assignment(required)
    assert [row["instrument_instance_id"] for row in required["records"]] == ["new", "old"]
    assert assignments["ambiguous"] == 2
    assert {row["source_assignment"] for row in assignments["records"]} == {"SOURCE_ASSIGNMENT_AMBIGUOUS"}


def test_unknown_is_never_absent_or_zero_and_listing_parser_is_metadata_only():
    required = required_domain(document(instance("a")))
    unknown = availability_observation(required)
    assert unknown["counts"]["unknown"] == required["determinate_market_object_count"]
    assert unknown["counts"]["absent"] == 0
    assert parse_archive_listing('<a href="TESTUSDT2024-01-01.csv.gz">x</a>', "TESTUSDT") == {"2024-01-01"}


def test_funding_pagination_covers_every_determinate_interval_and_reports_unknowns():
    required = required_domain(document(instance("a"), instance("b", end_state="AMBIGUOUS_TERMINAL", lifecycle="TERMINATED_AMBIGUOUS")))
    plan = funding_plan(required)
    assert plan["funding_instances_required"] == 2
    assert plan["enumerable"] == 1 and plan["unknown"] == 1
    segments = required["records"][0]["funding"]["segments"]
    assert segments and segments[0]["start_utc"].endswith("T00:00:00Z") and segments[-1]["end_utc"] == CUTOFF
    assert "200-record truncation" in plan["request_rule"]["checks"]


def test_verdict_fails_closed_for_identity_before_other_supply_conditions():
    required = required_domain(document(instance("a", identity="IDENTITY_AMBIGUOUS")))
    availability = availability_observation(required)
    assert determine_verdict(required, availability, identity_assignment(required), funding_plan(required)) == "R1_FREE_IDENTITY_DOMAIN_INSUFFICIENT"


def test_ambiguous_terminal_does_not_invent_an_acquisition_envelope():
    required = required_domain(document(instance("a", end_state="AMBIGUOUS_TERMINAL", lifecycle="TERMINATED_AMBIGUOUS")))
    audit = lifecycle_acquisition_audit(required)
    assert audit["ambiguous_terminal_instances"] == 1
    assert audit["acquisition_envelope_rule"] == "NOT_SPECIFIED_BY_FROZEN_PROTOCOL"
