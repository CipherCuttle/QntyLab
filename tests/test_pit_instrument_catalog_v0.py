"""C1..C24 artificial fixture matrix for PIT Instrument Catalog V0."""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import itertools

import pytest

from qntylab.market_observation import InstrumentIdentity, MarketObservation
from qntylab import pit_instrument_catalog as pic


T0, T1, T2, T3 = ("2024-01-01T00:00:00Z", "2024-01-02T00:00:00Z",
                  "2024-01-03T00:00:00Z", "2024-01-04T00:00:00Z")

def h(value: str) -> str:
    return sha256(value.encode()).hexdigest()

SCOPE = pic.RosterScopeV0("fixture-venue", "perpetual", "perpetual", T0, T3, "fixture")
OTHER_SCOPE = pic.RosterScopeV0("fixture-venue", "spot", "spot", T0, T3, "fixture")
POS = pic.DiscoverySourceCapabilityV0(pic.POSITIVE_IDENTITY_DISCOVERY_ONLY, "fixture-positive", "v0", h("positive"))
SNAP = pic.DiscoverySourceCapabilityV0(pic.COMPLETE_SNAPSHOT_AT_INSTANT, "fixture-snapshot", "v0", h("snapshot"))
DELTA = pic.DiscoverySourceCapabilityV0(pic.SEQUENCED_DELTA, "fixture-delta", "v0", h("delta"))
OBS = pic.DiscoverySourceCapabilityV0(pic.OBSERVATION_ONLY, "fixture-observation", "v0", h("observation"))

def ident(symbol: str, instance: str) -> InstrumentIdentity:
    return InstrumentIdentity(symbol, "perpetual", "perpetual", f"fixture|{symbol}|perp|{instance}")

A, B, C, D = ident("AAAUSDT", "a"), ident("BBBUSDT", "b"), ident("CCCUSDT", "c"), ident("DDDUSDT", "d")
EP_A, EP_B = ident("ABCUSDT", "episode-a"), ident("ABCUSDT", "episode-b")

def discovery(identity=A, at=T1, key="discovery", payload="payload", capability=POS, scope=SCOPE, mode=pic.STRICT_PIT):
    return pic.InstrumentDiscoveryRecordV0(identity, pic.DISCOVERED_EXACT_IDENTITY, capability, at, key, h(payload), scope, mode)

def snapshot(at=T1, identities=(A, B, C), scope=SCOPE, key="snapshot", payload="snapshot"):
    return pic.SourceRosterEvidenceV0(SNAP, key, h(payload), at, scope, at, pic.SNAPSHOT, tuple(identities))

def delta(seq, at, action, identity, key=None, payload=None, scope=SCOPE):
    return pic.SourceRosterEvidenceV0(DELTA, key or f"delta-{seq}", h(payload or f"delta-{seq}"), at, scope, at, pic.DELTA,
                                      sequence=seq, delta_action=action, delta_identity=identity)


def test_c1_c2_c3_positive_exact_and_relist_ambiguity():
    catalog = pic.build_catalog_snapshot((discovery(A), discovery(EP_A), discovery(EP_B)), as_of=T2, scope=SCOPE)
    assert catalog.identities == (A, EP_A, EP_B)
    unresolved = pic.InstrumentDiscoveryRecordV0(None, pic.IDENTITY_UNRESOLVED, POS, T1, "ambiguous", h("ambiguous"), SCOPE,
                                                 unresolved_identity_key="ABCUSDT")
    assert pic.build_catalog_snapshot((unresolved,), as_of=T2, scope=SCOPE).identities == ()


def test_c4_c5_future_is_invisible_to_earlier_catalog():
    before = pic.build_catalog_snapshot((discovery(A),), as_of=T1, scope=SCOPE)
    after_input = pic.build_catalog_snapshot((discovery(A), discovery(B, at=T3)), as_of=T1, scope=SCOPE)
    assert before.catalog_digest == after_input.catalog_digest and before.identities == after_input.identities


def test_c6_c7_c8_c24_canonical_order_dedup_and_distinct_provenance():
    first, second = discovery(A, key="one"), discovery(A, key="two", payload="different")
    one = pic.build_catalog_snapshot((first, second, first), as_of=T2, scope=SCOPE)
    for order in itertools.permutations((first, second, first)):
        assert pic.build_catalog_snapshot(order, as_of=T2, scope=SCOPE).catalog_digest == one.catalog_digest
    assert len(one.discovery_basis[0][1]) == 2


def test_c9_c10_c11_positive_only_and_scope_bound_snapshot():
    assert pic.assess_roster_completeness((snapshot(),), scope=SCOPE, as_of=T2, target_time=T1).status == pic.ESTABLISHED_COMPLETE
    assert pic.assess_roster_completeness((), scope=SCOPE, as_of=T2, target_time=T1).status == pic.UNRESOLVED
    assert pic.assess_roster_completeness((snapshot(scope=OTHER_SCOPE),), scope=SCOPE, as_of=T2, target_time=T1).status == pic.UNRESOLVED


def test_c12_c13_c14_c15_delta_proof_and_fail_closed_gaps_conflicts_anchor():
    chain = (snapshot(at=T1), delta(100, T2, pic.ADD, D), delta(101, T3, pic.MODIFY, B))
    assert pic.assess_roster_completeness(chain, scope=SCOPE, as_of=T3, target_time=T3).status == pic.ESTABLISHED_COMPLETE
    gap = (snapshot(at=T1), delta(100, T2, pic.ADD, D), delta(102, T3, pic.REMOVE, C))
    assert pic.assess_roster_completeness(gap, scope=SCOPE, as_of=T3, target_time=T3).reason == "DELTA_SEQUENCE_GAP"
    conflict = (snapshot(at=T1), delta(100, T2, pic.ADD, D), delta(100, T2, pic.REMOVE, C, key="conflict", payload="conflict"))
    assert pic.assess_roster_completeness(conflict, scope=SCOPE, as_of=T2, target_time=T2).reason == "CONFLICTING_DELTA_SEQUENCE"
    assert pic.assess_roster_completeness((delta(100, T2, pic.ADD, D),), scope=SCOPE, as_of=T2, target_time=T2).reason == "MISSING_COMPLETE_ANCHOR"


def test_c16_c17_append_only_catalog_is_not_source_roster_state():
    # REMOVE can be meaningful to the source state/completeness proof but does not remove a discovered identity.
    catalog = pic.build_catalog_snapshot((discovery(C), discovery(D)), as_of=T3, scope=SCOPE)
    proof = pic.assess_roster_completeness((snapshot(at=T1), delta(1, T2, pic.REMOVE, C)), scope=SCOPE, as_of=T2, target_time=T2)
    assert C in catalog.identities and proof.status == pic.ESTABLISHED_COMPLETE


def test_c18_c19_observation_and_absence_cannot_escalate():
    with pytest.raises(pic.InvalidCatalogContract, match="OBSERVATION_ONLY"):
        discovery(capability=OBS)
    assert pic.build_catalog_snapshot((), as_of=T2, scope=SCOPE).identities == ()
    assert pic.assess_roster_completeness((), scope=SCOPE, as_of=T2, target_time=T1).status == pic.UNRESOLVED


def test_c20_c21_correction_preserved_and_retrospective_refused():
    old, revised = discovery(A, at=T1, payload="old"), discovery(A, at=T3, payload="revised")
    assert pic.build_catalog_snapshot((old, revised), as_of=T1, scope=SCOPE).catalog_digest == pic.build_catalog_snapshot((old,), as_of=T1, scope=SCOPE).catalog_digest
    assert len(pic.build_catalog_snapshot((old, revised), as_of=T3, scope=SCOPE).discovery_basis[0][1]) == 2
    retro = discovery(A, mode=pic.RETROSPECTIVE_AUDIT)
    with pytest.raises(pic.InvalidCatalogContract, match="STRICT_PIT"):
        pic.build_catalog_snapshot((retro,), as_of=T2, scope=SCOPE)


def test_c22_exact_type_widening_and_c23_all_provenance_fields_are_load_bearing():
    @dataclass(frozen=True)
    class WiderIdentity(InstrumentIdentity):
        extra: str = "x"
    with pytest.raises(pic.InvalidCatalogContract):
        discovery(WiderIdentity("AAAUSDT", "perpetual", "perpetual", "x"))
    base = discovery()
    variants = [
        discovery(key="other"), discovery(payload="other"),
        pic.InstrumentDiscoveryRecordV0(A, pic.DISCOVERED_EXACT_IDENTITY, pic.DiscoverySourceCapabilityV0(pic.POSITIVE_IDENTITY_DISCOVERY_ONLY, "other-contract", "v0", h("positive")), T1, "discovery", h("payload"), SCOPE),
        pic.InstrumentDiscoveryRecordV0(A, pic.DISCOVERED_EXACT_IDENTITY, pic.DiscoverySourceCapabilityV0(pic.POSITIVE_IDENTITY_DISCOVERY_ONLY, "fixture-positive", "v1", h("positive")), T1, "discovery", h("payload"), SCOPE),
        pic.InstrumentDiscoveryRecordV0(A, pic.DISCOVERED_EXACT_IDENTITY, pic.DiscoverySourceCapabilityV0(pic.POSITIVE_IDENTITY_DISCOVERY_ONLY, "fixture-positive", "v0", h("other-contract")), T1, "discovery", h("payload"), SCOPE),
        discovery(at=T2), discovery(scope=OTHER_SCOPE),
    ]
    assert all(pic.discovery_record_digest(base) != pic.discovery_record_digest(x) for x in variants)


def test_catalog_snapshot_rejects_forged_digest_and_market_observation_has_no_input_channel():
    actual = pic.build_catalog_snapshot((discovery(),), as_of=T2, scope=SCOPE)
    forged = pic.InstrumentCatalogSnapshotV0(actual.as_of, actual.scope, actual.mode, actual.identities, actual.discovery_basis, "0" * 64)
    with pytest.raises(pic.InvalidCatalogContract, match="digest mismatch"):
        pic.catalog_payload(forged)
    assert "MarketObservation" not in pic.__dict__
