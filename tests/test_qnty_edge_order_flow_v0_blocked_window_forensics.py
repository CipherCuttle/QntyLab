import hashlib
import json
from pathlib import Path

from qntylab.qnty_edge_order_flow_v0_blocked_window_forensics import (
    BASE,
    TARGET_ROWS,
    build_artifact,
)


ROOT = Path(__file__).resolve().parents[1]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_forensic_artifact_is_deterministic_and_preserves_exact_scope():
    path = BASE / "blocked_window_forensics.json"
    committed = json.loads(path.read_text())
    assert committed == build_artifact()
    assert committed["exact_blocked_rows"] == [
        {"symbol": symbol, "period_id": period_id} for symbol, period_id in TARGET_ROWS
    ]
    assert len(committed["per_window_records"]) == 14
    assert len({(r["symbol"], r["period_id"]) for r in committed["per_window_records"]}) == 14


def test_classification_and_firewall_invariants():
    artifact = json.loads((BASE / "blocked_window_forensics.json").read_text())
    records = artifact["per_window_records"]
    assert {r["primary_classification"] for r in records} == {"C. GENUINE_FROZEN_SOURCE_ABSENCE"}
    assert artifact["aggregate"] == {
        "A_COUNT": 0,
        "B_COUNT": 0,
        "C_COUNT": 14,
        "D_COUNT": 0,
        "exactly_one_primary_class_per_row": True,
        "total_blocked": 14,
    }
    assert artifact["repairability_assessment"]["ALL_RECOVERABLE_UNDER_EXISTING_FROZEN_CONTRACT"] == "NO"
    assert artifact["repairability_assessment"]["ANY_GENUINE_FROZEN_SOURCE_ABSENCE"] == "YES"
    assert artifact["repairability_assessment"]["ANY_SCIENTIFIC_CONTRACT_CHANGE_REQUIRED_TO_REACH_60_OF_60"] == "YES"
    assert all(value is False for value in artifact["outcome_firewall"].values() if isinstance(value, bool))
    assert artifact["ledger_state"] == {
        "H010_untouched": True,
        "new_candidate_proposed_events": 0,
        "new_candidate_reopened_events": 0,
        "new_trial_completed_events": 0,
    }


def test_immutable_predecessor_and_frozen_identity_are_bound():
    artifact = json.loads((BASE / "blocked_window_forensics.json").read_text())
    assert artifact["predecessor_integrity"]["input_ready_windows"] == 46
    assert artifact["predecessor_integrity"]["blocked_windows"] == 14
    assert artifact["predecessor_integrity"]["required_asset_period_windows"] == 60
    assert artifact["frozen_identity"] == {
        "candidate_id": "CANDIDATE_ORDER_FLOW_SIGNED_TAKER_NOTIONAL_V0",
        "variant_id": "variant_23f758ef7052522d70172239",
        "proposal_event_id": "event_proposal_order_flow_v0_20260815",
        "preregistration_digest": "8e75f53f19c9719b97c3626c7e39626e206505e138107601748d9213eabe7757",
        "preregistration_json_sha256": "34252ccf245c9d963b987e697231d4a33d66c2450d44689b7b737c0686a24979",
        "universe_digest": "becdf4bd2157ebbad416526f414c3b9f647e8832753a61642d8a5d60b6620bcd",
        "feature_digest": "4db4f40cebc5f476727ef624281404b5443cddb49548eceeffa513118926c481",
        "cost_digest": "efb39c8f1635e833957f19148637afd527c1bb0584950084c3a6c36d0bc82877",
        "source_contract": "BINANCE_USD_M_PERPETUAL_1H_MATERIALIZER_V0",
        "input_snapshot_digest": "c4fb706307eea5cea1868675b71de5e8b251d07b8b9e8542108a037de77496bf",
        "source_manifest_digest": "fcfb94e0478b6d439140249f1c5d9e1ad18940b510a893d214856f49c64c67b2",
        "qualification_digest": "62da233fa185dd86257853747c4d8e4ae5af52e4580e492ec555d9661f4fa4da",
        "materialization_receipt_digest": "4e03f5d116da071fdc83aa23ed6bbac5b226510c93d00e4195d6f402a54b6944",
    }
    for name, digest in artifact["predecessor_artifact_sha256"].items():
        assert sha256(BASE / name) == digest


def test_source_absence_is_provider_or_lifecycle_evidence_not_local_cache_absence():
    artifact = json.loads((BASE / "blocked_window_forensics.json").read_text())
    for record in artifact["per_window_records"]:
        assert record["classification_evidence"]["no_alternate_source_used"] is True
        assert record["provider_object_exists"]["price"] is False or record["provider_object_exists"]["funding"] is False or record["observed_gap_or_missing_range"]["price"]
        if record["symbol"] == "REEFUSDT":
            assert record["observed_gap_or_missing_range"]["funding"]
            assert record["instrument_existed_for_required_window"] is False
        elif record["symbol"] in {"XRPUSDT", "LTCUSDT", "TRXUSDT", "XLMUSDT", "SANDUSDT", "ONEUSDT"}:
            assert record["observed_gap_or_missing_range"]["price"]
            assert record["provider_object_exists"] == {"price": True, "funding": True}
        else:
            assert record["instrument_existed_for_required_window"] is False


def test_qntyagenteval_is_not_applicable():
    artifact = json.loads((BASE / "blocked_window_forensics.json").read_text())
    assert artifact["qntyagenteval_applicability"] == {
        "bounded_lookup_count": 1,
        "evaluator_built": False,
        "match": "NO_MATCH",
    }
