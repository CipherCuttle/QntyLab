import copy

import pytest

from qntylab.breadth_v2_execution import FundingEvent, PortfolioKernel, PriceSeries
from qntylab.breadth_v2_path import BreadthV2PathError, build_path, describe, digest, reconcile, serialize


def _kernel_result(fee_bps=10.0, slippage_bps=0.0):
    boundaries = ["2024-01-01T00:00:00Z", "2024-01-01T01:00:00Z", "2024-01-01T02:00:00Z"]
    prices = {"BTCUSDT": PriceSeries(closes={boundaries[0]: 100.0, boundaries[1]: 110.0, boundaries[2]: 105.0})}
    funding = [FundingEvent(symbol="BTCUSDT", funding_time=boundaries[1], funding_rate=0.0001, source="test", coverage="COMPLETE")]

    def target_fn(t, prices_at_t, prior_weights, equity):
        return {"BTCUSDT": 1.0 if t != boundaries[-1] else 0.5}

    kernel = PortfolioKernel(initial_equity=1000.0, fee_bps=fee_bps, slippage_bps=slippage_bps)
    return kernel.execute(boundaries, prices, funding, target_fn, ["BTCUSDT"])


def test_path_reconciles_to_kernel_result():
    result = _kernel_result()
    rows = build_path(result)
    assert len(rows) == 3
    reconcile(rows, result, ["BTCUSDT"])  # must not raise


def test_path_is_not_bar_path_v1_and_has_own_schema():
    rows = build_path(_kernel_result())
    info = describe(rows)
    assert info["bar_path_schema_version"] == "BREADTH_V2_PATH_V0"
    assert info["bar_path_row_count"] == 3
    assert info["bar_path_first_timestamp"] == "2024-01-01T00:00:00Z"
    assert info["bar_path_last_timestamp"] == "2024-01-01T02:00:00Z"


def test_serialization_is_deterministic():
    rows = build_path(_kernel_result())
    assert serialize(rows) == serialize(copy.deepcopy(rows))
    assert digest(rows) == digest(copy.deepcopy(rows))
    payload = serialize(rows)
    assert payload.endswith(b"\n")
    assert not payload.endswith(b"\n\n")


def test_serialization_changes_with_content():
    baseline = digest(build_path(_kernel_result()))
    stressed = digest(build_path(_kernel_result(slippage_bps=10.0)))
    assert baseline != stressed


def test_reconciliation_detects_tampering():
    result = _kernel_result()
    rows = build_path(result)
    tampered = copy.deepcopy(rows)
    tampered[0]["price_pnl"] += 1.0
    with pytest.raises(BreadthV2PathError):
        reconcile(tampered, result, ["BTCUSDT"])


def test_empty_path_refused():
    with pytest.raises(BreadthV2PathError):
        serialize([])
