# Clean TSMOM experiment V2 preregistration

This directory freezes `EXP_V2` with two strategy packages: `CLEAN_V1` and
`CLEAN_V2`. It is exploratory QntyLab research only and is not validation,
trading authorization, deployment authorization, or a result artifact.

`CLEAN_V1` is unchanged: the 20-completed-8h-bar momentum signal receives
`signal / 9`, without active-only renormalization. `CLEAN_V2` changes only the
volatility timestamp alignment. At decision close `t`, it uses exactly the 90
completed returns `r_(t-89)..r_t`, where `r_j = log(close_j / close_(j-1))`.
Those weights apply to the following holding interval (`execution=t+1`).

All other frozen semantics remain unchanged: the retained nine-symbol source
bytes, dates, funding treatment, 20-bar momentum lookback, 90-return
volatility lookback, population standard deviation (`ddof=0`), 1.0 maximum
gross exposure, 7.5/15 bps costs, initial and final transaction charges, and
the existing classification thresholds.

No strategy evaluation, corrected performance, row-level output, or result
artifact exists in this preregistration directory.
