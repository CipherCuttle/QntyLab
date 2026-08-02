import csv
import json
import os
import shutil
from collections import Counter
from pathlib import Path

import pytest

from qntylab.curated_breadth_summary import (
    CELLS_PATH,
    PRIMARY_STRESS_THRESHOLD,
    VARIANTS_PATH,
    build_summary,
    sha256_path,
    write_outputs,
)


ROOT = Path(__file__).resolve().parents[1]
RESEARCH = ROOT / "experiments/research"


def _read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.open(newline="", encoding="utf-8")))


@pytest.fixture(scope="module")
def summary():
    return build_summary(ROOT)


def test_consumes_exactly_360_cells_and_15_variants(summary):
    assert len(summary["cells"]) == 360
    assert len(summary["variants"]) == 15
    assert set(Counter(row["variant_id"] for row in summary["cells"]).values()) == {24}
    assert summary["coverage"]["asset_counts"] == {"BTCUSDT": 120, "ETHUSDT": 120, "SOLUSDT": 120}
    assert summary["coverage"]["period_counts"] == {"2022": 90, "2024": 90, "2025": 90, "2026YTD": 90}
    assert summary["coverage"]["cost_mode_counts"] == {"baseline": 180, "stress": 180}
    assert summary["coverage"]["has_2023_cell"] is False


def test_missing_duplicate_or_unexpected_trial_id_is_not_accepted(tmp_path):
    shutil.copytree(ROOT / "experiments/specs", tmp_path / "experiments/specs")
    shutil.copytree(ROOT / "experiments/research", tmp_path / "experiments/research")
    shutil.copytree(ROOT / "experiments/runs/curated_breadth_screen_v1", tmp_path / "experiments/runs/curated_breadth_screen_v1")
    shutil.copytree(ROOT / "data/raw", tmp_path / "data/raw")
    trial_path = tmp_path / "experiments/research/trials/2026.jsonl"
    lines = trial_path.read_text(encoding="utf-8").splitlines()
    trial_path.write_text("\n".join(lines[:-1]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="BLOCKED_BY_SCREEN_EVIDENCE_INTEGRITY"):
        build_summary(tmp_path)
    trial_path.write_text("\n".join(lines + [lines[0]]) + "\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        build_summary(tmp_path)


def test_output_ordering_is_frozen_candidate_asset_period_cost(summary, tmp_path):
    hashes = write_outputs(summary, tmp_path)
    cells = _read_csv(tmp_path / CELLS_PATH)
    spec = json.loads((ROOT / "experiments/specs/curated_breadth_screen_v1.json").read_text(encoding="utf-8"))
    expected_prefix = []
    first_candidate = spec["candidate_details"][0]
    for symbol in spec["assets"]:
        for period_id in spec["periods"]:
            for cost_mode in spec["cost_modes"]:
                expected_prefix.append((first_candidate["candidate_id"], symbol, period_id, cost_mode))
    assert [(row["candidate_id"], row["symbol"], row["period_id"], row["cost_mode"]) for row in cells[:24]] == expected_prefix
    assert cells[0]["candidate_id"] == spec["new_candidate_ids"][0]
    assert cells[-1]["candidate_id"] == spec["new_candidate_ids"][-1]
    assert hashes[str(CELLS_PATH)] == sha256_path(tmp_path / CELLS_PATH)


def test_repeated_generation_is_byte_identical(summary, tmp_path):
    first = tmp_path / "first"
    second = tmp_path / "second"
    write_outputs(summary, first)
    rebuilt = build_summary(ROOT)
    write_outputs(rebuilt, second)
    for path in (CELLS_PATH, VARIANTS_PATH):
        assert (first / path).read_bytes() == (second / path).read_bytes()


def test_candidate_variant_identity_and_required_metrics_are_preserved(summary):
    spec = json.loads((ROOT / "experiments/specs/curated_breadth_screen_v1.json").read_text(encoding="utf-8"))
    pairs = [(row["candidate_id"], row["variant_id"]) for row in summary["variants"]]
    assert pairs == [(row["candidate_id"], row["variant_id"]) for row in spec["candidate_details"]]
    required = set(spec["common_metrics"])
    for cell in summary["cells"]:
        assert required <= set(cell)
        assert cell["candidate_id"] in spec["new_candidate_ids"]
        assert cell["variant_id"] in spec["new_variant_ids"]


def test_baseline_and_stress_cells_are_separated_and_threshold_is_8_of_12(summary):
    assert PRIMARY_STRESS_THRESHOLD == 8
    for row in summary["variants"]:
        assert row["baseline_cell_count"] == 12
        assert row["stress_cell_count"] == 12
        if row["stressed_primary_cell_count"] != "":
            assert row["stressed_primary_cell_count"] == 12
            assert row["stressed_positive_primary_gate_pass"] == (row["stressed_positive_primary_cells"] >= 8)


def test_no_performance_sorting_occurs(summary):
    cells = summary["cells"]
    net_returns = [row["net_return"] for row in cells[:24]]
    assert net_returns != sorted(net_returns)
    variants = summary["variants"]
    assert [row["candidate_id"] for row in variants] == summary["spec"]["new_candidate_ids"]


def test_no_candidate_or_decision_event_is_appended(summary):
    before = {
        "candidates": sha256_path(RESEARCH / "candidates.jsonl"),
        "decisions": sha256_path(RESEARCH / "decisions.jsonl"),
    }
    build_summary(ROOT)
    after = {
        "candidates": sha256_path(RESEARCH / "candidates.jsonl"),
        "decisions": sha256_path(RESEARCH / "decisions.jsonl"),
    }
    assert after == before


def test_source_digest_is_deterministic(summary):
    again = build_summary(ROOT)
    assert again["source_digest"] == summary["source_digest"]
    assert summary["source_hashes"][0]["path"] < summary["source_hashes"][-1]["path"]
    assert len(summary["source_hashes"]) == 728


def test_h007_comparison_fails_closed_when_historical_evidence_is_not_comparable(summary):
    comparison = summary["h007_comparison"]
    assert comparison["status"] == "H007_COMPARISON_LIMITED_BY_HISTORICAL_EVIDENCE"
    assert {"variant_id", "input_sha256", "relevant_source_sha256", "receipt_sha256"} <= set(comparison["limiting_dimensions"])
    for row in summary["variants"][-3:]:
        assert row["primary_result_metric"] == "H003_24_96_ANCHOR_DELTA_LIMITED"
        assert row["stressed_positive_primary_gate_pass"] == "H007_COMPARISON_LIMITED_BY_HISTORICAL_EVIDENCE"


def test_unrelated_wip_paths_are_not_touched(summary):
    snapshot = Path(os.environ.get("TMPDIR", "/tmp")) / "qntylab-summary"
    tracked = [line.strip() for line in (snapshot / "pre-tracked.txt").read_text(encoding="utf-8").splitlines()]
    before = (snapshot / "pre-tracked-sha256.txt").read_text(encoding="utf-8")
    now_lines = []
    for path in tracked:
        full = ROOT / path
        if full.is_file():
            now_lines.append(f"{sha256_path(full)}  {path}")
    assert "\n".join(now_lines) + ("\n" if now_lines else "") == before
