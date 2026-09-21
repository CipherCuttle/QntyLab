from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    log_loss,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler

from .research_ledger import (
    LedgerError,
    append_canonical_event,
    build_trial_completed_event,
    compute_variant_id,
    event_id,
    load_canonical_history,
    preflight,
    rebuild,
    sha256_bytes,
    utc_now,
    sha256_path,
)

FEATURE_SCHEMA = "PONS_S0_FEATURE_PACKET_V1"
OUTCOME_SCHEMA = "PONS_S0_OUTCOME_PACKET_V1"
MANIFEST_SCHEMA = "PONS_S0_EXPORT_MANIFEST_V1"
INPUT_KIND = "SENTRY_PONS_S0_EXPORT_V1"
SCREEN_ID = "PONS_S0_MODEL_SCREEN_V1"
SCREEN_VERSION = "pons-s0-model-screen-v1"
FAMILY_ID = "PONS_S0_24H_SELECTION_V1"
SYMBOL = "ROBINHOOD_PONS_S0"
BAR_INTERVAL = "IRREGULAR_LAUNCH_EVENTS"
GAP_POLICY = "OUTCOME_OBSERVED_BLOCK_LT_TEST_DECISION_BLOCK"
TARGET_HORIZON_MS = 86_400_000
PRIMARY_NOTIONAL_USD_MICROS = 1_000_000
NOTIONALS_USD_MICROS = (250_000, 500_000, 1_000_000, 2_000_000, 5_000_000)
POSITIVE_CLASSES = {"NORMAL_WIN"}
NEGATIVE_CLASSES = {
    "NORMAL_LOSS",
    "CATASTROPHIC_LOSS",
    "EXIT_FAILURE",
    "LIQUIDITY_COLLAPSE",
}
ADVERSE_CLASSES = {"CATASTROPHIC_LOSS", "EXIT_FAILURE", "LIQUIDITY_COLLAPSE"}
CAPACITY_SEMANTICS = "INDEPENDENT_PROBE_CAPACITY_NOT_SEQUENTIAL"
PERSONA_PARITY = "SHADOW_RECIPIENT_BOUND_LIVE_WALLET_UNVERIFIED"
MODE = "SHADOW_ONLY"

FROZEN_VARIANTS: tuple[dict[str, Any], ...] = (
    {
        "candidate_id": "PONS_S0_C0_BUY_EVERY_EXECUTABLE",
        "strategy_id": "PONS_S0_C0",
        "kind": "CONTROL",
        "parameters": {
            "policy": "BUY_EVERY_EXECUTABLE_CONTROL_R1",
            "target_horizon_ms": TARGET_HORIZON_MS,
        },
    },
    {
        "candidate_id": "PONS_S0_C1_FAST_VET_R1",
        "strategy_id": "PONS_S0_C1",
        "kind": "CONTROL",
        "parameters": {
            "policy": "FAST_VET_R1_CAPACITY_GATE",
            "target_horizon_ms": TARGET_HORIZON_MS,
        },
    },
    {
        "candidate_id": "PONS_S0_M1_LOGISTIC",
        "strategy_id": "PONS_S0_M1_LOGISTIC",
        "kind": "MODEL",
        "parameters": {
            "model": "LOGISTIC_REGRESSION_L2",
            "C": 1.0,
            "solver": "lbfgs",
            "max_iter": 1000,
            "threshold": 0.5,
            "target_horizon_ms": TARGET_HORIZON_MS,
        },
    },
    {
        "candidate_id": "PONS_S0_M2_HIST_GRADIENT_BOOSTING",
        "strategy_id": "PONS_S0_M2_HIST_GRADIENT_BOOSTING",
        "kind": "MODEL",
        "parameters": {
            "model": "HIST_GRADIENT_BOOSTING",
            "learning_rate": 0.1,
            "max_iter": 100,
            "max_leaf_nodes": 15,
            "min_samples_leaf": 5,
            "l2_regularization": 1.0,
            "random_state": 0,
            "threshold": 0.5,
            "target_horizon_ms": TARGET_HORIZON_MS,
        },
    },
)
REGISTERED_VARIANT_DENOMINATOR = len(FROZEN_VARIANTS)

FEATURE_NAMES: tuple[str, ...] = (
    "decision_delay_blocks",
    "creator_history_missing",
    "creator_prior_launch_count",
    "creator_classified_count",
    "creator_adverse_count",
    "creator_adverse_rate",
    "creator_normal_win_count",
    "creator_normal_loss_count",
    "creator_unresolved_count",
    "fee_bps",
    "creator_tax_bps",
    "effective_snipe_tax_bps",
    "tracked_to_graduation_ratio",
    "sellable_to_token_reserve_ratio",
    "quote_reserve_log1p",
    "capacity_rungs",
    "recovery_bps_025",
    "recovery_bps_050",
    "recovery_bps_100",
    "recovery_bps_200",
    "recovery_bps_500",
)

CONFIG_KEYS = {
    "schema_version",
    "screen_id",
    "screen_version",
    "preregistered_at_utc",
    "input_kind",
    "feature_schema",
    "outcome_schema",
    "target_horizon_ms",
    "positive_classes",
    "negative_classes",
    "min_train_rows",
    "test_rows",
    "max_folds",
    "probability_threshold",
    "registered_variant_denominator",
    "variants",
    "promotion_authority",
    "research_universe",
}


class PonsS0ScreenError(RuntimeError):
    pass


@dataclass(frozen=True)
class ExportBundle:
    manifest: dict[str, Any]
    features: tuple[dict[str, Any], ...]
    outcomes: tuple[dict[str, Any], ...]
    manifest_path: Path
    features_path: Path
    outcomes_path: Path


@dataclass(frozen=True)
class ScreenRow:
    launch_id: str
    baseline_id: str
    decision_block: int
    outcome_block: int
    label: int
    classification: str
    entry_notional_usd_micros: int
    gross_value_usd_micros: int
    net_value_usd_micros: int | None
    features: tuple[float, ...]
    c0_trade: bool
    c1_trade: bool


@dataclass(frozen=True)
class Fold:
    fold_index: int
    train_indices: tuple[int, ...]
    test_indices: tuple[int, ...]
    first_test_decision_block: int
    max_train_outcome_block: int


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def _read_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PonsS0ScreenError(f"{label} missing: {path}") from exc
    except json.JSONDecodeError as exc:
        raise PonsS0ScreenError(f"{label} malformed JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise PonsS0ScreenError(f"{label} must be a JSON object")
    return value


def _read_jsonl(path: Path, label: str) -> tuple[dict[str, Any], ...]:
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise PonsS0ScreenError(f"{label} missing: {path}") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(raw.splitlines(), start=1):
        if not line:
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PonsS0ScreenError(
                f"{label} malformed JSONL at line {line_number}: {exc}"
            ) from exc
        if not isinstance(value, dict):
            raise PonsS0ScreenError(
                f"{label} line {line_number} must be a JSON object"
            )
        rows.append(value)
    return tuple(rows)


def _hex64(value: Any, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(ch not in "0123456789abcdef" for ch in value.lower())
    ):
        raise PonsS0ScreenError(f"{label} must be a 64-character hex digest")
    return value.lower()


def _int_string(value: Any, label: str) -> int:
    if not isinstance(value, str) or not value or any(
        ch not in "-0123456789" for ch in value
    ):
        raise PonsS0ScreenError(f"{label} must be a decimal integer string")
    try:
        return int(value, 10)
    except ValueError as exc:
        raise PonsS0ScreenError(f"{label} must be a decimal integer string") from exc


def _int_field(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise PonsS0ScreenError(f"{label} must be an integer")
    return value


def _bool_field(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise PonsS0ScreenError(f"{label} must be boolean")
    return value


def _dict_field(value: Any, label: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PonsS0ScreenError(f"{label} must be an object")
    return value


def _list_field(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise PonsS0ScreenError(f"{label} must be an array")
    return value


def _validate_packet_digest(packet: dict[str, Any], label: str) -> None:
    expected = _hex64(packet.get("evidenceDigest"), f"{label}.evidenceDigest")
    material = {key: value for key, value in packet.items() if key != "evidenceDigest"}
    actual = canonical_sha256(material)
    if actual != expected:
        raise PonsS0ScreenError(f"{label} evidence digest mismatch")


def _feature_packet_id(packet: dict[str, Any]) -> str:
    creator = packet.get("creatorHistory")
    creator_digest = None
    if creator is not None:
        creator_digest = _dict_field(creator, "feature.creatorHistory").get(
            "evidenceDigest"
        )
    policy = _dict_field(packet.get("policyComparison"), "feature.policyComparison")
    edges = _list_field(packet.get("diagnosticEntityEdges"), "feature.diagnosticEntityEdges")
    return canonical_sha256(
        {
            "kind": FEATURE_SCHEMA,
            "launchId": _dict_field(packet.get("launch"), "feature.launch").get(
                "launchId"
            ),
            "baselineId": _dict_field(
                packet.get("baseline"), "feature.baseline"
            ).get("baselineId"),
            "baselineAuthorityDigest": _dict_field(
                packet.get("baseline"), "feature.baseline"
            ).get("authorityDigest"),
            "creatorEvidenceDigest": creator_digest,
            "policyEvidenceDigest": policy.get("evidenceDigest"),
            "entityEdgeDigests": [
                _dict_field(edge, "feature.entityEdge").get("evidenceDigest")
                for edge in edges
            ],
        }
    )


def _outcome_packet_id(packet: dict[str, Any]) -> str:
    cost = _dict_field(packet.get("costProjection"), "outcome.costProjection")
    return canonical_sha256(
        {
            "kind": OUTCOME_SCHEMA,
            "launchId": packet.get("launchId"),
            "baselineId": packet.get("baselineId"),
            "horizonMs": packet.get("horizonMs"),
            "outcomeId": packet.get("outcomeId"),
            "outcomeAuthorityDigest": packet.get("outcomeAuthorityDigest"),
            "executionCostEvidenceDigest": cost.get("executionCostEvidenceDigest"),
        }
    )


def _validate_feature_packet(packet: dict[str, Any], index: int) -> None:
    label = f"feature[{index}]"
    if packet.get("schemaVersion") != FEATURE_SCHEMA:
        raise PonsS0ScreenError(f"{label} schema mismatch")
    _validate_packet_digest(packet, label)
    if packet.get("packetId") != _feature_packet_id(packet):
        raise PonsS0ScreenError(f"{label} packetId mismatch")
    if packet.get("chainId") != 4663 or packet.get("ecosystem") != "ROBINHOOD":
        raise PonsS0ScreenError(f"{label} chain/ecosystem mismatch")
    if packet.get("launchProtocol") != "PONS":
        raise PonsS0ScreenError(f"{label} protocol mismatch")
    boundaries = _dict_field(packet.get("boundaries"), f"{label}.boundaries")
    if (
        boundaries.get("containsTargetLaunchFutureOutcome") is not False
        or boundaries.get("entityEdgesAtOrBeforeDecisionOnly") is not True
        or boundaries.get("mode") != MODE
        or boundaries.get("liveMoneyAuthority") is not False
        or boundaries.get("edge") != "UNPROVEN"
    ):
        raise PonsS0ScreenError(f"{label} research boundary mismatch")
    baseline = _dict_field(packet.get("baseline"), f"{label}.baseline")
    if baseline.get("capacitySemantics") != CAPACITY_SEMANTICS:
        raise PonsS0ScreenError(f"{label} capacity semantics mismatch")
    persona = packet.get("executionPersona")
    if persona is not None:
        persona = _dict_field(persona, f"{label}.executionPersona")
        if persona.get("parity") != PERSONA_PARITY:
            raise PonsS0ScreenError(f"{label} execution persona parity mismatch")


def _validate_outcome_packet(packet: dict[str, Any], index: int) -> None:
    label = f"outcome[{index}]"
    if packet.get("schemaVersion") != OUTCOME_SCHEMA:
        raise PonsS0ScreenError(f"{label} schema mismatch")
    _validate_packet_digest(packet, label)
    if packet.get("packetId") != _outcome_packet_id(packet):
        raise PonsS0ScreenError(f"{label} packetId mismatch")
    if packet.get("chainId") != 4663 or packet.get("ecosystem") != "ROBINHOOD":
        raise PonsS0ScreenError(f"{label} chain/ecosystem mismatch")
    if packet.get("launchProtocol") != "PONS":
        raise PonsS0ScreenError(f"{label} protocol mismatch")
    boundaries = _dict_field(packet.get("boundaries"), f"{label}.boundaries")
    if (
        boundaries.get("postOutcomeEvidence") is not True
        or boundaries.get("forbiddenAsFeatureInput") is not True
        or boundaries.get("mode") != MODE
        or boundaries.get("liveMoneyAuthority") is not False
        or boundaries.get("edge") != "UNPROVEN"
    ):
        raise PonsS0ScreenError(f"{label} outcome boundary mismatch")


def load_export_bundle(
    *, manifest_path: Path, features_path: Path, outcomes_path: Path
) -> ExportBundle:
    manifest = _read_json_object(manifest_path, "S0 manifest")
    if manifest.get("schemaVersion") != MANIFEST_SCHEMA:
        raise PonsS0ScreenError("S0 manifest schema mismatch")
    manifest_digest = _hex64(manifest.get("evidenceDigest"), "manifest.evidenceDigest")
    manifest_material = {
        key: value for key, value in manifest.items() if key != "evidenceDigest"
    }
    if canonical_sha256(manifest_material) != manifest_digest:
        raise PonsS0ScreenError("S0 manifest evidence digest mismatch")
    expected_manifest_id = canonical_sha256(
        {
            "kind": MANIFEST_SCHEMA,
            "featureStreamSha256": manifest.get("featureStreamSha256"),
            "outcomeStreamSha256": manifest.get("outcomeStreamSha256"),
            "featurePacketCount": manifest.get("featurePacketCount"),
            "outcomePacketCount": manifest.get("outcomePacketCount"),
        }
    )
    if manifest.get("manifestId") != expected_manifest_id:
        raise PonsS0ScreenError("S0 manifestId mismatch")
    if (
        manifest.get("featureSchema") != FEATURE_SCHEMA
        or manifest.get("outcomeSchema") != OUTCOME_SCHEMA
        or manifest.get("mode") != MODE
        or manifest.get("liveMoneyAuthority") is not False
        or manifest.get("edge") != "UNPROVEN"
    ):
        raise PonsS0ScreenError("S0 manifest authority mismatch")
    separation = _dict_field(manifest.get("separation"), "manifest.separation")
    if (
        separation.get("featureAndOutcomeStreamsDistinct") is not True
        or separation.get("featurePacketsContainTargetFutureOutcome") is not False
        or separation.get("outcomePacketsForbiddenAsFeatureInput") is not True
    ):
        raise PonsS0ScreenError("S0 manifest separation mismatch")

    feature_bytes = features_path.read_bytes()
    outcome_bytes = outcomes_path.read_bytes()
    if hashlib.sha256(feature_bytes).hexdigest() != manifest.get("featureStreamSha256"):
        raise PonsS0ScreenError("feature stream SHA-256 mismatch")
    if hashlib.sha256(outcome_bytes).hexdigest() != manifest.get("outcomeStreamSha256"):
        raise PonsS0ScreenError("outcome stream SHA-256 mismatch")

    features = _read_jsonl(features_path, "S0 features")
    outcomes = _read_jsonl(outcomes_path, "S0 outcomes")
    if len(features) != manifest.get("featurePacketCount"):
        raise PonsS0ScreenError("feature packet count mismatch")
    if len(outcomes) != manifest.get("outcomePacketCount"):
        raise PonsS0ScreenError("outcome packet count mismatch")

    for index, packet in enumerate(features):
        _validate_feature_packet(packet, index)
    for index, packet in enumerate(outcomes):
        _validate_outcome_packet(packet, index)

    feature_digests = [packet["evidenceDigest"] for packet in features]
    outcome_digests = [packet["evidenceDigest"] for packet in outcomes]
    if feature_digests != manifest.get("featurePacketDigests"):
        raise PonsS0ScreenError("feature packet digest list mismatch")
    if outcome_digests != manifest.get("outcomePacketDigests"):
        raise PonsS0ScreenError("outcome packet digest list mismatch")

    feature_keys: set[tuple[str, str]] = set()
    for packet in features:
        launch = _dict_field(packet["launch"], "feature.launch")
        baseline = _dict_field(packet["baseline"], "feature.baseline")
        key = (str(launch["launchId"]), str(baseline["baselineId"]))
        if key in feature_keys:
            raise PonsS0ScreenError(f"duplicate feature binding: {key}")
        feature_keys.add(key)
    outcome_keys: set[tuple[str, str, int]] = set()
    for packet in outcomes:
        key = (
            str(packet["launchId"]),
            str(packet["baselineId"]),
            _int_field(packet["horizonMs"], "outcome.horizonMs"),
        )
        if key in outcome_keys:
            raise PonsS0ScreenError(f"duplicate outcome binding: {key}")
        outcome_keys.add(key)
        if key[:2] not in feature_keys:
            raise PonsS0ScreenError(f"outcome without feature packet: {key[:2]}")

    return ExportBundle(
        manifest=manifest,
        features=features,
        outcomes=outcomes,
        manifest_path=manifest_path,
        features_path=features_path,
        outcomes_path=outcomes_path,
    )


def load_screen_config(path: Path) -> dict[str, Any]:
    config = _read_json_object(path, "Pons S0 screen config")
    extra = set(config) - CONFIG_KEYS
    missing = CONFIG_KEYS - set(config)
    if extra or missing:
        raise PonsS0ScreenError(
            f"screen config keys mismatch: extra={sorted(extra)} missing={sorted(missing)}"
        )
    expected = {
        "schema_version": 1,
        "screen_id": SCREEN_ID,
        "screen_version": SCREEN_VERSION,
        "input_kind": INPUT_KIND,
        "feature_schema": FEATURE_SCHEMA,
        "outcome_schema": OUTCOME_SCHEMA,
        "target_horizon_ms": TARGET_HORIZON_MS,
        "positive_classes": sorted(POSITIVE_CLASSES),
        "negative_classes": sorted(NEGATIVE_CLASSES),
        "registered_variant_denominator": REGISTERED_VARIANT_DENOMINATOR,
        "promotion_authority": "NONE",
        "research_universe": "C0_MECHANICALLY_ADMISSIBLE_WITH_RESOLVED_24H_OUTCOME",
    }
    for key, value in expected.items():
        if config.get(key) != value:
            raise PonsS0ScreenError(f"screen config mismatch: {key}")
    if config.get("variants") != list(FROZEN_VARIANTS):
        raise PonsS0ScreenError("screen variant denominator/configuration mismatch")
    for key in ("min_train_rows", "test_rows", "max_folds"):
        value = config.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value < 1:
            raise PonsS0ScreenError(f"{key} must be a positive integer")
    threshold = config.get("probability_threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise PonsS0ScreenError("probability_threshold must be numeric")
    if float(threshold) != 0.5:
        raise PonsS0ScreenError("probability_threshold is frozen at 0.5")
    preregistered = config.get("preregistered_at_utc")
    if not isinstance(preregistered, str) or not preregistered.endswith("Z"):
        raise PonsS0ScreenError("preregistered_at_utc must be a frozen UTC timestamp")
    return config


def _ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return float("nan")
    return float(numerator / denominator)


def _feature_vector(packet: dict[str, Any]) -> tuple[float, ...]:
    launch = _dict_field(packet["launch"], "feature.launch")
    baseline = _dict_field(packet["baseline"], "feature.baseline")
    timing = _dict_field(packet["timing"], "feature.timing")
    legs = _list_field(baseline.get("legs"), "feature.baseline.legs")
    notionals = [
        _int_string(_dict_field(leg, "feature.leg").get("notionalUsdMicros"), "leg.notionalUsdMicros")
        for leg in legs
    ]
    if tuple(notionals) != NOTIONALS_USD_MICROS:
        raise PonsS0ScreenError(f"baseline ladder mismatch: {notionals}")
    reference = _dict_field(legs[2], "feature.leg.1usd")
    entry = _dict_field(reference.get("entry"), "feature.leg.1usd.entry")
    state = _dict_field(entry.get("quoteState"), "feature.leg.1usd.quoteState")

    capacity_rungs = 0
    recoveries: list[float] = []
    for leg in legs:
        leg = _dict_field(leg, "feature.leg")
        entry_leg = _dict_field(leg.get("entry"), "feature.leg.entry")
        reverse = leg.get("reverse")
        reverse_ok = isinstance(reverse, dict) and reverse.get("executable") is True
        if entry_leg.get("executable") is True and reverse_ok and capacity_rungs == len(recoveries):
            capacity_rungs += 1
        recovery = leg.get("independentReverseRecoveryBps")
        recoveries.append(
            float(_int_string(recovery, "independentReverseRecoveryBps"))
            if recovery is not None
            else float("nan")
        )

    creator = packet.get("creatorHistory")
    if creator is None:
        creator_missing = 1.0
        prior_count = classified = adverse = normal_win = normal_loss = unresolved = float("nan")
        adverse_rate = float("nan")
    else:
        creator = _dict_field(creator, "feature.creatorHistory")
        creator_missing = 0.0
        prior_count = float(_int_field(creator.get("priorLaunchCount"), "creator.priorLaunchCount"))
        classified = float(_int_field(creator.get("classifiedOutcomeCount"), "creator.classifiedOutcomeCount"))
        unresolved = float(_int_field(creator.get("unresolvedOutcomeCount"), "creator.unresolvedOutcomeCount"))
        adverse = float(
            _int_field(creator.get("catastrophicLossCount"), "creator.catastrophicLossCount")
            + _int_field(creator.get("exitFailureCount"), "creator.exitFailureCount")
            + _int_field(creator.get("liquidityCollapseCount"), "creator.liquidityCollapseCount")
        )
        normal_win = float(_int_field(creator.get("normalWinCount"), "creator.normalWinCount"))
        normal_loss = float(_int_field(creator.get("normalLossCount"), "creator.normalLossCount"))
        adverse_rate = adverse / classified if classified > 0 else float("nan")

    graduation = _int_string(launch.get("graduationThreshold"), "launch.graduationThreshold")
    tracked = _int_string(state.get("trackedQuote"), "quote.trackedQuote")
    sellable = _int_string(state.get("sellableTokens"), "quote.sellableTokens")
    token_reserve = _int_string(state.get("tokenReserve"), "quote.tokenReserve")
    quote_reserve = _int_string(state.get("quoteReserve"), "quote.quoteReserve")

    values = (
        float(_int_string(timing.get("decisionDelayBlocks"), "timing.decisionDelayBlocks")),
        creator_missing,
        prior_count,
        classified,
        adverse,
        adverse_rate,
        normal_win,
        normal_loss,
        unresolved,
        float(_int_string(state.get("feeBps"), "quote.feeBps")),
        float(_int_string(state.get("creatorTaxBps"), "quote.creatorTaxBps")),
        float(_int_string(state.get("effectiveSnipeTaxBps"), "quote.effectiveSnipeTaxBps")),
        _ratio(tracked, graduation),
        _ratio(sellable, token_reserve),
        math.log1p(max(0, quote_reserve)),
        float(capacity_rungs),
        *recoveries,
    )
    if len(values) != len(FEATURE_NAMES):
        raise AssertionError("feature vector/schema length mismatch")
    if any(math.isinf(value) for value in values):
        raise PonsS0ScreenError("feature vector contains infinity")
    return tuple(float(value) for value in values)


def build_screen_rows(
    bundle: ExportBundle, *, target_horizon_ms: int = TARGET_HORIZON_MS
) -> tuple[tuple[ScreenRow, ...], dict[str, Any]]:
    outcomes = {
        (str(packet["launchId"]), str(packet["baselineId"]), int(packet["horizonMs"])): packet
        for packet in bundle.outcomes
    }
    rows: list[ScreenRow] = []
    unresolved: list[str] = []
    mechanically_inadmissible_resolved: list[str] = []
    resolved_target_count = 0
    for feature in bundle.features:
        launch = _dict_field(feature["launch"], "feature.launch")
        baseline = _dict_field(feature["baseline"], "feature.baseline")
        launch_id = str(launch["launchId"])
        baseline_id = str(baseline["baselineId"])
        outcome = outcomes.get((launch_id, baseline_id, target_horizon_ms))
        if outcome is None or outcome.get("status") != "COMPLETE":
            unresolved.append(launch_id)
            continue
        classification = outcome.get("classification")
        if classification in POSITIVE_CLASSES:
            label = 1
        elif classification in NEGATIVE_CLASSES:
            label = 0
        else:
            unresolved.append(launch_id)
            continue
        gross = outcome.get("grossExecutableValueUsdMicros")
        if gross is None:
            raise PonsS0ScreenError(
                f"COMPLETE classified outcome missing executable value: {launch_id}"
            )
        gross_value = _int_string(gross, "outcome.grossExecutableValueUsdMicros")
        entry_notional = _int_string(
            outcome.get("entryNotionalUsdMicros"), "outcome.entryNotionalUsdMicros"
        )
        if entry_notional != PRIMARY_NOTIONAL_USD_MICROS:
            raise PonsS0ScreenError(
                f"primary outcome notional mismatch for {launch_id}: {entry_notional}"
            )
        cost = _dict_field(outcome.get("costProjection"), "outcome.costProjection")
        net_value: int | None = None
        if cost.get("status") == "COMPLETE":
            net_value = _int_string(
                cost.get("netExecutableValueUsdMicros"),
                "outcome.costProjection.netExecutableValueUsdMicros",
            )
        policy = _dict_field(feature.get("policyComparison"), "feature.policyComparison")
        receipts = _dict_field(policy.get("receipts"), "feature.policyComparison.receipts")
        c0 = _dict_field(
            receipts.get("buyEveryExecutableControl"), "feature.policyComparison.control"
        )
        c1 = _dict_field(receipts.get("r1"), "feature.policyComparison.r1")
        resolved_target_count += 1
        c0_trade = c0.get("hypotheticalAction") == "WOULD_TRADE"
        if not c0_trade:
            mechanically_inadmissible_resolved.append(launch_id)
            continue
        rows.append(
            ScreenRow(
                launch_id=launch_id,
                baseline_id=baseline_id,
                decision_block=_int_string(
                    baseline.get("decisionBlock"), "baseline.decisionBlock"
                ),
                outcome_block=_int_string(
                    outcome.get("observedBlock"), "outcome.observedBlock"
                ),
                label=label,
                classification=str(classification),
                entry_notional_usd_micros=entry_notional,
                gross_value_usd_micros=gross_value,
                net_value_usd_micros=net_value,
                features=_feature_vector(feature),
                c0_trade=True,
                c1_trade=c1.get("hypotheticalAction") == "WOULD_TRADE",
            )
        )
    rows.sort(key=lambda row: (row.decision_block, row.launch_id))
    if len({row.launch_id for row in rows}) != len(rows):
        raise PonsS0ScreenError("duplicate resolved launch in screen rows")
    coverage = {
        "feature_packet_count": len(bundle.features),
        "resolved_target_count": resolved_target_count,
        "unresolved_target_count": len(unresolved),
        "target_coverage_bps": (
            resolved_target_count * 10_000 // len(bundle.features)
            if bundle.features
            else 0
        ),
        "mechanically_admissible_resolved_count": len(rows),
        "mechanically_inadmissible_resolved_count": len(
            mechanically_inadmissible_resolved
        ),
        "mechanically_inadmissible_resolved_launch_ids": sorted(
            mechanically_inadmissible_resolved
        ),
        "model_universe": "C0_MECHANICALLY_ADMISSIBLE_WITH_RESOLVED_24H_OUTCOME",
        "unresolved_launch_ids": sorted(unresolved),
    }
    return tuple(rows), coverage


def build_folds(
    rows: tuple[ScreenRow, ...],
    *,
    min_train_rows: int,
    test_rows: int,
    max_folds: int,
) -> tuple[Fold, ...]:
    folds: list[Fold] = []
    test_start = min_train_rows
    while test_start < len(rows) and len(folds) < max_folds:
        first_test_block = rows[test_start].decision_block
        train = tuple(
            index
            for index in range(test_start)
            if rows[index].outcome_block < first_test_block
        )
        labels = {rows[index].label for index in train}
        if len(train) < min_train_rows or labels != {0, 1}:
            test_start += 1
            continue
        end = min(test_start + test_rows, len(rows))
        test = tuple(range(test_start, end))
        if not test:
            break
        max_train_outcome = max(rows[index].outcome_block for index in train)
        if max_train_outcome >= first_test_block:
            raise PonsS0ScreenError("label-availability embargo violated")
        folds.append(
            Fold(
                fold_index=len(folds),
                train_indices=train,
                test_indices=test,
                first_test_decision_block=first_test_block,
                max_train_outcome_block=max_train_outcome,
            )
        )
        test_start = end
    if not folds:
        raise PonsS0ScreenError("INSUFFICIENT_EMBARGOED_CHRONOLOGICAL_FOLDS")
    return tuple(folds)


def _matrix(rows: tuple[ScreenRow, ...], indices: Iterable[int]) -> np.ndarray:
    return np.asarray([rows[index].features for index in indices], dtype=float)


def _labels(rows: tuple[ScreenRow, ...], indices: Iterable[int]) -> np.ndarray:
    return np.asarray([rows[index].label for index in indices], dtype=int)


def _logistic_model() -> Pipeline:
    numeric = Pipeline(
        [
            ("imputer", SimpleImputer(strategy="median", add_indicator=True)),
            ("scale", StandardScaler()),
        ]
    )
    # ColumnTransformer fixes the exact feature surface and prevents accidental
    # ingestion of IDs / policy outputs / future outcome fields.
    prep = ColumnTransformer(
        [("numeric", numeric, list(range(len(FEATURE_NAMES))))],
        remainder="drop",
    )
    return Pipeline(
        [
            ("prep", prep),
            (
                "model",
                LogisticRegression(
                    C=1.0,
                    penalty="l2",
                    solver="lbfgs",
                    max_iter=1000,
                ),
            ),
        ]
    )


def _hist_model() -> Pipeline:
    prep = ColumnTransformer(
        [
            (
                "numeric",
                SimpleImputer(strategy="median", add_indicator=False),
                list(range(len(FEATURE_NAMES))),
            )
        ],
        remainder="drop",
    )
    return Pipeline(
        [
            ("prep", prep),
            (
                "model",
                HistGradientBoostingClassifier(
                    learning_rate=0.1,
                    max_iter=100,
                    max_leaf_nodes=15,
                    min_samples_leaf=5,
                    l2_regularization=1.0,
                    random_state=0,
                ),
            ),
        ]
    )


def _probability_metrics(y_true: np.ndarray, probabilities: np.ndarray) -> dict[str, Any]:
    predictions = (probabilities >= 0.5).astype(int)
    result: dict[str, Any] = {
        "observation_count": int(len(y_true)),
        "positive_count": int(y_true.sum()),
        "brier_score": float(brier_score_loss(y_true, probabilities)),
        "log_loss": float(log_loss(y_true, probabilities, labels=[0, 1])),
        "accuracy": float(accuracy_score(y_true, predictions)),
        "balanced_accuracy": float(balanced_accuracy_score(y_true, predictions)),
        "roc_auc": None,
    }
    if len(set(int(value) for value in y_true)) == 2:
        result["roc_auc"] = float(roc_auc_score(y_true, probabilities))
    return result


def _policy_metrics(
    rows: tuple[ScreenRow, ...],
    evaluation_indices: tuple[int, ...],
    accepts: dict[int, bool],
) -> dict[str, Any]:
    gross_terminal = 0
    gross_control_terminal = 0
    positive_excess = 0
    accepted_positive_excess = 0
    trade_count = 0
    adverse_accepted = 0
    net_terminal = 0
    net_complete = True
    net_cost_covered_accepts = 0
    accepted_rows = 0
    for index in evaluation_indices:
        row = rows[index]
        accept = bool(accepts[index])
        control_accept = row.c0_trade
        gross_control_terminal += (
            row.gross_value_usd_micros
            if control_accept
            else row.entry_notional_usd_micros
        )
        excess = max(0, row.gross_value_usd_micros - row.entry_notional_usd_micros)
        if control_accept:
            positive_excess += excess
        if accept:
            trade_count += 1
            accepted_rows += 1
            gross_terminal += row.gross_value_usd_micros
            accepted_positive_excess += excess
            if row.classification in ADVERSE_CLASSES:
                adverse_accepted += 1
            if row.net_value_usd_micros is None:
                net_complete = False
            else:
                net_cost_covered_accepts += 1
                net_terminal += row.net_value_usd_micros
        else:
            gross_terminal += row.entry_notional_usd_micros
            net_terminal += row.entry_notional_usd_micros
    return {
        "observation_count": len(evaluation_indices),
        "trade_count": trade_count,
        "trade_retention_bps": (
            trade_count * 10_000 // len(evaluation_indices)
            if evaluation_indices
            else 0
        ),
        "gross_terminal_capital_usd_micros": gross_terminal,
        "gross_delta_vs_c0_usd_micros": gross_terminal - gross_control_terminal,
        "adverse_accepted_count": adverse_accepted,
        "positive_excess_capture_bps": (
            accepted_positive_excess * 10_000 // positive_excess
            if positive_excess > 0
            else None
        ),
        "net_cost_covered_accept_count": net_cost_covered_accepts,
        "net_cost_coverage_bps_among_accepts": (
            net_cost_covered_accepts * 10_000 // accepted_rows
            if accepted_rows > 0
            else 10_000
        ),
        "net_terminal_capital_usd_micros": net_terminal if net_complete else None,
        "net_economics_complete": net_complete,
    }


def _variant_event(config: dict[str, Any], variant: dict[str, Any]) -> dict[str, Any]:
    event: dict[str, Any] = {
        "event_id": "",
        "event_type": "CANDIDATE_PROPOSED",
        "candidate_id": variant["candidate_id"],
        "family_id": FAMILY_ID,
        "variant_id": "",
        "strategy_id": variant["strategy_id"],
        "strategy_version": SCREEN_VERSION,
        "objective": "FALSIFY_POINT_IN_TIME_24H_PONS_SELECTION_SIGNAL",
        "origin": "SENTRY_PONS_S0_EXPORT_V1",
        "mechanism": variant["kind"],
        "prediction": "POINT_IN_TIME_FEATURES_MAY_IMPROVE_24H_EXECUTABLE_SELECTION",
        "required_data": [FEATURE_SCHEMA, OUTCOME_SCHEMA],
        "decision_time": "SENTRY_BASELINE_DECISION_BLOCK",
        "execution_time": "SHADOW_ONLY_NO_EXECUTION",
        "benchmark": "PONS_S0_C0",
        "parameters": variant["parameters"],
        "mode": MODE,
        "bar_interval": BAR_INTERVAL,
        "required_input_kind": INPUT_KIND,
        "funding_boundary_mode": "NOT_APPLICABLE",
        "failure_condition": "NO_OUT_OF_SAMPLE_INCREMENTAL_INFORMATION_OR_ECONOMIC_VALUE",
        "recorded_at_utc": utc_now(),
        "registered_screen_id": SCREEN_ID,
        "registered_variant_denominator": REGISTERED_VARIANT_DENOMINATOR,
    }
    event["variant_id"] = compute_variant_id(event)
    event["event_id"] = event_id("event_candidate", event)
    return event


def _ensure_ledger_root(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "trials").mkdir(parents=True, exist_ok=True)
    for name in ("candidates.jsonl", "decisions.jsonl"):
        path = root / name
        if not path.exists():
            path.write_text("", encoding="utf-8")
    if not (root / "state.json").exists() or not (root / "trial_index.json").exists():
        rebuild(root)


def register_screen_candidates(config: dict[str, Any], root: Path) -> dict[str, dict[str, Any]]:
    _ensure_ledger_root(root)
    history = load_canonical_history(root)
    existing = {
        event["variant_id"]: event
        for event in history.candidates
        if event.get("event_type") == "CANDIDATE_PROPOSED"
    }
    result: dict[str, dict[str, Any]] = {}
    for variant in FROZEN_VARIANTS:
        event = _variant_event(config, variant)
        prior = existing.get(event["variant_id"])
        if prior is not None:
            if (
                prior.get("candidate_id") != event["candidate_id"]
                or prior.get("family_id") != FAMILY_ID
            ):
                raise PonsS0ScreenError("registered variant identity collision")
            result[variant["strategy_id"]] = prior
            continue
        append_canonical_event(event, root)
        result[variant["strategy_id"]] = event
    return result


def _iso_from_ms(value: int) -> str:
    from datetime import UTC, datetime

    return datetime.fromtimestamp(value / 1000, tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _repo_commit() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def _source_digest() -> str:
    paths = (
        Path("qntylab/pons_s0_screen.py"),
        Path("experiments/specs/pons_s0_model_screen_v1.json"),
        Path("requirements-pons-s0-v1.txt"),
    )
    rows = [{"path": str(path), "sha256": sha256_path(path)} for path in paths]
    return canonical_sha256(rows)


def _trial_config(
    event: dict[str, Any],
    *,
    evaluation_start: str,
    evaluation_end: str,
) -> dict[str, Any]:
    return {
        "bar_interval": BAR_INTERVAL,
        "funding_boundary_mode": "NOT_APPLICABLE",
        "mode": MODE,
        "parameters": event["parameters"],
        "required_input_kind": INPUT_KIND,
        "strategy_id": event["strategy_id"],
        "strategy_version": SCREEN_VERSION,
        "candidate_id": event["candidate_id"],
        "variant_id": event["variant_id"],
        "evaluation_start": evaluation_start,
        "evaluation_end": evaluation_end,
        "fee_bps": 0.0,
        "slippage_bps": 0.0,
        "gap_policy": GAP_POLICY,
        "expected_interval": BAR_INTERVAL,
        "research_intent": "SCREEN",
    }


def _write_variant_receipt_and_ledger(
    *,
    output_root: Path,
    research_root: Path,
    event: dict[str, Any],
    input_sha256: str,
    evaluation_start: str,
    evaluation_end: str,
    metrics: dict[str, Any],
    fold_receipts: list[dict[str, Any]],
    coverage: dict[str, Any],
) -> dict[str, Any]:
    config = _trial_config(
        event,
        evaluation_start=evaluation_start,
        evaluation_end=evaluation_end,
    )
    binding = preflight(
        config=config,
        symbol=SYMBOL,
        input_sha256=input_sha256,
        root=research_root,
    )
    receipt_dir = output_root / event["strategy_id"].lower()
    receipt_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipt_dir / "run_receipt.json"
    receipt = {
        "schema_version": 1,
        "screen_id": SCREEN_ID,
        "screen_version": SCREEN_VERSION,
        "run_id": receipt_dir.name,
        "repository_commit": _repo_commit(),
        "relevant_source_sha256": _source_digest(),
        "candidate_id": event["candidate_id"],
        "family_id": FAMILY_ID,
        "variant_id": event["variant_id"],
        "trial_id": binding["trial_id"],
        "research_intent": "SCREEN",
        "symbol": SYMBOL,
        "evaluation_range": {
            "start": evaluation_start,
            "end": evaluation_end,
        },
        "input_sha256": input_sha256,
        "input_kind": INPUT_KIND,
        "fee_assumption": {"fee_bps": 0.0, "semantics": "NOT_APPLICABLE_ALREADY_IN_OUTCOME_EVIDENCE"},
        "slippage_assumption": {"slippage_bps": 0.0, "semantics": "NOT_APPLICABLE_ALREADY_IN_OUTCOME_EVIDENCE"},
        "gap_policy": GAP_POLICY,
        "expected_interval": BAR_INTERVAL,
        "registered_screen_id": SCREEN_ID,
        "registered_variant_denominator": REGISTERED_VARIANT_DENOMINATOR,
        "research_universe": config["research_universe"],
        "target_horizon_ms": TARGET_HORIZON_MS,
        "feature_names": list(FEATURE_NAMES),
        "folds": fold_receipts,
        "coverage": coverage,
        "metrics": metrics,
        "candidate_artifact": None,
        "promotion_authority": "NONE",
        "exploratory_only": True,
        "live_money_authority": False,
        "edge": "UNPROVEN",
    }
    receipt_path.write_bytes(canonical_bytes(receipt) + b"\n")
    event_trial = build_trial_completed_event(
        receipt=receipt,
        receipt_path=receipt_path,
        receipt_sha256=sha256_path(receipt_path),
        metrics={
            "observation_count": int(metrics["policy"]["observation_count"]),
            "trade_count": int(metrics["policy"]["trade_count"]),
        },
        recorded_at_utc=None,
    )
    append_canonical_event(event_trial, research_root)
    return receipt


def run_screen(
    *,
    manifest_path: Path,
    features_path: Path,
    outcomes_path: Path,
    config_path: Path,
    output_root: Path,
    research_root: Path,
) -> dict[str, Any]:
    config = load_screen_config(config_path)
    events = register_screen_candidates(config, research_root)
    bundle = load_export_bundle(
        manifest_path=manifest_path,
        features_path=features_path,
        outcomes_path=outcomes_path,
    )
    rows, coverage = build_screen_rows(bundle)
    folds = build_folds(
        rows,
        min_train_rows=config["min_train_rows"],
        test_rows=config["test_rows"],
        max_folds=config["max_folds"],
    )
    predictions: dict[str, dict[int, float]] = {
        "PONS_S0_M1_LOGISTIC": {},
        "PONS_S0_M2_HIST_GRADIENT_BOOSTING": {},
    }
    no_feature_predictions: dict[int, float] = {}
    fold_receipts: list[dict[str, Any]] = []
    for fold in folds:
        train_x = _matrix(rows, fold.train_indices)
        train_y = _labels(rows, fold.train_indices)
        test_x = _matrix(rows, fold.test_indices)
        logistic = _logistic_model()
        hist = _hist_model()
        logistic.fit(train_x, train_y)
        hist.fit(train_x, train_y)
        logistic_p = logistic.predict_proba(test_x)[:, 1]
        hist_p = hist.predict_proba(test_x)[:, 1]
        train_prevalence = float(train_y.mean())
        for index in fold.test_indices:
            no_feature_predictions[index] = train_prevalence
        for index, probability in zip(fold.test_indices, logistic_p, strict=True):
            predictions["PONS_S0_M1_LOGISTIC"][index] = float(probability)
        for index, probability in zip(fold.test_indices, hist_p, strict=True):
            predictions["PONS_S0_M2_HIST_GRADIENT_BOOSTING"][index] = float(probability)
        fold_receipts.append(
            {
                "fold_index": fold.fold_index,
                "train_count": len(fold.train_indices),
                "test_count": len(fold.test_indices),
                "train_launch_ids": [rows[index].launch_id for index in fold.train_indices],
                "test_launch_ids": [rows[index].launch_id for index in fold.test_indices],
                "first_test_decision_block": fold.first_test_decision_block,
                "max_train_outcome_block": fold.max_train_outcome_block,
                "label_availability_embargo_satisfied": (
                    fold.max_train_outcome_block < fold.first_test_decision_block
                ),
            }
        )

    evaluation_indices = tuple(
        index for fold in folds for index in fold.test_indices
    )
    if len(set(evaluation_indices)) != len(evaluation_indices):
        raise PonsS0ScreenError("test rows overlap across folds")
    y_eval = _labels(rows, evaluation_indices)
    no_feature_probs = np.asarray(
        [no_feature_predictions[index] for index in evaluation_indices],
        dtype=float,
    )
    no_feature_probability = _probability_metrics(y_eval, no_feature_probs)

    variant_metrics: dict[str, dict[str, Any]] = {}
    c0_accepts = {index: rows[index].c0_trade for index in evaluation_indices}
    c1_accepts = {index: rows[index].c1_trade for index in evaluation_indices}
    variant_metrics["PONS_S0_C0"] = {
        "probability": None,
        "policy": _policy_metrics(rows, evaluation_indices, c0_accepts),
    }
    variant_metrics["PONS_S0_C1"] = {
        "probability": None,
        "policy": _policy_metrics(rows, evaluation_indices, c1_accepts),
    }
    for strategy_id in ("PONS_S0_M1_LOGISTIC", "PONS_S0_M2_HIST_GRADIENT_BOOSTING"):
        probs = np.asarray(
            [predictions[strategy_id][index] for index in evaluation_indices],
            dtype=float,
        )
        if not np.all(np.isfinite(probs)) or np.any((probs < 0) | (probs > 1)):
            raise PonsS0ScreenError(f"invalid model probabilities: {strategy_id}")
        accepts = {
            index: predictions[strategy_id][index] >= float(config["probability_threshold"])
            for index in evaluation_indices
        }
        probability = _probability_metrics(y_eval, probs)
        probability["no_feature_brier_score"] = no_feature_probability["brier_score"]
        probability["no_feature_log_loss"] = no_feature_probability["log_loss"]
        probability["brier_improvement_vs_no_feature"] = (
            no_feature_probability["brier_score"] - probability["brier_score"]
        )
        probability["log_loss_improvement_vs_no_feature"] = (
            no_feature_probability["log_loss"] - probability["log_loss"]
        )
        variant_metrics[strategy_id] = {
            "probability": probability,
            "policy": _policy_metrics(rows, evaluation_indices, accepts),
        }

    decision_times = [
        _dict_field(feature["timing"], "feature.timing")["baselineObservedAtMs"]
        for feature in bundle.features
    ]
    if not decision_times:
        raise PonsS0ScreenError("empty feature cohort")
    evaluation_start = _iso_from_ms(min(int(value) for value in decision_times))
    evaluation_end = _iso_from_ms(max(int(value) for value in decision_times))

    output_root.mkdir(parents=True, exist_ok=True)
    input_sha256 = _hex64(bundle.manifest["evidenceDigest"], "manifest.evidenceDigest")
    receipts: dict[str, Any] = {}
    for variant in FROZEN_VARIANTS:
        strategy_id = variant["strategy_id"]
        receipts[strategy_id] = _write_variant_receipt_and_ledger(
            output_root=output_root,
            research_root=research_root,
            event=events[strategy_id],
            input_sha256=input_sha256,
            evaluation_start=evaluation_start,
            evaluation_end=evaluation_end,
            metrics=variant_metrics[strategy_id],
            fold_receipts=fold_receipts,
            coverage=coverage,
        )

    screen_receipt = {
        "schema_version": 1,
        "screen_id": SCREEN_ID,
        "screen_version": SCREEN_VERSION,
        "input_manifest_id": bundle.manifest["manifestId"],
        "input_manifest_evidence_digest": bundle.manifest["evidenceDigest"],
        "registered_variant_denominator": REGISTERED_VARIANT_DENOMINATOR,
        "target_horizon_ms": TARGET_HORIZON_MS,
        "feature_names": list(FEATURE_NAMES),
        "coverage": coverage,
        "folds": fold_receipts,
        "variants": variant_metrics,
        "no_feature_probability_baseline": no_feature_probability,
        "candidate_artifact": None,
        "automatic_winner_selection": False,
        "promotion_authority": "NONE",
        "mode": MODE,
        "live_money_authority": False,
        "edge": "UNPROVEN",
        "verdict": "EXPLORATORY_SCREEN_COMPLETE_NO_PROMOTION",
    }
    screen_path = output_root / "screen_receipt.json"
    screen_path.write_bytes(canonical_bytes(screen_receipt) + b"\n")
    return {
        "receipt": screen_receipt,
        "receipt_path": screen_path,
        "variant_receipts": receipts,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Pons S0 exploratory point-in-time model screen"
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--features", required=True, type=Path)
    parser.add_argument("--outcomes", required=True, type=Path)
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("experiments/specs/pons_s0_model_screen_v1.json"),
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--research-root",
        type=Path,
        default=Path("experiments/research"),
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = _parser().parse_args(argv)
    try:
        result = run_screen(
            manifest_path=args.manifest,
            features_path=args.features,
            outcomes_path=args.outcomes,
            config_path=args.config,
            output_root=args.output,
            research_root=args.research_root,
        )
    except (OSError, ValueError, LedgerError, PonsS0ScreenError) as exc:
        raise SystemExit(f"PONS_S0_SCREEN_ERROR: {exc}") from exc
    print(
        json.dumps(
            {
                "verdict": result["receipt"]["verdict"],
                "receipt_path": str(result["receipt_path"]),
                "live_money_authority": False,
                "edge": "UNPROVEN",
            },
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    main()
