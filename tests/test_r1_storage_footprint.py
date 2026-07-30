import json
from pathlib import Path

from qntylab.r1_storage_footprint import deterministic_sample, probe_size, summarize


ROOT = Path(__file__).parents[1]


def bom():
    return json.loads((ROOT / "experiments/data/r1_population_raw_acquisition_bom_v3.json").read_text())


def test_sample_is_deterministic_bom_bound_and_cutoff_safe():
    first, second = deterministic_sample(bom()), deterministic_sample(bom())
    assert first == second and first
    assert all(row["utc_date"] <= "2026-06-30" for row in first)
    assert {"early", "middle", "late"}.issubset({label.rsplit(":", 1)[-1] for row in first for label in row["strata"] if label.startswith("year=")})


def test_head_size_and_authoritative_absence_are_typed():
    class Response:
        status = 200
        headers = {"Content-Length": "123"}
        def __enter__(self): return self
        def __exit__(self, *_): pass
    item = {"url": "https://example.test/x", "stream_id": "s", "symbol": "X", "utc_date": "2024-01-01", "strata": []}
    assert probe_size(item, opener=lambda *_args, **_kwargs: Response())["compressed_bytes"] == 123


def test_summary_is_explicit_about_unknown_funding_and_no_body_transfer():
    frozen = bom()
    stream_id = frozen["required_acquisition"]["streams"][0]["stream_id"]
    probes = [{"state": "SIZE_KNOWN", "compressed_bytes": 100, "body_bytes_transferred": 0, "utc_date": "2024-01-01", "stream_id": stream_id}, {"state": "SIZE_KNOWN", "compressed_bytes": 200, "body_bytes_transferred": 0, "utc_date": "2024-01-02", "stream_id": stream_id}]
    summary = summarize(frozen, probes, 10**15)
    assert summary["body_bytes_transferred"] == 0
    assert summary["market_raw_footprint_estimate"]["funding_bytes"] == "UNKNOWN_NOT_PROBED"
    assert set(summary["heavy_tail"]["top_stream_contribution"]) == {"1", "5", "10", "25"}
