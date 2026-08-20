"""Outcome-blind pre-execution integrity reconciliation tests.

Every fixture here is SYNTHETIC. No real evidence is loaded, no real
evaluation outcome is read, no evaluation origin is consumed, no market or
funding data is acquired, and no network call is made. The synthetic rows are
built by the frozen implementation phase's own generator, which is imported
rather than reimplemented so this phase cannot invent a different fixture.
"""
from __future__ import annotations

import copy
import decimal
import json
from decimal import Context, localcontext
from pathlib import Path

import pytest

from qntylab import jigsaw_funding_pressure_execution_v2 as v2
from qntylab import jigsaw_funding_pressure_incremental_forecast_value_executor_v0 as ex
from qntylab import jigsaw_funding_pressure_incremental_pre_execution_integrity_v0 as integrity
from qntylab import jigsaw_funding_pressure_provenance_v0 as provenance

from test_jigsaw_funding_pressure_incremental_forecast_value_executor_v0 import build_rows

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / integrity.EXPERIMENT_RELATIVE_PATH


@pytest.fixture(scope="module")
def synthetic_rows():
    return build_rows()


@pytest.fixture(scope="module")
def receipt(synthetic_rows):
    return integrity.reconcile(lambda: synthetic_rows)


# ==========================================================================
# 1 -- historical provenance: authenticated, not laundered, not rewritten
# ==========================================================================


def test_historical_materializer_identity_is_authenticated(receipt):
    historical = receipt["historical_provenance"]
    assert historical["historical_materializer_identity_authenticated"] is True
    assert historical["authentication_source"] == "IMMUTABLE_GIT_BLOB_AT_FROZEN_BASELINE_ANCESTORS"


def test_current_materializer_is_not_laundered_into_history(receipt):
    historical = receipt["historical_provenance"]
    assert historical["current_materializer_laundered_into_history"] is False
    kline = next(
        item for item in historical["materializers"]
        if item["relative_path"] == "qntylab/binance_um_kline_1h.py"
    )
    # The whole reason this phase exists: history and HEAD genuinely differ,
    # and the frozen record still carries the historical value.
    assert kline["diverged_from_current_worktree"] is True
    assert kline["frozen_historical_sha256"] == "e5a333f3ce08bb95fa7ef6144fffc672cf14ddf2226dc74817db62beb987cdfa"
    assert kline["current_worktree_sha256"] != kline["frozen_historical_sha256"]


def test_every_materializer_is_authenticated_against_every_anchor(receipt):
    for item in receipt["historical_provenance"]["materializers"]:
        assert item["authenticated_against"] == [provenance.PREREG_SHA, provenance.PIT_V1_SHA]


def test_frozen_provenance_baseline_bytes_are_unchanged():
    baseline_path = (
        ROOT / "experiments/research/jigsaw_funding_pressure_volatility_v0/provenance_baseline_v0.json"
    )
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    provenance.verify_self_digest(baseline, "provenance_baseline_digest")
    assert baseline["provenance_baseline_digest"] == (
        "sha256:902be2246b64d133e0f22dd71c04eba344d12ead659e5f57c69183ab92f878d9"
    )


def test_historical_provenance_fails_closed_when_the_frozen_record_is_laundered(monkeypatch):
    """A frozen record silently replaced with today's hash must not verify."""
    real_load = provenance._load
    current = provenance.file_digest(ROOT / "qntylab/binance_um_kline_1h.py")

    def _laundered(name):
        payload = copy.deepcopy(real_load(name))
        if name == "provenance_baseline_v0.json":
            for item in payload["materializer_files"]:
                if item["relative_path"] == "qntylab/binance_um_kline_1h.py":
                    item["file_sha256"] = current
        return payload

    monkeypatch.setattr(provenance, "_load", _laundered)
    with pytest.raises(AssertionError):
        integrity.verify_historical_provenance()


def test_full_provenance_baseline_verifier_passes_end_to_end():
    assert provenance.verify_baseline() == {
        "evidence_files": 505,
        "pressure_days": 975,
        "symbol_days_missing": 0,
        "historical_materializers": 2,
    }


# ==========================================================================
# 2 -- (M-02) exact panel binding
# ==========================================================================


def test_panel_binding_is_established_and_bound_to_the_frozen_prereg_digest(receipt):
    panel = receipt["panel_binding"]
    assert panel["panel_binding_established"] is True
    assert panel["m02_discharged"] is True
    assert panel["bound_to_preregistration_digest"] == (
        "d7ec718ab14e73d2aea24749a22caa2921fd81b8a336e2f2eaffb30ae1e992ef"
    )


def test_panel_is_exactly_twenty_ordered_members(receipt):
    panel = receipt["panel_binding"]["exact_ordered_panel"]
    assert len(panel) == 20
    assert len(set(panel)) == 20
    assert panel == [
        "BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT", "LINKUSDT",
        "XLMUSDT", "CHZUSDT", "SANDUSDT", "REEFUSDT", "CHRUSDT", "ALICEUSDT",
        "ONEUSDT", "API3USDT", "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT",
        "LDOUSDT", "APTUSDT",
    ]


def test_all_four_panel_sources_agree_exactly_and_in_order():
    prereg = json.loads((EXPERIMENT / "preregistration.json").read_text(encoding="utf-8"))
    source_binding = json.loads(
        (EXPERIMENT / "implementation_v0/source_binding.json").read_text(encoding="utf-8")
    )
    assert (
        list(prereg["feature_contract"]["panel"])
        == list(source_binding["exact_panel"])
        == list(v2.PANEL)
        == list(provenance.PANEL)
    )


def test_panel_order_mismatch_fails_closed(monkeypatch):
    reordered = list(provenance.PANEL)
    reordered[0], reordered[1] = reordered[1], reordered[0]
    monkeypatch.setattr(v2, "PANEL", tuple(reordered))
    with pytest.raises(integrity.PanelBindingError, match="panel order mismatch"):
        integrity.verify_panel_binding()


def test_panel_substitution_fails_closed(monkeypatch):
    substituted = list(provenance.PANEL)
    substituted[9] = "DOGEUSDT"  # REEFUSDT replaced: a declared kill condition
    monkeypatch.setattr(v2, "PANEL", tuple(substituted))
    with pytest.raises(integrity.PanelBindingError, match="panel substitution"):
        integrity.verify_panel_binding()


def test_panel_omission_fails_closed(monkeypatch):
    monkeypatch.setattr(v2, "PANEL", tuple(list(provenance.PANEL)[:-1]))
    with pytest.raises(integrity.PanelBindingError, match="panel substitution"):
        integrity.verify_panel_binding()


def test_panel_extra_member_fails_closed(monkeypatch):
    monkeypatch.setattr(v2, "PANEL", tuple(list(provenance.PANEL) + ["DOGEUSDT"]))
    with pytest.raises(integrity.PanelBindingError, match="panel substitution"):
        integrity.verify_panel_binding()


def test_provenance_panel_drift_fails_closed(monkeypatch):
    drifted = list(provenance.PANEL)
    drifted[-1] = "SOLUSDT"
    monkeypatch.setattr(provenance, "PANEL", drifted)
    with pytest.raises(integrity.PanelBindingError, match="panel substitution"):
        integrity.verify_panel_binding()


def test_panel_binding_refuses_a_preregistration_with_a_different_digest(monkeypatch, tmp_path):
    """Weak digest binding is the attack; the check must refuse to proceed."""
    fake_root = tmp_path / "root"
    target = fake_root / integrity.EXPERIMENT_RELATIVE_PATH
    target.mkdir(parents=True)
    prereg = json.loads((EXPERIMENT / "preregistration.json").read_text(encoding="utf-8"))
    prereg["feature_contract"]["panel"] = list(provenance.PANEL)
    prereg["scientific_question"] = "tampered"
    (target / "preregistration.json").write_text(json.dumps(prereg), encoding="utf-8")
    with pytest.raises(integrity.PanelBindingError, match="digest"):
        integrity.verify_panel_binding(root=fake_root)


def test_panel_binding_requires_the_preregistration_to_be_unexecuted():
    prereg = json.loads((EXPERIMENT / "preregistration.json").read_text(encoding="utf-8"))
    assert prereg["status"] == "PREREGISTERED_NOT_EXECUTED"
    assert prereg["implementation_execution_authorized"] is False


# ==========================================================================
# 3 -- exact implementation identity
# ==========================================================================


def test_implementation_identity_is_bound_to_exact_immutable_digests(receipt):
    identity = receipt["implementation_identity"]
    assert identity["implementation_identity_bound"] is True
    assert identity["governing_preregistration_digest"] == (
        "d7ec718ab14e73d2aea24749a22caa2921fd81b8a336e2f2eaffb30ae1e992ef"
    )
    assert identity["executor_sha256"] == (
        "b894d4d9316bed6f8c4f7171b32692aff7b1f0eb32abd686a33fdb38425a7490"
    )
    assert identity["v2_sha256"] == "d603e747952d31d1fa87df463b9c739bc495a4e94597c2be0f93c02c678fbbc6"
    assert identity["foundation_v0_sha256"] == (
        "834964137e4f2b77ab12a1d454f8ba8da9d71330e0806d00d1d2e26f113c980c"
    )
    assert identity["source_binding_sha256"] == (
        "9961d086b4c029f52d7840f1abfe200c0d37c6ff7368b81a14b067ae237db7ba"
    )
    assert identity["implementation_manifest_sha256"] == (
        "748c74c2cf039dab287a4b336f0443180202cc3545d1100d6ddc9532887b5fd3"
    )
    assert identity["origin_schedule_sha256"] == (
        "220eda6dc41b66820d6e1de31ed4023dcd11ec75ee713ea9d8fa9d1e74233d3a"
    )
    assert identity["execution_semantics_sha256"] == (
        "66000949a064fb913b2a61bcf716304ff324bb58e56602471a726fcbb1a7ccc4"
    )
    assert identity["frozen_implementation_sha"] == "f6f12994d65c3dfeaf7839de560e58ad99547c62"
    assert identity["evaluation_origin_count"] == 244


def test_executor_identity_drift_fails_closed(monkeypatch):
    monkeypatch.setattr(integrity, "FROZEN_EXECUTOR_SHA256", "0" * 64)
    monkeypatch.setitem(
        integrity._SOURCE_SHA256, integrity.FROZEN_EXECUTOR_RELATIVE_PATH, "0" * 64
    )
    with pytest.raises(integrity.ImplementationIdentityError, match="source identity drift"):
        integrity.verify_implementation_identity()


def test_frozen_artifact_drift_fails_closed(monkeypatch):
    monkeypatch.setitem(
        integrity._ARTIFACT_SHA256, "implementation_v0/source_binding.json", "0" * 64
    )
    with pytest.raises(integrity.ImplementationIdentityError, match="artifact identity drift"):
        integrity.verify_implementation_identity()


def test_a_missing_frozen_artifact_fails_closed(tmp_path):
    with pytest.raises(integrity.ImplementationIdentityError, match="required file is absent"):
        integrity.verify_implementation_identity(root=tmp_path)


def test_origin_schedule_still_declares_exactly_244_evaluation_origins():
    schedule = json.loads(
        (EXPERIMENT / "implementation_v0/origin_schedule.json").read_text(encoding="utf-8")
    )
    assert schedule["evaluation_origin_count"] == 244
    assert schedule["forecast_row_origin_count"] == 609
    assert schedule["evaluation_range"] == ["2024-10-19T00:00:00Z", "2025-06-19T00:00:00Z"]


def test_the_executor_self_reports_the_frozen_identity():
    identity = ex.implementation_identity()
    assert identity["implementation_source_sha256"] == (
        "b894d4d9316bed6f8c4f7171b32692aff7b1f0eb32abd686a33fdb38425a7490"
    )
    assert identity["execution_modes"] == ["SYNTHETIC_VALIDATION"]
    assert identity["downstream_authority"] == "NONE"
    assert identity["capital_authority"] == "NONE"


# ==========================================================================
# 4 -- (M-01) numerical runtime preflight, synthetic only
# ==========================================================================


def test_frozen_runtime_contract_is_built_from_literals_not_default_context():
    contract = integrity.SCIENTIFIC_RUNTIME_CONTRACT
    assert contract["constructed_from"] == "MODULE_LITERALS_NOT_DECIMAL_DEFAULTCONTEXT"
    context = integrity.SCIENTIFIC_RUNTIME_CONTEXT
    assert context.prec == 28
    assert context.rounding == decimal.ROUND_HALF_EVEN
    assert context.Emin == -999999 and context.Emax == 999999
    assert {trap for trap, on in context.traps.items() if on} == {
        decimal.InvalidOperation,
        decimal.DivisionByZero,
        decimal.Overflow,
    }


def test_synthetic_preflight_reproduces_the_frozen_synthetic_identity(receipt):
    preflight = receipt["numerical_runtime_preflight"]
    assert preflight["synthetic_runtime_preflight"] == "PASS"
    assert preflight["mode"] == "SYNTHETIC_VALIDATION"
    assert preflight["frozen_synthetic_result_digest"] == (
        "sha256:1fca55ebdbe5c4d5b835cb65f87930755d231449c924eae912b522bd04b53ea2"
    )
    assert preflight["replay_stable"] is True
    assert preflight["m01_discharged"] is True
    assert preflight["frozen_algorithm_modified"] is False


def test_no_ambient_context_ever_silently_changes_the_result(receipt):
    preflight = receipt["numerical_runtime_preflight"]
    assert preflight["silent_divergences"] == 0
    assert preflight["hostile_ambient_contexts_tested"] >= 20
    assert preflight["hostile_ambient_contexts_absorbed"] == preflight["hostile_ambient_contexts_tested"]
    assert all(
        item["outcome"] == "IDENTICAL" or item["outcome"].startswith("FAILED_CLOSED:")
        for item in preflight["unwrapped_behaviour"]
    )


@pytest.mark.parametrize(
    "ambient",
    [
        Context(prec=1, rounding=decimal.ROUND_UP),
        Context(prec=2, rounding=decimal.ROUND_FLOOR),
        Context(prec=7, rounding=decimal.ROUND_CEILING),
        Context(prec=300, rounding=decimal.ROUND_05UP),
        Context(prec=9, Emin=-5, Emax=5, rounding=decimal.ROUND_UP),
    ],
)
def test_frozen_digest_survives_hostile_ambient_precision_and_rounding(synthetic_rows, ambient):
    with localcontext(ambient):
        with integrity.scientific_runtime():
            digest = ex.run_incremental_forecast_evaluation(
                synthetic_rows, execution_mode=ex.EXECUTION_MODE_SYNTHETIC_VALIDATION
            ).result_digest
    assert digest == integrity.FROZEN_SYNTHETIC_RESULT_DIGEST


@pytest.mark.parametrize(
    "trap",
    [decimal.Inexact, decimal.Rounded, decimal.Subnormal, decimal.Clamped, decimal.Underflow, decimal.FloatOperation],
)
def test_frozen_digest_survives_hostile_ambient_traps(synthetic_rows, trap):
    ambient = Context(prec=9, rounding=decimal.ROUND_UP)
    ambient.traps[trap] = True
    with localcontext(ambient):
        with integrity.scientific_runtime():
            digest = ex.run_incremental_forecast_evaluation(
                synthetic_rows, execution_mode=ex.EXECUTION_MODE_SYNTHETIC_VALIDATION
            ).result_digest
    assert digest == integrity.FROZEN_SYNTHETIC_RESULT_DIGEST


@pytest.mark.parametrize("trap", [decimal.Inexact, decimal.Rounded])
def test_without_the_contract_a_nuisance_trap_fails_closed_and_never_diverges(synthetic_rows, trap):
    """M-01 characterised exactly: an unwrapped nuisance trap raises inside the
    precision guard. That is fail-closed -- it can never emit a *different*
    number -- and the runtime contract removes it entirely."""
    ambient = Context(prec=9, rounding=decimal.ROUND_UP)
    ambient.traps[trap] = True
    with pytest.raises(decimal.DecimalException):
        with localcontext(ambient):
            ex.run_incremental_forecast_evaluation(
                synthetic_rows, execution_mode=ex.EXECUTION_MODE_SYNTHETIC_VALIDATION
            )


def test_preflight_fails_closed_if_the_frozen_synthetic_identity_moves(monkeypatch, synthetic_rows):
    monkeypatch.setattr(integrity, "FROZEN_SYNTHETIC_RESULT_DIGEST", "sha256:" + "0" * 64)
    with pytest.raises(integrity.NumericalRuntimeError, match="frozen synthetic identity not reproduced"):
        integrity.run_synthetic_runtime_preflight(lambda: synthetic_rows)


# ==========================================================================
# 5 -- outcome firewall
# ==========================================================================


def test_outcome_firewall_attestation_is_uniformly_negative(receipt):
    firewall = receipt["outcome_firewall"]
    assert firewall["real_scientific_execution_performed"] is False
    assert firewall["real_evaluation_outcome_access_performed"] is False
    assert firewall["evaluation_origins_consumed"] == 0
    assert firewall["real_forecasts_computed"] == 0
    assert firewall["real_clark_west_computed"] is False
    assert firewall["real_mse_computed"] is False
    assert firewall["real_p_value_computed"] is False
    assert firewall["scientific_result_created"] is False
    assert firewall["scientific_result_persisted"] is False
    assert firewall["data_acquisition_performed"] is False
    assert firewall["network_access_performed"] is False
    assert firewall["frozen_evidence_mutated"] is False
    assert firewall["preregistration_mutated"] is False
    assert firewall["order_flow_modified"] is False
    assert firewall["jh01_modified"] is False
    assert firewall["authorized_execution_modes"] == ["SYNTHETIC_VALIDATION"]


def test_the_integrity_module_cannot_reach_a_real_evidence_entrypoint():
    source = (ROOT / "qntylab/jigsaw_funding_pressure_incremental_pre_execution_integrity_v0.py").read_text(
        encoding="utf-8"
    )
    for name in integrity._FORBIDDEN_REAL_EVIDENCE_ENTRYPOINTS:
        # exactly one occurrence: the forbidden-names tuple itself
        assert source.count(name) == 1, name


def test_the_integrity_module_performs_no_network_or_filesystem_write():
    source = (ROOT / "qntylab/jigsaw_funding_pressure_incremental_pre_execution_integrity_v0.py").read_text(
        encoding="utf-8"
    )
    for forbidden in ("requests", "urllib", "urlopen", "socket", "write_text", "write_bytes", "eval(", "exec("):
        assert forbidden not in source, forbidden


def test_the_executor_still_refuses_every_mode_but_synthetic_validation(synthetic_rows):
    assert ex.AUTHORIZED_EXECUTION_MODES == ("SYNTHETIC_VALIDATION",)
    for mode in ("REAL", "SCIENTIFIC_EXECUTION", "PRODUCTION", None, "", "synthetic_validation"):
        with pytest.raises(Exception):
            ex.run_incremental_forecast_evaluation(synthetic_rows, execution_mode=mode)


def test_no_scientific_result_artifact_exists_at_phase_closure():
    """No real result may exist anywhere in the funding incremental experiment."""
    forbidden = {"result.json", "execution_result.json", "scientific_result.json", "receipt.json"}
    present = {path.name for path in EXPERIMENT.rglob("*.json")}
    assert not (present & forbidden), present & forbidden


# ==========================================================================
# 6 -- the reconciliation grants no authority
# ==========================================================================


def test_the_receipt_grants_no_execution_or_downstream_authority(receipt):
    assert receipt["scientific_execution_authorized"] is False
    assert receipt["real_evaluation_outcome_access_authorized"] is False
    assert receipt["data_acquisition_authorized"] is False
    assert receipt["downstream_authority"] == "NONE"
    assert receipt["router_authority"] == "NONE"
    assert receipt["qnty_authority"] == "NONE"
    assert receipt["trading_authority"] == "NONE"
    assert receipt["capital_authority"] == "NONE"
    assert receipt["authority_level"] == "OUTCOME_BLIND_PRE_EXECUTION_INTEGRITY_VERIFICATION_ONLY"


def test_the_receipt_defers_the_real_run_to_a_separate_authorization(receipt):
    next_action = receipt["next_action"]
    assert "one-shot scientific execution authorization" in next_action
    assert "does not create, imply, or contain that authorization" in next_action


def test_module_level_authority_constants_are_all_negative():
    assert integrity.SCIENTIFIC_EXECUTION_AUTHORIZED is False
    assert integrity.REAL_EVALUATION_OUTCOME_ACCESS_AUTHORIZED is False
    assert integrity.DATA_ACQUISITION_AUTHORIZED is False
    assert integrity.DOWNSTREAM_AUTHORITY == "NONE"
    assert integrity.CAPITAL_AUTHORITY == "NONE"


def test_reconcile_without_a_synthetic_factory_does_not_silently_claim_a_preflight():
    receipt = integrity.reconcile()
    assert receipt["numerical_runtime_preflight"] == {"synthetic_runtime_preflight": "NOT_RUN"}
