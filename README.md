# QntyLab

**EXPLORATORY ONLY · NON_AUTHORITATIVE · NO SCIENTIFIC VALIDATION · NO HOLDOUT · NO PAPER/LIVE AUTHORITY · NO TRADING EXECUTION**

QntyLab is a standalone, public-data strategy scratchpad. It is not part of QNTY and has no connection to QNTY control state, continuity, scientific authorization, holdout, shadow, paper, or live status. It has no broker/exchange execution code and uses no credentials.

It downloads public Binance Spot OHLCV into `data/raw/` (ignored by Git), records per-file manifests, and evaluates fixed, pre-registered price-only strategy variants. The engine computes a signal with data through close *t*, applies it from bar *t+1*, and charges costs on absolute position changes. Results are exploratory diagnostics, never trading advice or validation.

Sprint v1 adds a narrowly scoped USD-M perpetual-futures path: complete monthly Binance archives for 1h futures klines, premium-index klines, and settled funding events. It keeps premiums distinct from perpetual closes, applies funding using `-position * funding_rate` (positive funding: long pays short), and never earns a return across a source gap. Its preregistration is frozen at `experiments/specs/sprint_v1_perp.json` before runs.

```bash
python -m qntylab.cli fetch --symbols BTCUSDT ETHUSDT SOLUSDT --start 2021-01-01
python -m qntylab.cli run experiments/specs/sprint_v0.json
python -m qntylab.cli fetch-perp --symbols BTCUSDT ETHUSDT SOLUSDT --start 2021-01-01
python -m qntylab.cli run experiments/specs/sprint_v1_perp.json
python -m pytest -q
```

Minimum single-strategy test path:

```bash
python -m qntylab.strategy_test run --strategy H002_momentum --input data/raw/BTCUSDT-1h.csv --config experiments/specs/minimum_strategy_test_h002_momentum.json --output experiments/runs/h002_momentum_btcusdt_20210101_20210115
```

The strategy-test config is strict JSON with `schema_version`,
`strategy_id`, `strategy_version`, `input_path`, `evaluation_start`,
`evaluation_end`, `initial_capital`, `fee_bps`, `slippage_bps`,
`funding_boundary_mode`, and `parameters`. The funding boundary is always
explicit in the config and receipt; this exploratory path does not resolve any
Formal QNTY C2 rule. A completed run writes `metrics.json` and
`run_receipt.json` under the requested run directory.

The source is Binance's documented public-market-data endpoint. The downloader excludes the currently open candle and validates monotonic timestamps, OHLC consistency, finite positive prices, non-negative volume, and gaps without filling them.
