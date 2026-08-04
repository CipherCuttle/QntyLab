# QNTYLAB CLEAN TSMOM SOURCE-RESOLVED V1 EVALUATION

Status: `CLEAN_TSMOM_V1_SOURCE_RESOLVED_AND_EVALUATED_FOR_HOSTILE_REVIEW`

Contract commit: `05a93ce00cc7795f565c9109176b884e97d7640a`.
Control completion commit: `d34e4c8fbae6a752ad9bddd16b935b12949f9f8d`.
Starting V0 head and blocked receipt: `ffdab68f3c3db753ef1d764ee02143a2d4718f9b`.

## Panel

The nine-symbol panel covers `2026-03-01T00:00:00Z` through
`2026-08-01T00:00:00Z` exclusive. Each symbol has 3,672 1h rows and 459
settled funding rows; there are no remaining gaps, duplicates or off-grid
rows. No premium-index rows were required. The source manifest SHA-256 is
`8605c6675be20510691f9ed840455de59acb0536c19b1a8fc7386606b3e2470a` and the
panel manifest SHA-256 is
`f423b21d1e7fa5d696021ce3a13889a4a0894a8a85de02db2e02128bd8cccd5f`.

## Results

| Package | Cost | Net return | Sharpe | Max drawdown | Turnover | Net funding |
|---|---:|---:|---:|---:|---:|---:|
| CLEAN_V1 | base | -7.388490% | -0.921987 | -12.140522% | 29.111111 | -33.808367 |
| CLEAN_V1 | stress | -9.388664% | -1.219049 | -13.585940% | 29.111111 | -33.808367 |
| CLEAN_V2 | base | -6.752004% | -0.868534 | -11.252150% | 31.511941 | -34.602686 |
| CLEAN_V2 | stress | -8.930084% | -1.202577 | -12.839488% | 31.511941 | -34.602686 |

V2 improves net return and drawdown but increases turnover and worsens Sharpe
relative to V1: `V2_PACKAGING_COMPARISON_INCONCLUSIVE`.

The result artifact SHA-256 is
`19196a8d40d2cde7ca362289d2c5368737d9ef7067cef6b78592fcdb5e3dd9aa`.
The identical technical rerun was byte-identical. No return, benchmark,
equity, or trade metric was computed before the contract commit.

## Verdict and limits

V1: `PRELIMINARY_KILLED`.

V2: `PRELIMINARY_KILLED`.

Both packages are exploratory, non-authoritative and post-selection. This
does not authorize tuning, another evaluation, paper/shadow/live trading,
deployment, capital allocation, QNTY integration, DVOL modification, or PR
merge. V1 is a new nine-symbol experiment, not a historical reproduction.
