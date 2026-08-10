from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 1
INDEX_SCHEMA_VERSION = "0.1.0"
RESEARCH_ROOT = Path("experiments/research")
CANDIDATES_PATH = RESEARCH_ROOT / "candidates.jsonl"
DECISIONS_PATH = RESEARCH_ROOT / "decisions.jsonl"
TRIALS_DIR = RESEARCH_ROOT / "trials"
STATE_PATH = RESEARCH_ROOT / "state.json"
TRIAL_INDEX_PATH = RESEARCH_ROOT / "trial_index.json"
LOCK_PATH = RESEARCH_ROOT / ".research_ledger.lock"
REQUIRED_INPUT_KIND = "OHLCV_1H_CSV"

RESEARCH_INTENTS = {"SCREEN", "FOLLOW_UP", "REPLICATION"}
DECISION_STATUSES = {"FOLLOW_UP", "SURVIVOR", "GRAVEYARDED", "BLOCKED"}
RUNNABLE_STATUSES = {"PROPOSED", "SCREENING", "FOLLOW_UP", "SURVIVOR"}
SCOPES = {"EXACT_VARIANT", "FAMILY"}

CANDIDATE_PROPOSED_KEYS = {
    "event_id",
    "event_type",
    "candidate_id",
    "family_id",
    "variant_id",
    "strategy_id",
    "strategy_version",
    "objective",
    "origin",
    "mechanism",
    "prediction",
    "required_data",
    "decision_time",
    "execution_time",
    "benchmark",
    "parameters",
    "mode",
    "bar_interval",
    "required_input_kind",
    "funding_boundary_mode",
    "failure_condition",
    "recorded_at_utc",
}
CANDIDATE_REOPENED_KEYS = {
    "event_id",
    "event_type",
    "candidate_id",
    "variant_id",
    "previous_decision_event_id",
    "reason",
    "material_change",
    "recorded_at_utc",
}
DECISION_KEYS = {
    "event_id",
    "event_type",
    "candidate_id",
    "family_id",
    "variant_id",
    "status",
    "scope",
    "reason_codes",
    "decision_note",
    "evidence_paths",
    "evidence_sha256",
    "revisit_condition",
    "recorded_at_utc",
}
TRIAL_KEYS = {
    "event_id",
    "event_type",
    "recorded_at_utc",
    "candidate_id",
    "family_id",
    "variant_id",
    "trial_id",
    "research_intent",
    "symbol",
    "evaluation_start",
    "evaluation_end",
    "input_sha256",
    "repository_commit",
    "relevant_source_sha256",
    "fee_bps",
    "slippage_bps",
    "gap_policy",
    "expected_interval",
    "receipt_path",
    "receipt_sha256",
    "compact_metrics",
}
COMPACT_METRIC_KEYS = {
    "observation_count",
    "trade_count",
    "exposure_fraction",
    "gross_return",
    "net_return",
    "buy_and_hold_return",
    "excess_return_vs_buy_and_hold",
    "total_cost",
    "maximum_drawdown",
}

# Research Factory V2 seams.  These keys are optional so the 378 historical
# trial events stay valid byte-for-byte; a new trial that declares
# instrument_contract_id is bound by the V2 trial identity instead of the V1 one.
TRIAL_OPTIONAL_KEYS = {
    "instrument_contract_id",
    "instrument_contract_digest",
    "funding_treatment",
    "research_generation",
    "period_id",
    "cost_mode",
    "canonical_family_id",
    "bar_path_schema_version",
    "bar_path_sha256",
    "bar_path_row_count",
    "bar_path_first_timestamp",
    "bar_path_last_timestamp",
    "registered_screen_id",
    "registered_variant_denominator",
}
DECISION_OPTIONAL_KEYS = {
    "registered_screen_id",
    "registered_variant_denominator",
}
CANDIDATE_OPTIONAL_KEYS = {
    "registered_screen_id",
    "registered_variant_denominator",
}

CORPUS_GENERATION_V1 = "CORPUS_GENERATION_V1_SUMMARY_ONLY"
CORPUS_GENERATION_V2 = "CORPUS_GENERATION_V2_BAR_PATH"
RESEARCH_GENERATIONS = {CORPUS_GENERATION_V1, CORPUS_GENERATION_V2}


class LedgerError(RuntimeError):
    pass


@dataclass(frozen=True)
class CanonicalHistory:
    candidates: tuple[dict[str, Any], ...]
    decisions: tuple[dict[str, Any], ...]
    trials: tuple[dict[str, Any], ...]
    generated_from: dict[str, Any]


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(canonical_bytes(value) + b"\n")


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LedgerError(f"index missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise LedgerError(f"malformed JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise LedgerError(f"JSON object required: {path}")
    return value


def event_id(prefix: str, payload: dict[str, Any]) -> str:
    clean = {key: value for key, value in payload.items() if key != "event_id"}
    return f"{prefix}_{sha256_bytes(canonical_bytes(clean))[:24]}"


def utc_now() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def variant_identity_payload(value: dict[str, Any]) -> dict[str, Any]:
    return {
        "bar_interval": value.get("bar_interval", value.get("expected_interval", "1h")),
        "funding_boundary_mode": value["funding_boundary_mode"],
        "mode": value.get("mode", value.get("parameters", {}).get("mode")),
        "parameters": value["parameters"],
        "required_input_kind": value.get("required_input_kind", REQUIRED_INPUT_KIND),
        "strategy_id": value["strategy_id"],
        "strategy_version": value["strategy_version"],
    }


def compute_variant_id(value: dict[str, Any]) -> str:
    return "variant_" + sha256_bytes(canonical_bytes(variant_identity_payload(value)))[:24]


def trial_identity_payload(
    *,
    variant_id: str,
    symbol: str,
    input_sha256: str,
    evaluation_start: str,
    evaluation_end: str,
    fee_bps: float,
    slippage_bps: float,
    gap_policy: str,
    expected_interval: str,
) -> dict[str, Any]:
    return {
        "evaluation_end": evaluation_end,
        "evaluation_start": evaluation_start,
        "expected_interval": expected_interval,
        "fee_bps": float(fee_bps),
        "gap_policy": gap_policy,
        "input_sha256": input_sha256,
        "slippage_bps": float(slippage_bps),
        "symbol": symbol,
        "variant_id": variant_id,
    }


def compute_trial_id(**kwargs: Any) -> str:
    return "trial_" + sha256_bytes(canonical_bytes(trial_identity_payload(**kwargs)))[:24]


def trial_identity_payload_v2(
    *,
    variant_id: str,
    instrument_contract_id: str,
    symbol: str,
    input_sha256: str,
    evaluation_start: str,
    evaluation_end: str,
    fee_bps: float,
    slippage_bps: float,
    funding_treatment: str,
    gap_policy: str,
    expected_interval: str,
    instrument_instance_id: str | None = None,
) -> dict[str, Any]:
    """V2 evaluation identity.

    Binds the instrument contract and the declared funding treatment in addition
    to the V1 fields, so the same strategy recipe evaluated on spot and on a
    perpetual yields two distinct trial IDs while keeping one ``variant_id``.
    ``instrument_instance_id`` carries exact instrument identity where the
    source provides it, and is omitted from the payload when unavailable so its
    absence cannot be confused with a declared null.
    """
    payload = {
        "evaluation_end": evaluation_end,
        "evaluation_start": evaluation_start,
        "expected_interval": expected_interval,
        "fee_bps": float(fee_bps),
        "funding_treatment": funding_treatment,
        "gap_policy": gap_policy,
        "input_sha256": input_sha256,
        "instrument_contract_id": instrument_contract_id,
        "slippage_bps": float(slippage_bps),
        "symbol": symbol,
        "trial_identity_version": 2,
        "variant_id": variant_id,
    }
    if instrument_instance_id:
        payload["instrument_instance_id"] = instrument_instance_id
    return payload


def compute_trial_id_v2(**kwargs: Any) -> str:
    return "trial_" + sha256_bytes(canonical_bytes(trial_identity_payload_v2(**kwargs)))[:24]


def trial_stream_path(recorded_at_utc: str, root: Path = RESEARCH_ROOT) -> Path:
    if len(recorded_at_utc) < 4 or not recorded_at_utc[:4].isdigit():
        raise LedgerError("recorded_at_utc must start with a year")
    return root / "trials" / f"{recorded_at_utc[:4]}.jsonl"


def _require_keys(event: dict[str, Any], expected: set[str], kind: str, optional: set[str] | None = None) -> None:
    extra = set(event) - expected - (optional or set())
    missing = expected - set(event)
    if extra:
        raise LedgerError(f"unknown event keys for {kind}: {sorted(extra)}")
    if missing:
        raise LedgerError(f"missing event keys for {kind}: {sorted(missing)}")


def _require_non_empty_string(event: dict[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if not isinstance(event.get(key), str) or not event[key].strip():
            raise LedgerError(f"{key} must be a non-empty string")


def _validate_registered_denominator(event: dict[str, Any]) -> None:
    """Registered-screen multiplicity fields, when a generation freezes them.

    Both fields are declared together or not at all: a denominator without a
    screen ID is an unattributable number, and a screen ID without a denominator
    cannot support a multiplicity claim.
    """
    screen_id = event.get("registered_screen_id")
    denominator = event.get("registered_variant_denominator")
    if screen_id is None and denominator is None:
        return
    if not isinstance(screen_id, str) or not screen_id.strip():
        raise LedgerError("registered_screen_id must be a non-empty string when a denominator is declared")
    if not isinstance(denominator, int) or isinstance(denominator, bool) or denominator < 1:
        raise LedgerError("registered_variant_denominator must be a positive integer")


def validate_candidate_event(event: dict[str, Any]) -> None:
    event_type = event.get("event_type")
    if event_type == "CANDIDATE_PROPOSED":
        _require_keys(event, CANDIDATE_PROPOSED_KEYS, event_type, optional=CANDIDATE_OPTIONAL_KEYS)
        _validate_registered_denominator(event)
        _require_non_empty_string(
            event,
            (
                "event_id",
                "candidate_id",
                "family_id",
                "variant_id",
                "strategy_id",
                "strategy_version",
                "mode",
                "bar_interval",
                "required_input_kind",
                "funding_boundary_mode",
                "recorded_at_utc",
            ),
        )
        if not isinstance(event["parameters"], dict):
            raise LedgerError("parameters must be an object")
        if event["variant_id"] != compute_variant_id(event):
            raise LedgerError(f"variant_id mismatch: {event['event_id']}")
    elif event_type == "CANDIDATE_REOPENED":
        _require_keys(event, CANDIDATE_REOPENED_KEYS, event_type)
        _require_non_empty_string(event, ("event_id", "candidate_id", "variant_id", "previous_decision_event_id", "recorded_at_utc"))
        if not isinstance(event["reason"], str) or len(event["reason"].strip()) < 12:
            raise LedgerError("reopen reason must be concrete and non-empty")
        if not isinstance(event["material_change"], str) or not event["material_change"].strip():
            raise LedgerError("material_change must be a non-empty string")
    else:
        raise LedgerError(f"unsupported candidate event_type: {event_type!r}")


def validate_decision_event(event: dict[str, Any]) -> None:
    if event.get("event_type") != "DECISION_RECORDED":
        raise LedgerError(f"unsupported decision event_type: {event.get('event_type')!r}")
    _require_keys(event, DECISION_KEYS, "DECISION_RECORDED", optional=DECISION_OPTIONAL_KEYS)
    _validate_registered_denominator(event)
    _require_non_empty_string(event, ("event_id", "candidate_id", "family_id", "variant_id", "status", "scope", "recorded_at_utc"))
    if event["status"] not in DECISION_STATUSES:
        raise LedgerError(f"unsupported decision status: {event['status']!r}")
    if event["scope"] not in SCOPES:
        raise LedgerError(f"unsupported decision scope: {event['scope']!r}")
    if event["status"] == "GRAVEYARDED" and event["scope"] != "EXACT_VARIANT" and event["scope"] != "FAMILY":
        raise LedgerError("invalid graveyard scope")
    if not isinstance(event["reason_codes"], list) or not all(isinstance(item, str) for item in event["reason_codes"]):
        raise LedgerError("reason_codes must be a list of strings")
    if not isinstance(event["evidence_paths"], list) or not all(isinstance(item, str) for item in event["evidence_paths"]):
        raise LedgerError("evidence_paths must be a list of strings")
    if not isinstance(event["evidence_sha256"], dict):
        raise LedgerError("evidence_sha256 must be an object")


def validate_trial_event(event: dict[str, Any]) -> None:
    if event.get("event_type") != "TRIAL_COMPLETED":
        raise LedgerError(f"unsupported trial event_type: {event.get('event_type')!r}")
    _require_keys(event, TRIAL_KEYS, "TRIAL_COMPLETED", optional=TRIAL_OPTIONAL_KEYS)
    _require_non_empty_string(
        event,
        (
            "event_id",
            "recorded_at_utc",
            "candidate_id",
            "family_id",
            "variant_id",
            "trial_id",
            "research_intent",
            "symbol",
            "evaluation_start",
            "evaluation_end",
            "input_sha256",
            "repository_commit",
            "relevant_source_sha256",
            "gap_policy",
            "expected_interval",
            "receipt_path",
            "receipt_sha256",
        ),
    )
    if event["research_intent"] not in RESEARCH_INTENTS:
        raise LedgerError(f"unsupported research_intent: {event['research_intent']!r}")
    if not isinstance(event["compact_metrics"], dict) or set(event["compact_metrics"]) - COMPACT_METRIC_KEYS:
        raise LedgerError("compact_metrics has unknown keys")
    _validate_trial_v2_fields(event)
    if "instrument_contract_id" in event:
        # V2 evaluation identity: instrument contract and funding treatment bind.
        expected_trial_id = compute_trial_id_v2(
            variant_id=event["variant_id"],
            instrument_contract_id=event["instrument_contract_id"],
            symbol=event["symbol"],
            input_sha256=event["input_sha256"],
            evaluation_start=event["evaluation_start"],
            evaluation_end=event["evaluation_end"],
            fee_bps=float(event["fee_bps"]),
            slippage_bps=float(event["slippage_bps"]),
            funding_treatment=event["funding_treatment"],
            gap_policy=event["gap_policy"],
            expected_interval=event["expected_interval"],
        )
    else:
        # V1 historical identity, preserved byte-for-byte.  No historical hash is
        # ever recomputed under the V2 payload.
        expected_trial_id = compute_trial_id(
            variant_id=event["variant_id"],
            symbol=event["symbol"],
            input_sha256=event["input_sha256"],
            evaluation_start=event["evaluation_start"],
            evaluation_end=event["evaluation_end"],
            fee_bps=float(event["fee_bps"]),
            slippage_bps=float(event["slippage_bps"]),
            gap_policy=event["gap_policy"],
            expected_interval=event["expected_interval"],
        )
    if event["trial_id"] != expected_trial_id:
        raise LedgerError(f"trial_id mismatch: {event['event_id']}")


def _validate_trial_v2_fields(event: dict[str, Any]) -> None:
    """Validate the optional V2 seam fields when a trial declares them."""
    from qntylab import family_ontology, instrument_contract

    has_contract = "instrument_contract_id" in event
    if not has_contract:
        # A V1-shaped event must not carry V2 fields that depend on the contract,
        # otherwise an event could claim bar-path evidence under an undeclared
        # instrument.
        stray = sorted(set(event) & (TRIAL_OPTIONAL_KEYS - {"period_id", "cost_mode", "canonical_family_id"}))
        if stray:
            raise LedgerError(f"V2 trial fields require instrument_contract_id: {stray}")
        return

    _require_non_empty_string(event, ("instrument_contract_id", "funding_treatment", "research_generation"))
    try:
        expected_digest = instrument_contract.contract_digest(event["instrument_contract_id"])
    except instrument_contract.InstrumentContractError as exc:
        raise LedgerError(str(exc)) from exc
    if event.get("instrument_contract_digest") != expected_digest:
        raise LedgerError(f"instrument_contract_digest mismatch: {event['event_id']}")
    if event["funding_treatment"] not in instrument_contract.FUNDING_TREATMENTS:
        raise LedgerError(f"unknown funding_treatment: {event['funding_treatment']!r}")
    if event["funding_treatment"] == instrument_contract.TRIAL_BLOCKED_BY_FUNDING_EVIDENCE:
        raise LedgerError("TRIAL_BLOCKED_BY_FUNDING_EVIDENCE cannot accompany a completed trial")
    exposure = event.get("compact_metrics", {}).get("exposure_fraction")
    try:
        instrument_contract.validate_funding_treatment(
            instrument_contract_id=event["instrument_contract_id"],
            funding_treatment=event["funding_treatment"],
            has_position_exposure=bool(exposure) and float(exposure) > 0.0,
        )
    except instrument_contract.InstrumentContractError as exc:
        raise LedgerError(str(exc)) from exc
    if event["research_generation"] not in RESEARCH_GENERATIONS:
        raise LedgerError(f"unsupported research_generation: {event['research_generation']!r}")
    if "canonical_family_id" in event:
        try:
            resolved = family_ontology.resolve_family(event["family_id"])
        except family_ontology.FamilyOntologyError as exc:
            raise LedgerError(str(exc)) from exc
        if event["canonical_family_id"] != resolved:
            raise LedgerError(f"canonical_family_id does not resolve from family_id: {event['event_id']}")
    if event["research_generation"] == CORPUS_GENERATION_V2:
        for key in ("bar_path_sha256", "bar_path_schema_version", "bar_path_row_count"):
            if not event.get(key):
                raise LedgerError(f"{CORPUS_GENERATION_V2} requires {key}")
        if not isinstance(event["bar_path_row_count"], int) or event["bar_path_row_count"] < 1:
            raise LedgerError("bar_path_row_count must be a positive integer")
        if event["bar_path_row_count"] != event["compact_metrics"].get("observation_count"):
            raise LedgerError("bar_path_row_count must equal observation_count")
    denominator = event.get("registered_variant_denominator")
    if denominator is not None and (not isinstance(denominator, int) or denominator < 1):
        raise LedgerError("registered_variant_denominator must be a positive integer when present")


def _read_jsonl(path: Path, validator: Any) -> list[dict[str, Any]]:
    if not path.exists():
        raise LedgerError(f"canonical history missing: {path}")
    events: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError as exc:
            raise LedgerError(f"canonical history malformed at {path}:{line_number}: {exc}") from exc
        if not isinstance(event, dict):
            raise LedgerError(f"event must be an object at {path}:{line_number}")
        try:
            validator(event)
        except LedgerError as exc:
            raise LedgerError(f"canonical event invalid at {path}:{line_number}: {exc}") from exc
        events.append(event)
    return events


def _trial_files(root: Path) -> list[Path]:
    directory = root / "trials"
    if not directory.exists():
        raise LedgerError(f"canonical history missing: {directory}")
    return sorted(directory.glob("*.jsonl"))


def load_canonical_history(root: Path = RESEARCH_ROOT) -> CanonicalHistory:
    candidates_path = root / "candidates.jsonl"
    decisions_path = root / "decisions.jsonl"
    candidates = _read_jsonl(candidates_path, validate_candidate_event)
    decisions = _read_jsonl(decisions_path, validate_decision_event)
    trials: list[dict[str, Any]] = []
    trial_hashes: dict[str, str] = {}
    for path in _trial_files(root):
        file_events = _read_jsonl(path, validate_trial_event)
        for event in file_events:
            if trial_stream_path(event["recorded_at_utc"], root) != path:
                raise LedgerError(f"trial event in wrong yearly stream: {event['event_id']}")
        trials.extend(file_events)
        trial_hashes[str(path.relative_to(root))] = sha256_path(path)
    return CanonicalHistory(
        tuple(candidates),
        tuple(decisions),
        tuple(trials),
        {
            "candidates_sha256": sha256_path(candidates_path),
            "decisions_sha256": sha256_path(decisions_path),
            "trial_files": trial_hashes,
        },
    )


def replay(history: CanonicalHistory, *, verify_evidence: bool = False, root: Path = RESEARCH_ROOT) -> tuple[dict[str, Any], dict[str, Any], list[str]]:
    issues: list[str] = []
    seen_events: set[str] = set()
    candidate_ids: set[str] = set()
    proposals: dict[str, dict[str, Any]] = {}
    reopen_by_decision: set[str] = set()
    variants: dict[str, dict[str, Any]] = {}
    trial_index = {"schema_version": INDEX_SCHEMA_VERSION, "trials": {}}

    for event in history.candidates:
        if event["event_id"] in seen_events:
            issues.append(f"duplicate event_id: {event['event_id']}")
        seen_events.add(event["event_id"])
        if event["event_type"] == "CANDIDATE_PROPOSED":
            if event["candidate_id"] in candidate_ids:
                issues.append(f"duplicate candidate proposal ID: {event['candidate_id']}")
            candidate_ids.add(event["candidate_id"])
            if event["variant_id"] in proposals:
                issues.append(f"duplicate variant proposal: {event['variant_id']}")
            proposals[event["variant_id"]] = event
            variants[event["variant_id"]] = {
                "candidate_id": event["candidate_id"],
                "family_id": event["family_id"],
                "status": "PROPOSED",
                "candidate_event_id": event["event_id"],
                "latest_decision_event_id": None,
                "revisit_condition": "",
            }
        else:
            proposal = proposals.get(event["variant_id"])
            if not proposal or proposal["candidate_id"] != event["candidate_id"]:
                issues.append(f"reopen before matching proposal: {event['event_id']}")
            reopen_by_decision.add(event["previous_decision_event_id"])

    for event in history.decisions:
        if event["event_id"] in seen_events:
            issues.append(f"duplicate event_id: {event['event_id']}")
        seen_events.add(event["event_id"])
        proposal = proposals.get(event["variant_id"])
        if proposal is None:
            issues.append(f"decision before proposal: {event['event_id']}")
            continue
        if proposal["candidate_id"] != event["candidate_id"] or proposal["family_id"] != event["family_id"]:
            issues.append(f"decision identity mismatch: {event['event_id']}")
        if verify_evidence:
            for evidence_path in event["evidence_paths"]:
                expected = event["evidence_sha256"].get(evidence_path)
                actual_path = root.parent.parent / evidence_path if not Path(evidence_path).is_absolute() else Path(evidence_path)
                if expected is None:
                    issues.append(f"evidence hash missing: {event['event_id']} {evidence_path}")
                elif not actual_path.exists():
                    issues.append(f"evidence path missing: {event['event_id']} {evidence_path}")
                elif sha256_path(actual_path) != expected:
                    issues.append(f"evidence hash mismatch: {event['event_id']} {evidence_path}")
        target_variants = [event["variant_id"]]
        if event["scope"] == "FAMILY":
            target_variants = [variant_id for variant_id, proposal_event in proposals.items() if proposal_event["family_id"] == event["family_id"]]
        for variant_id in sorted(target_variants):
            variants[variant_id]["status"] = event["status"]
            variants[variant_id]["latest_decision_event_id"] = event["event_id"]
            variants[variant_id]["revisit_condition"] = event["revisit_condition"]

    for event in history.candidates:
        if event["event_type"] != "CANDIDATE_REOPENED":
            continue
        variant = variants.get(event["variant_id"])
        if not variant:
            continue
        if variant["latest_decision_event_id"] != event["previous_decision_event_id"]:
            issues.append(f"reopen does not target latest decision: {event['event_id']}")
            continue
        if variant["status"] not in {"GRAVEYARDED", "BLOCKED"}:
            issues.append(f"reopen targets non-terminal status: {event['event_id']}")
            continue
        variant["status"] = "PROPOSED"
        variant["latest_decision_event_id"] = None

    for event in history.trials:
        if event["event_id"] in seen_events:
            issues.append(f"duplicate event_id: {event['event_id']}")
        seen_events.add(event["event_id"])
        if event["variant_id"] not in proposals:
            issues.append(f"trial before proposal: {event['event_id']}")
        prior_trial = trial_index["trials"].get(event["trial_id"])
        if prior_trial and event["research_intent"] != "REPLICATION":
            issues.append(f"duplicate trial_id without REPLICATION: {event['trial_id']}")
        elif not prior_trial:
            trial_index["trials"][event["trial_id"]] = {
                "variant_id": event["variant_id"],
                "receipt_path": event["receipt_path"],
                "receipt_sha256": event["receipt_sha256"],
                "completion_event_id": event["event_id"],
            }
        else:
            prior_trial.setdefault("replication_event_ids", []).append(event["event_id"])
        variant = variants.get(event["variant_id"])
        if variant and variant["status"] == "PROPOSED":
            variant["status"] = "SCREENING"

    state = {"schema_version": INDEX_SCHEMA_VERSION, "generated_from": history.generated_from, "variants": variants}
    trial_index["generated_from"] = history.generated_from
    return state, trial_index, issues


def rebuild(root: Path = RESEARCH_ROOT) -> tuple[dict[str, Any], dict[str, Any]]:
    history = load_canonical_history(root)
    state, trial_index, issues = replay(history, verify_evidence=True, root=root)
    if issues:
        raise LedgerError("; ".join(issues))
    _write_json(root / "state.json", state)
    _write_json(root / "trial_index.json", trial_index)
    return state, trial_index


def doctor(root: Path = RESEARCH_ROOT) -> list[str]:
    try:
        history = load_canonical_history(root)
        expected_state, expected_trial_index, issues = replay(history, verify_evidence=True, root=root)
    except LedgerError as exc:
        return [str(exc)]
    try:
        actual_state = _read_json(root / "state.json")
        if actual_state != expected_state:
            issues.append("stale or divergent state.json")
    except LedgerError as exc:
        issues.append(str(exc))
    try:
        actual_trial_index = _read_json(root / "trial_index.json")
        if actual_trial_index != expected_trial_index:
            issues.append("stale or divergent trial_index.json")
    except LedgerError as exc:
        issues.append(str(exc))
    return issues


def verify_indexes_current(root: Path = RESEARCH_ROOT) -> tuple[dict[str, Any], dict[str, Any], str]:
    state = _read_json(root / "state.json")
    trial_index = _read_json(root / "trial_index.json")
    if state.get("schema_version") != INDEX_SCHEMA_VERSION or trial_index.get("schema_version") != INDEX_SCHEMA_VERSION:
        raise LedgerError("index schema mismatch")
    if state.get("generated_from") != trial_index.get("generated_from"):
        raise LedgerError("indexes inconsistent")
    generated_from = state.get("generated_from")
    if not isinstance(generated_from, dict):
        raise LedgerError("state generated_from missing")
    expected = {
        "candidates_sha256": sha256_path(root / "candidates.jsonl"),
        "decisions_sha256": sha256_path(root / "decisions.jsonl"),
        "trial_files": {str(path.relative_to(root)): sha256_path(path) for path in _trial_files(root)},
    }
    if generated_from != expected:
        raise LedgerError("indexes stale")
    if not isinstance(state.get("variants"), dict) or not isinstance(trial_index.get("trials"), dict):
        raise LedgerError("indexes malformed")
    ledger_sha = sha256_bytes(canonical_bytes({"state": state["generated_from"], "trial_index": trial_index["generated_from"]}))
    return state, trial_index, ledger_sha


def preflight(
    *,
    config: dict[str, Any],
    symbol: str,
    input_sha256: str,
    root: Path = RESEARCH_ROOT,
) -> dict[str, Any]:
    state, trial_index, ledger_sha = verify_indexes_current(root)
    variant_id = compute_variant_id(config)
    if config.get("variant_id") is not None and config["variant_id"] != variant_id:
        raise LedgerError("variant identity mismatch")
    variant = state["variants"].get(variant_id)
    if variant is None:
        raise LedgerError(f"variant unregistered: {variant_id}")
    if config.get("candidate_id") != variant["candidate_id"]:
        raise LedgerError("variant identity mismatch")
    status = variant["status"]
    if status == "BLOCKED":
        raise LedgerError("latest variant state BLOCKED")
    if status == "GRAVEYARDED":
        raise LedgerError("latest variant state GRAVEYARDED")
    if status not in RUNNABLE_STATUSES:
        raise LedgerError(f"unsupported variant state {status}")
    instrument_contract_id = config.get("instrument_contract_id")
    if instrument_contract_id:
        from qntylab import family_ontology, instrument_contract as contracts

        funding_treatment = config.get("funding_treatment")
        if not isinstance(funding_treatment, str) or not funding_treatment.strip():
            raise LedgerError("funding_treatment is required when instrument_contract_id is declared")
        if funding_treatment == contracts.TRIAL_BLOCKED_BY_FUNDING_EVIDENCE:
            raise LedgerError("TRIAL_BLOCKED_BY_FUNDING_EVIDENCE: refusing to run a funding-blocked trial")
        try:
            contract_digest = contracts.contract_digest(instrument_contract_id)
        except contracts.InstrumentContractError as exc:
            raise LedgerError(str(exc)) from exc
        trial_id = compute_trial_id_v2(
            variant_id=variant_id,
            instrument_contract_id=instrument_contract_id,
            symbol=symbol,
            input_sha256=input_sha256,
            evaluation_start=config["evaluation_start"],
            evaluation_end=config["evaluation_end"],
            fee_bps=float(config["fee_bps"]),
            slippage_bps=float(config["slippage_bps"]),
            funding_treatment=funding_treatment,
            gap_policy=config["gap_policy"],
            expected_interval=config["expected_interval"],
        )
        canonical_family_id = family_ontology.resolve_family(variant["family_id"])
    else:
        funding_treatment = None
        contract_digest = None
        canonical_family_id = None
        trial_id = compute_trial_id(
            variant_id=variant_id,
            symbol=symbol,
            input_sha256=input_sha256,
            evaluation_start=config["evaluation_start"],
            evaluation_end=config["evaluation_end"],
            fee_bps=float(config["fee_bps"]),
            slippage_bps=float(config["slippage_bps"]),
            gap_policy=config["gap_policy"],
            expected_interval=config["expected_interval"],
        )
    if trial_id in trial_index["trials"] and config.get("research_intent") != "REPLICATION":
        raise LedgerError("exact trial already completed")
    return {
        "candidate_event_id": variant["candidate_event_id"],
        "candidate_id": variant["candidate_id"],
        "canonical_family_id": canonical_family_id,
        "family_id": variant["family_id"],
        "funding_treatment": funding_treatment,
        "instrument_contract_digest": contract_digest,
        "instrument_contract_id": instrument_contract_id,
        "latest_decision_event_id": variant["latest_decision_event_id"],
        "ledger_sha256_before_run": ledger_sha,
        "research_intent": config.get("research_intent"),
        "status": status,
        "trial_id": trial_id,
        "variant_id": variant_id,
    }


def compact_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    return {key: metrics[key] for key in sorted(COMPACT_METRIC_KEYS) if key in metrics}


def build_trial_completed_event(
    *,
    receipt: dict[str, Any],
    receipt_path: Path,
    receipt_sha256: str,
    metrics: dict[str, Any],
    recorded_at_utc: str | None = None,
) -> dict[str, Any]:
    event = {
        "event_id": "",
        "event_type": "TRIAL_COMPLETED",
        "recorded_at_utc": recorded_at_utc or utc_now(),
        "candidate_id": receipt["candidate_id"],
        "family_id": receipt["family_id"],
        "variant_id": receipt["variant_id"],
        "trial_id": receipt["trial_id"],
        "research_intent": receipt["research_intent"],
        "symbol": receipt["symbol"],
        "evaluation_start": receipt["evaluation_range"]["start"],
        "evaluation_end": receipt["evaluation_range"]["end"],
        "input_sha256": receipt["input_sha256"],
        "repository_commit": receipt["repository_commit"],
        "relevant_source_sha256": receipt["relevant_source_sha256"],
        "fee_bps": receipt["fee_assumption"]["fee_bps"],
        "slippage_bps": receipt["slippage_assumption"]["slippage_bps"],
        "gap_policy": receipt["gap_policy"],
        "expected_interval": receipt["expected_interval"],
        "receipt_path": str(receipt_path),
        "receipt_sha256": receipt_sha256,
        "compact_metrics": compact_metrics(metrics),
    }
    # V2 seam fields are copied from the receipt only when the receipt natively
    # declares an instrument contract.  A V1-shaped receipt produces a
    # V1-shaped event, unchanged.
    if receipt.get("instrument_contract_id"):
        for key in sorted(TRIAL_OPTIONAL_KEYS):
            value = receipt.get(key)
            if value is not None:
                event[key] = value
    event["event_id"] = event_id("event_trial", event)
    return event


@contextlib.contextmanager
def ledger_lock(root: Path = RESEARCH_ROOT):
    lock = root / ".research_ledger.lock"
    root.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as exc:
        raise LedgerError(f"research ledger lock exists: {lock}") from exc
    try:
        os.write(fd, str(os.getpid()).encode("ascii"))
        os.fsync(fd)
        os.close(fd)
        yield
    finally:
        with contextlib.suppress(FileNotFoundError):
            lock.unlink()


def _append_line(path: Path, event: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("ab") as out:
        out.write(canonical_bytes(event) + b"\n")
        out.flush()
        os.fsync(out.fileno())


def append_canonical_event(event: dict[str, Any], root: Path = RESEARCH_ROOT) -> None:
    event_type = event.get("event_type")
    if event_type in {"CANDIDATE_PROPOSED", "CANDIDATE_REOPENED"}:
        validate_candidate_event(event)
        path = root / "candidates.jsonl"
    elif event_type == "DECISION_RECORDED":
        validate_decision_event(event)
        path = root / "decisions.jsonl"
    elif event_type == "TRIAL_COMPLETED":
        validate_trial_event(event)
        path = trial_stream_path(event["recorded_at_utc"], root)
    else:
        raise LedgerError(f"unsupported event_type: {event_type!r}")
    with ledger_lock(root):
        existing_ids = {item["event_id"] for item in load_canonical_history(root).candidates + load_canonical_history(root).decisions + load_canonical_history(root).trials}
        if event["event_id"] in existing_ids:
            raise LedgerError(f"duplicate event_id: {event['event_id']}")
        _append_line(path, event)
        rebuild(root)
        issues = doctor(root)
        if issues:
            raise LedgerError("; ".join(issues))


def _load_event_file(path: Path, event_type: str) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise LedgerError("event file must contain a JSON object")
    value.setdefault("event_type", event_type)
    value.setdefault("recorded_at_utc", utc_now())
    if event_type == "DECISION_RECORDED":
        value.setdefault("scope", "EXACT_VARIANT")
    value.setdefault("event_id", event_id("event", value))
    return value


def context_text(root: Path = RESEARCH_ROOT, *, recent_limit: int = 10) -> str:
    state, trial_index, _ = verify_indexes_current(root)
    variants = state["variants"]
    trials = trial_index["trials"]
    history = load_canonical_history(root)
    by_status: dict[str, list[str]] = {status: [] for status in ("SURVIVOR", "FOLLOW_UP", "BLOCKED")}
    for variant_id, row in sorted(variants.items(), key=lambda item: item[1]["candidate_id"]):
        if row["status"] in by_status:
            by_status[row["status"]].append(f"{row['candidate_id']} {variant_id}")
    recent_graveyards = [
        f"{event['candidate_id']} {event['variant_id']} {','.join(event['reason_codes'])}"
        for event in history.decisions
        if event["status"] == "GRAVEYARDED"
    ][-recent_limit:]
    recent_trials = [
        f"{event['trial_id']} {event['candidate_id']} {event['symbol']} {event['evaluation_start']}..{event['evaluation_end']} {event['research_intent']}"
        for event in history.trials[-recent_limit:]
    ]
    family_warnings = [
        f"{event['family_id']} {event['status']} {event['decision_note']}"
        for event in history.decisions
        if event["scope"] == "FAMILY"
    ][-recent_limit:]
    revisits = [
        f"{row['candidate_id']}: {row['revisit_condition']}"
        for row in sorted(variants.values(), key=lambda item: item["candidate_id"])
        if row.get("revisit_condition")
    ][:recent_limit]
    sections = [
        ("active survivors", by_status["SURVIVOR"]),
        ("follow-up candidates", by_status["FOLLOW_UP"]),
        ("blocked variants", by_status["BLOCKED"]),
        ("recent graveyard decisions", recent_graveyards),
        ("recent completed trials", recent_trials),
        ("family-level warnings", family_warnings),
        ("revisit conditions", revisits),
    ]
    lines = [
        "QntyLab research context",
        f"total candidate variants: {len(variants)}",
        f"total completed trials: {len(trials)}",
    ]
    for title, values in sections:
        lines.append(f"{title}:")
        lines.extend(f"- {value}" for value in values) if values else lines.append("- none")
    return "\n".join(lines)


def show_family(root: Path, family_id: str) -> str:
    state, _, _ = verify_indexes_current(root)
    rows = [f"{variant_id} {row['candidate_id']} {row['status']}" for variant_id, row in sorted(state["variants"].items()) if row["family_id"] == family_id]
    if not rows:
        raise LedgerError(f"unknown family: {family_id}")
    return "\n".join(rows)


def show_variant(root: Path, variant_id: str) -> str:
    state, _, _ = verify_indexes_current(root)
    row = state["variants"].get(variant_id)
    if not row:
        raise LedgerError(f"unknown variant: {variant_id}")
    return "\n".join(f"{key}: {row[key]}" for key in sorted(row))


def recent(root: Path, limit: int) -> str:
    history = load_canonical_history(root)
    events = list(history.candidates + history.decisions + history.trials)
    events.sort(key=lambda event: (event["recorded_at_utc"], event["event_id"]))
    return "\n".join(f"{event['recorded_at_utc']} {event['event_type']} {event['event_id']}" for event in events[-limit:])


def graveyard(root: Path, reason: str) -> str:
    history = load_canonical_history(root)
    rows = [
        f"{event['candidate_id']} {event['variant_id']} {event['decision_note']}"
        for event in history.decisions
        if event["status"] == "GRAVEYARDED" and reason in event["reason_codes"]
    ]
    return "\n".join(rows)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="QntyLab append-only research ledger")
    parser.add_argument("--root", type=Path, default=RESEARCH_ROOT)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("context")
    sub.add_parser("rebuild")
    sub.add_parser("doctor")
    for name, event_type in (("propose", "CANDIDATE_PROPOSED"), ("decide", "DECISION_RECORDED"), ("reopen", "CANDIDATE_REOPENED")):
        command = sub.add_parser(name)
        command.add_argument("--event", required=True, type=Path)
        command.set_defaults(event_type=event_type)
    family = sub.add_parser("show-family")
    family.add_argument("family_id")
    variant = sub.add_parser("show-variant")
    variant.add_argument("variant_id")
    recent_cmd = sub.add_parser("recent")
    recent_cmd.add_argument("--limit", type=int, default=20)
    graveyard_cmd = sub.add_parser("graveyard")
    graveyard_cmd.add_argument("--reason", required=True)
    return parser


def main(argv: list[str] | None = None) -> None:
    parser = _parser()
    args = parser.parse_args(argv)
    try:
        if args.cmd == "context":
            print(context_text(args.root))
        elif args.cmd == "rebuild":
            rebuild(args.root)
            print("indexes rebuilt")
        elif args.cmd == "doctor":
            issues = doctor(args.root)
            if issues:
                for issue in issues:
                    print(issue)
                raise SystemExit(1)
            print("ledger ok")
        elif args.cmd in {"propose", "decide", "reopen"}:
            event = _load_event_file(args.event, args.event_type)
            append_canonical_event(event, args.root)
            print(event["event_id"])
        elif args.cmd == "show-family":
            print(show_family(args.root, args.family_id))
        elif args.cmd == "show-variant":
            print(show_variant(args.root, args.variant_id))
        elif args.cmd == "recent":
            print(recent(args.root, args.limit))
        elif args.cmd == "graveyard":
            print(graveyard(args.root, args.reason))
    except (OSError, json.JSONDecodeError, LedgerError) as exc:
        print(f"research ledger error: {exc}", file=sys.stderr)
        raise SystemExit(2) from exc


if __name__ == "__main__":
    main()
