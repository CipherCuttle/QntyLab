# ADR 0007: Clean TSMOM experiment V2 causal volatility

Status: FROZEN PREREGISTRATION

## Decision

Create `EXP_V2` with strategy packages `CLEAN_V1` and `CLEAN_V2`. Clean V1 is
preserved but the prior experiment is invalid because Clean V2 used
future-volatility information. Clean V1 matched independently; Clean V2 and
the packaging comparison were invalid. No corrected performance is reported
or used here.

The only scientific change is causal volatility alignment. Define
`r_j = log(close_j / close_(j-1))`; at decision close `t`, Clean V2 consumes
exactly `r_(t-89)..r_t`, uses `ddof=0`, and applies the resulting weights only
to the next holding interval. No observation after close `t` may affect those
weights. Clean V1 remains `signal / 9`.

The same retained nine-symbol source bytes are reused. Dates, source bytes,
momentum lookback, volatility lookback, funding semantics, costs, exposure
budget, thresholds, and all other frozen semantics are unchanged. MATIC and
POL are not in the universe.

No tuning or result-informed parameter change is allowed. Corrected results
have not been observed at contract-freeze time. This ADR is a preregistration
only and does not authorize evaluation, trading, deployment, or merge.

## Retention contract

After a separately authorized run, Git may retain compact metric and
classification summaries, source/panel/result manifests, hashes, short
diagnostic excerpts, and a receipt. Row-level panels, signals, weights,
funding assignments, turnover, costs, equity streams, controls, and diagnostic
tails remain in external run bundles referenced by SHA-256. Two independently
executed producer roots are required and must be byte-identical; the verifier
must be separate from the producing evaluator.
