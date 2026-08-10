"""Research Factory V2 minimum seams — F1..F18 test matrix.

Covers the canonical family ontology, the instrument contract and its funding
boundary, V2 trial identity, native receipt fields, deterministic bar paths, and
the derived corpus index with its fail-closed pooling rules.
"""

import json
import subprocess
from pathlib import Path

import numpy as np
import pytest

from qntylab import bar_path, corpus_index, family_ontology, instrument_contract
from qntylab.research_ledger import (
    CORPUS_GENERATION_V1,
    CORPUS_GENERATION_V2,
    LedgerError,
    canonical_bytes,
    compute_trial_id,
    compute_trial_id_v2,
    compute_variant_id,
    event_id,
    load_canonical_history,
    rebuild,
    validate_trial_event,
)
from qntylab.strategy_test import run_strategy

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "daily_market_BTCUSDT_1h.csv"
COMMITTED_RESEARCH_ROOT = REPO_ROOT / "experiments" / "research"

SPOT = instrument_contract.BINANCE_SPOT_USDT_V1
PERP = instrument_contract.BINANCE_USDM_PERPETUAL_USDT_V1


# --------------------------------------------------------------------------
# fixtures
# --------------------------------------------------------------------------
def v2_config(tmp_path, *, name="config.json", **overrides):
    value = {
        "schema_version": 1,
        "strategy_id": "H002_momentum",
        "strategy_version": "existing-qntylab-strategies-v1",
        "input_path": str(FIXTURE),
        "evaluation_start": "2021-01-01T00:00:00Z",
        "evaluation_end": "2021-01-02T05:00:00Z",
        "initial_capital": 10000,
        "fee_bps": 10,
        "slippage_bps": 5,
        "funding_boundary_mode": "NOT_APPLICABLE",
        "gap_policy": "REJECT",
        "expected_interval": "1h",
        "candidate_id": "TEST_V2_MOMENTUM_3",
        "research_intent": "SCREEN",
        "parameters": {"lookback": 3, "mode": "long_flat"},
        "instrument_contract_id": SPOT,
        "funding_treatment": instrument_contract.FUNDING_NOT_APPLICABLE,
        "period_id": "2021_TEST",
        "cost_mode": "stress",
    }
    value.update(overrides)
    path = tmp_path / name
    path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    return path


def research_root(tmp_path, config_paths, *, family_id="time_series_momentum", name="research"):
    root = tmp_path / name
    (root / "trials").mkdir(parents=True, exist_ok=True)
    events = []
    for config_path in config_paths:
        config = json.loads(Path(config_path).read_text(encoding="utf-8"))
        event = {
            "event_id": "",
            "event_type": "CANDIDATE_PROPOSED",
            "candidate_id": config["candidate_id"],
            "family_id": family_id,
            "variant_id": compute_variant_id(config),
            "strategy_id": config["strategy_id"],
            "strategy_version": config["strategy_version"],
            "objective": "v2 seam fixture",
            "origin": "unit test",
            "mechanism": "unit test",
            "prediction": "unit test",
            "required_data": "unit test fixture",
            "decision_time": "unit test",
            "execution_time": "unit test",
            "benchmark": "unit test",
            "parameters": config["parameters"],
            "mode": config["parameters"]["mode"],
            "bar_interval": config["expected_interval"],
            "required_input_kind": "OHLCV_1H_CSV",
            "funding_boundary_mode": config["funding_boundary_mode"],
            "failure_condition": "unit test",
            "recorded_at_utc": "2026-08-10T00:00:00Z",
        }
        event["event_id"] = event_id("event_proposal", event)
        events.append(event)
    seen = {}
    for event in events:
        seen[event["variant_id"]] = event
    (root / "candidates.jsonl").write_bytes(b"".join(canonical_bytes(event) + b"\n" for event in seen.values()))
    (root / "decisions.jsonl").write_text("", encoding="utf-8")
    (root / "trials" / "2026.jsonl").write_text("", encoding="utf-8")
    rebuild(root)
    return root


def run_v2(tmp_path, config_path, *, out="run", root=None, evidence=None, monkeypatch=None):
    if monkeypatch is not None:
        monkeypatch.setenv(bar_path.EVIDENCE_ROOT_ENV, str(evidence or (tmp_path / "evidence")))
    return run_strategy(
        strategy_id=json.loads(config_path.read_text())["strategy_id"],
        input_path=FIXTURE,
        config_path=config_path,
        output=tmp_path / out,
        research_root=root or research_root(tmp_path, [config_path]),
        require_clean_source=False,
    )


# --------------------------------------------------------------------------
# F1 / F2 — canonical family ontology
# --------------------------------------------------------------------------
def test_f1_legacy_family_aliases_resolve_to_one_canonical_family():
    assert family_ontology.resolve_family("FAMILY_MOMENTUM") == family_ontology.TIME_SERIES_MOMENTUM
    assert family_ontology.resolve_family("time_series_momentum") == family_ontology.TIME_SERIES_MOMENTUM
    assert family_ontology.resolve_family("FAMILY_MOVING_AVERAGE") == family_ontology.MOVING_AVERAGE_TREND
    assert family_ontology.resolve_family("moving_average_trend") == family_ontology.MOVING_AVERAGE_TREND
    assert family_ontology.resolve_family("FAMILY_BREAKOUT") == family_ontology.PRICE_BREAKOUT
    assert family_ontology.resolve_family("price_breakout") == family_ontology.PRICE_BREAKOUT
    assert family_ontology.resolve_family("FAMILY_MEAN_REVERSION") == family_ontology.MEAN_REVERSION
    assert family_ontology.resolve_family("short_horizon_reversal") == family_ontology.SHORT_HORIZON_REVERSAL
    assert family_ontology.resolve_family("volatility_scaled_trend") == family_ontology.VOLATILITY_SCALED_TREND


def test_f1_every_historical_variant_resolves_to_exactly_one_canonical_family():
    history = load_canonical_history(COMMITTED_RESEARCH_ROOT)
    resolved = {}
    for event in history.candidates:
        if event["event_type"] != "CANDIDATE_PROPOSED":
            continue
        resolved[event["variant_id"]] = family_ontology.resolve_family(event["family_id"])
    assert len(resolved) == 20
    assert all(isinstance(value, str) and value for value in resolved.values())


def test_f1_generation_1_h003_24_96_joins_its_real_family():
    """The variant the raw-label query silently loses must appear under MOVING_AVERAGE_TREND."""
    history = load_canonical_history(COMMITTED_RESEARCH_ROOT)
    by_candidate = {
        event["candidate_id"]: event for event in history.candidates if event["event_type"] == "CANDIDATE_PROPOSED"
    }
    lost = by_candidate["CANDIDATE_H003_MA_24_96_LONG_FLAT"]
    assert lost["family_id"] == "FAMILY_MOVING_AVERAGE"
    assert family_ontology.resolve_family(lost["family_id"]) == family_ontology.MOVING_AVERAGE_TREND

    siblings = [
        event
        for event in by_candidate.values()
        if family_ontology.resolve_family(event["family_id"]) == family_ontology.MOVING_AVERAGE_TREND
    ]
    assert len(siblings) == 4, "moving-average family has four variants once aliases resolve"
    raw_only = [event for event in by_candidate.values() if event["family_id"] == "moving_average_trend"]
    assert len(raw_only) == 3, "raw-label query is the one that loses a variant"


def test_f2_unknown_family_alias_fails_closed():
    with pytest.raises(family_ontology.FamilyOntologyError):
        family_ontology.resolve_family("FAMILY_SOMETHING_NEW")
    with pytest.raises(family_ontology.FamilyOntologyError):
        family_ontology.resolve_family("")
    with pytest.raises(family_ontology.FamilyOntologyError):
        family_ontology.verify_alias_coverage(["time_series_momentum", "totally_unknown"])


def test_f2_ontology_digest_is_stable_and_targets_declared():
    assert family_ontology.ontology_digest() == family_ontology.ontology_digest()
    for target in set(family_ontology.FAMILY_ALIASES.values()):
        assert target in family_ontology.CANONICAL_FAMILIES
    strategy_families = [
        key for key in family_ontology.CANONICAL_FAMILIES if family_ontology.is_strategy_family(key)
    ]
    assert len(strategy_families) == 6


# --------------------------------------------------------------------------
# F3 — instrument pooling fails closed
# --------------------------------------------------------------------------
def _synthetic_corpus(rows):
    return {"rows": rows, "schema_version": corpus_index.CORPUS_INDEX_SCHEMA_VERSION}


def _row(**overrides):
    row = {
        "canonical_family_id": family_ontology.TIME_SERIES_MOMENTUM,
        "evidence_capability": corpus_index.SUMMARY_ONLY,
        "instrument_contract_id": SPOT,
        "research_generation": CORPUS_GENERATION_V1,
        "trial_id": "trial_a",
        "bar_path_sha256": None,
    }
    row.update(overrides)
    return row


def test_f3_spot_and_usdm_trials_cannot_be_pooled_silently():
    corpus = _synthetic_corpus(
        [_row(trial_id="trial_spot"), _row(trial_id="trial_perp", instrument_contract_id=PERP)]
    )
    with pytest.raises(instrument_contract.InstrumentContractError, match="FAIL_CLOSED_ON_MIXED_INSTRUMENT_CORPUS"):
        corpus_index.select(corpus)


def test_f3_cross_instrument_requires_explicit_declaration():
    corpus = _synthetic_corpus(
        [_row(trial_id="trial_spot"), _row(trial_id="trial_perp", instrument_contract_id=PERP)]
    )
    result = corpus_index.select(corpus, allow_cross_instrument=True)
    assert result["telemetry"]["cross_instrument_declared"] is True
    assert result["telemetry"]["instrument_contracts"] == [SPOT, PERP]
    assert len(result["rows"]) == 2


def test_f3_matching_ticker_text_is_not_instrument_identity():
    """BTCUSDT spot and BTCUSDT perp differ by contract, not by symbol string."""
    corpus = _synthetic_corpus(
        [
            _row(trial_id="trial_spot", symbol="BTCUSDT"),
            _row(trial_id="trial_perp", symbol="BTCUSDT", instrument_contract_id=PERP),
        ]
    )
    with pytest.raises(instrument_contract.InstrumentContractError):
        corpus_index.select(corpus)
    assert instrument_contract.contract_digest(SPOT) != instrument_contract.contract_digest(PERP)


# --------------------------------------------------------------------------
# F4 / F5 / F6 — trial identity
# --------------------------------------------------------------------------
def _identity_kwargs(**overrides):
    kwargs = {
        "variant_id": "variant_test",
        "instrument_contract_id": SPOT,
        "symbol": "BTCUSDT",
        "input_sha256": "a" * 64,
        "evaluation_start": "2025-01-01T00:00:00Z",
        "evaluation_end": "2025-12-31T23:00:00Z",
        "fee_bps": 10.0,
        "slippage_bps": 10.0,
        "funding_treatment": instrument_contract.FUNDING_NOT_APPLICABLE,
        "gap_policy": "REJECT",
        "expected_interval": "1h",
    }
    kwargs.update(overrides)
    return kwargs


def test_f4_same_recipe_under_two_instrument_contracts_keeps_one_variant_id():
    spot_config = {
        "strategy_id": "H002_momentum",
        "strategy_version": "existing-qntylab-strategies-v1",
        "parameters": {"lookback": 720, "mode": "long_flat"},
        "mode": "long_flat",
        "bar_interval": "1h",
        "required_input_kind": "OHLCV_1H_CSV",
        "funding_boundary_mode": "NOT_APPLICABLE",
    }
    perp_config = dict(spot_config)
    assert compute_variant_id(spot_config) == compute_variant_id(perp_config)

    spot_trial = compute_trial_id_v2(**_identity_kwargs(variant_id=compute_variant_id(spot_config)))
    perp_trial = compute_trial_id_v2(
        **_identity_kwargs(
            variant_id=compute_variant_id(perp_config),
            instrument_contract_id=PERP,
            funding_treatment=instrument_contract.FUNDING_PROVEN_ZERO_BY_CONTRACT,
        )
    )
    assert spot_trial != perp_trial, "instrument contract must change evaluation identity"


def test_f5_new_trial_ids_distinguish_instrument_contracts_and_funding():
    base = compute_trial_id_v2(**_identity_kwargs())
    other_contract = compute_trial_id_v2(
        **_identity_kwargs(
            instrument_contract_id=PERP,
            funding_treatment=instrument_contract.FUNDING_PROVEN_ZERO_BY_CONTRACT,
        )
    )
    other_funding = compute_trial_id_v2(
        **_identity_kwargs(funding_treatment=instrument_contract.FUNDING_PROVEN_ZERO_BY_CONTRACT)
    )
    assert len({base, other_contract, other_funding}) == 3


def test_f5_v2_identity_differs_from_v1_identity_for_the_same_evaluation():
    v1 = compute_trial_id(
        variant_id="variant_test",
        symbol="BTCUSDT",
        input_sha256="a" * 64,
        evaluation_start="2025-01-01T00:00:00Z",
        evaluation_end="2025-12-31T23:00:00Z",
        fee_bps=10.0,
        slippage_bps=10.0,
        gap_policy="REJECT",
        expected_interval="1h",
    )
    assert v1 != compute_trial_id_v2(**_identity_kwargs())


def test_f6_historical_trial_ids_remain_unchanged():
    """Every committed trial must still validate under V1 identity, unrewritten."""
    history = load_canonical_history(COMMITTED_RESEARCH_ROOT)
    assert len(history.trials) == 378
    for event in history.trials:
        assert "instrument_contract_id" not in event, "no historical event may gain a V2 contract field"
        recomputed = compute_trial_id(
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
        assert event["trial_id"] == recomputed


def test_f6_v1_shaped_event_may_not_smuggle_v2_fields():
    history = load_canonical_history(COMMITTED_RESEARCH_ROOT)
    event = dict(history.trials[0])
    event["bar_path_sha256"] = "b" * 64
    with pytest.raises(LedgerError, match="require instrument_contract_id"):
        validate_trial_event(event)


# --------------------------------------------------------------------------
# F7 — native receipt fields
# --------------------------------------------------------------------------
def test_f7_new_receipt_stores_period_cost_and_instrument_natively(tmp_path, monkeypatch):
    result = run_v2(tmp_path, v2_config(tmp_path), monkeypatch=monkeypatch)
    receipt = result["receipt"]
    assert receipt["period_id"] == "2021_TEST"
    assert receipt["cost_mode"] == "stress"
    assert receipt["instrument_contract_id"] == SPOT
    assert receipt["instrument_contract_digest"] == instrument_contract.contract_digest(SPOT)
    assert receipt["funding_treatment"] == instrument_contract.FUNDING_NOT_APPLICABLE
    assert receipt["canonical_family_id"] == family_ontology.TIME_SERIES_MOMENTUM
    assert receipt["research_generation"] == CORPUS_GENERATION_V2
    assert receipt["bar_path_sha256"] and receipt["bar_path_row_count"] > 0
    assert receipt["bar_path_schema_version"] == bar_path.BAR_PATH_SCHEMA_VERSION
    # no directory-name parsing is needed to recover semantics
    assert receipt["period"] == receipt["period_id"]


def test_f7_v1_receipt_shape_is_untouched_when_no_contract_declared(tmp_path):
    config_path = v2_config(tmp_path, instrument_contract_id=None, funding_treatment=None, period_id=None, cost_mode=None)
    value = json.loads(config_path.read_text())
    for key in ("instrument_contract_id", "funding_treatment", "period_id", "cost_mode"):
        value.pop(key)
    config_path.write_text(json.dumps(value, sort_keys=True, indent=2) + "\n")
    result = run_v2(tmp_path, config_path)
    receipt = result["receipt"]
    assert "instrument_contract_id" not in receipt
    assert "bar_path_sha256" not in receipt
    assert receipt["cost_mode"] == "" and receipt["period"] == ""


# --------------------------------------------------------------------------
# F8 / F9 / F10 — bar-path determinism and accounting
# --------------------------------------------------------------------------
def test_f8_deterministic_rerun_produces_the_same_digest(tmp_path, monkeypatch):
    first = run_v2(tmp_path, v2_config(tmp_path), out="run_a", monkeypatch=monkeypatch)
    second = run_v2(
        tmp_path,
        v2_config(tmp_path, name="config_b.json"),
        out="run_b",
        root=research_root(tmp_path, [v2_config(tmp_path, name="config_b.json")], name="research_b"),
        monkeypatch=monkeypatch,
    )
    assert first["receipt"]["bar_path_sha256"] == second["receipt"]["bar_path_sha256"]
    assert first["receipt"]["trial_id"] == second["receipt"]["trial_id"]


def test_f8_bar_path_digest_is_content_addressed_and_reloadable(tmp_path, monkeypatch):
    result = run_v2(tmp_path, v2_config(tmp_path), monkeypatch=monkeypatch)
    digest = result["receipt"]["bar_path_sha256"]
    stored = bar_path.store_path_for_digest(digest, tmp_path / "evidence")
    assert stored.exists(), "bar-path bytes live outside Git in content-addressed storage"
    assert not (tmp_path / "run" / "bar_path.jsonl").exists()
    rows = bar_path.load(digest, tmp_path / "evidence")
    assert len(rows) == result["receipt"]["bar_path_row_count"]
    assert bar_path.digest(rows) == digest


def test_f9_bar_path_accounts_for_position_timing():
    close = np.array([100.0, 110.0, 121.0, 121.0, 100.0], dtype=float)
    position = np.array([0.0, 1.0, 1.0, 0.0, 0.0], dtype=float)
    rows = bar_path.build_bar_path(
        timestamps=[f"2025-01-01T0{i}:00:00Z" for i in range(5)],
        close=close,
        position=position,
        fee_bps=0.0,
        slippage_bps=0.0,
    )
    assert len(rows) == 4
    # position held over bar i earns the return from i to i+1
    assert rows[0]["position_before_return"] == 0.0
    assert rows[0]["asset_return"] == pytest.approx(0.10)
    assert rows[0]["gross_strategy_return"] == pytest.approx(0.0), "flat position earns nothing"
    assert rows[1]["position_before_return"] == 1.0
    assert rows[1]["gross_strategy_return"] == pytest.approx(0.10), "long position earns the bar return"
    assert rows[3]["gross_strategy_return"] == pytest.approx(0.0), "exited before the drawdown bar"


def test_f9_turnover_marks_position_transitions():
    close = np.array([100.0, 101.0, 102.0, 103.0], dtype=float)
    position = np.array([0.0, 1.0, 1.0, 0.0], dtype=float)
    rows = bar_path.build_bar_path(
        timestamps=[f"2025-01-01T0{i}:00:00Z" for i in range(4)],
        close=close,
        position=position,
        fee_bps=10.0,
        slippage_bps=0.0,
    )
    assert [row["turnover"] for row in rows] == [1.0, 0.0, 1.0]
    assert rows[1]["fee_cost"] == 0.0, "holding a position is not charged"


def test_f10_bar_path_accounts_for_fee_and_slippage_without_double_counting(tmp_path, monkeypatch):
    result = run_v2(tmp_path, v2_config(tmp_path), monkeypatch=monkeypatch)
    rows = bar_path.load(result["receipt"]["bar_path_sha256"], tmp_path / "evidence")
    metrics = result["metrics"]
    fee_total = sum(row["fee_cost"] for row in rows)
    slippage_total = sum(row["slippage_cost"] for row in rows)
    # 10 bps fee + 5 bps slippage: the split is proportional and sums to total_cost
    assert fee_total + slippage_total == pytest.approx(metrics["total_cost"], abs=1e-12)
    assert slippage_total == pytest.approx(fee_total * 0.5, abs=1e-12)
    assert rows[-1]["cumulative_return"] == pytest.approx(metrics["net_return"], abs=1e-12)


def test_f10_cost_reconciliation_failure_is_detected():
    rows = bar_path.build_bar_path(
        timestamps=[f"2025-01-01T0{i}:00:00Z" for i in range(4)],
        close=np.array([100.0, 101.0, 102.0, 103.0]),
        position=np.array([0.0, 1.0, 1.0, 0.0]),
        fee_bps=10.0,
        slippage_bps=0.0,
    )
    bad_metrics = {"observation_count": 3, "total_cost": 999.0, "net_return": 0.0, "trade_count": 2}
    with pytest.raises(bar_path.BarPathError, match="does not reconcile"):
        bar_path.verify_against_metrics(rows, bad_metrics)


def test_f9_cost_is_charged_for_the_transition_at_the_end_of_the_row():
    """Row i holds position[i] and pays for the move into position[i+1].

    This is ``evaluate``'s committed semantics, reproduced rather than corrected.
    Pinning it stops a later refactor from silently shifting cost by one bar.
    """
    close = np.array([100.0, 100.0, 100.0, 100.0], dtype=float)
    position = np.array([0.0, 0.0, 1.0, 1.0], dtype=float)
    rows = bar_path.build_bar_path(
        timestamps=[f"2025-01-01T0{i}:00:00Z" for i in range(4)],
        close=close,
        position=position,
        fee_bps=10.0,
        slippage_bps=0.0,
    )
    # the entry into the long position happens between row 1 and row 2, so the
    # charge lands on row 1 while row 1 itself is still flat
    assert rows[1]["position_before_return"] == 0.0
    assert rows[1]["turnover"] == 1.0
    assert rows[1]["fee_cost"] == pytest.approx(0.001)
    assert rows[2]["position_before_return"] == 1.0
    assert rows[2]["turnover"] == 0.0


def test_f10_bar_path_reconciles_gross_return_not_only_net():
    close = np.array([100.0, 110.0, 121.0, 121.0], dtype=float)
    position = np.array([1.0, 1.0, 1.0, 1.0], dtype=float)
    rows = bar_path.build_bar_path(
        timestamps=[f"2025-01-01T0{i}:00:00Z" for i in range(4)],
        close=close,
        position=position,
        fee_bps=0.0,
        slippage_bps=0.0,
    )
    good = {"observation_count": 3, "total_cost": 0.0, "net_return": 0.21, "trade_count": 0, "gross_return": 0.21}
    bar_path.verify_against_metrics(rows, good)
    bad = dict(good, gross_return=0.99)
    with pytest.raises(bar_path.BarPathError, match="compounded gross"):
        bar_path.verify_against_metrics(rows, bad)


def test_f8_bar_path_matches_the_committed_evaluate_accounting_on_long_series():
    """Independent cross-check against qntylab.backtest.evaluate."""
    from qntylab.backtest import evaluate

    rng = np.random.default_rng(11)
    for _ in range(15):
        n = int(rng.integers(500, 4000))
        close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
        position = rng.choice([-1.0, 0.0, 1.0], size=n)
        result = evaluate(close, position, 20.0)
        rows = bar_path.build_bar_path(
            timestamps=[f"t{i}" for i in range(n)],
            close=close,
            position=position,
            fee_bps=10.0,
            slippage_bps=10.0,
        )
        assert rows[-1]["cumulative_return"] == pytest.approx(result["net_cumulative_return"], abs=1e-12)
        assert sum(r["fee_cost"] + r["slippage_cost"] for r in rows) == pytest.approx(result["fee_cost"], abs=1e-12)
        assert sum(1 for r in rows if r["turnover"] != 0.0) == result["trade_count"]
        assert [r["position_before_return"] for r in rows] == pytest.approx(position[:-1], abs=0)


def test_f10_gap_and_flat_position_behaviour():
    close = np.array([100.0, 100.0, 100.0, 100.0], dtype=float)
    position = np.zeros(4, dtype=float)
    rows = bar_path.build_bar_path(
        timestamps=[f"2025-01-01T0{i}:00:00Z" for i in range(4)],
        close=close,
        position=position,
        fee_bps=10.0,
        slippage_bps=10.0,
    )
    assert all(row["net_strategy_return"] == 0.0 for row in rows)
    assert all(row["cumulative_return"] == 0.0 for row in rows)
    assert all(row["turnover"] == 0.0 for row in rows)


# --------------------------------------------------------------------------
# F11 — perpetual funding boundary
# --------------------------------------------------------------------------
def test_f11_perpetual_exposed_trial_cannot_declare_funding_not_applicable():
    with pytest.raises(instrument_contract.InstrumentContractError, match="forbidden"):
        instrument_contract.validate_funding_treatment(
            instrument_contract_id=PERP,
            funding_treatment=instrument_contract.FUNDING_NOT_APPLICABLE,
            has_position_exposure=True,
        )


def test_f11_perpetual_allows_the_three_declared_future_states():
    for treatment in (
        instrument_contract.FUNDING_INCLUDED_PROVENANCE_BOUND,
        instrument_contract.FUNDING_PROVEN_ZERO_BY_CONTRACT,
        instrument_contract.TRIAL_BLOCKED_BY_FUNDING_EVIDENCE,
    ):
        assert (
            instrument_contract.validate_funding_treatment(
                instrument_contract_id=PERP, funding_treatment=treatment, has_position_exposure=True
            )
            == treatment
        )


def test_f11_spot_may_declare_not_applicable():
    assert instrument_contract.validate_funding_treatment(
        instrument_contract_id=SPOT,
        funding_treatment=instrument_contract.FUNDING_NOT_APPLICABLE,
        has_position_exposure=True,
    )


def test_f11_runner_rejects_perpetual_not_applicable(tmp_path, monkeypatch):
    config_path = v2_config(
        tmp_path,
        instrument_contract_id=PERP,
        funding_treatment=instrument_contract.FUNDING_NOT_APPLICABLE,
    )
    with pytest.raises(instrument_contract.InstrumentContractError):
        run_v2(tmp_path, config_path, monkeypatch=monkeypatch)


def test_f11_blocked_by_funding_evidence_cannot_complete_a_trial(tmp_path, monkeypatch):
    config_path = v2_config(
        tmp_path,
        instrument_contract_id=PERP,
        funding_treatment=instrument_contract.TRIAL_BLOCKED_BY_FUNDING_EVIDENCE,
    )
    with pytest.raises(ValueError, match="TRIAL_BLOCKED_BY_FUNDING_EVIDENCE"):
        run_v2(tmp_path, config_path, monkeypatch=monkeypatch)


def test_f11_ledger_rejects_a_perpetual_event_declaring_not_applicable():
    event = {
        "event_id": "event_trial_x",
        "event_type": "TRIAL_COMPLETED",
        "recorded_at_utc": "2026-08-10T00:00:00Z",
        "candidate_id": "C",
        "family_id": "time_series_momentum",
        "variant_id": "variant_x",
        "trial_id": "trial_x",
        "research_intent": "SCREEN",
        "symbol": "BTCUSDT",
        "evaluation_start": "2025-01-01T00:00:00Z",
        "evaluation_end": "2025-12-31T23:00:00Z",
        "input_sha256": "a" * 64,
        "repository_commit": "deadbeef",
        "relevant_source_sha256": "b" * 64,
        "fee_bps": 10.0,
        "slippage_bps": 10.0,
        "gap_policy": "REJECT",
        "expected_interval": "1h",
        "receipt_path": "/tmp/x/run_receipt.json",
        "receipt_sha256": "c" * 64,
        "compact_metrics": {"exposure_fraction": 0.5, "observation_count": 10},
        "instrument_contract_id": PERP,
        "instrument_contract_digest": instrument_contract.contract_digest(PERP),
        "funding_treatment": instrument_contract.FUNDING_NOT_APPLICABLE,
        "research_generation": CORPUS_GENERATION_V1,
    }
    with pytest.raises(LedgerError, match="forbidden"):
        validate_trial_event(event)


# --------------------------------------------------------------------------
# F12 / F13 / F14 / F15 — corpus index
# --------------------------------------------------------------------------
def test_f12_corpus_rebuild_is_deterministic():
    first = corpus_index.build_corpus(COMMITTED_RESEARCH_ROOT)
    second = corpus_index.build_corpus(COMMITTED_RESEARCH_ROOT)
    assert corpus_index.corpus_digest(first) == corpus_index.corpus_digest(second)
    assert canonical_bytes(first) == canonical_bytes(second)


def test_f12_corpus_row_order_is_stable_and_complete():
    corpus = corpus_index.build_corpus(COMMITTED_RESEARCH_ROOT)
    assert corpus["summary"]["total_rows"] == 378
    trial_ids = [row["trial_id"] for row in corpus["rows"]]
    assert trial_ids == sorted(trial_ids)
    assert len(set(trial_ids)) == 378


def test_f13_v1_rows_classify_summary_only_with_reconstructed_semantics():
    corpus = corpus_index.build_corpus(COMMITTED_RESEARCH_ROOT)
    assert corpus["summary"]["by_evidence_capability"] == {corpus_index.SUMMARY_ONLY: 378}
    assert corpus["summary"]["by_research_generation"] == {CORPUS_GENERATION_V1: 378}
    assert corpus["summary"]["by_instrument_contract"] == {SPOT: 378}
    for row in corpus["rows"]:
        assert row["instrument_contract_value_origin"] == corpus_index.HISTORICAL_RECONSTRUCTION
        assert row["bar_path_sha256"] is None
        assert row["period_id"] and row["cost_mode"]
    assert "Generation-level historical classification" in corpus["historical_instrument_provenance"]


def test_f13_registered_denominator_is_frozen_only_where_declared():
    corpus = corpus_index.build_corpus(COMMITTED_RESEARCH_ROOT)
    breadth = [row for row in corpus["rows"] if row["registered_screen_id"] == "CURATED_BREADTH_SCREEN_V1"]
    focused = [row for row in corpus["rows"] if row["registered_screen_id"] == "FOCUSED_TREND_VALIDATION_V1"]
    assert len(breadth) == 360
    assert {row["registered_variant_denominator"] for row in breadth} == {15}
    assert len(focused) == 18
    assert {row["registered_variant_denominator"] for row in focused} == {None}, "never invent a denominator"


def test_f13_canonical_family_counts_include_the_alias_resolved_variants():
    corpus = corpus_index.build_corpus(COMMITTED_RESEARCH_ROOT)
    counts = corpus["summary"]["by_canonical_family"]
    assert counts[family_ontology.MOVING_AVERAGE_TREND] == 84
    assert counts[family_ontology.TIME_SERIES_MOMENTUM] == 78
    assert counts[family_ontology.SHORT_HORIZON_REVERSAL] == 96


def test_f14_v2_rows_classify_bar_path(tmp_path, monkeypatch):
    config_path = v2_config(tmp_path)
    root = research_root(tmp_path, [config_path])
    run_v2(tmp_path, config_path, root=root, monkeypatch=monkeypatch)
    corpus = corpus_index.build_corpus(root)
    assert corpus["summary"]["by_evidence_capability"] == {corpus_index.BAR_PATH: 1}
    assert corpus["summary"]["by_research_generation"] == {CORPUS_GENERATION_V2: 1}
    row = corpus["rows"][0]
    assert row["instrument_contract_value_origin"] == corpus_index.NATIVE_RECEIPT
    assert row["period_id"] == "2021_TEST" and row["cost_mode"] == "stress"
    assert row["canonical_family_id"] == family_ontology.TIME_SERIES_MOMENTUM
    assert row["bar_path_sha256"]


def test_f15_bar_path_query_cannot_silently_consume_summary_only_rows():
    corpus = corpus_index.build_corpus(COMMITTED_RESEARCH_ROOT)
    with pytest.raises(corpus_index.CorpusIndexError, match="SUMMARY_ONLY"):
        corpus_index.select(corpus, require_bar_path=True)


def test_f15_bar_path_query_reports_exclusion_telemetry():
    corpus = _synthetic_corpus(
        [
            _row(trial_id="trial_v1"),
            _row(
                trial_id="trial_v2",
                evidence_capability=corpus_index.BAR_PATH,
                research_generation=CORPUS_GENERATION_V2,
                bar_path_sha256="d" * 64,
            ),
        ]
    )
    result = corpus_index.select(corpus, require_bar_path=True)
    assert len(result["rows"]) == 1
    assert result["telemetry"]["excluded"]["summary_only_rows"] == 1
    assert result["telemetry"]["summary_only_excluded_generations"] == [CORPUS_GENERATION_V1]


def test_f15_mixed_generation_bar_path_query_still_enforces_one_instrument():
    corpus = _synthetic_corpus(
        [
            _row(
                trial_id="trial_spot_v2",
                evidence_capability=corpus_index.BAR_PATH,
                research_generation=CORPUS_GENERATION_V2,
                bar_path_sha256="d" * 64,
            ),
            _row(
                trial_id="trial_perp_v2",
                instrument_contract_id=PERP,
                evidence_capability=corpus_index.BAR_PATH,
                research_generation=CORPUS_GENERATION_V2,
                bar_path_sha256="e" * 64,
            ),
        ]
    )
    with pytest.raises(instrument_contract.InstrumentContractError):
        corpus_index.select(corpus, require_bar_path=True)


# --------------------------------------------------------------------------
# F16 / F17 / F18 — generation-1 survivor disposition and append-only history
# --------------------------------------------------------------------------
def test_f16_h003_24_96_is_blocked_not_graveyarded():
    state = json.loads((COMMITTED_RESEARCH_ROOT / "state.json").read_text())
    variant = state["variants"]["variant_aa66ba0edf856ac06f055917"]
    assert variant["candidate_id"] == "CANDIDATE_H003_MA_24_96_LONG_FLAT"
    assert variant["status"] == "BLOCKED"
    assert variant["status"] != "GRAVEYARDED"
    assert "preregistered strategy-family catalogue" in variant["revisit_condition"]


def test_f16_disposition_decision_carries_the_evidence_standing_reason():
    decisions = [
        json.loads(line)
        for line in (COMMITTED_RESEARCH_ROOT / "decisions.jsonl").read_text().splitlines()
        if line.strip()
    ]
    matching = [
        event
        for event in decisions
        if event["variant_id"] == "variant_aa66ba0edf856ac06f055917" and event["status"] == "BLOCKED"
    ]
    assert len(matching) == 1
    event = matching[0]
    assert event["reason_codes"] == ["GENERATION_1_EVIDENCE_NOT_TRIAL_BACKED"]
    assert event["scope"] == "EXACT_VARIANT"
    assert "retained exploratory summary evidence" in event["decision_note"]
    assert "not eligible to serve as validated edge" in event["decision_note"]


def test_f16_no_survivors_remain_and_no_new_graveyard_was_created():
    state = json.loads((COMMITTED_RESEARCH_ROOT / "state.json").read_text())
    statuses = [variant["status"] for variant in state["variants"].values()]
    assert statuses.count("SURVIVOR") == 0
    assert statuses.count("GRAVEYARDED") == 15, "no variant was graveyarded by this phase"
    assert statuses.count("BLOCKED") == 4


def test_f17_h007_status_unchanged():
    state = json.loads((COMMITTED_RESEARCH_ROOT / "state.json").read_text())
    h007 = {
        key: value for key, value in state["variants"].items() if value["candidate_id"].startswith("CANDIDATE_H007_")
    }
    assert len(h007) == 3
    for variant in h007.values():
        assert variant["status"] == "BLOCKED"
        assert "H003 24/96 benchmark reconstruction" in variant["revisit_condition"]


def test_f18_history_is_append_only_against_the_starting_commit():
    """Only one decision line may be added; candidates and trials are untouched."""
    for path, expected in (
        ("experiments/research/candidates.jsonl", 0),
        ("experiments/research/trials/2026.jsonl", 0),
    ):
        diff = subprocess.run(
            ["git", "diff", "e8c00a5", "--numstat", "--", path],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.strip()
        assert diff == "", f"{path} must be byte-identical to the starting commit"
        assert expected == 0

    numstat = subprocess.run(
        ["git", "diff", "e8c00a5", "--numstat", "--", "experiments/research/decisions.jsonl"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert numstat[0] == "1" and numstat[1] == "0", "exactly one appended decision line, zero deletions"


def test_f18_committed_history_still_replays_without_issues():
    history = load_canonical_history(COMMITTED_RESEARCH_ROOT)
    assert len(history.candidates) == 20
    assert len(history.decisions) == 24
    assert len(history.trials) == 378
