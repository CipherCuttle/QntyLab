from pathlib import Path

import pytest

from qntylab.jfp03_terminal_evidence import SourceProofError, census


ROOT = Path(__file__).parents[1]
SOURCE_ROOT = Path("/home/swirky/DevHub/repos/QntyLab")


def test_complete_authenticated_census_is_deterministic_and_not_cherry_picked():
    first = census(ROOT, source_root=SOURCE_ROOT)
    second = census(ROOT, source_root=SOURCE_ROOT)
    assert first == second
    assert first["required_afi_rows_inspected"] == 43_848
    assert first["source_object_count_authenticated"] == 63
    assert first["source_reacquisition"] is False
    assert first["violation_count"] == len(first["violations"])
    assert first["violations"] == sorted(first["violations"], key=lambda item: (item["close_boundary_ms"], item["source_object_digest"]))


def test_missing_source_object_fails_closed(tmp_path):
    with pytest.raises(SourceProofError, match="required frozen source object missing"):
        census(ROOT, source_root=tmp_path)


def test_source_algorithm_has_no_expected_historical_row_literal():
    implementation = (ROOT / "qntylab/jfp03_terminal_evidence.py").read_text(encoding="utf-8")
    assert "2024-10-28" not in implementation
