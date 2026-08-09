"""Artificial fixture: evidence non-escalation (Evidence Claim Split V0).

Every fact here is synthetic. No network, no Binance acquisition, no archive
read, no lifecycle mutation. The tests prove NON-ESCALATION -- that evidence
for one proposition, one instrument instance, or one causal time cannot
silently establish a stronger or different claim -- not happy-path
serialisation.

Falsifier map:
    F1 suspension gap between observations       test_f1_*
    F2 delist -> relist instance separation      test_f2_*
    F3 launch boundary before first observation  test_f3_*
    F4 missing evidence stays UNKNOWN            test_f4_*
    F5 wrong contract variant (spot vs perp)     test_f5_*
    F6 generic asset evidence                    test_f6_*
    F7 future-known evidence / anti-lookahead    test_f7_*
    F8 no evidence at all                        test_f8_*
"""
import pytest

from qntylab.evidence_claim_split import (
    BOUNDARY_KINDS,
    DELIST,
    EPISTEMIC_STATUSES,
    ESTABLISHED,
    LAUNCH,
    UNKNOWN,
    Assessment,
    BoundaryProposition,
    EvidenceRecord,
    IntervalEligibilityProposition,
    PointObservationProposition,
    assess,
    fixture_digest,
    is_established,
    proposition_payload,
)
from qntylab.market_observation import InstrumentIdentity


# --- Artificial identities ---------------------------------------------------

# The instrument instance under study.
PERP_A = InstrumentIdentity(
    symbol="BTCUSDT", market="usd-m", contract_type="perpetual",
    instrument_instance_id="binance|BTCUSDT|perpetual|usd-m|2024-01-01T00:00:00Z",
)
# Same ticker, same venue, relisted later: a DIFFERENT instrument instance.
PERP_B = InstrumentIdentity(
    symbol="BTCUSDT", market="usd-m", contract_type="perpetual",
    instrument_instance_id="binance|BTCUSDT|perpetual|usd-m|2025-03-01T00:00:00Z",
)
# Same ticker, wrong contract variant.
SPOT_A = InstrumentIdentity(
    symbol="BTCUSDT", market="spot", contract_type="spot",
    instrument_instance_id="binance|BTCUSDT|spot|spot|2024-01-01T00:00:00Z",
)
# Generic asset-level identity: not any tradable instrument instance.
GENERIC_BTC = InstrumentIdentity(
    symbol="BTC", market="asset", contract_type="asset",
    instrument_instance_id="asset|BTC",
)

# --- Artificial timeline -----------------------------------------------------
#
#   launch boundary   effective 2024-06-01T08:00:00Z (known 08:05)
#   observation       effective 2024-06-01T11:00:00Z (known 11:05)
#   [ suspension gap -- no evidence at all for 12:00 ]
#   observation       effective 2024-06-01T13:00:00Z (known 13:05)
#   delist boundary   effective 2025-01-15T00:00:00Z (known 2025-01-15T00:05)

LAUNCH_A = BoundaryProposition(identity=PERP_A, kind=LAUNCH,
                               effective_time="2024-06-01T08:00:00Z")
DELIST_A = BoundaryProposition(identity=PERP_A, kind=DELIST,
                               effective_time="2025-01-15T00:00:00Z")
OBS_A_1100 = PointObservationProposition(identity=PERP_A,
                                         effective_time="2024-06-01T11:00:00Z")
OBS_A_1300 = PointObservationProposition(identity=PERP_A,
                                         effective_time="2024-06-01T13:00:00Z")
OBS_A_1200 = PointObservationProposition(identity=PERP_A,
                                         effective_time="2024-06-01T12:00:00Z")
INTERVAL_A_11_13 = IntervalEligibilityProposition(
    identity=PERP_A,
    effective_start="2024-06-01T11:00:00Z",
    effective_end="2024-06-01T13:00:00Z",
)

BASE_EVIDENCE = (
    EvidenceRecord(proposition=LAUNCH_A, available_time="2024-06-01T08:05:00Z",
                   source_key="artificial-boundary-launch-a"),
    EvidenceRecord(proposition=OBS_A_1100, available_time="2024-06-01T11:05:00Z",
                   source_key="artificial-observation-a-1100"),
    EvidenceRecord(proposition=OBS_A_1300, available_time="2024-06-01T13:05:00Z",
                   source_key="artificial-observation-a-1300"),
    EvidenceRecord(proposition=DELIST_A, available_time="2025-01-15T00:05:00Z",
                   source_key="artificial-boundary-delist-a"),
)

NOW = "2026-01-01T00:00:00Z"


def _status(proposition, evidence=BASE_EVIDENCE, as_of=NOW):
    return assess(evidence, proposition, as_of=as_of).status


# --- Vocabulary invariants ---------------------------------------------------


def test_epistemic_status_has_no_negative_member():
    """Absence of evidence cannot become negative evidence because no negative
    status exists to render it into."""
    assert EPISTEMIC_STATUSES == {ESTABLISHED, UNKNOWN}


def test_unknown_is_not_a_proposition_and_not_eligible():
    """UNKNOWN lives on the epistemic axis only; it is neither a proposition
    domain member nor a usable eligibility answer."""
    assert UNKNOWN not in BOUNDARY_KINDS
    unresolved = assess((), OBS_A_1200, as_of=NOW)
    assert unresolved.status == UNKNOWN
    assert not is_established(unresolved)
    # It is also not an ineligibility claim: nothing in the assessment says so.
    assert unresolved.status != ESTABLISHED
    assert unresolved.supporting_source_keys == ()


# --- F1: suspension gap between two observations -----------------------------


def test_f1_gap_between_observations_is_not_manufactured():
    """Observations at 11:00 and 13:00 must not manufacture a 12:00 observation."""
    assert _status(OBS_A_1100) == ESTABLISHED
    assert _status(OBS_A_1300) == ESTABLISHED
    assert _status(OBS_A_1200) == UNKNOWN


def test_f1_bracketing_observations_do_not_establish_the_interval():
    """The central success example: both endpoints observed, interval still
    unresolved. No bridging."""
    assert _status(OBS_A_1100) == ESTABLISHED
    assert _status(OBS_A_1300) == ESTABLISHED
    assert _status(INTERVAL_A_11_13) == UNKNOWN


def test_f1_point_observation_evidence_never_supports_an_interval_query():
    """Escalation must fail structurally, not just numerically: an interval
    assessment draws zero support from point evidence."""
    interval = assess(BASE_EVIDENCE, INTERVAL_A_11_13, as_of=NOW)
    assert interval.supporting_source_keys == ()


def test_f1_degenerate_interval_over_an_observed_instant_is_rejected():
    """A caller cannot smuggle a point observation in as a zero-width interval."""
    with pytest.raises(ValueError):
        IntervalEligibilityProposition(
            identity=PERP_A,
            effective_start="2024-06-01T11:00:00Z",
            effective_end="2024-06-01T11:00:00Z",
        )


# --- F2: delist -> relist ----------------------------------------------------


def test_f2_relisted_instance_inherits_nothing():
    """Instance A's boundary and observation evidence must not authorise
    instance B, despite identical symbol/market/contract_type."""
    assert PERP_A.symbol == PERP_B.symbol
    assert PERP_A.contract_type == PERP_B.contract_type
    assert _status(BoundaryProposition(identity=PERP_B, kind=LAUNCH,
                                       effective_time="2024-06-01T08:00:00Z")) == UNKNOWN
    assert _status(PointObservationProposition(
        identity=PERP_B, effective_time="2024-06-01T11:00:00Z")) == UNKNOWN


def test_f2_delist_boundary_does_not_establish_relist_continuity():
    """A verified delist on A says nothing about B, in either direction."""
    assert _status(DELIST_A) == ESTABLISHED
    assert _status(IntervalEligibilityProposition(
        identity=PERP_B,
        effective_start="2024-06-01T11:00:00Z",
        effective_end="2024-06-01T13:00:00Z")) == UNKNOWN


# --- F3: launch boundary before first observation ----------------------------


def test_f3_launch_boundary_creates_no_observations():
    """An established launch boundary at 08:00 must not synthesise an
    observation at 08:00, later, or over any interval."""
    assert _status(LAUNCH_A) == ESTABLISHED
    assert _status(PointObservationProposition(
        identity=PERP_A, effective_time="2024-06-01T08:00:00Z")) == UNKNOWN
    assert _status(PointObservationProposition(
        identity=PERP_A, effective_time="2024-06-01T09:00:00Z")) == UNKNOWN


def test_f3_boundary_does_not_establish_interval_eligibility():
    """Launch + delist bracket the whole timeline yet establish no eligible
    interval inside it."""
    assert _status(LAUNCH_A) == ESTABLISHED
    assert _status(DELIST_A) == ESTABLISHED
    assert _status(IntervalEligibilityProposition(
        identity=PERP_A,
        effective_start="2024-06-01T08:00:00Z",
        effective_end="2025-01-15T00:00:00Z")) == UNKNOWN


def test_f3_boundary_kinds_do_not_cross_establish():
    """A LAUNCH at time T never establishes a DELIST at time T."""
    assert _status(BoundaryProposition(identity=PERP_A, kind=DELIST,
                                       effective_time="2024-06-01T08:00:00Z")) == UNKNOWN


# --- F4: missing observation / archive evidence ------------------------------


def test_f4_missing_evidence_is_unknown_not_negative():
    """Dropping the 13:00 observation must turn it UNKNOWN, never into a
    NOT_TRADABLE / false claim, and must not disturb its neighbours."""
    pruned = tuple(r for r in BASE_EVIDENCE if r.proposition != OBS_A_1300)
    missing = assess(pruned, OBS_A_1300, as_of=NOW)
    assert missing.status == UNKNOWN
    assert missing.status in EPISTEMIC_STATUSES
    assert not is_established(missing)
    assert _status(OBS_A_1100, evidence=pruned) == ESTABLISHED


def test_f4_missing_evidence_never_flips_a_sibling_claim():
    """Absence anywhere in the fixture must not escalate anything else."""
    for record in BASE_EVIDENCE:
        pruned = tuple(r for r in BASE_EVIDENCE if r is not record)
        assert _status(record.proposition, evidence=pruned) == UNKNOWN
        assert _status(INTERVAL_A_11_13, evidence=pruned) == UNKNOWN


# --- F5: wrong contract variant ----------------------------------------------


def test_f5_perpetual_evidence_does_not_establish_spot():
    assert _status(PointObservationProposition(
        identity=SPOT_A, effective_time="2024-06-01T11:00:00Z")) == UNKNOWN
    assert _status(BoundaryProposition(identity=SPOT_A, kind=LAUNCH,
                                       effective_time="2024-06-01T08:00:00Z")) == UNKNOWN


def test_f5_spot_evidence_does_not_establish_perpetual():
    spot_evidence = (
        EvidenceRecord(
            proposition=PointObservationProposition(
                identity=SPOT_A, effective_time="2024-06-01T12:00:00Z"),
            available_time="2024-06-01T12:05:00Z",
            source_key="artificial-observation-spot-1200"),
    )
    assert _status(PointObservationProposition(
        identity=SPOT_A, effective_time="2024-06-01T12:00:00Z"),
        evidence=spot_evidence) == ESTABLISHED
    assert _status(OBS_A_1200, evidence=spot_evidence) == UNKNOWN


# --- F6: generic asset evidence ----------------------------------------------


def test_f6_generic_asset_evidence_binds_no_instrument_instance():
    """Generic BTC evidence must not bind the exact BTCUSDT perpetual."""
    generic_evidence = (
        EvidenceRecord(
            proposition=PointObservationProposition(
                identity=GENERIC_BTC, effective_time="2024-06-01T12:00:00Z"),
            available_time="2024-06-01T12:05:00Z",
            source_key="artificial-observation-generic-btc"),
        EvidenceRecord(
            proposition=BoundaryProposition(identity=GENERIC_BTC, kind=LAUNCH,
                                            effective_time="2024-06-01T08:00:00Z"),
            available_time="2024-06-01T08:05:00Z",
            source_key="artificial-boundary-generic-btc"),
    )
    assert _status(OBS_A_1200, evidence=generic_evidence) == UNKNOWN
    assert _status(LAUNCH_A, evidence=generic_evidence) == UNKNOWN
    assert _status(INTERVAL_A_11_13, evidence=generic_evidence) == UNKNOWN


# --- F7: future-known evidence (anti-lookahead) ------------------------------


def test_f7_future_known_evidence_is_inadmissible_at_historical_as_of():
    """effective_time <= as_of but available_time > as_of must NOT be usable."""
    late_known = (
        EvidenceRecord(
            proposition=OBS_A_1200,
            # The fact holds at 12:00 -- before the query -- but only became
            # knowable a year later.
            available_time="2025-06-01T00:00:00Z",
            source_key="artificial-observation-a-1200-late-known"),
    )
    assert late_known[0].proposition.effective_time < "2024-06-01T12:30:00Z"
    assert _status(OBS_A_1200, evidence=late_known,
                   as_of="2024-06-01T12:30:00Z") == UNKNOWN
    # Admissible only once the cutoff reaches its availability time.
    assert _status(OBS_A_1200, evidence=late_known,
                   as_of="2025-06-01T00:00:00Z") == ESTABLISHED


def test_f7_as_of_boundary_is_inclusive_and_one_second_matters():
    record = EvidenceRecord(proposition=OBS_A_1200,
                            available_time="2024-06-01T12:05:00Z",
                            source_key="artificial-observation-a-1200")
    assert _status(OBS_A_1200, evidence=(record,), as_of="2024-06-01T12:04:59Z") == UNKNOWN
    assert _status(OBS_A_1200, evidence=(record,), as_of="2024-06-01T12:05:00Z") == ESTABLISHED


def test_f7_historical_replay_never_sees_later_boundary():
    """Replaying the base fixture at an early cutoff must not leak the 13:00
    observation or the 2025 delist."""
    early = "2024-06-01T11:30:00Z"
    assert _status(OBS_A_1100, as_of=early) == ESTABLISHED
    assert _status(OBS_A_1300, as_of=early) == UNKNOWN
    assert _status(DELIST_A, as_of=early) == UNKNOWN


# --- F8: no evidence ---------------------------------------------------------


def test_f8_empty_evidence_leaves_every_proposition_unresolved():
    for proposition in (LAUNCH_A, DELIST_A, OBS_A_1100, OBS_A_1300,
                        OBS_A_1200, INTERVAL_A_11_13):
        result = assess((), proposition, as_of=NOW)
        assert result.status == UNKNOWN
        assert not is_established(result)
        assert result.proposition == proposition


# --- Fail-closed input handling ----------------------------------------------


def test_malformed_query_raises_instead_of_reading_as_evidence():
    with pytest.raises(ValueError):
        assess(BASE_EVIDENCE, OBS_A_1100, as_of="2024-06-01")
    with pytest.raises(ValueError):
        assess(BASE_EVIDENCE, "OBS_A_1100", as_of=NOW)
    with pytest.raises(ValueError):
        assess(("not-a-record",), OBS_A_1100, as_of=NOW)


def test_malformed_evidence_cannot_be_constructed():
    with pytest.raises(ValueError):
        BoundaryProposition(identity=PERP_A, kind="RELIST",
                            effective_time="2024-06-01T08:00:00Z")
    with pytest.raises(ValueError):
        PointObservationProposition(identity=PERP_A,
                                    effective_time="2024-02-31T00:00:00Z")
    with pytest.raises(ValueError):
        PointObservationProposition(
            identity=InstrumentIdentity(symbol="BTCUSDT", market="usd-m",
                                        contract_type="perpetual",
                                        instrument_instance_id=" "),
            effective_time="2024-06-01T11:00:00Z")
    with pytest.raises(ValueError):
        EvidenceRecord(proposition=OBS_A_1100,
                       available_time="2024-06-01T11:05:00Z", source_key="")


# --- Serialisation must preserve the split -----------------------------------


def test_proposition_domains_never_collapse_under_equality_or_serialisation():
    """Same identity, same instant, different domain: never equal, never the
    same canonical payload."""
    boundary = BoundaryProposition(identity=PERP_A, kind=LAUNCH,
                                   effective_time="2024-06-01T11:00:00Z")
    observation = PointObservationProposition(identity=PERP_A,
                                              effective_time="2024-06-01T11:00:00Z")
    assert boundary != observation
    assert proposition_payload(boundary) != proposition_payload(observation)
    assert proposition_payload(boundary)["proposition_domain"] == "LIFECYCLE_BOUNDARY"
    assert proposition_payload(observation)["proposition_domain"] == "POINT_MARKET_OBSERVATION"
    assert proposition_payload(INTERVAL_A_11_13)["proposition_domain"] == "INTERVAL_ELIGIBILITY"


def test_fixture_digest_is_deterministic_order_insensitive_and_identity_sensitive():
    digest = fixture_digest(BASE_EVIDENCE)
    assert digest == fixture_digest(tuple(reversed(BASE_EVIDENCE)))
    assert len(digest) == 64
    relabelled = tuple(
        EvidenceRecord(proposition=PointObservationProposition(
            identity=PERP_B, effective_time=r.proposition.effective_time)
            if isinstance(r.proposition, PointObservationProposition) else r.proposition,
            available_time=r.available_time, source_key=r.source_key)
        for r in BASE_EVIDENCE
    )
    assert fixture_digest(relabelled) != digest


def test_subtype_widening_is_refused_at_every_entry_point():
    """Hostile-review H-1 regression.

    A proposition subclass carrying an extra distinguishing field must not be
    accepted, serialised as its base domain, or digested -- otherwise two
    different propositions collapse onto one fixture identity.
    """
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class WidenedObservation(PointObservationProposition):
        venue_hint: str = "elsewhere"

    widened = WidenedObservation(identity=PERP_A,
                                 effective_time="2024-06-01T11:00:00Z",
                                 venue_hint="somewhere-else")
    with pytest.raises(ValueError):
        assess(BASE_EVIDENCE, widened, as_of=NOW)
    with pytest.raises(ValueError):
        proposition_payload(widened)
    with pytest.raises(ValueError):
        EvidenceRecord(proposition=widened, available_time="2024-06-01T11:05:00Z",
                       source_key="artificial-widened")


def test_identity_subtype_widening_is_refused():
    """An identity subclass would be flattened by the canonical payload, so a
    distinguishing field could vanish from the digest. Refuse it."""
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class WidenedIdentity(InstrumentIdentity):
        sub_account: str = "shadow"

    widened = WidenedIdentity(symbol="BTCUSDT", market="usd-m",
                              contract_type="perpetual",
                              instrument_instance_id=PERP_A.instrument_instance_id,
                              sub_account="shadow")
    with pytest.raises(ValueError):
        PointObservationProposition(identity=widened,
                                    effective_time="2024-06-01T11:00:00Z")


def test_evidence_record_subtype_widening_is_refused_by_assess():
    from dataclasses import dataclass

    @dataclass(frozen=True)
    class WidenedRecord(EvidenceRecord):
        override: bool = True

    widened = WidenedRecord(proposition=OBS_A_1200,
                            available_time="2024-06-01T12:05:00Z",
                            source_key="artificial-widened-record")
    with pytest.raises(ValueError):
        assess((widened,), OBS_A_1200, as_of=NOW)


def test_future_effective_evidence_establishes_only_its_own_proposition():
    """Documented non-claim: an announced future boundary is knowable now, but
    it must not establish anything about the present or any interval."""
    announced = BoundaryProposition(identity=PERP_A, kind=DELIST,
                                    effective_time="2027-01-01T00:00:00Z")
    evidence = (EvidenceRecord(proposition=announced,
                               available_time="2026-01-01T00:00:00Z",
                               source_key="artificial-announced-delist"),)
    assert _status(announced, evidence=evidence) == ESTABLISHED
    # ...and nothing else moves.
    assert _status(DELIST_A, evidence=evidence) == UNKNOWN
    assert _status(OBS_A_1200, evidence=evidence) == UNKNOWN
    assert _status(INTERVAL_A_11_13, evidence=evidence) == UNKNOWN


def test_assessment_echoes_the_assessed_proposition_and_cutoff():
    """A status can never be read detached from what it is a status about."""
    result = assess(BASE_EVIDENCE, OBS_A_1100, as_of=NOW)
    assert isinstance(result, Assessment)
    assert result.proposition == OBS_A_1100
    assert result.as_of == NOW
    assert result.supporting_source_keys == ("artificial-observation-a-1100",)


# --- Isolation from production lifecycle semantics ---------------------------


def test_module_does_not_touch_lifecycle_state_machine():
    """V0 is built beside qntylab.lifecycle, not on top of it: it imports no
    lifecycle symbol, so no code path exists by which this fixture can read or
    alter production lifecycle semantics."""
    import ast

    import qntylab.evidence_claim_split as module

    tree = ast.parse(open(module.__file__, encoding="utf-8").read())
    imported_modules = set()
    imported_names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported_modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported_modules.add(node.module or "")
            imported_names.update(alias.name for alias in node.names)

    assert "qntylab.lifecycle" not in imported_modules
    assert imported_names & {"EvidenceEvent", "state_at", "eligible_at", "terminal_policy"} == set()
    # The only qntylab import is the shared exact-identity type.
    assert {m for m in imported_modules if m.startswith("qntylab")} == {"qntylab.market_observation"}
    assert imported_names & {"observed_at", "Capture", "MarketObservation"} == set()


def test_no_caller_controlled_authentication_switch_exists():
    """No parameter, field or name anywhere in the module lets a caller assert
    authority (e.g. ``authenticated=True``)."""
    import ast

    import qntylab.evidence_claim_split as module

    tree = ast.parse(open(module.__file__, encoding="utf-8").read())
    declared = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.arg):
            declared.add(node.arg)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            declared.add(node.target.id)
        elif isinstance(node, ast.Name):
            declared.add(node.id)

    forbidden = {"authenticated", "authentic", "authority", "verified", "trusted", "grade"}
    assert declared & forbidden == set()
    assert not any(name.lower() in forbidden for name in vars(module))
