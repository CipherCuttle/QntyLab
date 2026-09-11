from __future__ import annotations

import json
from pathlib import Path

import pytest

from qntylab.h003_defensive_followup_v1_activation import (
    ASSETS,
    AUTHORIZATION_ID,
    COST_MODES,
    VARIANT_ID,
    WINDOWS,
    build_authorization_contract,
    diagnostic_trial_rows,
)
from qntylab.research_ledger import LedgerError, preflight


ROOT = Path(__file__).resolve().parents[1]
RESEARCH_ROOT = ROOT / "experiments/research"
AUTH_PATH = ROOT / "experiments/specs/h003_defensive_followup_v1_activation.json"
REOPEN_PATH = ROOT / "experiments/research/h003_defensive_followup_v1/activation_reopen_event.json"
STATE_PATH = RESEARCH_ROOT / "state.json"
REOPEN_EVENT_ID = "event_reopen_h003_defensive_followup_v1_activation"


def _config(row: dict, *, research_intent: str = "FOLLOW_UP") -> dict:
    return {
        "candidate_id": "CANDIDATE_H003_MA_48_192_LONG_FLAT",
        "strategy_id": "H003_moving_average",
        "strategy_version": "existing-qntylab-strategies-v1",
        "parameters": {"fast": 48, "slow": 192, "mode": "long_flat"},
        "funding_boundary_mode": "NOT_APPLICABLE",
        "expected_interval": "1h",
        "gap_policy": "REJECT",
        "evaluation_start": row["evaluation_start"],
        "evaluation_end": row["evaluation_end"],
        "fee_bps": row["fee_bps"],
        "slippage_bps": row["slippage_bps"],
        "research_intent": research_intent,
    }


def test_compiler_freezes_exact_88_prior_exposed_diagnostic_trials() -> None:
    rows = diagnostic_trial_rows()
    assert len(ASSETS) == 2
    assert len(WINDOWS) == 11
    assert len(COST_MODES) == 4
    assert len(rows) == 88
    assert len({row["trial_id"] for row in rows}) == 88
    assert sum(row["symbol"] == "BTCUSDT" for row in rows) == 44
    assert sum(row["symbol"] == "ETHUSDT" for row in rows) == 44
    assert {row["cost_mode"] for row in rows} == {
        "zero_cost_diagnostic",
        "baseline",
        "stress",
        "severe_stress",
    }
    assert {row["window_id"] for row in rows} == {row["id"] for row in WINDOWS}


def test_2023_uses_asset_specific_normalized_input_and_2026_end_is_frozen() -> None:
    rows = diagnostic_trial_rows()
    btc_2023 = {row["input_sha256"] for row in rows if row["symbol"] == "BTCUSDT" and row["window_id"] == "BLOCK_2023_KNOWN_HOLDOUT"}
    eth_2023 = {row["input_sha256"] for row in rows if row["symbol"] == "ETHUSDT" and row["window_id"] == "BLOCK_2023_KNOWN_HOLDOUT"}
    assert btc_2023 == {"08d5649e86743e9485fb55a3978b96f7b0b5483b33223534d52d4fe0a745d10e"}
    assert eth_2023 == {"a3cfb7733aad701b43fd383ac32f52252d229d2275147698449b2007bdff0d40"}
    assert {row["evaluation_end"] for row in rows if row["window_id"] == "BLOCK_2026_TO_FREEZE"} == {"2026-07-28T18:00:00Z"}


def test_authorization_arms_recorder_but_cannot_start_it() -> None:
    contract = build_authorization_contract(reopen_event_id=REOPEN_EVENT_ID)
    assert contract["authorization_id"] == AUTHORIZATION_ID
    assert contract["reopen_event_id"] == REOPEN_EVENT_ID
    assert len(contract["authorized_trial_ids"]) == 88
    recorder = contract["metadata"]["prospective_recorder"]
    assert recorder["status"] == "ARMED_BUT_INACTIVE_PENDING_ORIGIN_ARTIFACT"
    assert recorder["assets"] == ["SOLUSDT", "BTCUSDT", "ETHUSDT"]
    assert recorder["origin"] is None
    assert recorder["market_data_recording_authorized"] is False
    assert recorder["signal_recording_authorized"] is False
    assert recorder["economic_verdict_authorized"] is False
    assert recorder["origin_artifact_requires_separate_git_commit"] is True


def test_materialized_contract_matches_compiler_when_present() -> None:
    if not AUTH_PATH.exists():
        pytest.skip("activation contract is materialized by the bounded workflow")
    contract = json.loads(AUTH_PATH.read_text(encoding="utf-8"))
    assert contract == build_authorization_contract(reopen_event_id=REOPEN_EVENT_ID)
    assert REOPEN_PATH.is_file()


def test_active_reopen_allows_only_exact_authorized_diagnostic_ids_when_materialized() -> None:
    if not AUTH_PATH.exists() or not REOPEN_PATH.exists():
        pytest.skip("activation is not materialized yet")
    state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    variant = state["variants"][VARIANT_ID]
    assert variant["active_reopen_event_id"] == REOPEN_EVENT_ID
    assert variant["reopen_authorization_contract_path"] == "experiments/specs/h003_defensive_followup_v1_activation.json"

    row = diagnostic_trial_rows()[0]
    binding = preflight(
        config=_config(row),
        symbol=row["symbol"],
        input_sha256=row["input_sha256"],
        root=RESEARCH_ROOT,
    )
    assert binding["trial_id"] == row["trial_id"]
    assert binding["reopen_authorization_id"] == AUTHORIZATION_ID

    unauthorized = dict(row, evaluation_start="2021-01-01T01:00:00Z")
    with pytest.raises(LedgerError, match="trial not authorized by active reopen contract"):
        preflight(
            config=_config(unauthorized),
            symbol=unauthorized["symbol"],
            input_sha256=unauthorized["input_sha256"],
            root=RESEARCH_ROOT,
        )

    with pytest.raises(LedgerError, match="research_intent not authorized by active reopen contract"):
        preflight(
            config=_config(row, research_intent="SCREEN"),
            symbol=row["symbol"],
            input_sha256=row["input_sha256"],
            root=RESEARCH_ROOT,
        )
