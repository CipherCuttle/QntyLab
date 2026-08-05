import json
from pathlib import Path

def test_benchmark_contract_has_exact_three_benchmarks():
    p=Path(__file__).parents[1]/"experiments/clean_tsmom/v2r2/benchmark_contract_r2.json"
    assert len(json.loads(p.read_text())["benchmarks"]) == 3
