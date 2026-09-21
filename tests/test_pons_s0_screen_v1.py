from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from qntylab.pons_s0_screen import (
    CAPACITY_SEMANTICS,
    FEATURE_SCHEMA,
    FROZEN_VARIANTS,
    MANIFEST_SCHEMA,
    OUTCOME_SCHEMA,
    PERSONA_PARITY,
    REGISTERED_VARIANT_DENOMINATOR,
    SCREEN_ID,
    TARGET_HORIZON_MS,
    PonsS0ScreenError,
    build_folds,
    build_screen_rows,
    canonical_bytes,
    canonical_sha256,
    load_export_bundle,
    load_screen_config,
    run_screen,
)
from qntylab.research_ledger import doctor, load_canonical_history

CONFIG_PATH = Path("experiments/specs/pons_s0_model_screen_v1.json")


def h(seed: int) -> str:
    return f"{seed:064x}"[-64:]


def addr(seed: int) -> str:
    return "0x" + f"{seed:040x}"[-40:]


def _feature_packet(i: int, *, positive: bool, c0_trade: bool = True) -> dict:
    launch_id = f"launch-{i:03d}"
    baseline_id = f"baseline-{i:03d}"
    decision_block = 100_000 + i * 100
    launch_block = decision_block - 2
    adverse = 0 if positive else 1
    classified = 3 + (i % 4)
    normal_win = classified - adverse
    creator = {
        "receiptId": h(10_000 + i),
        "evidenceDigest": h(20_000 + i),
        "coverage": "COMPLETE",
        "priorLaunchCount": classified,
        "classifiedOutcomeCount": classified,
        "unresolvedOutcomeCount": 0,
        "unsellableOutcomeCount": 0,
        "catastrophicLossCount": adverse,
        "exitFailureCount": 0,
        "liquidityCollapseCount": 0,
        "normalLossCount": 0 if positive else 1,
        "normalWinCount": normal_win,
        "fatTailWinCount": 0,
        "sourceFactIds": [f"fact-{i}"],
    }

    legs = []
    notionals = [250_000, 500_000, 1_000_000, 2_000_000, 5_000_000]
    for j, notional in enumerate(notionals):
        base = notional * 1_000_000
        tokens = notional * (100 + i)
        recovery = 9_600 if positive else 7_500
        quote_state = {
            "curve": addr(50_000 + i),
            "pairToken": addr(0),
            "shadowRecipient": addr(999),
            "quoteReserve": str(10**18 + i * 10**14),
            "tokenReserve": str(10**24 + i * 10**20),
            "trackedQuote": str(4 * 10**17 + i * 10**13),
            "sellableTokens": str(7 * 10**23),
            "feeBps": "100",
            "creatorTaxBps": str(25 if positive else 75),
            "snipeTaxBps": "0",
            "effectiveSnipeTaxBps": "0",
            "amountInRequested": str(base),
            "amountInExecutable": str(base),
            "amountOut": str(tokens),
            "feeAmount": "1",
            "creatorTaxAmount": "1",
            "snipeTaxAmount": "0",
            "partialFill": False,
            "executable": True,
            "failureReason": None,
            "marketState": "CURVE_ACTIVE",
            "sourceAuthorityDigest": h(30_000 + i * 10 + j),
        }
        legs.append(
            {
                "notionalUsdMicros": str(notional),
                "baseAmount": str(base),
                "entry": {
                    "quoteId": h(40_000 + i * 10 + j),
                    "observedAtMs": 1_789_000_000_000 + i * 60_000 + j,
                    "executable": True,
                    "amountIn": str(base),
                    "amountOut": str(tokens),
                    "failureReason": None,
                    "gasEstimate": "100000",
                    "quoteState": quote_state,
                },
                "reverse": {
                    "quoteId": h(50_000 + i * 10 + j),
                    "observedAtMs": 1_789_000_000_100 + i * 60_000 + j,
                    "executable": True,
                    "amountIn": str(tokens),
                    "amountOut": str(base * recovery // 10_000),
                    "failureReason": None,
                    "gasEstimate": "120000",
                    "sourceAuthorityDigest": h(60_000 + i * 10 + j),
                },
                "independentReverseRecoveryBps": str(recovery),
            }
        )

    policy_digest = h(70_000 + i)
    comparison = {
        "receiptVersion": "SHADOW_POLICY_DECISION_RECEIPTS_R1",
        "comparisonId": h(71_000 + i),
        "launchId": launch_id,
        "baselineId": baseline_id,
        "decisionBlock": str(decision_block),
        "inputDigest": h(72_000 + i),
        "receipts": {
            "r0": {
                "hypotheticalAction": "WOULD_TRADE",
            },
            "r1": {
                "hypotheticalAction": "WOULD_TRADE" if positive else "WOULD_SKIP",
            },
            "buyEveryExecutableControl": {
                "hypotheticalAction": "WOULD_TRADE" if c0_trade else "WOULD_SKIP",
            },
        },
        "evidenceDigest": policy_digest,
        "mode": "SHADOW_ONLY",
        "liveMoneyAuthority": False,
        "edge": "UNPROVEN",
    }

    core = {
        "chainId": 4663,
        "ecosystem": "ROBINHOOD",
        "launchProtocol": "PONS",
        "launch": {
            "launchId": launch_id,
            "eventId": f"event-{i}",
            "factory": addr(100),
            "txHash": "0x" + h(80_000 + i),
            "blockNumber": str(launch_block),
            "blockHash": "0x" + h(81_000 + i),
            "logIndex": i,
            "token": addr(1_000 + i),
            "creator": addr(2_000 + i),
            "name": f"Candidate {i}",
            "symbol": f"S{i}",
            "observedAtMs": 1_789_000_000_000 + i * 60_000,
            "launchConfigId": "7",
            "graduationThreshold": str(10**18),
            "curve": addr(50_000 + i),
            "pairToken": addr(0),
            "sourceAuthorityDigest": h(82_000 + i),
        },
        "baseline": {
            "baselineId": baseline_id,
            "authorityDigest": h(83_000 + i),
            "policyVersion": "EXECUTABLE_BASELINE_R1",
            "decisionBlock": str(decision_block),
            "decisionBlockHash": "0x" + h(84_000 + i),
            "observedAtMs": 1_789_000_000_500 + i * 60_000,
            "status": "COMPLETE",
            "reason": None,
            "marketId": f"market-{i}",
            "venue": "PONS_V2_BONDING_CURVE",
            "baseAsset": addr(0),
            "reverseSemantics": "INDEPENDENT_SAME_STATE_NOT_SEQUENTIAL",
            "capacitySemantics": CAPACITY_SEMANTICS,
            "legs": legs,
        },
        "creatorHistory": creator,
        "executionPersona": {
            "recipient": addr(999),
            "recipientRole": "PONS_V2_SHADOW_QUOTE_RECIPIENT",
            "parity": PERSONA_PARITY,
            "sourceQuoteSchema": "ROBINHOOD_PONS_V2_CURVE_QUOTE_R1",
            "snipeTaxBps": "0",
            "effectiveSnipeTaxBps": "0",
            "adapterInvariants": [
                "RECIPIENT_HAS_NO_CODE",
                "RECIPIENT_NOT_SNIPE_TAX_EXEMPT",
            ],
        },
        "timing": {
            "clockSemantics": "LOCAL_CAPTURE_WALL_CLOCK_NOT_CHAIN_TIMESTAMP",
            "launchObservedAtMs": 1_789_000_000_000 + i * 60_000,
            "baselineObservedAtMs": 1_789_000_000_500 + i * 60_000,
            "firstQuoteObservedAtMs": 1_789_000_000_600 + i * 60_000,
            "lastQuoteObservedAtMs": 1_789_000_000_700 + i * 60_000,
            "decisionDelayBlocks": "2",
        },
        "diagnosticEntityEdges": [],
        "policyComparison": comparison,
        "boundaries": {
            "pointInTimeDecisionBlock": str(decision_block),
            "containsTargetLaunchFutureOutcome": False,
            "entityEdgesAtOrBeforeDecisionOnly": True,
            "mode": "SHADOW_ONLY",
            "liveMoneyAuthority": False,
            "edge": "UNPROVEN",
        },
    }
    packet_id = canonical_sha256(
        {
            "kind": FEATURE_SCHEMA,
            "launchId": launch_id,
            "baselineId": baseline_id,
            "baselineAuthorityDigest": core["baseline"]["authorityDigest"],
            "creatorEvidenceDigest": creator["evidenceDigest"],
            "policyEvidenceDigest": policy_digest,
            "entityEdgeDigests": [],
        }
    )
    material = {"schemaVersion": FEATURE_SCHEMA, "packetId": packet_id, **core}
    return {**material, "evidenceDigest": canonical_sha256(material)}


def _outcome_packet(i: int, *, positive: bool) -> dict:
    launch_id = f"launch-{i:03d}"
    baseline_id = f"baseline-{i:03d}"
    decision_block = 100_000 + i * 100
    outcome_block = decision_block + 200
    gross = 1_250_000 if positive else 700_000
    classification = "NORMAL_WIN" if positive else "NORMAL_LOSS"
    cost_digest = h(90_000 + i)
    core = {
        "chainId": 4663,
        "ecosystem": "ROBINHOOD",
        "launchProtocol": "PONS",
        "launchId": launch_id,
        "baselineId": baseline_id,
        "outcomeId": h(91_000 + i),
        "horizonMs": TARGET_HORIZON_MS,
        "observedBlock": str(outcome_block),
        "observedBlockHash": "0x" + h(92_000 + i),
        "targetTimestampMs": 1_789_086_400_000 + i * 60_000,
        "observedTimestampMs": 1_789_086_401_000 + i * 60_000,
        "status": "COMPLETE",
        "reason": None,
        "entryNotionalUsdMicros": "1000000",
        "exitExecutable": True,
        "baseAsset": addr(0),
        "baseAmountOut": str(gross * 1_000_000),
        "grossExecutableValueUsdMicros": str(gross),
        "grossExecutableReturnBps": str(gross * 10_000 // 1_000_000),
        "classification": classification,
        "liquidityState": "SURVIVED",
        "slippageBps": "20",
        "costProjection": {
            "status": "COMPLETE",
            "executionCostPolicyVersion": "PONS_S0_FULL_EXECUTION_COST_V1",
            "executionCostUsdMicros": "20000",
            "executionCostEvidenceDigest": cost_digest,
            "netExecutableValueUsdMicros": str(gross - 20_000),
            "netExecutableReturnBps": str((gross - 20_000) * 10_000 // 1_000_000),
            "semantics": "GROSS_EXECUTABLE_VALUE_MINUS_VERIFIED_FULL_EXECUTION_COST",
        },
        "outcomeAuthorityDigest": h(93_000 + i),
        "sourceAuthorityDigest": h(94_000 + i),
        "boundaries": {
            "postOutcomeEvidence": True,
            "forbiddenAsFeatureInput": True,
            "mode": "SHADOW_ONLY",
            "liveMoneyAuthority": False,
            "edge": "UNPROVEN",
        },
    }
    packet_id = canonical_sha256(
        {
            "kind": OUTCOME_SCHEMA,
            "launchId": launch_id,
            "baselineId": baseline_id,
            "horizonMs": TARGET_HORIZON_MS,
            "outcomeId": core["outcomeId"],
            "outcomeAuthorityDigest": core["outcomeAuthorityDigest"],
            "executionCostEvidenceDigest": cost_digest,
        }
    )
    material = {"schemaVersion": OUTCOME_SCHEMA, "packetId": packet_id, **core}
    return {**material, "evidenceDigest": canonical_sha256(material)}


def _write_bundle(
    root: Path,
    count: int = 72,
    *,
    c0_skip_indices: frozenset[int] = frozenset(),
) -> tuple[Path, Path, Path]:
    features = []
    outcomes = []
    for i in range(count):
        positive = i % 3 != 0
        features.append(
            _feature_packet(
                i,
                positive=positive,
                c0_trade=i not in c0_skip_indices,
            )
        )
        outcomes.append(_outcome_packet(i, positive=positive))
    feature_bytes = b"".join(canonical_bytes(row) + b"\n" for row in features)
    outcome_bytes = b"".join(canonical_bytes(row) + b"\n" for row in outcomes)
    feature_sha = hashlib.sha256(feature_bytes).hexdigest()
    outcome_sha = hashlib.sha256(outcome_bytes).hexdigest()
    core = {
        "featureSchema": FEATURE_SCHEMA,
        "outcomeSchema": OUTCOME_SCHEMA,
        "featurePacketCount": len(features),
        "outcomePacketCount": len(outcomes),
        "featureStreamSha256": feature_sha,
        "outcomeStreamSha256": outcome_sha,
        "featurePacketDigests": [row["evidenceDigest"] for row in features],
        "outcomePacketDigests": [row["evidenceDigest"] for row in outcomes],
        "separation": {
            "featureAndOutcomeStreamsDistinct": True,
            "featurePacketsContainTargetFutureOutcome": False,
            "outcomePacketsForbiddenAsFeatureInput": True,
        },
        "mode": "SHADOW_ONLY",
        "liveMoneyAuthority": False,
        "edge": "UNPROVEN",
    }
    manifest_id = canonical_sha256(
        {
            "kind": MANIFEST_SCHEMA,
            "featureStreamSha256": feature_sha,
            "outcomeStreamSha256": outcome_sha,
            "featurePacketCount": len(features),
            "outcomePacketCount": len(outcomes),
        }
    )
    material = {"schemaVersion": MANIFEST_SCHEMA, "manifestId": manifest_id, **core}
    manifest = {**material, "evidenceDigest": canonical_sha256(material)}
    root.mkdir(parents=True, exist_ok=True)
    features_path = root / "features.jsonl"
    outcomes_path = root / "outcomes.jsonl"
    manifest_path = root / "manifest.json"
    features_path.write_bytes(feature_bytes)
    outcomes_path.write_bytes(outcome_bytes)
    manifest_path.write_bytes(canonical_bytes(manifest) + b"\n")
    return manifest_path, features_path, outcomes_path


def test_preregistered_denominator_is_exactly_four():
    config = load_screen_config(CONFIG_PATH)
    assert config["screen_id"] == SCREEN_ID
    assert config["target_horizon_ms"] == TARGET_HORIZON_MS
    assert config["registered_variant_denominator"] == 4
    assert config["variants"] == list(FROZEN_VARIANTS)
    assert REGISTERED_VARIANT_DENOMINATOR == 4
    assert config["promotion_authority"] == "NONE"
    assert (
        config["research_universe"]
        == "C0_MECHANICALLY_ADMISSIBLE_WITH_RESOLVED_24H_OUTCOME"
    )


def test_export_integrity_and_tamper_fail_closed(tmp_path: Path):
    manifest, features, outcomes = _write_bundle(tmp_path / "bundle")
    loaded = load_export_bundle(
        manifest_path=manifest,
        features_path=features,
        outcomes_path=outcomes,
    )
    assert len(loaded.features) == 72
    assert len(loaded.outcomes) == 72

    original = features.read_bytes()
    features.write_bytes(original + b" ")
    with pytest.raises(PonsS0ScreenError, match="feature stream SHA-256 mismatch"):
        load_export_bundle(
            manifest_path=manifest,
            features_path=features,
            outcomes_path=outcomes,
        )


def test_model_universe_cannot_override_mechanical_c0_gate(tmp_path: Path):
    manifest, features, outcomes = _write_bundle(
        tmp_path / "bundle",
        c0_skip_indices=frozenset({5, 11}),
    )
    bundle = load_export_bundle(
        manifest_path=manifest,
        features_path=features,
        outcomes_path=outcomes,
    )
    rows, coverage = build_screen_rows(bundle)
    assert coverage["resolved_target_count"] == 72
    assert coverage["mechanically_admissible_resolved_count"] == 70
    assert coverage["mechanically_inadmissible_resolved_count"] == 2
    assert coverage["mechanically_inadmissible_resolved_launch_ids"] == [
        "launch-005",
        "launch-011",
    ]
    assert all(row.c0_trade for row in rows)
    assert {row.launch_id for row in rows}.isdisjoint({"launch-005", "launch-011"})


def test_block_embargo_excludes_labels_not_known_by_test_decision(tmp_path: Path):
    manifest, features, outcomes = _write_bundle(tmp_path / "bundle")
    bundle = load_export_bundle(
        manifest_path=manifest,
        features_path=features,
        outcomes_path=outcomes,
    )
    rows, coverage = build_screen_rows(bundle)
    assert coverage["resolved_target_count"] == 72
    folds = build_folds(rows, min_train_rows=30, test_rows=10, max_folds=3)
    assert len(folds) == 3
    for fold in folds:
        assert fold.max_train_outcome_block < fold.first_test_decision_block
        for index in fold.train_indices:
            assert rows[index].outcome_block < fold.first_test_decision_block
        assert not set(fold.train_indices) & set(fold.test_indices)


def test_end_to_end_screen_reuses_append_only_ledger_without_promotion(tmp_path: Path):
    manifest, features, outcomes = _write_bundle(tmp_path / "bundle")
    research_root = tmp_path / "research"
    output = tmp_path / "runs"
    result = run_screen(
        manifest_path=manifest,
        features_path=features,
        outcomes_path=outcomes,
        config_path=CONFIG_PATH,
        output_root=output,
        research_root=research_root,
    )
    receipt = result["receipt"]
    assert receipt["verdict"] == "EXPLORATORY_SCREEN_COMPLETE_NO_PROMOTION"
    assert receipt["candidate_artifact"] is None
    assert receipt["automatic_winner_selection"] is False
    assert receipt["promotion_authority"] == "NONE"
    assert receipt["live_money_authority"] is False
    assert receipt["edge"] == "UNPROVEN"
    assert len(receipt["variants"]) == 4
    assert len(receipt["folds"]) == 3
    assert receipt["no_feature_probability_baseline"]["observation_count"] > 0
    assert all(
        fold["label_availability_embargo_satisfied"] for fold in receipt["folds"]
    )

    for model in ("PONS_S0_M1_LOGISTIC", "PONS_S0_M2_HIST_GRADIENT_BOOSTING"):
        metrics = receipt["variants"][model]["probability"]
        assert metrics["observation_count"] > 0
        assert 0 <= metrics["brier_score"] <= 1
        assert metrics["log_loss"] >= 0
        assert 0 <= metrics["accuracy"] <= 1
        assert 0 <= metrics["balanced_accuracy"] <= 1
        assert 0 <= metrics["no_feature_brier_score"] <= 1
        assert metrics["no_feature_log_loss"] >= 0
        assert isinstance(metrics["brier_improvement_vs_no_feature"], float)
        assert isinstance(metrics["log_loss_improvement_vs_no_feature"], float)

    history = load_canonical_history(research_root)
    proposals = [
        event for event in history.candidates if event["event_type"] == "CANDIDATE_PROPOSED"
    ]
    assert len(proposals) == 4
    assert len(history.trials) == 4
    assert {
        event["registered_variant_denominator"] for event in proposals
    } == {4}
    assert {
        event["required_input_kind"] for event in proposals
    } == {"SENTRY_PONS_S0_EXPORT_V1"}
    config = load_screen_config(CONFIG_PATH)
    assert all(
        event["recorded_at_utc"] > config["preregistered_at_utc"]
        for event in proposals
    )
    assert not doctor(research_root)

    for variant in FROZEN_VARIANTS:
        path = output / variant["strategy_id"].lower() / "run_receipt.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["candidate_artifact"] is None
        assert data["promotion_authority"] == "NONE"
        assert data["live_money_authority"] is False
        assert data["registered_variant_denominator"] == 4
