"""OHLCV leading-edge evidence assembly repair V0 -- regression suite.

JIGSAW_FUNDING_PRESSURE_VOLATILITY_OHLCV_LEADING_EDGE_EVIDENCE_REPAIR_V0

These tests prove the repaired loader assembles each symbol's execution series
from the already-certified evidence components (1 verified PIT V1 leading row +
14,640 verified V0 rows) and fails closed on every way that assembly can go
wrong. Nothing here creates an authorization, creates a remote claim, or
computes any scientific quantity; no economic price value is asserted on or
printed anywhere in this file.
"""
from __future__ import annotations

import csv
import dataclasses
import hashlib
import subprocess
import sys
import types

import pytest

from qntylab import jigsaw_funding_pressure_execution_foundation_v0 as foundation
from qntylab import jigsaw_funding_pressure_provenance_v0 as provenance

BASE_CANONICAL_SHA = "1d881739630c0da7c6a4ed03e84078b447c92bba"

REQUIRED_FIRST_SOURCE_OPEN = "2023-10-18T23:00:00Z"
REQUIRED_LAST_SOURCE_OPEN = "2025-06-19T23:00:00Z"
REQUIRED_ROWS_PER_SYMBOL = 14641
V0_ONLY_FIRST_SOURCE_OPEN = "2023-10-19T00:00:00Z"
V0_ONLY_ROWS_PER_SYMBOL = 14640


@pytest.fixture(scope="module")
def baseline() -> dict:
    return provenance._load("provenance_baseline_v0.json")


@pytest.fixture(scope="module")
def coverage(baseline) -> foundation.FrozenOhlcvCoverage:
    return foundation._verify_ohlcv_semantics_are_frozen(baseline)


@pytest.fixture(scope="module")
def extension_index(baseline, coverage) -> dict:
    return foundation._load_ohlcv_extension_index(baseline, provenance.ROOT, coverage)


@pytest.fixture(scope="module")
def assembled(baseline, coverage, extension_index) -> dict:
    """Assemble all 20 symbols once; structural verification only."""
    return {
        symbol: foundation._load_ohlcv_symbol(
            symbol, baseline, provenance.ROOT, extension_bar=extension_index[symbol], coverage=coverage
        )
        for symbol in provenance.PANEL
    }


def _extension_rows() -> list[dict]:
    path = provenance.EXPERIMENT / "pit_coverage_evidence_v1/source_bar_extension.csv"
    with path.open("r", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def _git_show_bytes(spec: str) -> bytes:
    return subprocess.run(
        ["git", "show", spec], cwd=provenance.ROOT, check=True, capture_output=True
    ).stdout


# ==========================================================================
# A. Reproduce the old failure at the pre-repair base
# ==========================================================================


def test_a_pre_repair_v0_only_evidence_misses_the_required_leading_hour():
    """The V0 normalized evidence -- all the pre-repair loader ever read -- starts
    one hour late for every frozen symbol."""
    for symbol in provenance.PANEL:
        path = provenance.EXPERIMENT / f"pit_coverage_evidence_v0/raw/{symbol}-perp-1h.csv"
        with path.open("r", encoding="utf-8", newline="") as fh:
            rows = list(csv.DictReader(fh))
        assert len(rows) == V0_ONLY_ROWS_PER_SYMBOL
        assert rows[0]["timestamp"] == V0_ONLY_FIRST_SOURCE_OPEN
        assert rows[-1]["timestamp"] == REQUIRED_LAST_SOURCE_OPEN
        assert all(row["timestamp"] != REQUIRED_FIRST_SOURCE_OPEN for row in rows)


def test_a_pre_repair_loader_source_read_only_the_v0_entry():
    """At BASE_CANONICAL_SHA the loader seam knew nothing about the extension."""
    source = _git_show_bytes(
        f"{BASE_CANONICAL_SHA}:qntylab/jigsaw_funding_pressure_execution_foundation_v0.py"
    ).decode("utf-8")
    assert "ohlcv_leading_edge_extension_evidence" not in source
    assert "_load_ohlcv_extension_index" not in source
    assert "source_bar_extension" not in source


# ==========================================================================
# B / C / I. Correct assembly, contiguity, trailing boundary
# ==========================================================================


def test_b_assembled_series_has_exact_required_coverage(assembled):
    for symbol in provenance.PANEL:
        bars = assembled[symbol]
        assert len(bars) == REQUIRED_ROWS_PER_SYMBOL
        assert bars[0].source_open_time == REQUIRED_FIRST_SOURCE_OPEN
        assert bars[-1].source_open_time == REQUIRED_LAST_SOURCE_OPEN


def test_c_every_adjacent_source_open_differs_by_exactly_one_hour(assembled):
    from datetime import datetime, timedelta

    one_hour = timedelta(hours=1)
    for symbol in provenance.PANEL:
        bars = assembled[symbol]
        stamps = [datetime.fromisoformat(bar.source_open_time[:-1] + "+00:00") for bar in bars]
        assert all(b - a == one_hour for a, b in zip(stamps, stamps[1:]))
        assert len(set(stamps)) == REQUIRED_ROWS_PER_SYMBOL  # zero duplicates


def test_i_trailing_boundary_is_unchanged_by_the_repair(assembled, coverage):
    assert coverage.last_source_open == REQUIRED_LAST_SOURCE_OPEN
    for symbol in provenance.PANEL:
        assert assembled[symbol][-1].source_open_time == REQUIRED_LAST_SOURCE_OPEN


def test_coverage_is_derived_from_the_frozen_pit_v1_certificate(coverage):
    certificate = provenance._load("pit_coverage_certificate_v1.json")
    assert coverage.first_source_open == certificate["first_required_source_bar"]
    assert coverage.last_source_open == certificate["last_required_source_bar"]
    assert coverage.rows_per_symbol == certificate["ohlcv_census"][0]["rows_per_symbol"]
    assert coverage.rows_per_symbol == REQUIRED_ROWS_PER_SYMBOL


# ==========================================================================
# D. The V1 extension is actually consumed (not accidentally still V0-only)
# ==========================================================================


def test_d_leading_bar_of_every_symbol_comes_from_the_v1_extension(assembled, extension_index):
    for symbol in provenance.PANEL:
        assert assembled[symbol][0] is extension_index[symbol]
        assert assembled[symbol][0].source_open_time == REQUIRED_FIRST_SOURCE_OPEN


def test_d_removing_the_extension_evidence_entry_fails_closed(baseline, coverage):
    """A baseline with no leading-edge extension role cannot load OHLCV evidence."""
    stripped = dict(baseline)
    stripped["evidence_files"] = [
        entry
        for entry in baseline["evidence_files"]
        if entry["logical_role"] != foundation.OHLCV_LEADING_EDGE_EXTENSION_ROLE
    ]
    with pytest.raises(foundation.EvidenceValidationError, match="expected exactly one"):
        foundation._load_ohlcv_extension_index(stripped, provenance.ROOT, coverage)


def test_d_missing_symbol_in_extension_fails_closed(coverage):
    rows = [row for row in _extension_rows() if row["symbol"] != "APTUSDT"]
    with pytest.raises(foundation.EvidenceValidationError, match="missing required rows"):
        foundation._index_extension_rows(rows, coverage)


def test_d_v0_only_series_is_rejected_by_exact_coverage_validation(baseline, coverage):
    """Assembling without the leading row can no longer reach scientific code."""
    symbol = "BCHUSDT"
    entry = foundation._ohlcv_raw_evidence_entry(symbol, baseline)
    path = provenance.ROOT / entry["relative_path"]
    with path.open("r", encoding="utf-8", newline="") as fh:
        v0_only = tuple(foundation.parse_ohlcv_row(row, symbol=symbol) for row in csv.DictReader(fh))
    assert len(v0_only) == V0_ONLY_ROWS_PER_SYMBOL
    with pytest.raises(foundation.EvidenceValidationError, match="required exactly 14641"):
        foundation._validate_exact_ohlcv_coverage(v0_only, symbol=symbol, coverage=coverage)


# ==========================================================================
# E / F / G. Duplicate, wrong symbol, wrong timestamp
# ==========================================================================


def test_e_duplicate_extension_row_for_one_symbol_fails_closed(coverage):
    rows = _extension_rows()
    duplicated = rows + [dict(rows[0])]
    with pytest.raises(foundation.EvidenceValidationError, match="duplicate extension row"):
        foundation._index_extension_rows(duplicated, coverage)


def test_f_off_panel_extension_symbol_fails_closed(coverage):
    rows = _extension_rows()
    rows[0] = dict(rows[0], symbol="BTCUSDT")
    with pytest.raises(foundation.EvidenceValidationError, match="not in the frozen panel"):
        foundation._index_extension_rows(rows, coverage)


def test_f_extension_bar_for_the_wrong_symbol_fails_closed(baseline, coverage, extension_index):
    with pytest.raises(foundation.EvidenceValidationError, match="carries symbol"):
        foundation._load_ohlcv_symbol(
            "BCHUSDT",
            baseline,
            provenance.ROOT,
            extension_bar=extension_index["XRPUSDT"],
            coverage=coverage,
        )


def test_g_wrong_leading_timestamp_fails_closed(coverage):
    rows = _extension_rows()
    rows[0] = dict(rows[0], timestamp="2023-10-18T22:00:00Z")
    with pytest.raises(foundation.EvidenceValidationError, match="is not the required leading source-open"):
        foundation._index_extension_rows(rows, coverage)


def test_g_malformed_extension_row_fails_closed(coverage):
    rows = _extension_rows()
    rows[0] = dict(rows[0], close="not-a-decimal")
    with pytest.raises(foundation.EvidenceValidationError, match="close is not a valid decimal"):
        foundation._index_extension_rows(rows, coverage)


def test_interior_hourly_gap_fails_closed(assembled, coverage):
    """A bridged interior hour is rejected even when count and both boundaries are exact."""
    bars = assembled["BCHUSDT"]
    # Same length, same first/last: only the interior adjacency is broken.
    displaced = dataclasses.replace(bars[5], source_open_time=bars[6].source_open_time)
    gapped = bars[:5] + (displaced,) + bars[6:]
    assert len(gapped) == REQUIRED_ROWS_PER_SYMBOL
    assert gapped[0].source_open_time == REQUIRED_FIRST_SOURCE_OPEN
    assert gapped[-1].source_open_time == REQUIRED_LAST_SOURCE_OPEN
    with pytest.raises(foundation.EvidenceValidationError, match="interior hourly gap"):
        foundation._validate_exact_ohlcv_coverage(gapped, symbol="BCHUSDT", coverage=coverage)


def test_missing_interior_hour_fails_closed(assembled, coverage):
    """Dropping an interior hour is caught by the exact row-count requirement."""
    bars = assembled["BCHUSDT"]
    with pytest.raises(foundation.EvidenceValidationError, match="required exactly 14641"):
        foundation._validate_exact_ohlcv_coverage(bars[:5] + bars[6:], symbol="BCHUSDT", coverage=coverage)


# ==========================================================================
# H. Hash / provenance mutation fails closed before evidence is returned
# ==========================================================================


def test_h_extension_hash_mutation_fails_closed(baseline, coverage):
    mutated = dict(baseline)
    mutated["evidence_files"] = [
        dict(entry, sha256="0" * 64)
        if entry["logical_role"] == foundation.OHLCV_LEADING_EDGE_EXTENSION_ROLE
        else entry
        for entry in baseline["evidence_files"]
    ]
    with pytest.raises(AssertionError, match="evidence byte mismatch"):
        foundation._load_ohlcv_extension_index(mutated, provenance.ROOT, coverage)


def test_h_extension_size_mutation_fails_closed(baseline, coverage):
    mutated = dict(baseline)
    mutated["evidence_files"] = [
        dict(entry, size_bytes=entry["size_bytes"] + 1)
        if entry["logical_role"] == foundation.OHLCV_LEADING_EDGE_EXTENSION_ROLE
        else entry
        for entry in baseline["evidence_files"]
    ]
    with pytest.raises(AssertionError, match="evidence byte mismatch"):
        foundation._load_ohlcv_extension_index(mutated, provenance.ROOT, coverage)


def test_h_extension_path_redirection_fails_closed(baseline, coverage):
    """The selected extension path must match the path the PIT V1 certificate binds."""
    mutated = dict(baseline)
    mutated["evidence_files"] = [
        dict(entry, relative_path="experiments/research/jigsaw_funding_pressure_volatility_v0/elsewhere.csv")
        if entry["logical_role"] == foundation.OHLCV_LEADING_EDGE_EXTENSION_ROLE
        else entry
        for entry in baseline["evidence_files"]
    ]
    with pytest.raises(foundation.EvidenceValidationError, match="does not match the path bound by the"):
        foundation._load_ohlcv_extension_index(mutated, provenance.ROOT, coverage)


def test_h_two_canonical_extension_artifacts_fail_closed(baseline, coverage):
    extension = next(
        entry for entry in baseline["evidence_files"]
        if entry["logical_role"] == foundation.OHLCV_LEADING_EDGE_EXTENSION_ROLE
    )
    mutated = dict(baseline, evidence_files=[*baseline["evidence_files"], dict(extension)])
    with pytest.raises(foundation.EvidenceValidationError, match="expected exactly one"):
        foundation._load_ohlcv_extension_index(mutated, provenance.ROOT, coverage)


def test_h_provenance_baseline_self_digest_is_intact():
    provenance.verify_self_digest(provenance._load("provenance_baseline_v0.json"), "provenance_baseline_digest")


def test_h_foundation_contract_self_digest_is_intact():
    assert foundation.execution_foundation_contract_digest().startswith("sha256:")


def test_h_repaired_baseline_binds_the_extension_with_a_narrow_role(baseline):
    matches = [
        entry
        for entry in baseline["evidence_files"]
        if entry["logical_role"] == foundation.OHLCV_LEADING_EDGE_EXTENSION_ROLE
    ]
    assert len(matches) == 1
    assert matches[0]["relative_path"].endswith("pit_coverage_evidence_v1/source_bar_extension.csv")
    # The role is narrow: it did not turn generic experiment metadata into evidence.
    assert not any(
        entry["logical_role"] == foundation.OHLCV_LEADING_EDGE_EXTENSION_ROLE
        and entry["relative_path"].endswith("extension_manifest.json")
        for entry in baseline["evidence_files"]
    )


# ==========================================================================
# J. Frozen science is byte-identical to the base canonical commit
# ==========================================================================


@pytest.mark.parametrize(
    "relative_path",
    [
        "experiments/research/jigsaw_funding_pressure_volatility_v0/preregistration.json",
        "experiments/research/jigsaw_funding_pressure_volatility_v0/execution_enablement_v2_contract.json",
        "qntylab/jigsaw_funding_pressure_execution_v2.py",
    ],
)
def test_j_frozen_science_bytes_unchanged_from_base_canonical_commit(relative_path):
    base = _git_show_bytes(f"{BASE_CANONICAL_SHA}:{relative_path}")
    current = (provenance.ROOT / relative_path).read_bytes()
    assert hashlib.sha256(current).hexdigest() == hashlib.sha256(base).hexdigest()


@pytest.mark.parametrize(
    "relative_path",
    [
        "experiments/research/jigsaw_funding_pressure_volatility_v0/pit_coverage_certificate_v1.json",
        "experiments/research/jigsaw_funding_pressure_volatility_v0/pit_coverage_evidence_v1/source_bar_extension.csv",
        "experiments/research/jigsaw_funding_pressure_volatility_v0/pit_coverage_evidence_v1/extension_manifest.json",
    ],
)
def test_j_certified_evidence_and_certificate_bytes_unchanged(relative_path):
    """No evidence byte was rewritten: the repair is pure assembly."""
    base = _git_show_bytes(f"{BASE_CANONICAL_SHA}:{relative_path}")
    current = (provenance.ROOT / relative_path).read_bytes()
    assert hashlib.sha256(current).hexdigest() == hashlib.sha256(base).hexdigest()


def test_j_all_twenty_v0_raw_evidence_files_unchanged():
    for symbol in provenance.PANEL:
        relative_path = (
            "experiments/research/jigsaw_funding_pressure_volatility_v0"
            f"/pit_coverage_evidence_v0/raw/{symbol}-perp-1h.csv"
        )
        base = _git_show_bytes(f"{BASE_CANONICAL_SHA}:{relative_path}")
        current = (provenance.ROOT / relative_path).read_bytes()
        assert hashlib.sha256(current).hexdigest() == hashlib.sha256(base).hexdigest()


def test_j_pit_v1_and_ohlcv_identities_are_preserved():
    assert provenance.PIT_V1_DIGEST == "sha256:eee5ce2769e49970a7a4e8d4851d7da569abc156d4f183959b416bfb8dbf188b"
    assert provenance.OHLCV_DIGEST == "sha256:97760d127e33c51f2ac687f5f8edb92ffa3ac01b1c7c963951872a87ab3b5ae9"


# ==========================================================================
# K. No claim, no authorization, no scientific outcome
# ==========================================================================


def test_k_no_outcome_attestation_still_holds():
    assert all(value is False for value in foundation.NO_OUTCOME_ATTESTATION.values())


def test_k_repair_module_never_touches_the_scientific_executor():
    source = (provenance.ROOT / "qntylab/jigsaw_funding_pressure_execution_foundation_v0.py").read_text(
        encoding="utf-8"
    )
    assert "compute_frozen_experiment" not in source
    assert "jigsaw_funding_pressure_execution_v2" not in source


def test_k_this_suite_creates_no_remote_claim_and_no_authorization():
    """No test function in this suite references the claim, authorization, or science surface."""
    forbidden = {
        "".join(("claim_", "authorization_once")),
        "".join(("GitHubRest", "RemoteClaimTransport")),
        "".join(("compute_", "frozen_experiment")),
        "".join(("from_", "environment")),
        "".join(("create_", "ref")),
    }
    referenced: set[str] = set()
    for value in list(vars(sys.modules[__name__]).values()):
        if isinstance(value, types.FunctionType):
            referenced |= set(value.__code__.co_names)
    assert not (forbidden & referenced)
