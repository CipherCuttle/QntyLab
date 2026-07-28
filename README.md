# QntyLab

**EXPLORATORY ONLY · NON_AUTHORITATIVE · NO SCIENTIFIC VALIDATION · NO HOLDOUT · NO PAPER/LIVE AUTHORITY · NO TRADING EXECUTION**

QntyLab is a standalone, public-data strategy scratchpad. It is not part of QNTY and has no connection to QNTY control state, continuity, scientific authorization, holdout, shadow, paper, or live status. It has no broker/exchange execution code and uses no credentials.

It downloads public Binance Spot OHLCV into `data/raw/` (ignored by Git), records per-file manifests, and evaluates fixed, pre-registered price-only strategy variants. The engine computes a signal with data through close *t*, applies it from bar *t+1*, and charges costs on absolute position changes. Results are exploratory diagnostics, never trading advice or validation.

```bash
python -m qntylab.cli fetch --symbols BTCUSDT ETHUSDT SOLUSDT --start 2021-01-01
python -m qntylab.cli run experiments/specs/sprint_v0.json
python -m pytest -q
```

The source is Binance's documented public-market-data endpoint. The downloader excludes the currently open candle and validates monotonic timestamps, OHLC consistency, finite positive prices, non-negative volume, and gaps without filling them.
