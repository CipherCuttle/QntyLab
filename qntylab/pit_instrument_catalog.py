"""PIT Instrument Catalog + Roster Completeness Contract V0.

Artificial, in-memory semantic machinery only.  It answers two deliberately
separate questions: which *exact* identities were positively knowable at a
cutoff, and whether a declared source scope has a mechanically sufficient
roster-completeness proof.  It neither makes lifecycle/admission claims nor
consumes market observations as identity evidence.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Iterable

from qntylab.evidence_claim_split import _require_identity, _require_non_empty, _require_timestamp
from qntylab.market_observation import InstrumentIdentity


CATALOG_ID = "qntylab.pit_instrument_catalog"
CATALOG_VERSION = "v0"
STRICT_PIT = "STRICT_PIT"
RETROSPECTIVE_AUDIT = "RETROSPECTIVE_AUDIT"
MODES = frozenset({STRICT_PIT, RETROSPECTIVE_AUDIT})

COMPLETE_SNAPSHOT_AT_INSTANT = "COMPLETE_SNAPSHOT_AT_INSTANT"
SEQUENCED_DELTA = "SEQUENCED_DELTA"
POSITIVE_IDENTITY_DISCOVERY_ONLY = "POSITIVE_IDENTITY_DISCOVERY_ONLY"
OBSERVATION_ONLY = "OBSERVATION_ONLY"
SOURCE_CAPABILITIES = frozenset({COMPLETE_SNAPSHOT_AT_INSTANT, SEQUENCED_DELTA,
                                 POSITIVE_IDENTITY_DISCOVERY_ONLY, OBSERVATION_ONLY})
DISCOVERED_EXACT_IDENTITY = "DISCOVERED_EXACT_IDENTITY"
IDENTITY_UNRESOLVED = "IDENTITY_UNRESOLVED"
DISCOVERY_KINDS = frozenset({DISCOVERED_EXACT_IDENTITY, IDENTITY_UNRESOLVED})
ESTABLISHED_COMPLETE = "ESTABLISHED_COMPLETE"
UNRESOLVED = "UNRESOLVED"
COMPLETENESS_STATUSES = frozenset({ESTABLISHED_COMPLETE, UNRESOLVED})
SNAPSHOT = "SNAPSHOT"
DELTA = "DELTA"
ADD = "ADD"
MODIFY = "MODIFY"
REMOVE = "REMOVE"


class InvalidCatalogContract(ValueError):
    """Malformed input is never represented as an epistemic result."""


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(value) -> str:
    return sha256(_json(value).encode()).hexdigest()


def _hash(value: str, name: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise InvalidCatalogContract(f"{name}: expected lowercase SHA-256 hex")


def _identity(identity: InstrumentIdentity) -> dict:
    try:
        _require_identity(identity)
    except ValueError as exc:
        raise InvalidCatalogContract(str(exc)) from None
    return {"symbol": identity.symbol, "market": identity.market,
            "contract_type": identity.contract_type,
            "instrument_instance_id": identity.instrument_instance_id}


def _identity_key(identity: InstrumentIdentity) -> str:
    return _json(_identity(identity))


@dataclass(frozen=True)
class RosterScopeV0:
    venue: str
    market: str
    contract_type: str
    coverage_start: str
    coverage_end: str
    namespace: str = ""

    def __post_init__(self) -> None:
        try:
            for name in ("venue", "market", "contract_type"):
                _require_non_empty(getattr(self, name), name)
            _require_timestamp(self.coverage_start, "coverage_start")
            _require_timestamp(self.coverage_end, "coverage_end")
        except ValueError as exc:
            raise InvalidCatalogContract(str(exc)) from None
        if self.coverage_start > self.coverage_end:
            raise InvalidCatalogContract("scope coverage_start must not exceed coverage_end")
        if not isinstance(self.namespace, str) or self.namespace != self.namespace.strip():
            raise InvalidCatalogContract("namespace must be an unpadded string")


def scope_payload(scope: RosterScopeV0) -> dict:
    if type(scope) is not RosterScopeV0:
        raise InvalidCatalogContract("scope: expected exactly RosterScopeV0")
    return {"venue": scope.venue, "market": scope.market, "contract_type": scope.contract_type,
            "coverage_start": scope.coverage_start, "coverage_end": scope.coverage_end,
            "namespace": scope.namespace}


@dataclass(frozen=True)
class DiscoverySourceCapabilityV0:
    capability: str
    source_contract_id: str
    source_contract_version: str
    source_contract_digest: str

    def __post_init__(self) -> None:
        if self.capability not in SOURCE_CAPABILITIES:
            raise InvalidCatalogContract("unsupported source capability")
        try:
            _require_non_empty(self.source_contract_id, "source_contract_id")
            _require_non_empty(self.source_contract_version, "source_contract_version")
        except ValueError as exc:
            raise InvalidCatalogContract(str(exc)) from None
        _hash(self.source_contract_digest, "source_contract_digest")


def capability_payload(capability: DiscoverySourceCapabilityV0) -> dict:
    if type(capability) is not DiscoverySourceCapabilityV0:
        raise InvalidCatalogContract("source_capability: expected exactly DiscoverySourceCapabilityV0")
    return {"capability": capability.capability, "source_contract_id": capability.source_contract_id,
            "source_contract_version": capability.source_contract_version,
            "source_contract_digest": capability.source_contract_digest}


@dataclass(frozen=True)
class InstrumentDiscoveryRecordV0:
    exact_identity: InstrumentIdentity | None
    discovery_kind: str
    source_capability: DiscoverySourceCapabilityV0
    available_time: str
    source_key: str
    source_payload_digest: str
    scope: RosterScopeV0
    mode: str = STRICT_PIT
    unresolved_identity_key: str = ""

    def __post_init__(self) -> None:
        if self.discovery_kind not in DISCOVERY_KINDS:
            raise InvalidCatalogContract("unsupported discovery_kind")
        if type(self.source_capability) is not DiscoverySourceCapabilityV0 or type(self.scope) is not RosterScopeV0:
            raise InvalidCatalogContract("discovery record contains widened boundary object")
        if self.mode not in MODES:
            raise InvalidCatalogContract("unsupported discovery mode")
        try:
            _require_timestamp(self.available_time, "available_time")
            _require_non_empty(self.source_key, "source_key")
        except ValueError as exc:
            raise InvalidCatalogContract(str(exc)) from None
        _hash(self.source_payload_digest, "source_payload_digest")
        if self.discovery_kind == DISCOVERED_EXACT_IDENTITY:
            if self.source_capability.capability == OBSERVATION_ONLY:
                raise InvalidCatalogContract("OBSERVATION_ONLY cannot establish identity discovery")
            if self.exact_identity is None or self.unresolved_identity_key:
                raise InvalidCatalogContract("exact discovery requires exactly one exact identity")
            _identity(self.exact_identity)
        else:
            if self.exact_identity is not None:
                raise InvalidCatalogContract("unresolved discovery must not manufacture an identity")
            try:
                _require_non_empty(self.unresolved_identity_key, "unresolved_identity_key")
            except ValueError as exc:
                raise InvalidCatalogContract(str(exc)) from None


def discovery_payload(record: InstrumentDiscoveryRecordV0) -> dict:
    if type(record) is not InstrumentDiscoveryRecordV0:
        raise InvalidCatalogContract("record: expected exactly InstrumentDiscoveryRecordV0")
    return {"exact_identity": None if record.exact_identity is None else _identity(record.exact_identity),
            "discovery_kind": record.discovery_kind, "source_capability": capability_payload(record.source_capability),
            "available_time": record.available_time, "source_key": record.source_key,
            "source_payload_digest": record.source_payload_digest, "scope": scope_payload(record.scope),
            "mode": record.mode, "unresolved_identity_key": record.unresolved_identity_key}


def discovery_record_digest(record: InstrumentDiscoveryRecordV0) -> str:
    return _digest(discovery_payload(record))


@dataclass(frozen=True)
class InstrumentCatalogSnapshotV0:
    as_of: str
    scope: RosterScopeV0
    mode: str
    identities: tuple[InstrumentIdentity, ...]
    discovery_basis: tuple[tuple[InstrumentIdentity, tuple[str, ...]], ...]
    catalog_digest: str


def build_catalog_snapshot(records: Iterable[InstrumentDiscoveryRecordV0], *, as_of: str,
                           scope: RosterScopeV0, mode: str = STRICT_PIT) -> InstrumentCatalogSnapshotV0:
    try:
        _require_timestamp(as_of, "as_of")
    except ValueError as exc:
        raise InvalidCatalogContract(str(exc)) from None
    scope_payload(scope)
    if mode != STRICT_PIT:
        raise InvalidCatalogContract("historical catalog accepts STRICT_PIT records only")
    grouped: dict[str, tuple[InstrumentIdentity, set[str]]] = {}
    for record in records:
        if type(record) is not InstrumentDiscoveryRecordV0:
            raise InvalidCatalogContract("records: expected exactly InstrumentDiscoveryRecordV0")
        # A strict historical artifact must not merely *ignore* retrospective
        # input: that makes an accidental mixed-mode call look successful.
        if record.mode != STRICT_PIT:
            raise InvalidCatalogContract("STRICT_PIT catalog cannot consume RETROSPECTIVE_AUDIT record")
        if record.available_time > as_of or record.scope != scope:
            continue
        if record.discovery_kind != DISCOVERED_EXACT_IDENTITY:
            continue
        assert record.exact_identity is not None
        key = _identity_key(record.exact_identity)
        identity, bases = grouped.setdefault(key, (record.exact_identity, set()))
        bases.add(discovery_record_digest(record))
    pairs = tuple((identity, tuple(sorted(bases))) for _, (identity, bases) in sorted(grouped.items()))
    identities = tuple(pair[0] for pair in pairs)
    payload = {"catalog_id": CATALOG_ID, "catalog_version": CATALOG_VERSION, "as_of": as_of,
               "scope": scope_payload(scope), "mode": mode, "identities": [_identity(x) for x in identities],
               "discovery_basis": [{"identity": _identity(i), "record_digests": list(b)} for i, b in pairs]}
    return InstrumentCatalogSnapshotV0(as_of, scope, mode, identities, pairs, _digest(payload))


def catalog_payload(snapshot: InstrumentCatalogSnapshotV0) -> dict:
    if type(snapshot) is not InstrumentCatalogSnapshotV0:
        raise InvalidCatalogContract("snapshot: expected exactly InstrumentCatalogSnapshotV0")
    # Validate exact boundary types and digest without accepting caller-forged snapshots.
    if snapshot.mode != STRICT_PIT or type(snapshot.scope) is not RosterScopeV0:
        raise InvalidCatalogContract("invalid catalog snapshot mode/scope")
    if type(snapshot.identities) is not tuple or type(snapshot.discovery_basis) is not tuple:
        raise InvalidCatalogContract("catalog collections must be tuples")
    identity_keys = tuple(_identity_key(x) for x in snapshot.identities)
    basis_keys: list[str] = []
    for pair in snapshot.discovery_basis:
        if type(pair) is not tuple or len(pair) != 2 or type(pair[1]) is not tuple:
            raise InvalidCatalogContract("catalog discovery_basis must contain identity/digest tuples")
        key = _identity_key(pair[0])
        if not pair[1] or any(not isinstance(x, str) or len(x) != 64 for x in pair[1]):
            raise InvalidCatalogContract("catalog discovery basis is malformed")
        if tuple(sorted(set(pair[1]))) != pair[1]:
            raise InvalidCatalogContract("catalog discovery basis is not canonical")
        basis_keys.append(key)
    if identity_keys != tuple(sorted(identity_keys)) or tuple(basis_keys) != identity_keys:
        raise InvalidCatalogContract("catalog identities/basis are not an exact canonical partition")
    payload = {"catalog_id": CATALOG_ID, "catalog_version": CATALOG_VERSION, "as_of": snapshot.as_of,
               "scope": scope_payload(snapshot.scope), "mode": snapshot.mode,
               "identities": [_identity(x) for x in snapshot.identities],
               "discovery_basis": [{"identity": _identity(i), "record_digests": list(b)} for i, b in snapshot.discovery_basis]}
    if _digest(payload) != snapshot.catalog_digest:
        raise InvalidCatalogContract("catalog digest mismatch")
    return payload


@dataclass(frozen=True)
class SourceRosterEvidenceV0:
    source_capability: DiscoverySourceCapabilityV0
    source_key: str
    source_payload_digest: str
    available_time: str
    scope: RosterScopeV0
    effective_time: str
    evidence_kind: str
    identities: tuple[InstrumentIdentity, ...] = ()
    sequence: int | None = None
    delta_action: str | None = None
    delta_identity: InstrumentIdentity | None = None
    mode: str = STRICT_PIT

    def __post_init__(self) -> None:
        if type(self.source_capability) is not DiscoverySourceCapabilityV0 or type(self.scope) is not RosterScopeV0:
            raise InvalidCatalogContract("source roster evidence contains widened boundary object")
        if self.mode not in MODES or self.mode != STRICT_PIT:
            raise InvalidCatalogContract("source roster evidence is STRICT_PIT only")
        try:
            _require_non_empty(self.source_key, "source_key")
            _require_timestamp(self.available_time, "available_time")
            _require_timestamp(self.effective_time, "effective_time")
        except ValueError as exc:
            raise InvalidCatalogContract(str(exc)) from None
        _hash(self.source_payload_digest, "source_payload_digest")
        if self.evidence_kind == SNAPSHOT:
            if self.source_capability.capability != COMPLETE_SNAPSHOT_AT_INSTANT or self.sequence is not None or self.delta_action is not None or self.delta_identity is not None:
                raise InvalidCatalogContract("snapshot requires COMPLETE_SNAPSHOT_AT_INSTANT only")
            if type(self.identities) is not tuple:
                raise InvalidCatalogContract("snapshot identities must be tuple")
            keys = [_identity_key(x) for x in self.identities]
            if len(keys) != len(set(keys)):
                raise InvalidCatalogContract("snapshot contains duplicate exact identity")
        elif self.evidence_kind == DELTA:
            if self.source_capability.capability != SEQUENCED_DELTA or type(self.sequence) is not int or self.sequence < 0:
                raise InvalidCatalogContract("delta requires non-negative integer sequence and SEQUENCED_DELTA")
            if self.delta_action not in {ADD, MODIFY, REMOVE} or self.delta_identity is None or self.identities:
                raise InvalidCatalogContract("delta requires action, exact identity, and no snapshot identities")
            _identity(self.delta_identity)
        else:
            raise InvalidCatalogContract("unsupported roster evidence kind")


@dataclass(frozen=True)
class RosterCompletenessAssessmentV0:
    status: str
    scope: RosterScopeV0
    as_of: str
    mode: str
    reason: str
    evidence_digests: tuple[str, ...]
    assessment_digest: str


def _roster_evidence_payload(row: SourceRosterEvidenceV0) -> dict:
    if type(row) is not SourceRosterEvidenceV0:
        raise InvalidCatalogContract("roster evidence: expected exactly SourceRosterEvidenceV0")
    return {"source_capability": capability_payload(row.source_capability), "source_key": row.source_key,
            "source_payload_digest": row.source_payload_digest, "available_time": row.available_time,
            "scope": scope_payload(row.scope), "effective_time": row.effective_time,
            "evidence_kind": row.evidence_kind, "identities": [_identity(x) for x in sorted(row.identities, key=_identity_key)],
            "sequence": row.sequence, "delta_action": row.delta_action,
            "delta_identity": None if row.delta_identity is None else _identity(row.delta_identity), "mode": row.mode}


def _assessment(status: str, scope: RosterScopeV0, as_of: str, reason: str, rows: Iterable[SourceRosterEvidenceV0]) -> RosterCompletenessAssessmentV0:
    digests = tuple(sorted({_digest(_roster_evidence_payload(x)) for x in rows}))
    payload = {"status": status, "scope": scope_payload(scope), "as_of": as_of, "mode": STRICT_PIT,
               "reason": reason, "evidence_digests": list(digests)}
    return RosterCompletenessAssessmentV0(status, scope, as_of, STRICT_PIT, reason, digests, _digest(payload))


def assess_roster_completeness(records: Iterable[SourceRosterEvidenceV0], *, scope: RosterScopeV0,
                               as_of: str, target_time: str) -> RosterCompletenessAssessmentV0:
    """Fail-closed proof: matching complete snapshot, optionally contiguous deltas."""
    scope_payload(scope)
    try:
        _require_timestamp(as_of, "as_of"); _require_timestamp(target_time, "target_time")
    except ValueError as exc:
        raise InvalidCatalogContract(str(exc)) from None
    eligible = []
    for row in records:
        if type(row) is not SourceRosterEvidenceV0:
            raise InvalidCatalogContract("records: expected exactly SourceRosterEvidenceV0")
        if row.available_time <= as_of and row.scope == scope:
            eligible.append(row)
    anchors = [x for x in eligible if x.evidence_kind == SNAPSHOT and x.effective_time <= target_time]
    if not anchors:
        return _assessment(UNRESOLVED, scope, as_of, "MISSING_COMPLETE_ANCHOR", eligible)
    # One exact latest anchor; conflicting same-time snapshots cannot be arbitrarily preferred.
    latest_time = max(x.effective_time for x in anchors)
    latest = [x for x in anchors if x.effective_time == latest_time]
    if len({_digest(_roster_evidence_payload(x)) for x in latest}) != 1:
        return _assessment(UNRESOLVED, scope, as_of, "CONFLICTING_COMPLETE_ANCHOR", eligible)
    anchor = latest[0]
    if anchor.effective_time == target_time:
        return _assessment(ESTABLISHED_COMPLETE, scope, as_of, "MATCHING_COMPLETE_SNAPSHOT", (anchor,))
    deltas = [x for x in eligible if x.evidence_kind == DELTA and anchor.effective_time < x.effective_time <= target_time]
    if not deltas:
        return _assessment(UNRESOLVED, scope, as_of, "MISSING_SEQUENCED_DELTAS", (anchor,))
    by_seq: dict[int, list[SourceRosterEvidenceV0]] = {}
    for delta in deltas:
        by_seq.setdefault(delta.sequence, []).append(delta)  # type: ignore[arg-type]
    if any(len({_digest(_roster_evidence_payload(x)) for x in rows}) != 1 for rows in by_seq.values()):
        return _assessment(UNRESOLVED, scope, as_of, "CONFLICTING_DELTA_SEQUENCE", [anchor, *deltas])
    sequences = sorted(by_seq)
    if sequences != list(range(sequences[0], sequences[-1] + 1)):
        return _assessment(UNRESOLVED, scope, as_of, "DELTA_SEQUENCE_GAP", [anchor, *deltas])
    if max(x.effective_time for x in deltas) != target_time:
        return _assessment(UNRESOLVED, scope, as_of, "DELTA_CHAIN_DOES_NOT_REACH_TARGET", [anchor, *deltas])
    return _assessment(ESTABLISHED_COMPLETE, scope, as_of, "COMPLETE_ANCHOR_PLUS_CONTIGUOUS_DELTAS", [anchor, *deltas])
