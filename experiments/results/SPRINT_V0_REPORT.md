# Sprint v0 — exploratory result report

**EXPLORATORY ONLY · NON_AUTHORITATIVE · NO SCIENTIFIC VALIDATION · NO HOLDOUT · NO PAPER/LIVE AUTHORITY · NO TRADING EXECUTION**

## Dataset and quality

Public Binance Spot 1h OHLCV was retrieved from the documented `data-api.binance.vision/api/v3/klines` endpoint without credentials. Each asset has 48,821 closed bars from `2021-01-01T00:00:00Z` through `2026-07-28T18:00:00Z`.

| Asset | SHA-256 | Gaps |
|---|---|---:|
| BTCUSDT | `6dcc8c6293f24e2e91957b286a96d9b87fd646e4b57c846495bd41d1aa225b65` | 7 |
| ETHUSDT | `3584c161874dc3b8d8f9961901e5abaadebe32a1aaba6d321106b8ccb1f61187` | 7 |
| SOLUSDT | `c431aa068acbfedf3cb0c38845dfac275044a9cf83367075b47d47f06974e99d` | 7 |

The seven common gaps are retained and reported by the manifests; no bars were filled. They span two to five hours on 2021-02-11, 2021-03-06, 2021-04-20, 2021-04-25, 2021-08-13, 2021-09-29, and 2023-03-24. The equal gaps across all assets point to source availability, not an asset-specific effect.

## Semantics and matrix

Signals use information through close *t*, positions become effective for the close-*t* to close-*t+1* return, and 5/10/20 bps are charged per unit of absolute position change. A long-to-short reversal therefore costs two units. The 45 fixed runs are 15 declared variants × BTC/ETH/SOL. Full sample, chronological early/middle/late thirds, annual returns, buy-and-hold, cost stress, and concentration diagnostics are retained in the JSON receipt.

Families: H002 trailing-return momentum (four variants), H003 moving-average trend (four), H004 z-score mean reversion (three), and H005 Donchian breakouts (four). Their hypothesis, economic story, falsifier, and expected failure mode were saved in the pre-result spec.

## Ranking (best run within each family, 10 bps)

| Rank | Strategy | Assets | Net | DD | Robustness | Verdict |
|---:|---|---|---:|---:|---|---|
| 1 | H003 MA 48/192 long/flat | SOL only | 7,846.3% | -69.2% | late third -7.0%; no BTC/ETH confirmation | KILLED_SINGLE_ASSET |
| 2 | H002 168h momentum long/flat | SOL only | 1,654.3% | -82.8% | late third -37.9%; long beta; no cross-asset support | KILLED_LONG_BETA |
| 3 | H005 168h Donchian long/flat | BTC | -77.9% | -78.9% | negative at base costs | KILLED_NEGATIVE_BASE_COST |
| 4 | H004 72h z=2 mean reversion long/short | SOL | -98.2% | -98.5% | negative at base costs | KILLED_NEGATIVE_BASE_COST |

The two apparent SOL returns are compounded full-period returns, not annualized claims. For scale, 10-bps buy-and-hold was +119.8% BTC, +160.4% ETH, and +4,684.4% SOL over the same data.

## Red team, kills, and outcome

- 37/45 runs were killed for negative base-cost performance; five more were long-beta dominated; two were one-regime results; and the sole initially interesting run failed cross-asset confirmation.
- The top MA result is cost-resilient numerically (+9,197.5%, +7,846.3%, +5,703.1% at 5/10/20 bps), but that does not rescue it: it is SOL-only and turns slightly negative in the late third.
- Its best five hourly net bars contributed 64.4 percentage points and removing the best bar still left +6,754.6%, so one bar does not explain the entire result. The stronger failure is lack of cross-asset and late-period confirmation.
- H002 SOL 168h also survives 20 bps (+252.6%) but is long-only, has an -82.8% drawdown, turns negative late, and fails the buy-and-hold / cross-asset falsifiers.
- No funding claims were made: this sprint was price-only so funding did not delay its first result table.

**Conclusion: all four families are killed for this fixed sprint.** The results are exploratory diagnostics only and convey no QNTY or trading authority.
