"""Protocol tests for
experiments/data/r1_daily_market_evidence_schema_admission_amendment_v1.json
(a PROTOCOL_AMENDMENT_CANDIDATE, not yet frozen -- see its own "status" field).

Closes H1_PROTOCOL_UNDERSPECIFICATION (unregistered schema does not
normatively entail invalid/inadmissible DailyMarketEvidenceV1) via
semantic_body.schema_admission_rule, and then repairs
BLOCK_REGISTRY_TIME_AMBIGUITY (an independent hostile review verdict on that
rule's first draft, which read known_schema_variants "at the time of
evaluation" -- a live, wall-clock-dependent read with no per-decision
registry-version binding) via semantic_body.registry_snapshot_binding.

These tests do not modify, and do not require modifying, Parser A, Parser B,
or the materialization boundary. They:
  1. verify the amendment artifact's self-consistent digests and its binding
     to the actual current bytes of the base contract and schema registry it
     amends (both left byte-for-byte unedited by this amendment);
  2. reimplement schema_admission_rule standalone (not by importing either
     parser's internals) as the minimal, registry-snapshot-bound predicate the
     amendment defines: every evaluation carries an explicit
     registry_snapshot_sha256 and is a pure function of (schema_id,
     known_schema_variants, registry_snapshot_sha256) only;
  3. empirically corroborate, using the CURRENT unmodified implementation,
     that Parser A already conforms and Parser B does not -- the exact
     countermodel the amendment closes at the protocol level; remediating
     Parser B remains an explicitly out-of-scope, required subsequent
     implementation task;
  4. prove raw retention and scientific admission are independent, and that a
     registered schema confers no automatic validity, under more than one
     registry snapshot;
  5. prove the real T1/T2 registry-time counterfactual: an evaluation
     recorded under registry snapshot R1 is immutable and is never silently
     replaced by a fresh evaluation under a later registry snapshot R2 for
     byte-identical raw input; R2 admission is obtainable only as an
     explicitly new, separately identified evaluation; and evaluation under a
     fixed (X, R, C) is deterministic across execution time and independent
     of any ambient/global registry state;
  6. prove the amendment leaves duplicate/container/lifecycle/PIT semantics,
     and the base contract/registry bytes themselves, untouched.
"""
import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Optional

from qntylab import r1_reference_parser as rp
from qntylab.r1_daily_market_materializer import (
    MATERIALIZATION_QUARANTINED,
    MATERIALIZED_VALID,
    ALL_CONTRACT_FIELDS,
    materialize_parser_a,
    materialize_parser_b,
    validate_daily_market_evidence_v1,
)
from qntylab.r1_retention_candidate import (
    ANOMALY_SCHEMA_MISMATCH,
    BASE_SCHEMA,
    daily_primitive,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
AMENDMENT_PATH = REPO_ROOT / "experiments/data/r1_daily_market_evidence_schema_admission_amendment_v1.json"
BASE_CONTRACT_PATH = REPO_ROOT / "experiments/data/r1_normalized_evidence_contract_v1.json"
SCHEMA_REGISTRY_PATH = REPO_ROOT / "experiments/data/r1_source_schema_registry_v1.json"
DUP_AMENDMENT_PATH = REPO_ROOT / "experiments/data/r1_normalized_evidence_duplicate_semantics_amendment_v1.json"

CUTOFF = "2026-06-30T23:59:59Z"


def _canonical_bytes(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True) + "\n").encode()


def _canonical_hash(value):
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _load_amendment():
    return json.loads(AMENDMENT_PATH.read_bytes())


def _load_known_schema_variants():
    registry = json.loads(SCHEMA_REGISTRY_PATH.read_bytes())
    return dict(registry["known_schema_variants"])


def _registry_snapshot_sha256():
    """R1: the registry snapshot identity is the sha256 of the actual, current
    registry artifact bytes -- the same sha256-artifact-pinning convention
    already used by bound_authority/base_registry_sha256 elsewhere in this
    document, applied to the admission evaluation itself."""
    return hashlib.sha256(SCHEMA_REGISTRY_PATH.read_bytes()).hexdigest()


# --- 1. amendment self-consistency and provenance binding -------------------

def test_amendment_is_candidate_not_frozen():
    amendment = _load_amendment()
    assert amendment["status"] == "CANDIDATE_NOT_YET_FROZEN"
    assert amendment["self_freeze_authorized"] is False
    assert amendment["artifact_kind"] == "PROTOCOL_AMENDMENT_CANDIDATE"


def test_amendment_addresses_the_audited_verdict():
    amendment = _load_amendment()
    assert amendment["audit_origin"]["verdict_addressed"] == "H1_PROTOCOL_UNDERSPECIFICATION"


def test_repair_history_records_the_registry_time_repair():
    amendment = _load_amendment()
    history = amendment["repair_history"]
    assert len(history) == 3
    assert history[0]["addressed_review_verdict"] == "BLOCK_REGISTRY_TIME_AMBIGUITY"
    assert history[1]["addressed_review_verdict"] == "BLOCK_UNBOUND_REGISTRY_HASH"
    assert history[2]["addressed_review_verdict"] == "BLOCK_REGISTRY_CONTENT_IDENTITY_DECOUPLED"
    assert history[0]["still_not_frozen"] is True
    assert history[1]["still_not_frozen"] is True
    assert history[2]["still_not_frozen"] is True


def test_amendment_semantic_content_digest_is_self_consistent():
    amendment = _load_amendment()
    recomputed = _canonical_hash(amendment["semantic_body"])
    assert recomputed == amendment["amendment_semantic_content_sha256"]


def test_amendment_effective_combined_binding_digest_is_self_consistent():
    amendment = _load_amendment()
    binding = amendment["effective_combined_contract_binding"]
    recomputed_semantic = _canonical_hash(amendment["semantic_body"])
    recomputed_binding = _canonical_hash({
        "amendment_semantic_content_sha256": recomputed_semantic,
        "base_contract_artifact": binding["base_contract_artifact"],
        "base_contract_sha256": binding["base_contract_sha256"],
        "base_registry_artifact": binding["base_registry_artifact"],
        "base_registry_sha256": binding["base_registry_sha256"],
    })
    assert recomputed_binding == amendment["effective_combined_contract_binding_sha256"]


def test_amendment_binds_current_bytes_of_base_contract_and_registry():
    """The amendment must be bound to the CURRENT bytes of both artifacts it
    amends -- if either ever changes without a new amendment revision, this
    must fail rather than silently amend stale text."""
    amendment = _load_amendment()
    actual_contract_sha256 = hashlib.sha256(BASE_CONTRACT_PATH.read_bytes()).hexdigest()
    actual_registry_sha256 = hashlib.sha256(SCHEMA_REGISTRY_PATH.read_bytes()).hexdigest()
    assert actual_contract_sha256 == amendment["semantic_body"]["amends"]["target_artifact_sha256_at_amendment_time"]
    assert actual_contract_sha256 == amendment["effective_combined_contract_binding"]["base_contract_sha256"]
    assert actual_registry_sha256 == amendment["semantic_body"]["amends"]["target_registry_sha256_at_amendment_time"]
    assert actual_registry_sha256 == amendment["effective_combined_contract_binding"]["base_registry_sha256"]


def test_amendment_does_not_authorize_raw_deletion():
    amendment = _load_amendment()
    assert amendment["raw_deletion_authorized"] is False
    assert amendment["semantic_body"]["raw_deletion_authorized"] is False


def test_registry_snapshot_binding_section_present_and_adopted():
    amendment = _load_amendment()
    binding = amendment["semantic_body"]["registry_snapshot_binding"]
    assert binding["adopted"] is True
    assert binding["closes"].startswith("Independent hostile review verdict BLOCK_REGISTRY_TIME_AMBIGUITY")


# --- 2. standalone reimplementation of the exact-artifact predicate --------

SCHEMA_ADMISSIBLE = "SCHEMA_ADMISSIBLE"
SCHEMA_INADMISSIBLE = "SCHEMA_INADMISSIBLE"
EVALUATION_RECEIPT_KIND = "SCHEMA_ADMISSION_EVALUATION_RECEIPT_V1"
_SOURCE_X = "a" * 64


def _require_sha256(value: str, field: str) -> None:
    if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError(f"{field} must be a 64-character lowercase SHA-256")


@dataclass(frozen=True, init=False)
class RegistrySnapshot:
    """A registry snapshot has exactly one authoritative input: its bytes."""
    exact_artifact_bytes: bytes

    def __init__(self, exact_artifact_bytes: bytes) -> None:
        if not isinstance(exact_artifact_bytes, bytes):
            raise TypeError("registry artifact must be exact bytes")
        parsed = json.loads(exact_artifact_bytes)
        if not isinstance(parsed.get("known_schema_variants"), dict):
            raise ValueError("registry artifact lacks object known_schema_variants")
        object.__setattr__(self, "exact_artifact_bytes", exact_artifact_bytes)

    @classmethod
    def from_exact_artifact_bytes(cls, artifact_bytes: bytes) -> "RegistrySnapshot":
        return cls(artifact_bytes)

    @property
    def known_schema_variants(self) -> dict[str, object]:
        return dict(json.loads(self.exact_artifact_bytes)["known_schema_variants"])

    @property
    def registry_snapshot_sha256(self) -> str:
        return hashlib.sha256(self.exact_artifact_bytes).hexdigest()


def _governing_binding_from_authoritative_artifacts(
    amendment_bytes: bytes, base_contract_bytes: bytes, base_registry_bytes: bytes,
) -> str:
    """Derive C only after checking every artifact named by the binding."""
    amendment = json.loads(amendment_bytes)
    semantic_hash = _canonical_hash(amendment["semantic_body"])
    if semantic_hash != amendment["amendment_semantic_content_sha256"]:
        raise ValueError("amendment semantic content hash mismatch")
    binding = amendment["effective_combined_contract_binding"]
    binding_hash = _canonical_hash(binding)
    if binding_hash != amendment["effective_combined_contract_binding_sha256"]:
        raise ValueError("effective combined contract binding mismatch")
    if binding["amendment_semantic_content_sha256"] != semantic_hash:
        raise ValueError("binding does not name the governing semantics")
    if hashlib.sha256(base_contract_bytes).hexdigest() != binding["base_contract_sha256"]:
        raise ValueError("governing base contract bytes do not match binding")
    if hashlib.sha256(base_registry_bytes).hexdigest() != binding["base_registry_sha256"]:
        raise ValueError("governing base registry bytes do not match binding")
    return binding_hash


@dataclass(frozen=True, init=False)
class GoverningRule:
    """C is derived from verified governing-authority artifact bytes."""
    amendment_bytes: bytes
    base_contract_bytes: bytes
    base_registry_bytes: bytes

    def __init__(self, amendment_bytes: bytes, base_contract_bytes: bytes,
                 base_registry_bytes: bytes) -> None:
        if not all(isinstance(value, bytes) for value in
                   (amendment_bytes, base_contract_bytes, base_registry_bytes)):
            raise TypeError("governing rule requires authoritative artifact bytes")
        _governing_binding_from_authoritative_artifacts(
            amendment_bytes, base_contract_bytes, base_registry_bytes,
        )
        object.__setattr__(self, "amendment_bytes", amendment_bytes)
        object.__setattr__(self, "base_contract_bytes", base_contract_bytes)
        object.__setattr__(self, "base_registry_bytes", base_registry_bytes)

    @classmethod
    def from_authoritative_artifacts(
        cls, amendment_bytes: bytes, base_contract_bytes: bytes, base_registry_bytes: bytes,
    ) -> "GoverningRule":
        return cls(amendment_bytes, base_contract_bytes, base_registry_bytes)

    @property
    def effective_combined_contract_binding_sha256(self) -> str:
        return _governing_binding_from_authoritative_artifacts(
            self.amendment_bytes, self.base_contract_bytes, self.base_registry_bytes,
        )


@dataclass(frozen=True)
class SchemaAdmissionEvaluation:
    """Canonical durable X/R/C/D provenance, not an in-memory-only fact."""
    source_object_sha256: str
    schema_id: Optional[str]
    registry_snapshot_sha256: str
    governing_effective_combined_contract_binding_sha256: str
    disposition: str

    @property
    def identity(self) -> tuple[str, str, str]:
        return (self.source_object_sha256, self.registry_snapshot_sha256,
                self.governing_effective_combined_contract_binding_sha256)

    def durable_value(self) -> dict:
        return {
            "disposition": self.disposition,
            "governing_effective_combined_contract_binding_sha256": self.governing_effective_combined_contract_binding_sha256,
            "receipt_kind": EVALUATION_RECEIPT_KIND,
            "registry_snapshot_sha256": self.registry_snapshot_sha256,
            "schema_id": self.schema_id,
            "source_object_sha256": self.source_object_sha256,
        }

    def durable_bytes(self) -> bytes:
        return _canonical_bytes(self.durable_value())

    @classmethod
    def from_durable_bytes(cls, receipt_bytes: bytes) -> "SchemaAdmissionEvaluation":
        value = json.loads(receipt_bytes)
        expected = {"receipt_kind", "source_object_sha256", "registry_snapshot_sha256",
                    "governing_effective_combined_contract_binding_sha256", "schema_id", "disposition"}
        if set(value) != expected or value["receipt_kind"] != EVALUATION_RECEIPT_KIND:
            raise ValueError("invalid schema-admission evaluation receipt shape")
        if _canonical_bytes(value) != receipt_bytes:
            raise ValueError("evaluation receipt must use canonical durable bytes")
        _require_sha256(value["source_object_sha256"], "source_object_sha256")
        _require_sha256(value["registry_snapshot_sha256"], "registry_snapshot_sha256")
        _require_sha256(value["governing_effective_combined_contract_binding_sha256"], "governing binding")
        if value["disposition"] not in (SCHEMA_ADMISSIBLE, SCHEMA_INADMISSIBLE):
            raise ValueError("invalid schema-admission disposition")
        return cls(value["source_object_sha256"], value["schema_id"], value["registry_snapshot_sha256"],
                   value["governing_effective_combined_contract_binding_sha256"], value["disposition"])


def _r1_snapshot() -> RegistrySnapshot:
    return RegistrySnapshot.from_exact_artifact_bytes(SCHEMA_REGISTRY_PATH.read_bytes())


def _governing_rule() -> GoverningRule:
    return GoverningRule.from_authoritative_artifacts(
        AMENDMENT_PATH.read_bytes(), BASE_CONTRACT_PATH.read_bytes(), SCHEMA_REGISTRY_PATH.read_bytes(),
    )


def daily_market_evidence_v1_schema_admission(
    source_object_sha256: str, schema_id: Optional[str], registry_snapshot: RegistrySnapshot,
    governing_rule: GoverningRule,
) -> SchemaAdmissionEvaluation:
    """Pure X/R/C evaluation; R and C are derived objects, never assertions."""
    _require_sha256(source_object_sha256, "source_object_sha256")
    if not isinstance(registry_snapshot, RegistrySnapshot) or not isinstance(governing_rule, GoverningRule):
        raise TypeError("evaluation requires exact RegistrySnapshot and GoverningRule objects")
    snapshot = RegistrySnapshot.from_exact_artifact_bytes(registry_snapshot.exact_artifact_bytes)
    rule = GoverningRule.from_authoritative_artifacts(
        governing_rule.amendment_bytes, governing_rule.base_contract_bytes,
        governing_rule.base_registry_bytes,
    )
    disposition = (SCHEMA_INADMISSIBLE if schema_id is None or schema_id not in snapshot.known_schema_variants
                   else SCHEMA_ADMISSIBLE)
    return SchemaAdmissionEvaluation(source_object_sha256, schema_id, snapshot.registry_snapshot_sha256,
                                     rule.effective_combined_contract_binding_sha256, disposition)


def verify_schema_admission_evaluation(
    receipt_bytes: bytes, upstream_source_object_sha256: str, registry_artifact_bytes: bytes,
    governing_amendment_bytes: bytes, base_contract_bytes: bytes, base_registry_bytes: bytes,
) -> SchemaAdmissionEvaluation:
    """Accept durable provenance only when X/R/C/D all recompute from authority."""
    parsed = SchemaAdmissionEvaluation.from_durable_bytes(receipt_bytes)
    _require_sha256(upstream_source_object_sha256, "upstream source_object_sha256")
    if parsed.source_object_sha256 != upstream_source_object_sha256:
        raise ValueError("receipt source object does not match supplied upstream identity")
    recomputed = daily_market_evidence_v1_schema_admission(
        upstream_source_object_sha256, parsed.schema_id,
        RegistrySnapshot.from_exact_artifact_bytes(registry_artifact_bytes),
        GoverningRule.from_authoritative_artifacts(
            governing_amendment_bytes, base_contract_bytes, base_registry_bytes,
        ),
    )
    if parsed != recomputed:
        raise ValueError("receipt X/R/C/schema/disposition does not verify against authoritative artifacts")
    return recomputed


def _evaluate(schema_id: Optional[str], snapshot: Optional[RegistrySnapshot] = None,
              governing_rule: Optional[GoverningRule] = None) -> SchemaAdmissionEvaluation:
    return daily_market_evidence_v1_schema_admission(_SOURCE_X, schema_id, snapshot or _r1_snapshot(),
                                                      governing_rule or _governing_rule())


def _verify(receipt_bytes: bytes, registry_artifact_bytes: Optional[bytes] = None,
            governing_amendment_bytes: Optional[bytes] = None) -> SchemaAdmissionEvaluation:
    return verify_schema_admission_evaluation(
        receipt_bytes, _SOURCE_X, registry_artifact_bytes or SCHEMA_REGISTRY_PATH.read_bytes(),
        governing_amendment_bytes or AMENDMENT_PATH.read_bytes(),
        BASE_CONTRACT_PATH.read_bytes(), SCHEMA_REGISTRY_PATH.read_bytes(),
    )


def _r2_snapshot(schema_id: str = "future_variant_not_yet_registered") -> RegistrySnapshot:
    registry = json.loads(SCHEMA_REGISTRY_PATH.read_bytes())
    registry["known_schema_variants"][schema_id] = {"status": "KNOWN_VALID_SCHEMA_VARIANT"}
    return RegistrySnapshot.from_exact_artifact_bytes(
        (json.dumps(registry, indent=2, ensure_ascii=True) + "\n").encode()
    )


def test_registry_identity_uses_exact_artifact_bytes_not_canonical_json():
    snapshot = _r1_snapshot()
    assert snapshot.registry_snapshot_sha256 == _registry_snapshot_sha256()
    assert snapshot.registry_snapshot_sha256 != _canonical_hash(json.loads(snapshot.exact_artifact_bytes))


def test_predicate_requires_derived_snapshot_and_governing_rule_not_claimed_hash():
    import pytest
    with pytest.raises(TypeError):
        daily_market_evidence_v1_schema_admission(_SOURCE_X, "bybit_trade_v1", {}, _governing_rule())
    with pytest.raises(TypeError):
        daily_market_evidence_v1_schema_admission(_SOURCE_X, "bybit_trade_v1", _r1_snapshot(), "f" * 64)


def test_predicate_registered_none_and_unknown_schema_dispositions():
    snapshot = _r1_snapshot()
    for schema_id in snapshot.known_schema_variants:
        assert _evaluate(schema_id, snapshot).disposition == SCHEMA_ADMISSIBLE
    assert _evaluate(None, snapshot).disposition == SCHEMA_INADMISSIBLE
    assert _evaluate("some_never_seen_variant", snapshot).disposition == SCHEMA_INADMISSIBLE


# --- 3. countermodel: current implementation reproduces the audited gap ----
# (empirical corroboration only -- the gap being closed is a protocol-text
# gap, not this specific implementation bug; see
# semantic_body.underspecification_recorded.empirical_corroboration_not_itself_the_gap)

_UNKNOWN_HEADER = BASE_SCHEMA + ("EXTRA_UNSEEN_COLUMN",)


def _unknown_schema_row():
    return {"timestamp": "1700000000.000", "symbol": "MONUSDT", "side": "Buy", "size": "1",
            "price": "1", "tickDirection": "PlusTick", "trdMatchID": "t-1",
            "grossValue": "1e8", "homeNotional": "1", "foreignNotional": "1",
            "EXTRA_UNSEEN_COLUMN": "x"}


def _unknown_schema_raw_bytes():
    import gzip
    row = _unknown_schema_row()
    text = ",".join(_UNKNOWN_HEADER) + "\n" + ",".join(row[h] for h in _UNKNOWN_HEADER) + "\n"
    return gzip.compress(text.encode())


def test_countermodel_reproduced_on_current_parser_b_path():
    """Direct reproduction of the auditor's countermodel using the current,
    unmodified Parser B / materializer code: an unknown-schema object with
    otherwise-parseable rows is currently MATERIALIZED_VALID, is_valid=True,
    despite carrying SCHEMA_MISMATCH and schema_id=None."""
    core, anomalies = daily_primitive(stream_id="s", utc_date="2023-11-14", header=_UNKNOWN_HEADER,
                                       rows=[_unknown_schema_row()], historical_cutoff_utc=CUTOFF)
    assert core["schema_id"] is None
    assert ANOMALY_SCHEMA_MISMATCH in anomalies
    assert core["trade_count"] == 1  # record otherwise complete, not empty/refused

    raw = _unknown_schema_raw_bytes()
    result = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert result.status == MATERIALIZED_VALID
    assert result.is_valid is True
    assert result.record["schema_id"] is None
    assert ANOMALY_SCHEMA_MISMATCH in result.anomalies
    # validate_daily_market_evidence_v1 (unmodified) does not itself check
    # schema_id membership -- this is exactly the gap being closed at the
    # protocol level, not by editing this function.
    assert validate_daily_market_evidence_v1(result.record) == []


def test_countermodel_rejected_under_new_predicate():
    """The same record that the current implementation calls
    MATERIALIZED_VALID is SCHEMA_INADMISSIBLE under the amendment's
    registry-snapshot-bound predicate -- the protocol-level contradiction the
    amendment resolves, without requiring any code change here."""
    raw = _unknown_schema_raw_bytes()
    result = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    assert result.status == MATERIALIZED_VALID  # current implementation, unchanged
    evaluation = daily_market_evidence_v1_schema_admission(
        result.record["source_object_sha256"], result.record["schema_id"], _r1_snapshot(), _governing_rule(),
    )
    assert evaluation.disposition == SCHEMA_INADMISSIBLE
    assert result.is_valid is True and evaluation.disposition == SCHEMA_INADMISSIBLE, (
        "this contradiction between implementation-level is_valid and the new "
        "protocol-level admission predicate is exactly parser_status.parser_b_current's "
        "recorded NONCONFORMING disposition; remediation is explicitly out of scope here"
    )


def test_parser_a_already_conforms_never_valid_on_unknown_schema():
    """Parser A already never emits a non-None record for an unrecognized
    column set -- it already satisfies schema_admission_rule without any
    change, per semantic_body.parser_status.parser_a_current."""
    raw = _unknown_schema_raw_bytes()
    result = materialize_parser_a(raw, date(2023, 11, 14), "x")
    assert result.status == MATERIALIZATION_QUARANTINED
    assert result.record is None
    assert result.status != MATERIALIZED_VALID

    direct = rp.parse_daily_object(raw, date(2023, 11, 14), "x")
    assert direct.status == rp.STATUS_UNKNOWN_SCHEMA_QUARANTINE
    assert direct.record is None


# --- 4. red-team scenario B: raw retention independent of admission --------

def test_raw_retention_independent_of_admission_parser_a():
    """Scenario B: raw object identity (raw_object_sha256) remains available
    for an unknown-schema object even though it is not admitted -- retention
    is not gated on, and does not grant, admission."""
    raw = _unknown_schema_raw_bytes()
    result = materialize_parser_a(raw, date(2023, 11, 14), "x")
    assert result.status == MATERIALIZATION_QUARANTINED
    assert result.raw_object_sha256 == hashlib.sha256(raw).hexdigest()


def test_raw_retention_independent_of_admission_parser_b():
    raw = _unknown_schema_raw_bytes()
    result = materialize_parser_b(raw, "2023-11-14", "s", CUTOFF)
    evaluation = daily_market_evidence_v1_schema_admission(
        result.record["source_object_sha256"], result.record["schema_id"], _r1_snapshot(), _governing_rule(),
    )
    assert evaluation.disposition == SCHEMA_INADMISSIBLE
    # raw identity is present regardless of the (inadmissible) predicate result
    assert result.raw_object_sha256 == hashlib.sha256(raw).hexdigest()
    assert result.record["source_object_sha256"] == hashlib.sha256(raw).hexdigest()


# --- 5. red-team scenario C: registration is not overall validity (M6) -----

def test_registered_schema_with_missing_required_field_still_invalid():
    """A record with a SCHEMA_ADMISSIBLE schema_id but a pre-existing
    contract violation (missing required non-null field when trade_count>0)
    remains invalid under the unmodified validator -- schema registration is
    necessary, not sufficient. Checked under both R1 and a simulated R2 to
    prove the sufficiency-collapse a later registry snapshot must not grant."""
    r1, r2 = _r1_snapshot(), _r2_snapshot()
    assert r1.registry_snapshot_sha256 != r2.registry_snapshot_sha256

    for schema_id, snapshot in (("bybit_trade_v1", r1),
                                ("future_variant_not_yet_registered", r2)):
        evaluation = _evaluate(schema_id, snapshot)
        assert evaluation.disposition == SCHEMA_ADMISSIBLE

        record = {f: None for f in ALL_CONTRACT_FIELDS}
        record.update({
            "instrument_instance_id": "x", "utc_date": "2023-11-14", "trade_count": 1,
            "duplicate_count": 0, "rejected_row_count": 0, "schema_id": schema_id,
            "open": "1", "high": "1", "low": "1",
            # "close" deliberately omitted (stays None) -- required when trade_count>0
            "base_volume": "1", "quote_turnover": "1",
            "first_source_timestamp_utc": "2023-11-14T00:00:00.000Z",
            "last_source_timestamp_utc": "2023-11-14T00:00:00.000Z",
            "first_source_trade_id": "t-1", "last_source_trade_id": "t-1",
            "source_object_sha256": "a" * 64,
        })
        violations = validate_daily_market_evidence_v1(record)
        assert any("close" in v for v in violations), (
            "SCHEMA_ADMISSIBLE under a registry snapshot must never make condition (a) "
            "unnecessary, regardless of which registry snapshot granted (b)"
        )


# --- 6. hostile exact-snapshot and durable X/R/C/D counterfactuals ---------

_AMBIENT_REGISTRY_FOR_DETERMINISM_TEST = {"latest": None}


def test_r1_r2_explicit_snapshots_are_distinct_and_ambient_independent():
    """M1/M4: R2 cannot replace an explicitly supplied R1 snapshot."""
    schema_id, r1, r2 = "future_variant_not_yet_registered", _r1_snapshot(), _r2_snapshot()
    _AMBIENT_REGISTRY_FOR_DETERMINISM_TEST["latest"] = r2
    evaluation_r1_t1 = _evaluate(schema_id, r1)
    _AMBIENT_REGISTRY_FOR_DETERMINISM_TEST["latest"] = r1
    evaluation_r1_t2 = _evaluate(schema_id, r1)
    evaluation_r2 = _evaluate(schema_id, r2)
    assert evaluation_r1_t1 == evaluation_r1_t2
    assert evaluation_r1_t1.disposition == SCHEMA_INADMISSIBLE
    assert evaluation_r2.disposition == SCHEMA_ADMISSIBLE
    assert evaluation_r1_t1.identity != evaluation_r2.identity


def test_hostile_r1_hash_plus_r2_contents_is_structurally_unavailable():
    """M2: R1 bytes/hash cannot be paired with R2 membership."""
    import pytest
    r1, r2 = _r1_snapshot(), _r2_snapshot()
    with pytest.raises(TypeError):
        daily_market_evidence_v1_schema_admission(_SOURCE_X, "future_variant_not_yet_registered", r2, _governing_rule(),
                                                   claimed_registry_hash=r1.registry_snapshot_sha256)
    with pytest.raises(TypeError):
        RegistrySnapshot(r1.exact_artifact_bytes, r2.known_schema_variants, r1.registry_snapshot_sha256)
    evaluation = _evaluate("future_variant_not_yet_registered", r2)
    assert evaluation.registry_snapshot_sha256 == hashlib.sha256(r2.exact_artifact_bytes).hexdigest()
    assert evaluation.registry_snapshot_sha256 != r1.registry_snapshot_sha256


def test_hostile_r2_hash_plus_r1_contents_is_structurally_unavailable():
    """M2b: the reverse independent-content construction is also rejected."""
    import pytest
    r1, r2 = _r1_snapshot(), _r2_snapshot()
    with pytest.raises(TypeError):
        RegistrySnapshot(r2.exact_artifact_bytes, r1.known_schema_variants, r2.registry_snapshot_sha256)
    assert _evaluate("future_variant_not_yet_registered", r1).disposition == SCHEMA_INADMISSIBLE
    assert _evaluate("future_variant_not_yet_registered", r2).disposition == SCHEMA_ADMISSIBLE


def test_arbitrary_governing_binding_is_not_a_protocol_valid_input():
    """M5: C can only be derived from verified governing authority bytes."""
    import pytest
    with pytest.raises(TypeError):
        GoverningRule("f" * 64)
    with pytest.raises(ValueError):
        GoverningRule.from_authoritative_artifacts(
            AMENDMENT_PATH.read_bytes(), b"different base contract", SCHEMA_REGISTRY_PATH.read_bytes(),
        )


def test_registry_byte_mutation_cannot_retain_old_identity():
    """M9: any byte change creates a new exact-byte snapshot identity."""
    r1 = _r1_snapshot()
    mutated = RegistrySnapshot.from_exact_artifact_bytes(r1.exact_artifact_bytes.replace(b'"artifact"', b'"Artifact"', 1))
    assert mutated.registry_snapshot_sha256 != r1.registry_snapshot_sha256
    assert mutated.known_schema_variants == r1.known_schema_variants


def test_durable_receipt_replays_and_verifies_x_r_c_and_d_after_object_loss():
    """M8: process-state loss is safe only after authority-backed verification."""
    schema_id, r1, r2 = "future_variant_not_yet_registered", _r1_snapshot(), _r2_snapshot()
    receipt_r1 = _evaluate(schema_id, r1).durable_bytes()
    receipt_r2 = _evaluate(schema_id, r2).durable_bytes()
    del r1, r2
    replay_r1 = _verify(receipt_r1)
    r2_bytes = _r2_snapshot().exact_artifact_bytes
    replay_r2 = _verify(receipt_r2, r2_bytes)
    assert replay_r1.disposition == SCHEMA_INADMISSIBLE
    assert replay_r2.disposition == SCHEMA_ADMISSIBLE
    assert replay_r1.identity != replay_r2.identity
    assert replay_r1.durable_bytes() == receipt_r1


def test_same_x_r_c_is_deterministic_and_different_c_is_distinct():
    """M5/M10: C is derived from verified governing bytes and part of identity."""
    r1, c1 = _r1_snapshot(), _governing_rule()
    first = _evaluate("bybit_trade_v1", r1, c1)
    second = _evaluate("bybit_trade_v1", r1, c1)
    assert first == second and first.durable_bytes() == second.durable_bytes()

    amendment = _load_amendment()
    amended = dict(amendment)
    semantic = dict(amendment["semantic_body"])
    semantic["schema_admission_rule"] = dict(semantic["schema_admission_rule"])
    semantic["schema_admission_rule"]["why_minimum_vocabulary"] += " distinct C"
    amended["semantic_body"] = semantic
    amended["amendment_semantic_content_sha256"] = _canonical_hash(semantic)
    binding = dict(amended["effective_combined_contract_binding"])
    binding["amendment_semantic_content_sha256"] = amended["amendment_semantic_content_sha256"]
    amended["effective_combined_contract_binding"] = binding
    amended["effective_combined_contract_binding_sha256"] = _canonical_hash(binding)
    c2 = GoverningRule.from_authoritative_artifacts(
        _canonical_bytes(amended), BASE_CONTRACT_PATH.read_bytes(), SCHEMA_REGISTRY_PATH.read_bytes(),
    )
    changed_rule = _evaluate("bybit_trade_v1", r1, c2)
    assert changed_rule.disposition == first.disposition
    assert changed_rule.identity != first.identity


def test_receipt_rejects_noncanonical_or_missing_identity_components():
    """M3/M8: omission or noncanonical process memory stand-ins fail closed."""
    import pytest
    receipt = _evaluate("bybit_trade_v1").durable_bytes()
    value = json.loads(receipt)
    del value["registry_snapshot_sha256"]
    with pytest.raises(ValueError):
        SchemaAdmissionEvaluation.from_durable_bytes(_canonical_bytes(value))
    with pytest.raises(ValueError):
        SchemaAdmissionEvaluation.from_durable_bytes(receipt.rstrip())


def test_receipt_verifier_rejects_forged_disposition_registry_and_governing_binding():
    """M11/M12/M13: receipt fields never establish their own correctness."""
    import pytest
    receipt = _evaluate("bybit_trade_v1").durable_bytes()
    value = json.loads(receipt)
    for field, replacement in (
        ("disposition", SCHEMA_INADMISSIBLE),
        ("registry_snapshot_sha256", "0" * 64),
        ("governing_effective_combined_contract_binding_sha256", "f" * 64),
    ):
        forged = dict(value)
        forged[field] = replacement
        with pytest.raises(ValueError):
            _verify(_canonical_bytes(forged))


# --- 7. red-team scenario E: unrelated frozen semantics left untouched -----

def test_amendment_declares_unrelated_semantics_out_of_scope():
    amendment = _load_amendment()
    out_of_scope = amendment["semantic_body"]["explicitly_not_addressed_by_this_amendment"]
    joined = " ".join(out_of_scope)
    for term in ("duplicate semantics", "timestamp", "funding", "gap classification", "lifecycle"):
        assert term in joined, term


def test_amendment_leaves_duplicate_semantics_amendment_bytes_untouched():
    amendment = _load_amendment()
    actual_sha256 = hashlib.sha256(DUP_AMENDMENT_PATH.read_bytes()).hexdigest()
    recorded = amendment["semantic_body"]["amends"]["also_informed_by_unchanged"][
        "r1_normalized_evidence_duplicate_semantics_amendment_v1.json_sha256"
    ]
    assert actual_sha256 == recorded


def test_amendment_leaves_base_contract_and_registry_bytes_untouched():
    """Redundant with test_amendment_binds_current_bytes_of_base_contract_and_registry
    but asserted directly against amends.original_*_bytes_unchanged_by_this_amendment
    to pin the amendment's own explicit claim, not just the digest binding."""
    amendment = _load_amendment()
    assert amendment["semantic_body"]["amends"]["original_contract_bytes_unchanged_by_this_amendment"] is True
    assert amendment["semantic_body"]["amends"]["original_schema_registry_bytes_unchanged_by_this_amendment"] is True


def test_known_schema_duplicate_semantics_regression_unaffected():
    """Sanity regression: a KNOWN-schema duplicate-group fixture must still
    resolve exactly as the (unmodified) duplicate-semantics amendment
    already governs -- this amendment does not touch that logic."""
    from decimal import Decimal
    rows = [
        {"timestamp": "1751328000.0", "symbol": "MONUSDT", "side": "Buy", "size": "2", "price": "1.1",
         "tickDirection": "PlusTick", "trdMatchID": "z" * 32, "grossValue": "220000000",
         "homeNotional": "2", "foreignNotional": "2.2"},
        {"timestamp": "1751328000.0", "symbol": "MONUSDT", "side": "Sell", "size": "2.00", "price": "1.10",
         "tickDirection": "MinusTick", "trdMatchID": "z" * 32, "grossValue": "220000000",
         "homeNotional": "2.00", "foreignNotional": "2.20"},
    ]
    core, anomalies = daily_primitive(stream_id="s", utc_date="2025-07-01", header=BASE_SCHEMA,
                                       rows=rows, historical_cutoff_utc=CUTOFF)
    assert core["schema_id"] == "bybit_trade_v1"
    assert Decimal(core["close"]) == Decimal("1.1")
    assert core["duplicate_count"] == 1


def test_parser_status_snapshots_match_current_module_bytes():
    """Governance snapshot accuracy: parser_status records the exact current
    module bytes at candidate-authoring time, so a later, legitimate repair
    of either module is detectable as a snapshot mismatch rather than
    silently assumed still accurate."""
    amendment = _load_amendment()
    import qntylab.r1_reference_parser as rp_mod
    import qntylab.r1_retention_candidate as rc_mod
    a_sha = hashlib.sha256(Path(rp_mod.__file__).read_bytes()).hexdigest()
    b_sha = hashlib.sha256(Path(rc_mod.__file__).read_bytes()).hexdigest()
    assert a_sha == amendment["semantic_body"]["parser_status"]["parser_a_current"]["current_sha256"]
    assert b_sha == amendment["semantic_body"]["parser_status"]["parser_b_current"]["current_sha256"]
