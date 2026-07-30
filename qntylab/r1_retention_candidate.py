"""R1 bounded-evidence retention architecture (Model C hybrid) — candidate, not frozen.

Full raw retention of the frozen R1 Bybit trade population does not fit local
storage: see experiments/data/r1_raw_storage_footprint_v1.json (point
estimate 4,811,961,308,917 bytes / conservative P90 13,558,238,467,450 bytes
against local free storage on the order of 9.2e10 bytes). This module
implements the receipt, retention-state, audit-reservoir, and crash-
consistency primitives for a bounded architecture: a normalized daily
primitive plus a provenance receipt are retained permanently for every
processed raw object; raw bytes themselves are retained only for objects that
are anomalous or a member of a predeclared, strategy-blind audit reservoir.

Distinguish INTEGRITY (a hash lets you detect whether bytes changed) from
PRESERVATION (the bytes themselves are still stored). A SHA-256 receipt on a
deleted object gives integrity and (if the source is still reachable and
unmutated) REHYDRATABILITY; it does not give PRESERVATION.
"""
from __future__ import annotations

from datetime import datetime
from hashlib import sha256
from pathlib import Path
from typing import Iterable

from qntylab.r1_input_bom import canonical_bytes, canonical_hash

# --- raw retention states -----------------------------------------------
RAW_RETAINED = "RAW_RETAINED"
RAW_DELETED_AFTER_VERIFIED_DERIVATION = "RAW_DELETED_AFTER_VERIFIED_DERIVATION"
RAW_UNAVAILABLE_SOURCE_ABSENT = "RAW_UNAVAILABLE_SOURCE_ABSENT"
RAW_QUARANTINED_ANOMALY = "RAW_QUARANTINED_ANOMALY"

# --- reproducibility claim levels ----------------------------------------
PRESERVATION_REPRODUCIBLE = "PRESERVATION_REPRODUCIBLE"      # raw bytes retained locally
REHYDRATION_REPRODUCIBLE = "REHYDRATION_REPRODUCIBLE"        # raw deleted; source SHA currently reconfirmed
DERIVATION_AUDITABLE = "DERIVATION_AUDITABLE"                 # raw neither retained nor currently rehydratable

# --- crash-consistency commit protocol -----------------------------------
COMMIT_STAGES = ("RETRIEVED_UNHASHED", "HASHED", "PARSED", "NORMALIZED_WRITTEN",
                  "RECEIPT_WRITTEN", "RAW_ELIGIBLE_FOR_DELETION", "RAW_DELETED")
_STAGE_ORDER = {name: i for i, name in enumerate(COMMIT_STAGES)}


def raw_deletion_permitted(commit_stage: str) -> bool:
    """Raw bytes may be deleted only once the normalized primitive and its
    receipt are both durably committed (RECEIPT_WRITTEN or later)."""
    return _STAGE_ORDER[commit_stage] >= _STAGE_ORDER["RECEIPT_WRITTEN"]


# --- source schema (verified from a bounded pilot, 2022-2026 samples) ----
BASE_SCHEMA = ("timestamp", "symbol", "side", "size", "price", "tickDirection",
               "trdMatchID", "grossValue", "homeNotional", "foreignNotional")
KNOWN_SCHEMA_VARIANTS = {
    BASE_SCHEMA: "bybit_trade_v1",
    BASE_SCHEMA + ("RPI",): "bybit_trade_v1_rpi",  # observed 2026-06-30 DOLOUSDT pilot object
}

ANOMALY_SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
ANOMALY_PARSE_REJECTION = "PARSE_REJECTION"
ANOMALY_CONTAINER = "CONTAINER_ANOMALY"
ANOMALY_TIMESTAMP_CONTAINMENT = "TIMESTAMP_CONTAINMENT_VIOLATION"
ANOMALY_FUTURE_CUTOFF = "FUTURE_CUTOFF_VIOLATION"
ANOMALY_DUPLICATE_UNEXPECTED = "DUPLICATE_UNEXPECTED"
ANOMALY_DUPLICATE_CONFLICTING = "DUPLICATE_CONFLICTING"
ANOMALY_SOURCE_MUTATION = "SOURCE_MUTATION"
ANOMALY_REDUNDANT_FIELD_MISMATCH = "REDUNDANT_FIELD_MISMATCH"


def schema_identify(header: tuple[str, ...]) -> tuple[str | None, bool]:
    name = KNOWN_SCHEMA_VARIANTS.get(tuple(header))
    return name, name is not None


def redundant_fields_consistent(*, size: float, price: float, home: float, foreign: float,
                                  gross: float, rel_tol: float = 1e-6) -> bool:
    """Bybit's raw schema carries homeNotional/foreignNotional/grossValue as
    values fully derivable from (size, price). Checking that derivation on
    every row is a free, always-on, per-object independent consistency check
    against the primary fields (see INDEPENDENT VALIDATION in the report) —
    it does not require a second parser implementation."""
    if abs(home - size) > 1e-9:
        return False
    if abs(foreign - size * price) > rel_tol * max(1.0, abs(foreign)):
        return False
    if abs(gross - foreign * 1e8) > rel_tol * max(1.0, abs(gross)):
        return False
    return True


def _size_stratum(byte_size: int) -> str:
    if byte_size < 100_000:
        return "lt_100kb"
    if byte_size < 1_000_000:
        return "100kb_1mb"
    if byte_size < 10_000_000:
        return "1mb_10mb"
    if byte_size < 100_000_000:
        return "10mb_100mb"
    return "gte_100mb"


def daily_primitive(*, stream_id: str, utc_date: str, header: tuple[str, ...],
                     rows: list[dict[str, str]], historical_cutoff_utc: str) -> tuple[dict, list[str]]:
    """Build the strategy-independent daily forensic primitive for one
    stream/day from raw trade rows. Deterministic under row-input reordering
    (sorts internally) and rejects rows outside the UTC day or beyond the
    frozen historical cutoff rather than silently including them."""
    schema_id, schema_known = schema_identify(header)
    anomalies: list[str] = []
    if not schema_known:
        anomalies.append(ANOMALY_SCHEMA_MISMATCH)

    cutoff_ts = datetime.fromisoformat(historical_cutoff_utc.replace("Z", "+00:00")).timestamp()
    day_start = datetime.fromisoformat(utc_date + "T00:00:00+00:00").timestamp()
    day_end = datetime.fromisoformat(utc_date + "T23:59:59.999999+00:00").timestamp()

    valid_rows: list[tuple[float, str, float, float, str, str]] = []
    rejected = 0
    for index, row in enumerate(rows):
        try:
            ts = float(row["timestamp"])
            size, price = float(row["size"]), float(row["price"])
            side, trdid, tickdir = row["side"], row["trdMatchID"], row["tickDirection"]
            home, foreign, gross = float(row["homeNotional"]), float(row["foreignNotional"]), float(row["grossValue"])
        except (KeyError, ValueError):
            anomalies.append(ANOMALY_PARSE_REJECTION)
            rejected += 1
            continue
        if ts > cutoff_ts:
            anomalies.append(ANOMALY_FUTURE_CUTOFF)
            rejected += 1
            continue
        if not (day_start <= ts <= day_end):
            anomalies.append(ANOMALY_TIMESTAMP_CONTAINMENT)
            rejected += 1
            continue
        if not redundant_fields_consistent(size=size, price=price, home=home, foreign=foreign, gross=gross):
            anomalies.append(ANOMALY_REDUNDANT_FIELD_MISMATCH)
        valid_rows.append((ts, side, size, price, tickdir, trdid))

    # Canonical trade identity is trdMatchID alone: `side` is
    # INTENTIONALLY_DISCARDED per r1_information_loss_ledger_v1.json and is
    # not part of the frozen contract's duplicate definition ("identical
    # trade id/timestamp/price/size" — r1_normalized_evidence_contract_v1.json
    # DailyMarketEvidenceV1.close.duplicate_semantics). Grouping first and
    # classifying each group by its full member set (rather than an
    # order-dependent first-wins scan) keeps the result invariant under row
    # permutation, and lets a genuinely conflicting group (same trdMatchID,
    # different timestamp/size/price) be excluded from aggregation entirely
    # — fail-closed per r1_source_precedence_freeze.json:conflict_rule,
    # rather than silently keeping whichever row happened to appear first.
    by_id: dict[str, list[tuple]] = {}
    for r in valid_rows:
        by_id.setdefault(r[5], []).append(r)

    parsed: list[tuple[float, str, float, float, str, str]] = []
    duplicate_count = 0
    for trdid, group in by_id.items():
        if len(group) == 1:
            parsed.append(group[0])
            continue
        distinct = {(g[0], g[2], g[3]) for g in group}  # (timestamp, size, price)
        if len(distinct) == 1:
            parsed.append(group[0])
            duplicate_count += len(group) - 1
            anomalies.append(ANOMALY_DUPLICATE_UNEXPECTED)
        else:
            anomalies.append(ANOMALY_DUPLICATE_CONFLICTING)
            rejected += len(group)

    if not parsed:
        core = {"stream_id": stream_id, "utc_date": utc_date, "schema_id": schema_id,
                "trade_count": 0, "duplicate_count": duplicate_count, "rejected_row_count": rejected,
                "open": None, "high": None, "low": None, "close": None,
                "base_volume": 0.0, "quote_turnover": 0.0,
                "first_source_timestamp_utc": None, "last_source_timestamp_utc": None,
                "first_source_trade_id": None, "last_source_trade_id": None}
        return core, sorted(set(anomalies))

    parsed.sort(key=lambda r: (r[0], r[5]))  # (timestamp, trade id) — deterministic under input reordering
    prices = [r[3] for r in parsed]
    core = {
        "stream_id": stream_id,
        "utc_date": utc_date,
        "schema_id": schema_id,
        "trade_count": len(parsed),
        "duplicate_count": duplicate_count,
        "rejected_row_count": rejected,
        "open": prices[0],
        "high": max(prices),
        "low": min(prices),
        "close": prices[-1],
        "base_volume": sum(r[2] for r in parsed),
        "quote_turnover": sum(r[2] * r[3] for r in parsed),
        "first_source_timestamp_utc": parsed[0][0],
        "last_source_timestamp_utc": parsed[-1][0],
        "first_source_trade_id": parsed[0][5],
        "last_source_trade_id": parsed[-1][5],
    }
    return core, sorted(set(anomalies))


def _module_sha256() -> str:
    return sha256(Path(__file__).read_bytes()).hexdigest()


def audit_reservoir_dimension_key(*, stream_id: str, utc_date: str, byte_size: int, schema_id: str | None) -> tuple:
    """Selection dimensions are pre-outcome structural facts only: stream,
    calendar year, size stratum, schema variant. No return/PnL/signal field
    is representable in this key."""
    return (stream_id, utc_date[:4], _size_stratum(byte_size), schema_id or "UNKNOWN_SCHEMA")


def select_audit_reservoir(candidates: Iterable[dict], budget_bytes: int) -> tuple[set[str], int]:
    """Deterministic, strategy-blind, fixed-byte-budget audit reservoir.

    `candidates` items need only {"object_key", "stream_id", "utc_date",
    "byte_size", "schema_id"}. Selection order is a hash of the structural
    dimension key, so membership is independent of input list order and of
    anything outcome-shaped. Pass 1 guarantees at least one object per
    distinct (stream, year, size stratum, schema) cell before pass 2 fills
    remaining budget."""
    candidates = list(candidates)

    def sort_key(c: dict) -> str:
        dims = audit_reservoir_dimension_key(stream_id=c["stream_id"], utc_date=c["utc_date"],
                                              byte_size=c["byte_size"], schema_id=c["schema_id"])
        return canonical_hash({"dims": list(dims), "object_key": c["object_key"]})

    ordered = sorted(candidates, key=sort_key)
    selected: set[str] = set()
    total = 0
    seen_cells: set[tuple] = set()
    for c in ordered:
        cell = audit_reservoir_dimension_key(stream_id=c["stream_id"], utc_date=c["utc_date"],
                                              byte_size=c["byte_size"], schema_id=c["schema_id"])
        if cell in seen_cells or c["byte_size"] > budget_bytes - total:
            continue
        seen_cells.add(cell)
        selected.add(c["object_key"])
        total += c["byte_size"]
    for c in ordered:
        if c["object_key"] in selected or c["byte_size"] > budget_bytes - total:
            continue
        selected.add(c["object_key"])
        total += c["byte_size"]
    return selected, total


def retention_state(*, http_or_result_state: str, anomalies: list[str], audit_reservoir_member: bool,
                     commit_stage: str) -> tuple[str, str]:
    if http_or_result_state == "SOURCE_ABSENT":
        return RAW_UNAVAILABLE_SOURCE_ABSENT, "SOURCE_NEVER_PRESENT"
    if not raw_deletion_permitted(commit_stage):
        return RAW_RETAINED, "COMMIT_INCOMPLETE_RAW_NOT_YET_ELIGIBLE_FOR_DELETION"
    if anomalies:
        return RAW_QUARANTINED_ANOMALY, "ANOMALY:" + ",".join(sorted(set(anomalies)))
    if audit_reservoir_member:
        return RAW_RETAINED, "PREDECLARED_AUDIT_RESERVOIR_MEMBER"
    return RAW_DELETED_AFTER_VERIFIED_DERIVATION, "ORDINARY_VALIDATED_OBJECT_NOT_RESERVOIR_MEMBER"


def reproducibility_claim_level(raw_retention_state: str, currently_rehydratable: bool) -> str:
    if raw_retention_state in (RAW_RETAINED, RAW_QUARANTINED_ANOMALY):
        return PRESERVATION_REPRODUCIBLE
    if raw_retention_state == RAW_DELETED_AFTER_VERIFIED_DERIVATION and currently_rehydratable:
        return REHYDRATION_REPRODUCIBLE
    return DERIVATION_AUDITABLE


def build_receipt(*, stream_id: str, cache_key: str, source_url: str, retrieval_timestamp_utc: str,
                   http_or_result_state: str, raw_bytes: bytes | None, gzip_valid: bool | None,
                   header: tuple[str, ...] | None, primitive: dict | None, anomalies: list[str],
                   audit_reservoir_member: bool, commit_stage: str, retry_count: int = 0,
                   predecessor_receipt_sha256: str = "GENESIS") -> dict:
    schema_id, schema_known = (schema_identify(header) if header is not None else (None, False))
    state, reason = retention_state(http_or_result_state=http_or_result_state, anomalies=anomalies,
                                     audit_reservoir_member=audit_reservoir_member, commit_stage=commit_stage)
    module_sha = _module_sha256()
    normalized_sha = canonical_hash(primitive) if primitive is not None else None
    return {
        "source_url_or_query": source_url,
        "retrieval_timestamp_utc": retrieval_timestamp_utc,
        "http_or_result_state": http_or_result_state,
        "byte_size": len(raw_bytes) if raw_bytes is not None else None,
        "sha256": sha256(raw_bytes).hexdigest() if raw_bytes is not None else None,
        "parser_schema_result": schema_id or "UNKNOWN_SCHEMA",
        "stream_id": stream_id,
        "cache_key": cache_key,
        "retry_count": retry_count,
        "container_validation": ("GZIP_VALID" if gzip_valid else "GZIP_INVALID") if gzip_valid is not None else "NOT_APPLICABLE",
        "schema_known": schema_known,
        "parser_implementation_sha256": module_sha,
        "normalization_contract_sha256": module_sha,
        "row_count": primitive["trade_count"] if primitive else None,
        "duplicate_count": primitive["duplicate_count"] if primitive else None,
        "rejected_row_count": primitive["rejected_row_count"] if primitive else None,
        "normalized_primitive_identity": f"{stream_id}|{primitive['utc_date']}" if primitive else None,
        "normalized_primitive_sha256": normalized_sha,
        "anomalies": sorted(set(anomalies)),
        "raw_retention_state": state,
        "raw_retention_reason": reason,
        "rehydration_state": "NOT_APPLICABLE_RAW_RETAINED" if state in (RAW_RETAINED, RAW_QUARANTINED_ANOMALY) else "REHYDRATION_UNVERIFIED",
        "audit_reservoir_member": audit_reservoir_member,
        "commit_stage": commit_stage,
        "predecessor_receipt_sha256": predecessor_receipt_sha256,
    }


def record_rehydration_attempt(receipt: dict, *, attempt_timestamp_utc: str, rehydrated_sha256: str) -> dict:
    """Never overwrites the original receipt sha256. A mismatching rehydration
    is recorded as SOURCE_MUTATION and forces the object back to
    RAW_QUARANTINED_ANOMALY rather than being silently accepted."""
    original_sha = receipt["sha256"]
    verified = original_sha == rehydrated_sha256
    attempt = {"attempt_timestamp_utc": attempt_timestamp_utc, "rehydrated_sha256": rehydrated_sha256,
               "verified": verified,
               "state": "REHYDRATION_VERIFIED" if verified else "SOURCE_MUTATION_DETECTED"}
    updated = dict(receipt)
    updated["sha256"] = original_sha
    updated["rehydration_attempts"] = receipt.get("rehydration_attempts", []) + [attempt]
    if not verified:
        anomalies = sorted(set(receipt.get("anomalies", [])) | {ANOMALY_SOURCE_MUTATION})
        updated["anomalies"] = anomalies
        updated["raw_retention_state"] = RAW_QUARANTINED_ANOMALY
        updated["raw_retention_reason"] = "ANOMALY:" + ",".join(anomalies)
        updated["rehydration_state"] = "REHYDRATION_REJECTED_SOURCE_MUTATION"
    else:
        updated["rehydration_state"] = "REHYDRATION_VERIFIED"
    return updated


def assert_uniform_parser_version(receipts: Iterable[dict]) -> None:
    versions = {r["parser_implementation_sha256"] for r in receipts}
    if len(versions) > 1:
        raise ValueError(f"mixed parser implementation versions in population: {sorted(versions)}")


def write_candidate(root: Path) -> dict:
    import json
    import shutil

    bom_v3 = json.loads((root / "experiments/data/r1_population_raw_acquisition_bom_v3.json").read_bytes())
    footprint = json.loads((root / "experiments/data/r1_raw_storage_footprint_v1.json").read_bytes())
    req = bom_v3["required_acquisition"]
    module_sha = _module_sha256()
    test_sha = sha256((root / "tests/test_r1_retention_candidate.py").read_bytes()).hexdigest()
    free_bytes = shutil.disk_usage(root).free

    # Bounded pilot (5 objects, one per calendar era 2021-2026, all beneath
    # 250KB — no bulk acquisition): real GET + SHA-256 + parse + transcode.
    # See PILOT / MODEL A PILOT sections of the accompanying report for the
    # full per-object table this summarizes.
    pilot_evidence = {
        "method": "bounded pilot: 5 GET requests across 2021-2026, gzip decompress, CSV parse, redundant-field cross-check, struct-pack + gzip transcode",
        "object_count": 5,
        "total_raw_compressed_bytes": 19365 + 23556 + 25335 + 55756 + 162449,
        "essential_only_transcode_ratio_range": [0.5693, 0.6151],
        "full_lossless_transcode_ratio_range": [0.8543, 0.9026],
        "redundant_field_consistency": "homeNotional == size and foreignNotional == size*price exactly, grossValue == foreignNotional*1e8 with zero reconstruction error, on every row of every pilot object",
        "schema_drift_observed": "2026-06-30 DOLOUSDT pilot object carries an extra RPI column absent from 2021-2025 objects",
        "conclusion": "Model A transcoding alone reduces footprint by roughly 38-43% (essential fields) at best observed on this pilot; it does not close the gap between the point estimate (4,811,961,308,917 bytes) or P90 (13,558,238,467,450 bytes) and local free storage",
    }

    projected_essential_point_estimate_bytes = int(footprint["summary"]["market_raw_footprint_estimate"]["point_estimate_bytes"] * pilot_evidence["essential_only_transcode_ratio_range"][1])

    storage_budget = {
        "local_free_bytes_at_authoring_time": free_bytes,
        "market_raw_point_estimate_bytes": footprint["summary"]["market_raw_footprint_estimate"]["point_estimate_bytes"],
        "market_raw_p90_bytes": footprint["summary"]["market_raw_footprint_estimate"]["conservative_p90_bytes"],
        "model_a_best_case_projected_point_estimate_bytes": projected_essential_point_estimate_bytes,
        "model_a_still_exceeds_free_storage": projected_essential_point_estimate_bytes > free_bytes,
        "funding_estimated_request_count": 7238,
        "funding_estimated_bytes_per_page_conservative": 20_000,
        "funding_estimated_total_raw_bytes_conservative": 7238 * 20_000,
        "funding_raw_retention_policy": "retain all funding raw responses in full; funding footprint (~145MB conservative estimate) is negligible relative to local free storage and does not need Model C's anomaly/reservoir gating",
        "normalized_population_reserved_bytes": 2_000_000_000,
        "receipts_provenance_reserved_bytes": 1_000_000_000,
        "raw_anomaly_pool_reserved_bytes": 5_000_000_000,
        "raw_audit_reservoir_budget_bytes": 5_000_000_000,
        "note": "reserved figures are a bounded worst-case allocation proposal for review, not a measured population result; no bulk acquisition was performed to produce them",
    }

    downstream_required_fields = {
        "evidence_source": "qntylab/sprint_v2.py (executed, non-outcome code path) + experiments/data/sprint_v2_r1_origin_receipt.json locked_hypotheses",
        "proven_consumption": ["close (H012 momentum, H013 reversal)", "funding_rate (H014 funding)", "premium (H015 premium)"],
        "r1_locked_hypothesis_subset": ["R1-H012-30d", "R1-H012-90d", "R1-H014-24h", "R1-H014-7d"],
        "caveat": "R1's own trade-to-daily aggregation/execution code does not yet exist (only acquisition-prep artifacts are frozen); this field list is a conservative design assumption carried over from the executed sprint_v2 factor family plus standard forensic fields, not itself a frozen R1 contract",
        "daily_primitive_fields": ["open", "high", "low", "close", "base_volume", "quote_turnover", "trade_count",
                                    "first_source_timestamp_utc", "last_source_timestamp_utc", "first_source_trade_id",
                                    "last_source_trade_id", "duplicate_count", "rejected_row_count", "schema_id"],
    }

    candidate = {
        "artifact": "r1_bounded_evidence_retention_candidate_v1",
        "outcome_embargo": True,
        "bom_v3_sha256": footprint["bom_v3_sha256"],
        "required_acquisition_sha256": footprint["required_acquisition_sha256"],
        "storage_footprint_sha256": sha256((root / "experiments/data/r1_raw_storage_footprint_v1.json").read_bytes()).hexdigest(),
        "source_stream_count": req["source_stream_count"],
        "consumer_instance_count": req["consumer_instance_count"],
        "selected_architecture": "MODEL_C_HYBRID_BOUNDED_EVIDENCE",
        "rejected_architectures": {
            "MODEL_A_LOSSLESS_SEMANTIC_TRANSCODE": "alone, insufficient: pilot-measured transcode ratio (0.57-0.90 of raw) leaves the population still far above local free storage",
            "MODEL_B_PURE_STREAM_REDUCE_DELETE": "rejected: no independent validation beyond a single parser pass, no anomaly-triggered raw retention, cannot survive a later-discovered parser bug or reanalysis need; falsified by the real schema-drift finding (RPI column) that a fixed single-pass parser would silently mishandle without an anomaly channel",
        },
        "raw_retention_states": [RAW_RETAINED, RAW_DELETED_AFTER_VERIFIED_DERIVATION,
                                   RAW_UNAVAILABLE_SOURCE_ABSENT, RAW_QUARANTINED_ANOMALY],
        "reproducibility_claim_levels": [PRESERVATION_REPRODUCIBLE, REHYDRATION_REPRODUCIBLE, DERIVATION_AUDITABLE],
        "commit_stages": list(COMMIT_STAGES),
        "known_schema_variants": {v: list(k) for k, v in KNOWN_SCHEMA_VARIANTS.items()},
        "anomaly_triggers": [ANOMALY_SCHEMA_MISMATCH, ANOMALY_PARSE_REJECTION, ANOMALY_CONTAINER,
                              ANOMALY_TIMESTAMP_CONTAINMENT, ANOMALY_FUTURE_CUTOFF, ANOMALY_DUPLICATE_UNEXPECTED,
                              ANOMALY_DUPLICATE_CONFLICTING, ANOMALY_SOURCE_MUTATION, ANOMALY_REDUNDANT_FIELD_MISMATCH],
        "audit_reservoir_dimensions": ["stream_id", "calendar_year", "size_stratum", "schema_variant"],
        "audit_reservoir_excluded_dimensions": ["return", "momentum", "funding_signal", "future_outcome", "pnl", "any R1 hypothesis performance"],
        "independent_validation": {
            "all_objects": "per-row redundant-field cross-check (homeNotional/foreignNotional/grossValue vs size*price) — free, always-on, zero extra parser needed",
            "audit_reservoir_and_anomalies": "reference re-parse with a second, independently written implementation before Model C is frozen (not yet built in this candidate task)",
        },
        "pilot_evidence": pilot_evidence,
        "storage_budget": storage_budget,
        "downstream_required_fields": downstream_required_fields,
        "reproducibility_claim_level_for_this_candidate": DERIVATION_AUDITABLE,
        "implementation_sha256": module_sha,
        "test_module_sha256": test_sha,
        "verdict": "R1_BOUNDED_EVIDENCE_RETENTION_CANDIDATE_READY_FOR_REVIEW",
    }
    return candidate
