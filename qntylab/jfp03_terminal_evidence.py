"""Read-only, fail-closed source proof for the frozen JFP03 AFI input.

This is deliberately not a scientific executor: it authenticates the exact
V0R3 local objects and enumerates every decision-time AFI denominator once.
It contains no network client and never writes source data.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import math
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .research_ledger import canonical_bytes

ROOT = Path("experiments/research/jigsaw_fast_prospective_signal_discovery_v0")
MANIFEST = ROOT / "materialization/v0r3_source_manifest.json"
SNAPSHOT = ROOT / "materialization/v0r3_input_snapshot.json"
QUALIFICATION = ROOT / "materialization/v0r3_input_qualification.json"
RESULT = ROOT / "execution/v0r1/historical_scientific_execution_result.json"
CACHE = Path("data/archive/binance_jfp_v0")
SNAPSHOT_DIGEST = "24311649d541c28d068addc2fc76121d614a11f0f191581c7dd988ba0b99c69f"
QUALIFICATION_DIGEST = "420b0a4a84a57814d13393eb008affc05eb81223e06a9cf4a86c7772bc8bef5d"
RESULT_DIGEST = "aa42724ef37466babaf7fb81a44524fe9568d8679d0a2cf967ee9faaf9ae6dbb"
FIRST_DECISION_MS, LAST_DECISION_MS, HOUR_MS = 1577836800000, 1735686000000, 3600000
OBSERVATION_COUNT = 43848


class SourceProofError(RuntimeError):
    """Any provenance or frozen-contract failure; callers must fail closed."""


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SourceProofError(f"missing or invalid frozen artifact: {path}") from exc
    if not isinstance(value, dict):
        raise SourceProofError("frozen artifact must be an object")
    return value


def _digest_without(value: dict[str, Any], field: str) -> str:
    return hashlib.sha256(canonical_bytes({k: v for k, v in value.items() if k != field})).hexdigest()


def _verify_metadata(root: Path) -> dict[str, Any]:
    snapshot, qualification, manifest, result = (_json(root / p) for p in (SNAPSHOT, QUALIFICATION, MANIFEST, RESULT))
    snapshot_body = {k: v for k, v in snapshot.items() if k not in {"snapshot_id", "snapshot_digest"}}
    if snapshot.get("snapshot_digest") != SNAPSHOT_DIGEST or hashlib.sha256(canonical_bytes(snapshot_body)).hexdigest() != SNAPSHOT_DIGEST:
        raise SourceProofError("frozen snapshot digest mismatch")
    if qualification.get("qualification_digest") != QUALIFICATION_DIGEST or _digest_without(qualification, "qualification_digest") != QUALIFICATION_DIGEST:
        raise SourceProofError("frozen qualification digest mismatch")
    manifest_digest = manifest.get("source_manifest_digest")
    if not isinstance(manifest_digest, str) or _digest_without(manifest, "source_manifest_digest") != manifest_digest:
        raise SourceProofError("frozen source manifest digest mismatch")
    if snapshot.get("source_manifest_digest") != manifest_digest or manifest.get("source_object_count") != 63:
        raise SourceProofError("frozen snapshot/manifest binding mismatch")
    if result.get("result_digest") != RESULT_DIGEST or _digest_without(result, "result_digest") != RESULT_DIGEST:
        raise SourceProofError("terminal result digest mismatch")
    if result.get("terminal_classification") != "BLOCKED_CANDIDATE" or result.get("integrity_failure") != "AFI total quote-volume denominator must be positive":
        raise SourceProofError("terminal result identity mismatch")
    objects = manifest.get("source_objects")
    if not isinstance(objects, list) or len(objects) != 63:
        raise SourceProofError("exact source-object census unavailable")
    return {"manifest": manifest, "objects": objects, "manifest_digest": manifest_digest}


def _rows(data: bytes, member: str | None) -> list[list[str]]:
    try:
        if member is None:
            value = json.loads(data)
            if not isinstance(value, list): raise ValueError
            return value
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if z.namelist() != [member]: raise SourceProofError("source member substitution")
            with z.open(member) as f:
                values = list(csv.reader(io.TextIOWrapper(f, encoding="utf-8", newline="")))
        return values[1:] if values and values[0] and not values[0][0].isdigit() else values
    except (UnicodeDecodeError, json.JSONDecodeError, zipfile.BadZipFile, ValueError) as exc:
        raise SourceProofError("frozen source object parse failure") from exc


def _object_bytes(identity: dict[str, Any], cache_root: Path) -> tuple[bytes, str | None, str]:
    role = identity.get("source_role")
    if role == "PREFIX_REST_OBJECT":
        try: data = base64.b64decode(identity["authoritative_response_bytes_base64"], validate=True)
        except (KeyError, ValueError) as exc: raise SourceProofError("invalid embedded prefix") from exc
        expected, member = identity.get("response_sha256"), None
    elif role == "EXISTING_720_ROW_REST_OBJECT":
        expected, member = identity.get("response_sha256"), None
        data = (cache_root / f"{expected}.json").read_bytes()
    elif role in {"ORIGINAL_MONTHLY_OBJECT", "EXISTING_2025_01_OBJECT"}:
        expected, member = identity.get("local_sha256"), (identity.get("archive_member_names") or [None])[0]
        if not isinstance(member, str) or len(identity.get("archive_member_names", [])) != 1: raise SourceProofError("invalid frozen member identity")
        data = (cache_root / f"{expected}.zip").read_bytes()
        if identity.get("official_checksum") != expected: raise SourceProofError("monthly official identity mismatch")
    else: raise SourceProofError("unexpected frozen source role")
    if not isinstance(expected, str) or hashlib.sha256(data).hexdigest() != expected: raise SourceProofError("frozen source byte digest mismatch")
    return data, member, expected


def _time(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).isoformat().replace("+00:00", "Z")


def _denominator_violation(total_raw: Any, taker_raw: Any) -> bool:
    """Mirror the frozen AFI input order without computing AFI itself."""
    try:
        total, taker = float(total_raw), float(taker_raw)
    except (TypeError, ValueError) as exc:
        raise SourceProofError("AFI inputs must be finite") from exc
    if not math.isfinite(total) or not math.isfinite(taker):
        raise SourceProofError("AFI inputs must be finite")
    return total <= 0


def census(root: Path, *, source_root: Path) -> dict[str, Any]:
    """Authenticate all V0R3 objects and census each exact AFI decision row."""
    verified = _verify_metadata(root)
    cache_root = source_root / CACHE
    by_boundary: dict[int, tuple[list[str], dict[str, Any], str]] = {}
    for identity in verified["objects"]:
        if not isinstance(identity, dict): raise SourceProofError("invalid source identity")
        try: data, member, digest = _object_bytes(identity, cache_root)
        except OSError as exc: raise SourceProofError("required frozen source object missing") from exc
        for row in _rows(data, member):
            if not isinstance(row, list) or len(row) != 12: raise SourceProofError("invalid frozen source row structure")
            try: boundary = int(row[6]) + 1
            except (TypeError, ValueError) as exc: raise SourceProofError("invalid source close boundary") from exc
            if boundary in by_boundary: raise SourceProofError("duplicate frozen source row")
            by_boundary[boundary] = (row, identity, digest)
    schedule = tuple(range(FIRST_DECISION_MS, LAST_DECISION_MS + HOUR_MS, HOUR_MS))
    if len(schedule) != OBSERVATION_COUNT: raise SourceProofError("frozen decision schedule drift")
    violations = []
    for boundary in schedule:
        try:
            row, identity, digest = by_boundary[boundary]
            denominator_violation = _denominator_violation(row[7], row[10])
        except (KeyError, IndexError) as exc:
            raise SourceProofError("required AFI row unavailable or malformed") from exc
        if denominator_violation:
            violations.append({"decision_time": _time(boundary), "close_boundary_ms": boundary, "source_role": identity["source_role"], "source_object_digest": digest, "source_member": (identity.get("archive_member_names") or [None])[0], "total_quote_volume_raw": row[7], "taker_buy_quote_volume_raw": row[10]})
    violations.sort(key=lambda v: (v["close_boundary_ms"], v["source_object_digest"]))
    proof = {"schema_version": "jfp03-afi-source-proof-v0", "frozen_observation_domain": "every canonical JFP03 decision boundary from 2020-01-01T00:00:00Z through 2024-12-31T23:00:00Z inclusive at 1h", "required_afi_rows_inspected": len(schedule), "source_object_count_authenticated": len(verified["objects"]), "source_manifest_digest": verified["manifest_digest"], "snapshot_digest": SNAPSHOT_DIGEST, "qualification_digest": QUALIFICATION_DIGEST, "terminal_result_digest": RESULT_DIGEST, "denominator_validity_condition": "total_quote_volume > 0", "violations": violations, "violation_count": len(violations), "source_reacquisition": False}
    proof["proof_digest"] = hashlib.sha256(canonical_bytes(proof)).hexdigest()
    return proof
