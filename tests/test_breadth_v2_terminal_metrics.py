from types import SimpleNamespace

from qntylab.breadth_v2_runner import _single_asset_cell


def test_single_asset_mdd_includes_terminal_final_equity():
    result = SimpleNamespace(
        initial_equity=1000.0,
        final_pnl=-110.0,
        turnover_notional=0.0,
        contributions={"BCHUSDT": SimpleNamespace(price_pnl=0.0, funding_pnl=0.0, fee_cost=0.0, slippage_cost=0.0)},
        boundary_path=[{"equity_after_rebalance": 900.0, "final_equity": 890.0, "turnover": 1.0, "target_weights": {"BCHUSDT": 1.0}}],
    )
    benchmark = SimpleNamespace(initial_equity=1000.0, final_pnl=0.0, contributions={"BCHUSDT": SimpleNamespace(net_contribution=0.0)})
    cell = _single_asset_cell("BCHUSDT", result, benchmark)
    assert cell["maximum_drawdown"] == -0.11
