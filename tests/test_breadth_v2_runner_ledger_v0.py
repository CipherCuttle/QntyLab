"""Synthetic-only integration tests for BREADTH_V2_RUNNER_LEDGER_INTEGRATION_V0.

No real market data, no real campaign execution.  All prices and funding
events are deterministic closed-form fixtures (see ``_breadth_v2_fixtures``).
Ledger writes happen only in a temporary fixture root copied from the
canonical research ledger; the canonical ``experiments/research`` tree is
never appended to.
"""
from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from qntylab import research_ledger
from qntylab.breadth_v2_input_bundle import build_breadth_v2_input_bundle, required_history_for_variant
from qntylab.breadth_v2_runner import (
    PANEL_EXECUTION_UNIT_ID,
    REGISTERED_PERIODS,
    RunnerBlocked,
    SINGLE_ASSET,
    SYNCHRONIZED_PANEL,
    enumerate_registered_execution_plan,
    prepare_breadth_v2_evaluation,
    record_breadth_v2_evaluation,
    resolve_candidate,
    scientific_cell_count,
)
from tests._breadth_v2_fixtures import FROZEN_PANEL_ORDER, build_sources

TSMOM_72_VARIANT = "variant_07e9c327cb88170fec74bada"          # TIME_SERIES_MOMENTUM lookback=72
XSMOM_24_VARIANT = "variant_7e63843cf5bd2e7a7de4fdad"           # CROSS_SECTIONAL_MOMENTUM lookback=24
PERIOD_ID = "DEV_2022"
SINGLE_SYMBOL = FROZEN_PANEL_ORDER[0]


def _canonical_research_root() -> Path:
    return Path("experiments/research")


def _fresh_ledger_root(tmp_path: Path) -> Path:
    # Preserve the real repo-relative nesting (experiments/research under a
    # fixture root) so relative evidence paths in DECISION_RECORDED events
    # still resolve during doctor()/rebuild() evidence verification.
    fixture_repo = tmp_path / "fixture_repo"
    shutil.copytree(Path("experiments/specs"), fixture_repo / "experiments" / "specs")
    shutil.copytree(_canonical_research_root(), fixture_repo / "experiments" / "research")
    return fixture_repo / "experiments" / "research"


def _single_asset_bundle():
    candidate = resolve_candidate(TSMOM_72_VARIANT)
    history = required_history_for_variant(candidate["family_id"], candidate["parameters"])
    start, end = REGISTERED_PERIODS[PERIOD_ID]
    price_sources, funding_sources = build_sources(
        [SINGLE_SYMBOL], start, end,
        required_price_closes=history["required_price_closes"],
        required_funding_signal_events=history["required_funding_signal_events"],
    )
    return build_breadth_v2_input_bundle(
        evaluation_start=start, evaluation_end=end, symbols=[SINGLE_SYMBOL],
        price_sources=price_sources, funding_sources=funding_sources,
        family=candidate["family_id"], parameters=candidate["parameters"],
    )


def _panel_bundle():
    candidate = resolve_candidate(XSMOM_24_VARIANT)
    history = required_history_for_variant(candidate["family_id"], candidate["parameters"])
    start, end = REGISTERED_PERIODS[PERIOD_ID]
    price_sources, funding_sources = build_sources(
        list(FROZEN_PANEL_ORDER), start, end,
        required_price_closes=history["required_price_closes"],
        required_funding_signal_events=history["required_funding_signal_events"],
    )
    return build_breadth_v2_input_bundle(
        evaluation_start=start, evaluation_end=end, symbols=list(FROZEN_PANEL_ORDER),
        price_sources=price_sources, funding_sources=funding_sources,
        family=candidate["family_id"], parameters=candidate["parameters"],
    )


# --- Section 48: pure execution-plan count, no data access -----------------


def test_execution_plan_counts():
    plan = enumerate_registered_execution_plan()
    single = [d for d in plan if d.execution_unit_type == SINGLE_ASSET]
    panel = [d for d in plan if d.execution_unit_type == SYNCHRONIZED_PANEL]
    assert len(single) == 1920
    assert len(panel) == 72
    assert len(plan) == 1992
    assert scientific_cell_count(plan) == 3360
    assert len({(d.family_id, d.variant_id, d.execution_unit_type, d.execution_unit_id, d.period_id, d.cost_mode) for d in plan}) == 1992


# --- Section 42: single-asset synthetic integration -------------------------


def test_single_asset_synthetic_integration(tmp_path):
    bundle = _single_asset_bundle()
    assert bundle["status"] == "READY"
    root = _fresh_ledger_root(tmp_path)

    prepared = prepare_breadth_v2_evaluation(
        variant_id=TSMOM_72_VARIANT, execution_unit_type=SINGLE_ASSET, execution_unit_id=SINGLE_SYMBOL,
        period_id=PERIOD_ID, cost_mode="BASELINE_EXECUTION", input_bundle=bundle, ledger_root=root, require_clean_source=False,
    )
    assert prepared.status == "READY"
    assert prepared.trial_event["scientific_cell_count"] == 1
    assert prepared.trial_event["cell_semantics"] == "SINGLE_ASSET_EVALUATION"
    assert prepared.receipt["scientific_cells"][0]["symbol"] == SINGLE_SYMBOL

    event = record_breadth_v2_evaluation(prepared, root=root)
    issues = research_ledger.doctor(root)
    assert issues == []
    history = research_ledger.load_canonical_history(root)
    assert event["event_id"] in {e["event_id"] for e in history.trials}

    # Canonical history is untouched.
    canonical = research_ledger.load_canonical_history(_canonical_research_root())
    assert len(canonical.trials) == 378
    assert not any(e.get("registered_screen_id") == "QNTYLAB_BREADTH_V2_20260810" for e in canonical.trials)

    # Second identical SCREEN preparation is refused before any write happens.
    with pytest.raises(RunnerBlocked, match="duplicate"):
        prepare_breadth_v2_evaluation(
            variant_id=TSMOM_72_VARIANT, execution_unit_type=SINGLE_ASSET, execution_unit_id=SINGLE_SYMBOL,
            period_id=PERIOD_ID, cost_mode="BASELINE_EXECUTION", input_bundle=bundle, ledger_root=root, require_clean_source=False,
        )


def test_prepare_refuses_duplicate_before_writing(tmp_path):
    bundle = _single_asset_bundle()
    root = _fresh_ledger_root(tmp_path)
    prepared = prepare_breadth_v2_evaluation(
        variant_id=TSMOM_72_VARIANT, execution_unit_type=SINGLE_ASSET, execution_unit_id=SINGLE_SYMBOL,
        period_id=PERIOD_ID, cost_mode="BASELINE_EXECUTION", input_bundle=bundle, ledger_root=root, require_clean_source=False,
    )
    record_breadth_v2_evaluation(prepared, root=root)
    with pytest.raises(RunnerBlocked, match="duplicate"):
        prepare_breadth_v2_evaluation(
            variant_id=TSMOM_72_VARIANT, execution_unit_type=SINGLE_ASSET, execution_unit_id=SINGLE_SYMBOL,
            period_id=PERIOD_ID, cost_mode="BASELINE_EXECUTION", input_bundle=bundle, ledger_root=root, require_clean_source=False,
        )


# --- Section 43: panel synthetic integration --------------------------------


def test_panel_synthetic_integration_emits_one_trial_and_twenty_cells(tmp_path):
    bundle = _panel_bundle()
    assert bundle["status"] == "READY"
    root = _fresh_ledger_root(tmp_path)

    prepared = prepare_breadth_v2_evaluation(
        variant_id=XSMOM_24_VARIANT, execution_unit_type=SYNCHRONIZED_PANEL, execution_unit_id=PANEL_EXECUTION_UNIT_ID,
        period_id=PERIOD_ID, cost_mode="BASELINE_EXECUTION", input_bundle=bundle, ledger_root=root, require_clean_source=False,
    )
    assert prepared.status == "READY"
    assert prepared.trial_event["scientific_cell_count"] == 20
    assert prepared.trial_event["cell_semantics"] == "PORTFOLIO_ASSET_CONTRIBUTION"
    cells = prepared.receipt["scientific_cells"]
    assert len(cells) == 20
    assert {cell["symbol"] for cell in cells} == set(FROZEN_PANEL_ORDER)

    record_breadth_v2_evaluation(prepared, root=root)
    history = research_ledger.load_canonical_history(root)
    breadth_trials = [e for e in history.trials if e.get("registered_screen_id") == "QNTYLAB_BREADTH_V2_20260810"]
    assert len(breadth_trials) == 1  # one execution unit -> one TRIAL_COMPLETED, not twenty
    assert research_ledger.doctor(root) == []


# --- Section 44: cost mode changes identity, not funding --------------------


def test_cost_mode_changes_identity():
    bundle = _single_asset_bundle()
    baseline = prepare_breadth_v2_evaluation(
        variant_id=TSMOM_72_VARIANT, execution_unit_type=SINGLE_ASSET, execution_unit_id=SINGLE_SYMBOL,
        period_id=PERIOD_ID, cost_mode="BASELINE_EXECUTION", input_bundle=bundle, require_clean_source=False,
    )
    stressed = prepare_breadth_v2_evaluation(
        variant_id=TSMOM_72_VARIANT, execution_unit_type=SINGLE_ASSET, execution_unit_id=SINGLE_SYMBOL,
        period_id=PERIOD_ID, cost_mode="STRESS_EXECUTION", input_bundle=bundle, require_clean_source=False,
    )
    assert baseline.trial_event["breadth_v2_evaluation_id"] != stressed.trial_event["breadth_v2_evaluation_id"]
    assert baseline.trial_event["trial_id"] != stressed.trial_event["trial_id"]
    assert baseline.trial_event["receipt_sha256"] != stressed.trial_event["receipt_sha256"]
    assert stressed.receipt["slippage_bps"] - baseline.receipt["slippage_bps"] == 10.0
    assert baseline.receipt["funding_treatment"] == stressed.receipt["funding_treatment"] == "FUNDING_INCLUDED_PROVENANCE_BOUND"


# --- Section 45: input mutation changes identity ----------------------------


def test_input_mutation_changes_identity():
    candidate = resolve_candidate(TSMOM_72_VARIANT)
    history = required_history_for_variant(candidate["family_id"], candidate["parameters"])
    start, end = REGISTERED_PERIODS[PERIOD_ID]
    price_sources, funding_sources = build_sources(
        [SINGLE_SYMBOL], start, end, required_price_closes=history["required_price_closes"],
        required_funding_signal_events=history["required_funding_signal_events"],
    )
    bundle_a = build_breadth_v2_input_bundle(
        evaluation_start=start, evaluation_end=end, symbols=[SINGLE_SYMBOL],
        price_sources=price_sources, funding_sources=funding_sources,
        family=candidate["family_id"], parameters=candidate["parameters"],
    )
    price_sources_b, funding_sources_b = build_sources(
        [SINGLE_SYMBOL], start, end, required_price_closes=history["required_price_closes"],
        required_funding_signal_events=history["required_funding_signal_events"], seed_offset=1000,
    )
    bundle_b = build_breadth_v2_input_bundle(
        evaluation_start=start, evaluation_end=end, symbols=[SINGLE_SYMBOL],
        price_sources=price_sources_b, funding_sources=funding_sources_b,
        family=candidate["family_id"], parameters=candidate["parameters"],
    )
    assert bundle_a["evaluation_input_bundle_sha256"] != bundle_b["evaluation_input_bundle_sha256"]

    prepared_a = prepare_breadth_v2_evaluation(
        variant_id=TSMOM_72_VARIANT, execution_unit_type=SINGLE_ASSET, execution_unit_id=SINGLE_SYMBOL,
        period_id=PERIOD_ID, cost_mode="BASELINE_EXECUTION", input_bundle=bundle_a, require_clean_source=False,
    )
    prepared_b = prepare_breadth_v2_evaluation(
        variant_id=TSMOM_72_VARIANT, execution_unit_type=SINGLE_ASSET, execution_unit_id=SINGLE_SYMBOL,
        period_id=PERIOD_ID, cost_mode="BASELINE_EXECUTION", input_bundle=bundle_b, require_clean_source=False,
    )
    assert prepared_a.trial_event["breadth_v2_evaluation_id"] != prepared_b.trial_event["breadth_v2_evaluation_id"]
    assert prepared_a.trial_event["trial_id"] != prepared_b.trial_event["trial_id"]
    assert prepared_a.trial_event["receipt_sha256"] != prepared_b.trial_event["receipt_sha256"]


# --- Section 46: provenance-only mutation changes identity ------------------


def test_provenance_only_mutation_changes_identity_but_not_economics():
    candidate = resolve_candidate(TSMOM_72_VARIANT)
    history = required_history_for_variant(candidate["family_id"], candidate["parameters"])
    start, end = REGISTERED_PERIODS[PERIOD_ID]
    price_sources, funding_sources = build_sources(
        [SINGLE_SYMBOL], start, end, required_price_closes=history["required_price_closes"],
        required_funding_signal_events=history["required_funding_signal_events"],
    )
    bundle_a = build_breadth_v2_input_bundle(
        evaluation_start=start, evaluation_end=end, symbols=[SINGLE_SYMBOL],
        price_sources=price_sources, funding_sources=funding_sources,
        family=candidate["family_id"], parameters=candidate["parameters"],
    )
    mutated_price = {SINGLE_SYMBOL: {**price_sources[SINGLE_SYMBOL], "manifest": {**price_sources[SINGLE_SYMBOL]["manifest"], "aggregate_source_receipt_digest": "b" * 64}}}
    bundle_b = build_breadth_v2_input_bundle(
        evaluation_start=start, evaluation_end=end, symbols=[SINGLE_SYMBOL],
        price_sources=mutated_price, funding_sources=funding_sources,
        family=candidate["family_id"], parameters=candidate["parameters"],
    )
    assert bundle_a["evaluation_input_bundle_sha256"] != bundle_b["evaluation_input_bundle_sha256"]
    assert bundle_a["admitted_price"] == bundle_b["admitted_price"]  # same causal observations

    prepared_a = prepare_breadth_v2_evaluation(
        variant_id=TSMOM_72_VARIANT, execution_unit_type=SINGLE_ASSET, execution_unit_id=SINGLE_SYMBOL,
        period_id=PERIOD_ID, cost_mode="BASELINE_EXECUTION", input_bundle=bundle_a, require_clean_source=False,
    )
    prepared_b = prepare_breadth_v2_evaluation(
        variant_id=TSMOM_72_VARIANT, execution_unit_type=SINGLE_ASSET, execution_unit_id=SINGLE_SYMBOL,
        period_id=PERIOD_ID, cost_mode="BASELINE_EXECUTION", input_bundle=bundle_b, require_clean_source=False,
    )
    assert prepared_a.trial_event["breadth_v2_evaluation_id"] != prepared_b.trial_event["breadth_v2_evaluation_id"]
    assert prepared_a.trial_event["trial_id"] != prepared_b.trial_event["trial_id"]
    assert prepared_a.trial_event["receipt_sha256"] != prepared_b.trial_event["receipt_sha256"]
    assert prepared_a.receipt["candidate_result"] == prepared_b.receipt["candidate_result"]


# --- Section 39/40: blocked input produces no trial -------------------------


def test_blocked_input_produces_no_trial():
    blocked_bundle = {"status": "BLOCKED_PRICE_COVERAGE"}
    prepared = prepare_breadth_v2_evaluation(
        variant_id=TSMOM_72_VARIANT, execution_unit_type=SINGLE_ASSET, execution_unit_id=SINGLE_SYMBOL,
        period_id=PERIOD_ID, cost_mode="BASELINE_EXECUTION", input_bundle=blocked_bundle, require_clean_source=False,
    )
    assert prepared.status == "BLOCKED"
    assert prepared.trial_event is None
    with pytest.raises(RunnerBlocked):
        record_breadth_v2_evaluation(prepared, root=Path("unused"))


# --- Historical trial identities are untouched ------------------------------


def test_historical_trial_identities_unchanged():
    history = research_ledger.load_canonical_history(_canonical_research_root())
    assert len(history.trials) == 378
    for event in history.trials:
        research_ledger.validate_trial_event(event)  # recomputes and checks trial_id


def test_candidate_resolution_rejects_parameter_override():
    candidate = resolve_candidate(TSMOM_72_VARIANT)
    assert candidate["parameters"] == {"lookback": 72, "mode": "long_flat"}
    with pytest.raises(RunnerBlocked):
        resolve_candidate("variant_does_not_exist")


# --- Section 47: dirty relevant source is refused in production mode -------


def test_dirty_relevant_source_is_refused(tmp_path):
    from qntylab.breadth_v2_runner import RELEVANT_SOURCE_PATHS, require_clean_relevant_source

    # Build a fresh, freshly-committed snapshot of the relevant source tree so
    # this test does not depend on the ambient dev worktree being clean.
    snapshot_root = tmp_path / "clean_copy"
    shutil.copytree(Path(".").resolve(), snapshot_root, ignore=shutil.ignore_patterns(".git", "__pycache__", ".pytest_cache", "data"))
    import subprocess

    subprocess.run(["git", "init", "-q"], cwd=snapshot_root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=snapshot_root, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "snapshot"], cwd=snapshot_root, check=True)

    require_clean_relevant_source(snapshot_root)  # freshly committed: must not raise

    target = snapshot_root / RELEVANT_SOURCE_PATHS[0]
    target.write_text(target.read_text() + "\n# dirty\n")
    with pytest.raises(RunnerBlocked, match="dirty"):
        require_clean_relevant_source(snapshot_root)
