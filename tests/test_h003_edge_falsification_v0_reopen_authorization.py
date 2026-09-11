from __future__ import annotations

import json
from pathlib import Path

import pytest

from qntylab.research_ledger import LedgerError, compute_trial_id, preflight, sha256_path


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_ROOT = ROOT / "experiments/research"
AUTH = ROOT / "experiments/specs/h003_edge_falsification_v0_trial_authorization.json"
REOPEN = ROOT / "experiments/research/h003_edge_falsification_v0/reopen_event.json"
ANALYSIS = ROOT / "experiments/specs/h003_edge_falsification_v0_analysis_contract.json"
TRIAL_INDEX = RESEARCH_ROOT / "trial_index.json"
STATE = RESEARCH_ROOT / "state.json"

VARIANT_ID = "variant_00eb140f03a5f6ab40600160"
CANDIDATE_ID = "CANDIDATE_H003_MA_48_192_LONG_FLAT"
CANONICAL_SHA = "64bdb27a31003b0de25f3802affa8b412143a50bc8a5b76a399924626b01174a"
V0_REOPEN_EVENT_ID = "event_reopen_h003_edge_falsification_v0"
V1_ACTIVATION_REOPEN_EVENT_ID = "event_reopen_h003_defensive_followup_v1_activation"
V2_PROSPECTIVE_REOPEN_EVENT_ID = "event_reopen_h003_defensive_followup_v1_prospective_v2"
V2_PROSPECTIVE_CONTRACT_PATH = "experiments/specs/h003_defensive_followup_v1_prospective_reopen_v2.json"


def _config(*, start: str, end: str, fee_bps: float, slippage_bps: float, research_intent: str = "FOLLOW_UP") -> dict:
    return {
        "candidate_id": CANDIDATE_ID,
        "strategy_id": "H003_moving_average",
        "strategy_version": "existing-qntylab-strategies-v1",
        "parameters": {"fast": 48, "slow": 192, "mode": "long_flat"},
        "funding_boundary_mode": "NOT_APPLICABLE",
        "expected_interval": "1h",
        "gap_policy": "REJECT",
        "evaluation_start": start,
        "evaluation_end": end,
        "fee_bps": fee_bps,
        "slippage_bps": slippage_bps,
        "research_intent": research_intent,
    }


def test_reopen_contract_hash_and_trial_ids_are_frozen_from_declared_matrix() -> None:
    event = json.loads(REOPEN.read_text(encoding="utf-8"))
    contract = json.loads(AUTH.read_text(encoding="utf-8"))

    assert event["authorization_contract_path"] == "experiments/specs/h003_edge_falsification_v0_trial_authorization.json"
    assert event["authorization_contract_sha256"] == sha256_path(AUTH)
    assert contract["reopen_event_id"] == event["event_id"]
    assert contract["candidate_id"] == CANDIDATE_ID
    assert contract["variant_id"] == VARIANT_ID
    assert contract["allowed_research_intents"] == ["FOLLOW_UP"]

    metadata = contract["metadata"]
    computed = {
        compute_trial_id(
            variant_id=VARIANT_ID,
            symbol=metadata["symbol"],
            input_sha256=window["input_sha256"],
            evaluation_start=window["evaluation_start"],
            evaluation_end=window["evaluation_end"],
            fee_bps=float(cost["fee_bps"]),
            slippage_bps=float(cost["slippage_bps"]),
            gap_policy=metadata["gap_policy"],
            expected_interval=metadata["expected_interval"],
        )
        for window in metadata["windows"]
        for cost in metadata["cost_modes"]
    }
    assert len(metadata["windows"]) == 11
    assert len(metadata["cost_modes"]) == 4
    assert len(computed) == 44
    assert computed == set(contract["authorized_trial_ids"])


def test_causal_boundary_contract_requires_193_pre_reporting_closes() -> None:
    contract = json.loads(AUTH.read_text(encoding="utf-8"))
    analysis = json.loads(ANALYSIS.read_text(encoding="utf-8"))

    assert contract["metadata"]["minimum_pre_reporting_closes"] == 193
    assert analysis["state_continuity"]["minimum_pre_block_history_closes"] == 193
    windows = {row["id"]: row for row in contract["metadata"]["windows"]}
    assert windows["BLOCK_2022"]["evaluation_start"] == "2021-12-23T23:00:00Z"
    assert windows["BLOCK_2024"]["evaluation_start"] == "2023-12-23T23:00:00Z"
    assert windows["BLOCK_2025"]["evaluation_start"] == "2024-12-23T23:00:00Z"
    assert windows["BLOCK_2026_TO_FREEZE"]["evaluation_start"] == "2025-12-23T23:00:00Z"
    assert contract["metadata"]["excluded_windows"] == [
        {
            "id": "BLOCK_2021_SEGMENT_04",
            "evaluation_start": "2021-04-20T04:00:00Z",
            "evaluation_end": "2021-04-25T04:00:00Z",
            "reason": "121_CLOSES_LT_193_MINIMUM",
        }
    ]


def test_central_preflight_enforces_reopen_authorization_and_duplicate_lifecycle() -> None:
    allowed = _config(
        start="2021-12-23T23:00:00Z",
        end="2022-12-31T23:00:00Z",
        fee_bps=10,
        slippage_bps=0,
    )
    state = json.loads(STATE.read_text(encoding="utf-8"))
    variant_state = state["variants"][VARIANT_ID]

    # A later terminal decision blocks all trials until a new scoped reopen.
    if variant_state["status"] == "BLOCKED":
        assert variant_state["latest_decision_event_id"] is not None
        for config in (
            allowed,
            dict(allowed, evaluation_start="2021-12-24T00:00:00Z"),
            dict(allowed, fee_bps=7),
            dict(allowed, research_intent="SCREEN"),
        ):
            with pytest.raises(LedgerError, match="latest variant state BLOCKED"):
                preflight(config=config, symbol="SOLUSDT", input_sha256=CANONICAL_SHA, root=RESEARCH_ROOT)
        return

    active_reopen = variant_state.get("active_reopen_event_id")
    if active_reopen == V1_ACTIVATION_REOPEN_EVENT_ID:
        # V0 SOL trials are outside the activation generation. They must fail at
        # the active authorization boundary even if already completed.
        for config in (
            allowed,
            dict(allowed, evaluation_start="2021-12-24T00:00:00Z"),
            dict(allowed, fee_bps=7),
        ):
            with pytest.raises(LedgerError, match="trial not authorized by active reopen contract"):
                preflight(config=config, symbol="SOLUSDT", input_sha256=CANONICAL_SHA, root=RESEARCH_ROOT)
        with pytest.raises(LedgerError, match="research_intent not authorized by active reopen contract"):
            preflight(
                config=dict(allowed, research_intent="SCREEN"),
                symbol="SOLUSDT",
                input_sha256=CANONICAL_SHA,
                root=RESEARCH_ROOT,
            )
        return

    if active_reopen == V2_PROSPECTIVE_REOPEN_EVENT_ID:
        # The explicit prospective-only generation must not reactivate any V0
        # historical SOL trial. Its active contract is exact and recorder-only.
        assert variant_state["status"] == "SCREENING"
        assert variant_state["latest_decision_event_id"] is None
        assert variant_state["reopen_authorization_contract_path"] == V2_PROSPECTIVE_CONTRACT_PATH
        for config in (
            allowed,
            dict(allowed, evaluation_start="2021-12-24T00:00:00Z"),
            dict(allowed, fee_bps=7),
        ):
            with pytest.raises(LedgerError, match="trial not authorized by active reopen contract"):
                preflight(config=config, symbol="SOLUSDT", input_sha256=CANONICAL_SHA, root=RESEARCH_ROOT)
        with pytest.raises(LedgerError, match="research_intent not authorized by active reopen contract"):
            preflight(
                config=dict(allowed, research_intent="SCREEN"),
                symbol="SOLUSDT",
                input_sha256=CANONICAL_SHA,
                root=RESEARCH_ROOT,
            )
        return

    assert active_reopen in {None, V0_REOPEN_EVENT_ID}
    allowed_trial_id = compute_trial_id(
        variant_id=VARIANT_ID,
        symbol="SOLUSDT",
        input_sha256=CANONICAL_SHA,
        evaluation_start=allowed["evaluation_start"],
        evaluation_end=allowed["evaluation_end"],
        fee_bps=float(allowed["fee_bps"]),
        slippage_bps=float(allowed["slippage_bps"]),
        gap_policy=allowed["gap_policy"],
        expected_interval=allowed["expected_interval"],
    )
    trial_index = json.loads(TRIAL_INDEX.read_text(encoding="utf-8"))
    if allowed_trial_id in trial_index["trials"]:
        with pytest.raises(LedgerError, match="exact trial already completed"):
            preflight(config=allowed, symbol="SOLUSDT", input_sha256=CANONICAL_SHA, root=RESEARCH_ROOT)
    else:
        binding = preflight(config=allowed, symbol="SOLUSDT", input_sha256=CANONICAL_SHA, root=RESEARCH_ROOT)
        assert binding["variant_id"] == VARIANT_ID
        assert binding["reopen_authorization_id"] == "H003_EDGE_FALSIFICATION_V0"

    unauthorized_window = dict(allowed, evaluation_start="2021-12-24T00:00:00Z")
    with pytest.raises(LedgerError, match="not authorized by active reopen contract"):
        preflight(config=unauthorized_window, symbol="SOLUSDT", input_sha256=CANONICAL_SHA, root=RESEARCH_ROOT)

    unauthorized_cost = dict(allowed, fee_bps=7)
    with pytest.raises(LedgerError, match="not authorized by active reopen contract"):
        preflight(config=unauthorized_cost, symbol="SOLUSDT", input_sha256=CANONICAL_SHA, root=RESEARCH_ROOT)

    unauthorized_intent = dict(allowed, research_intent="SCREEN")
    with pytest.raises(LedgerError, match="research_intent not authorized by active reopen contract"):
        preflight(config=unauthorized_intent, symbol="SOLUSDT", input_sha256=CANONICAL_SHA, root=RESEARCH_ROOT)
