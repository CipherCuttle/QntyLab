"""Minimal, fail-closed operation seam for the frozen JH01 V1 recorder.

This module owns campaign activation state and due-origin ordering.  It does
not own the frozen models, source admission, release transport, or attestation
policy; those remain in the qualified recorder module and are injected here.
Synthetic qualification and future real prospective operation are distinct,
durably bound campaign modes.  No real source or publication client is
constructed by this module.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from enum import Enum
from hashlib import sha256
import inspect
import json
from pathlib import Path
import argparse
from typing import Any, Callable, Mapping, Sequence

from . import jh01_v1_prospective_recorder_implementation_v0 as recorder


AUTHORIZATION_PROJECT_ID = "JH01_V1_REAL_ACTIVATION_AND_FORWARD_RECORDER_IMPLEMENTATION_V0"
AUTHORIZATION_CANONICAL_MERGE = "4e0555c1af1d3653ba656740b81fdc7e8a134c6e"
AUTHORIZATION_PATH = Path(
    "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/"
    "real_activation_and_forward_recorder_implementation_authorization_v0.json"
)
REAL_OPERATION_AUTHORIZATION_PROJECT_ID = "JH01_V1_REAL_PROSPECTIVE_OPERATION_AUTHORIZATION_V0"
REAL_OPERATION_AUTHORIZATION_PATH = Path(
    "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/"
    "real_prospective_operation_authorization_v0.json"
)
PREREGISTRATION_DIGEST = "bdb85130cae75e9f156db9aa1fd955d7f565a3714ae091871d5ac4447c1ec27b"
QUALIFIED_RECORDER_MERGE = "b50e8e3cd17199265cb7040588d97822d45dd170"
QUALIFIED_RECORDER_CANDIDATE = "5dc86826040b9bd3403f03c31cfc8a64249ed907"
EXPECTED_RECORDER_SOURCE_DIGEST = "4f5e1791be9f17c1871f9b510329a1632412e028d2a84223fa59e83bbe95ec1a"
PERSISTENCE_MECHANISM = "GITHUB_IMMUTABLE_RELEASE_V0R3_QUALIFIED"
SOURCE_CONTRACT = "BINANCE_USD_M_PERPETUAL_1H_LOGICAL_CLOSE"
TARGET_STATE = "REAL_V1_ARMED_BUT_INACTIVE"


class OperationBlocked(ValueError):
    """The frozen activation or prospective-operation contract rejects a call."""


class OperationMode(str, Enum):
    SYNTHETIC_QUALIFICATION = "SYNTHETIC_QUALIFICATION"
    REAL_PROSPECTIVE = "REAL_PROSPECTIVE"


class CampaignState(str, Enum):
    UNARMED = "UNARMED"
    ACTIVATION_PREPARED = "ACTIVATION_PREPARED"
    ARMED_BUT_INACTIVE = "ARMED_BUT_INACTIVE"
    BLOCKED = "BLOCKED"


class DueState(str, Enum):
    NOT_DUE = "NOT_DUE"
    DUE = "DUE"
    BLOCKED_MISSED_WINDOW = "BLOCKED_MISSED_WINDOW"
    RECORDED = "RECORDED"
    CONFLICT = "CONFLICT"


def _stamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise OperationBlocked("UTC-aware timestamp required")
    value = value.astimezone(UTC)
    if value.minute or value.second or value.microsecond:
        raise OperationBlocked("hour-aligned timestamp required")
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def _instant(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise OperationBlocked("UTC-aware timestamp required")
    return parsed.astimezone(UTC)


def _timestamp(value: datetime) -> str:
    parsed = _instant(value)
    return parsed.isoformat().replace("+00:00", "Z")


def _digest(value: Any) -> str:
    return sha256(recorder.canonical_bytes(value)).hexdigest()


def implementation_identity() -> str:
    """Digest this wrapper separately from the qualified recorder digest."""
    return sha256(Path(inspect.getsourcefile(implementation_identity) or __file__).read_bytes()).hexdigest()


def required_origins() -> tuple[datetime, ...]:
    origins = recorder.required_origins()
    if len(origins) != 365 or origins[0] != recorder.FIRST_LIVE_ORIGIN or origins[-1] != recorder.LAST_LIVE_ORIGIN:
        raise OperationBlocked("frozen 365-origin schedule drift")
    if any(origin.tzinfo != UTC or origin.hour or origin.minute or origin.second or origin.microsecond for origin in origins):
        raise OperationBlocked("frozen schedule is not UTC midnight")
    if any(right - left != timedelta(days=1) for left, right in zip(origins, origins[1:])):
        raise OperationBlocked("frozen schedule is not daily")
    return origins


def schedule_digest(origins: Sequence[datetime] | None = None) -> str:
    values = tuple(origins or required_origins())
    if values != required_origins():
        raise OperationBlocked("schedule differs from frozen required origins")
    return _digest([_stamp(origin) for origin in values])


def _load_authorization(root: Path) -> dict[str, Any]:
    path = root / AUTHORIZATION_PATH
    try:
        document = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise OperationBlocked("canonical JH01 implementation authorization unavailable") from exc
    if (
        document.get("project_id") != AUTHORIZATION_PROJECT_ID
        or document.get("state") != "ACTIVE"
        or document.get("implementation_authorized") is not True
        or document.get("authority_level") != "SOURCE_BOUND_BOUNDED_REAL_OPERATION_SEAM_IMPLEMENTATION_ONLY"
    ):
        raise OperationBlocked("canonical JH01 implementation authority is not active")
    firewall = document.get("authority_firewall", {})
    forbidden = (
        "real_v1_collection_authorized", "real_market_data_authorized",
        "real_forecast_executed", "real_github_forecast_publication_authorized",
        "scientific_evaluation_authorized", "interim_metrics_authorized",
        "jigsaw_authorized", "state_snapshot_authorized", "router_authorized",
        "qnty_authorized", "trading_authorized",
    )
    if any(firewall.get(key) is not False for key in forbidden) or firewall.get("capital_authority") != "NONE":
        raise OperationBlocked("JH01 authority firewall drift")
    return document


def _validate_recorder_lineage(root: Path, authorization: Mapping[str, Any]) -> str:
    lineage = authorization.get("lineage", {})
    source_path = root / str(lineage.get("qualified_recorder_source_path", ""))
    if str(lineage.get("qualified_recorder_source_path")) != "qntylab/jh01_v1_prospective_recorder_implementation_v0.py":
        raise OperationBlocked("qualified recorder source path drift")
    if not source_path.is_file():
        raise OperationBlocked("qualified recorder source unavailable")
    source_digest = sha256(source_path.read_bytes()).hexdigest()
    expected = str(lineage.get("qualified_recorder_source_sha256", ""))
    if source_digest != expected or source_digest != EXPECTED_RECORDER_SOURCE_DIGEST:
        raise OperationBlocked("qualified recorder source bytes changed")
    if recorder.implementation_identity() != source_digest:
        raise OperationBlocked("qualified recorder implementation identity mismatch")
    if lineage.get("recorder_qualification_merge") != QUALIFIED_RECORDER_MERGE or lineage.get("qualified_implementation_candidate") != QUALIFIED_RECORDER_CANDIDATE:
        raise OperationBlocked("qualified recorder lineage drift")
    return source_digest


def _load_real_operation_authority(root: Path, *, fixture: Mapping[str, Any] | None = None) -> tuple[dict[str, Any], str]:
    """Load the separate future real-operation authority, or fail closed.

    ``fixture`` is an explicit test-only seam used by synthetic tests.  The
    production path always reads the canonical future authority pathname; the
    implementation authorization above is never accepted as a substitute.
    """
    if fixture is None:
        path = root / REAL_OPERATION_AUTHORIZATION_PATH
        try:
            document = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            raise OperationBlocked("REAL_OPERATION_AUTHORITY_REQUIRED") from exc
    else:
        document = dict(fixture)
    if not isinstance(document, dict):
        raise OperationBlocked("malformed real-operation authority")
    required = {
        "project_id": REAL_OPERATION_AUTHORIZATION_PROJECT_ID,
        "state": "ACTIVE",
        "candidate_id": recorder.CANDIDATE_ID,
        "preregistration_digest": PREREGISTRATION_DIGEST,
        "qualified_recorder_identity": EXPECTED_RECORDER_SOURCE_DIGEST,
        "wrapper_implementation_identity": implementation_identity(),
        "first_live_origin": _stamp(recorder.FIRST_LIVE_ORIGIN),
        "last_live_origin": _stamp(recorder.LAST_LIVE_ORIGIN),
        "required_origin_count": 365,
        "schedule_digest": schedule_digest(),
        "ordered_panel_digest": "e6d1447ff2be57f81eaf943b62218ce9a7b9a6f5bf2d25f9be255cb3f2040cd8",
        "source_contract_identity": SOURCE_CONTRACT,
        "persistence_mechanism_identity": PERSISTENCE_MECHANISM,
        "attestation_policy_identity": "JH01_V1_GITHUB_RELEASE_SIGSTORE_V0R3",
    }
    if any(document.get(key) != value for key, value in required.items()):
        raise OperationBlocked("real-operation authority binding mismatch")
    if (
        document.get("real_v1_activation_authorized") is not True
        or document.get("forward_collection_authorized") is not True
        or document.get("scientific_evaluation_authorized") is not False
        or document.get("interim_metrics_authorized") is not False
        or document.get("downstream_authority") != "NONE"
    ):
        raise OperationBlocked("real-operation authority firewall mismatch")
    if document.get("implementation_canonical_lineage") != {
        "base_canonical_merge": AUTHORIZATION_CANONICAL_MERGE,
        "implementation_pr": 104,
    }:
        raise OperationBlocked("real-operation authority lineage mismatch")
    return document, _digest(document)


def build_activation_contract(
    root: Path,
    *,
    mode: OperationMode = OperationMode.SYNTHETIC_QUALIFICATION,
    real_authority: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build and validate one immutable campaign binding for one mode."""
    mode = OperationMode(mode)
    authorization = _load_authorization(root)
    recorder_digest = _validate_recorder_lineage(root, authorization)
    origins = required_origins()
    prereg = authorization["frozen_contract"]
    if authorization["lineage"].get("preregistration_digest") != PREREGISTRATION_DIGEST:
        raise OperationBlocked("preregistration digest drift")
    panel = tuple(prereg["ordered_panel"])
    if _digest(list(panel)) != str(prereg["ordered_panel_sha256"]):
        raise OperationBlocked("ordered panel digest drift")
    if (
        prereg.get("candidate_id") != recorder.CANDIDATE_ID
        or prereg.get("first_live_origin") != _stamp(origins[0])
        or prereg.get("last_live_origin") != _stamp(origins[-1])
        or prereg.get("required_valid_origins") != len(origins)
        or prereg.get("first_required_source_close") != "2025-08-15T00:00:00Z"
        or prereg.get("source_contract") != SOURCE_CONTRACT
        or prereg.get("persistence_backend") != PERSISTENCE_MECHANISM
    ):
        raise OperationBlocked("frozen JH01 contract drift")
    contract = {
        "project_id": AUTHORIZATION_PROJECT_ID,
        "candidate_id": recorder.CANDIDATE_ID,
        "preregistration_digest": PREREGISTRATION_DIGEST,
        "canonical_authorization_identity": {
            "project_id": AUTHORIZATION_PROJECT_ID,
            "canonical_merge": AUTHORIZATION_CANONICAL_MERGE,
            "document_sha256": sha256((root / AUTHORIZATION_PATH).read_bytes()).hexdigest(),
        },
        "qualified_recorder_implementation_identity": recorder_digest,
        "qualified_recorder_lineage": {
            "qualification_merge": QUALIFIED_RECORDER_MERGE,
            "qualified_implementation_candidate": QUALIFIED_RECORDER_CANDIDATE,
            "source_path": "qntylab/jh01_v1_prospective_recorder_implementation_v0.py",
            "source_sha256": recorder_digest,
        },
        "wrapper_implementation_identity": implementation_identity(),
        "first_live_origin": _stamp(origins[0]),
        "last_live_origin": _stamp(origins[-1]),
        "required_origin_count": len(origins),
        "schedule_digest": schedule_digest(origins),
        "ordered_panel_digest": str(prereg["ordered_panel_sha256"]),
        "source_contract_identity": SOURCE_CONTRACT,
        "first_required_source_close": "2025-08-15T00:00:00Z",
        "persistence_mechanism_identity": PERSISTENCE_MECHANISM,
        "attestation_policy_identity": "JH01_V1_GITHUB_RELEASE_SIGSTORE_V0R3",
        "target_state": TARGET_STATE,
        "operation_mode": mode.value,
        "real_operation_authorization_project_id": None,
        "real_operation_authorization_artifact_digest": None,
    }
    if mode is OperationMode.REAL_PROSPECTIVE:
        _, authority_digest = _load_real_operation_authority(root, fixture=real_authority)
        contract["real_operation_authorization_project_id"] = REAL_OPERATION_AUTHORIZATION_PROJECT_ID
        contract["real_operation_authorization_artifact_digest"] = authority_digest
    return {**contract, "activation_contract_digest": _digest(contract)}


def _validate_activation_contract(root: Path, contract: Mapping[str, Any]) -> None:
    expected = build_activation_contract(root)
    if dict(contract) != expected:
        raise OperationBlocked("activation contract identity mismatch")


class OperationLedger:
    """Append-only local event ledger for activation and operational receipts."""

    def __init__(self, root: Path, *, filename: str = "jh01_v1_operation_events.jsonl"):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self.path = self.root / filename

    def events(self) -> tuple[dict[str, Any], ...]:
        if not self.path.exists():
            return ()
        result: list[dict[str, Any]] = []
        for line in self.path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as exc:
                raise OperationBlocked("operation ledger is malformed") from exc
            if not isinstance(event, dict) or not isinstance(event.get("payload"), dict) or event.get("event_digest") != _digest({"event_type": event.get("event_type"), "payload": event.get("payload")}):
                raise OperationBlocked("operation ledger integrity failure")
            result.append(event)
        return tuple(result)

    def append(self, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        body = {"event_type": event_type, "payload": dict(payload)}
        event = {**body, "event_digest": _digest(body)}
        with self.path.open("ab") as handle:
            handle.write(recorder.canonical_bytes(event) + b"\n")
            handle.flush()
            import os
            os.fsync(handle.fileno())
        return event

    def activation(self) -> tuple[CampaignState, dict[str, Any] | None]:
        prepared = [event for event in self.events() if event["event_type"] == "ACTIVATION_PREPARED"]
        committed = [event for event in self.events() if event["event_type"] == "ACTIVATION_COMMITTED"]
        if len(prepared) > 1 or len(committed) > 1:
            raise OperationBlocked("multiple activation campaigns")
        if committed:
            if not prepared or committed[0]["payload"].get("activation_contract_digest") != prepared[0]["payload"].get("activation_contract_digest"):
                raise OperationBlocked("activation commit does not match preparation")
            return CampaignState.ARMED_BUT_INACTIVE, committed[0]["payload"]
        if prepared:
            return CampaignState.ACTIVATION_PREPARED, prepared[0]["payload"]
        return CampaignState.UNARMED, None

    def origin_events(self) -> tuple[dict[str, Any], ...]:
        return tuple(event for event in self.events() if event["event_type"] in {"ORIGIN_RECORDED", "ORIGIN_BLOCKED"})


def _origin_index(origin: datetime) -> int:
    values = required_origins()
    try:
        return values.index(origin)
    except ValueError as exc:
        raise OperationBlocked("origin is not a frozen required origin") from exc


def _event_for_origin(events: Sequence[Mapping[str, Any]], origin: datetime) -> Mapping[str, Any] | None:
    matches = [event for event in events if event.get("payload", {}).get("origin_utc") == _stamp(origin)]
    if len(matches) > 1:
        raise OperationBlocked("duplicate local origin receipt")
    return matches[0] if matches else None


def _recorded_digest(event: Mapping[str, Any] | None) -> str | None:
    return None if event is None else str(event.get("payload", {}).get("artifact_digest"))


def _validate_order(events: Sequence[Mapping[str, Any]]) -> None:
    origins = required_origins()
    indexes = sorted(_origin_index(_instant(event["payload"]["origin_utc"])) for event in events)
    if indexes != list(range(len(indexes))):
        raise OperationBlocked("origin order or replacement origin violation")
    for index, event in enumerate(sorted(events, key=lambda item: _origin_index(_instant(item["payload"]["origin_utc"])) )):
        expected = origins[index]
        if event["payload"].get("origin_utc") != _stamp(expected):
            raise OperationBlocked("origin does not match exact next required origin")


def due_state(ledger: OperationLedger, *, now: datetime) -> tuple[DueState, datetime | None]:
    now = _instant(now)
    campaign, _ = ledger.activation()
    if campaign is CampaignState.UNARMED:
        return DueState.NOT_DUE, None
    if campaign is CampaignState.ACTIVATION_PREPARED:
        raise OperationBlocked("activation is not committed")
    events = ledger.origin_events()
    _validate_order(events)
    origins = required_origins()
    blocked = next((event for event in events if event["event_type"] == "ORIGIN_BLOCKED"), None)
    if blocked is not None:
        return DueState.BLOCKED_MISSED_WINDOW, _instant(blocked["payload"]["origin_utc"])
    if len(events) >= len(origins):
        return DueState.RECORDED, None
    origin = origins[len(events)]
    existing = _event_for_origin(events, origin)
    if existing is not None:
        return (DueState.RECORDED if existing["event_type"] == "ORIGIN_RECORDED" else DueState.BLOCKED_MISSED_WINDOW), origin
    if now < origin:
        return DueState.NOT_DUE, origin
    if now < origin + timedelta(hours=1):
        return DueState.DUE, origin
    return DueState.BLOCKED_MISSED_WINDOW, origin


def _operational_artifact(root: Path, bars: Sequence[recorder.Bar], *, origin: datetime) -> dict[str, Any]:
    """Assemble the qualified artifact schema from qualified primitives.

    The qualified builder cannot accept a real frozen origin by design.  This
    wrapper therefore reuses its source validator, manifest, model function,
    frozen contract, canonical serializer, and identity functions, while only
    assembling the already-qualified artifact envelope.
    """
    contract = recorder.frozen_contract(root)
    preregistration = contract["preregistration"]
    repair = contract["repair"]
    panel = preregistration["frozen_target"]["ordered_20_symbol_panel"]
    first_required = _instant(repair["repair"]["repaired_first_required_source_close"])
    manifest = recorder.source_manifest(bars, panel=panel, origin=origin, first_required_close=first_required)
    models = recorder.compute_models(bars, panel=panel, origin=origin)
    artifact = {
        "project_id": recorder.PROJECT_ID,
        "experiment_id": recorder.EXPERIMENT_ID,
        "candidate_id": recorder.CANDIDATE_ID,
        "v1_preregistration_digest": preregistration["preregistration_digest"],
        "forecast_origin_utc": _stamp(origin),
        "ordered_20_symbol_panel": panel,
        "ordered_20_symbol_panel_digest": recorder.digest(panel),
        "target_horizon_identity": "RV24_FUTURE_24H",
        "source_provider_contract_identity": SOURCE_CONTRACT,
        "first_required_source_close": _stamp(first_required),
        "maximum_source_bar_close_utc": manifest["maximum_source_bar_close_utc"],
        "training_target_cutoff_exclusive_utc": _stamp(origin),
        "source_data_manifest_identity": manifest["source_data_manifest_sha256"],
        "source_data_manifest_sha256": manifest["source_data_manifest_sha256"],
        "model_implementation_identity_digest": recorder.implementation_identity(),
        "nonnegative_floor_application": "AFTER_FORECAST_MAX_0",
        "persistence_mechanism": PERSISTENCE_MECHANISM,
        "qualification_mode": False,
        **models,
    }
    return {**artifact, "forecast_artifact_canonical_digest": recorder.digest(artifact)}


def _release_metadata(release: recorder.RemoteRelease) -> dict[str, Any]:
    value = asdict(release)
    if value.get("published_at") is not None:
        value["published_at"] = value["published_at"].astimezone(UTC).isoformat().replace("+00:00", "Z")
    return value


OfflineReverify = Callable[[Path], None]


class Operation:
    """Campaign API with mechanically separated synthetic and real modes."""

    def __init__(self, root: Path, state_dir: Path, *, _test_real_authority: Mapping[str, Any] | None = None):
        self.root = root
        self.ledger = OperationLedger(state_dir)
        self.retention_dir = state_dir / "retention"
        self._test_real_authority = dict(_test_real_authority) if _test_real_authority is not None else None

    @classmethod
    def for_test_real_authority(cls, root: Path, state_dir: Path, authority: Mapping[str, Any]) -> "Operation":
        """Construct only a test fixture seam for a future authority document."""
        return cls(root, state_dir, _test_real_authority=authority)

    def _activate(self, *, mode: OperationMode, activation_time: datetime) -> dict[str, Any]:
        authority = self._test_real_authority if mode is OperationMode.REAL_PROSPECTIVE else None
        contract = build_activation_contract(self.root, mode=mode, real_authority=authority)
        state, existing = self.ledger.activation()
        if state is not CampaignState.UNARMED or existing is not None:
            raise OperationBlocked("second activation campaign rejected")
        activation_time = _instant(activation_time)
        if activation_time >= recorder.FIRST_LIVE_ORIGIN:
            raise OperationBlocked("activation cannot occur after first frozen origin")
        payload = {**contract, "activation_time_utc": activation_time.isoformat().replace("+00:00", "Z"), "activation_state": CampaignState.ACTIVATION_PREPARED.value}
        self.ledger.append("ACTIVATION_PREPARED", payload)
        committed = {**payload, "activation_state": CampaignState.ARMED_BUT_INACTIVE.value}
        self.ledger.append("ACTIVATION_COMMITTED", committed)
        return self.status(now=activation_time)

    def activate_synthetic(self, *, activation_time: datetime) -> dict[str, Any]:
        return self._activate(mode=OperationMode.SYNTHETIC_QUALIFICATION, activation_time=activation_time)

    def activate_real(self, *, activation_time: datetime) -> dict[str, Any]:
        return self._activate(mode=OperationMode.REAL_PROSPECTIVE, activation_time=activation_time)

    def _require_mode(self, mode: OperationMode) -> dict[str, Any]:
        campaign, activation = self.ledger.activation()
        if campaign is not CampaignState.ARMED_BUT_INACTIVE or activation is None:
            raise OperationBlocked("activation is not committed")
        if activation.get("operation_mode") != mode.value:
            if mode is OperationMode.REAL_PROSPECTIVE:
                raise OperationBlocked("REAL_OPERATION_AUTHORITY_REQUIRED")
            raise OperationBlocked("synthetic campaign cannot execute real-operation path")
        authority = self._test_real_authority if mode is OperationMode.REAL_PROSPECTIVE else None
        expected = build_activation_contract(self.root, mode=mode, real_authority=authority)
        for key, value in expected.items():
            if activation.get(key) != value:
                raise OperationBlocked("durable activation binding mismatch")
        return activation

    def status(self, *, now: datetime) -> dict[str, Any]:
        campaign, activation = self.ledger.activation()
        next_state, next_origin = due_state(self.ledger, now=now)
        events = self.ledger.origin_events()
        _validate_order(events)
        if any(event["event_type"] == "ORIGIN_BLOCKED" for event in events):
            campaign = CampaignState.BLOCKED
        recorded = [event for event in events if event["event_type"] == "ORIGIN_RECORDED"]
        blocked = [event for event in events if event["event_type"] == "ORIGIN_BLOCKED"]
        latest = events[-1]["payload"] if events else {}
        return {
            "campaign_state": campaign.value,
            "activation_present": activation is not None,
            "operation_mode": activation.get("operation_mode") if activation else None,
            "real_operation_authorization_project_id": activation.get("real_operation_authorization_project_id") if activation else None,
            "real_operation_authorization_artifact_digest": activation.get("real_operation_authorization_artifact_digest") if activation else None,
            "candidate_id": activation.get("candidate_id") if activation else recorder.CANDIDATE_ID,
            "preregistration_digest": activation.get("preregistration_digest") if activation else PREREGISTRATION_DIGEST,
            "wrapper_implementation_identity": activation.get("wrapper_implementation_identity") if activation else implementation_identity(),
            "qualified_recorder_identity": activation.get("qualified_recorder_implementation_identity") if activation else EXPECTED_RECORDER_SOURCE_DIGEST,
            "first_live_origin": _stamp(recorder.FIRST_LIVE_ORIGIN),
            "last_live_origin": _stamp(recorder.LAST_LIVE_ORIGIN),
            "required_origin_count": len(required_origins()),
            "next_required_origin": _stamp(next_origin) if next_origin else None,
            "next_origin_due_state": next_state.value,
            "completed_origin_count": len(recorded),
            "blocked_origin_count": len(blocked),
            "last_origin_state": latest.get("origin_state"),
            "last_publication_state": latest.get("publication_state"),
            "last_release_tag": latest.get("release_tag"),
            "last_attestation_state": latest.get("attestation_status"),
            "last_tsa_state": latest.get("tsa_status"),
            "last_offline_reverification_state": latest.get("offline_reverification_status"),
        }

    def _record_due(
        self,
        *,
        now: datetime,
        bars: Sequence[recorder.Bar],
        runtime: recorder.PublicationRuntime,
        target_commit: str,
        offline_reverify: OfflineReverify,
    ) -> dict[str, Any]:
        state, origin = due_state(self.ledger, now=now)
        if origin is None:
            raise OperationBlocked("no next required origin")
        existing = _event_for_origin(self.ledger.origin_events(), origin)
        if state is DueState.RECORDED and existing is not None and existing["event_type"] == "ORIGIN_RECORDED":
            artifact = _operational_artifact(self.root, bars, origin=origin)
            if _recorded_digest(existing) != artifact["forecast_artifact_canonical_digest"]:
                raise OperationBlocked("same origin different digest")
            return dict(existing["payload"], recovery="IDEMPOTENT_AUTHORITATIVE_RECOVERY")
        if state is DueState.NOT_DUE:
            return {"origin_state": DueState.NOT_DUE.value, "origin_utc": _stamp(origin)}
        if state is DueState.BLOCKED_MISSED_WINDOW:
            payload = {"origin_utc": _stamp(origin), "origin_index": _origin_index(origin), "origin_state": DueState.BLOCKED_MISSED_WINDOW.value, "reason": "persistence window missed", "prospective": False}
            if _event_for_origin(self.ledger.origin_events(), origin) is None:
                self.ledger.append("ORIGIN_BLOCKED", payload)
            return payload
        if state is not DueState.DUE:
            raise OperationBlocked(f"origin cannot be recorded in state {state.value}")
        if existing is not None:
            raise OperationBlocked("duplicate origin receipt")
        artifact = _operational_artifact(self.root, bars, origin=origin)
        states, release, verified = runtime.publish(artifact, origin=origin, target_commit=target_commit)
        package = self.retention_dir / f"{_origin_index(origin):03d}-{recorder.origin_identity(origin)[:24]}"
        if package.exists() and (package / "retention_manifest.json").exists():
            recorder.verify_retention_package(package)
            existing_forecast = json.loads((package / "forecast.json").read_text())
            if existing_forecast.get("forecast_artifact_canonical_digest") != artifact["forecast_artifact_canonical_digest"]:
                raise OperationBlocked("same origin retention package has different digest")
        else:
            recorder.retention_package(package, forecast=artifact, release_metadata=_release_metadata(release), bundle=verified.bundle, trusted_root=verified.trusted_root)
        recorder.verify_retention_package(package)
        if offline_reverify is None:
            raise OperationBlocked("offline re-verification required")
        offline_reverify(package)
        payload = {
            "origin_utc": _stamp(origin),
            "origin_index": _origin_index(origin),
            "origin_identity": recorder.origin_identity(origin),
            "origin_state": DueState.RECORDED.value,
            "publication_state": states[-1].value,
            "artifact_digest": artifact["forecast_artifact_canonical_digest"],
            "release_tag": release.tag,
            "persistence_timestamp": _timestamp(release.published_at),
            "attestation_status": "VERIFIED",
            "tsa_status": "VERIFIED",
            "offline_reverification_status": "VERIFIED",
            "retention_package": str(package.relative_to(self.ledger.root)),
            "prospective": True,
        }
        self.ledger.append("ORIGIN_RECORDED", payload)
        return payload

    def record_due(
        self,
        *,
        now: datetime,
        bars: Sequence[recorder.Bar],
        runtime: recorder.PublicationRuntime,
        target_commit: str,
        offline_reverify: OfflineReverify,
    ) -> dict[str, Any]:
        """Production-capable seam; only a validated real campaign may enter."""
        self._require_mode(OperationMode.REAL_PROSPECTIVE)
        return self._record_due(now=now, bars=bars, runtime=runtime, target_commit=target_commit, offline_reverify=offline_reverify)

    def record_due_synthetic(
        self,
        *,
        now: datetime,
        bars: Sequence[recorder.Bar],
        runtime: recorder.PublicationRuntime,
        target_commit: str,
        offline_reverify: OfflineReverify,
    ) -> dict[str, Any]:
        """Fixture-only seam; a synthetic campaign can never enter ``record_due``."""
        self._require_mode(OperationMode.SYNTHETIC_QUALIFICATION)
        return self._record_due(now=now, bars=bars, runtime=runtime, target_commit=target_commit, offline_reverify=offline_reverify)


def status(root: Path, state_dir: Path, *, now: datetime) -> dict[str, Any]:
    return Operation(root, state_dir).status(now=now)


__all__ = [
    "AUTHORIZATION_CANONICAL_MERGE", "AUTHORIZATION_PROJECT_ID", "CampaignState", "DueState", "OperationMode",
    "Operation", "OperationBlocked", "OperationLedger", "build_activation_contract",
    "implementation_identity", "required_origins", "schedule_digest", "status",
]


def main(argv: Sequence[str] | None = None) -> int:
    """Read-only status and synthetic activation CLI.

    ``record-due`` is intentionally an API-only seam in this phase: a caller
    must inject authenticated bars, a qualified publication runtime, and an
    offline verifier.  The CLI never constructs real network clients.
    """
    parser = argparse.ArgumentParser(description="JH01 V1 prospective operation seam")
    parser.add_argument("command", choices=("status", "activate-synthetic", "activate-real", "record-due"))
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--now", required=True, help="UTC timestamp")
    args = parser.parse_args(argv)
    operation = Operation(args.root, args.state_dir)
    now = _instant(args.now)
    if args.command == "status":
        print(json.dumps(operation.status(now=now), sort_keys=True))
        return 0
    if args.command == "activate-synthetic":
        print(json.dumps(operation.activate_synthetic(activation_time=now), sort_keys=True))
        return 0
    if args.command == "activate-real":
        print(json.dumps(operation.activate_real(activation_time=now), sort_keys=True))
        return 0
    raise OperationBlocked("record-due CLI requires injected source, transport, and verifier seams")


if __name__ == "__main__":  # pragma: no cover - exercised by shell integration
    try:
        raise SystemExit(main())
    except OperationBlocked as exc:
        raise SystemExit(str(exc))
