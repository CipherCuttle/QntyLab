# Hostile review — Breadth V2 family decision aggregation V0

Independent review scope: only `qntylab/breadth_v2_family_decision.py` and
its synthetic test matrix.

| Attack | Result | Severity | Disposition |
|---|---|---:|---|
| Best variant dominates | Frozen adjacent-pair gate; winner-only fixture fails | Critical | Fixed/covered |
| BLOCKED becomes zero/negative | BLOCKED rows are excluded from arithmetic and retained in denominators | Critical | Fixed/covered |
| Asset/window denominator shrinks | Receipt retains 20 assets and 3 periods | High | Fixed/covered |
| Positive support concentration bypass | Positive-only denominator and 35% boundary are explicit | High | Fixed/covered |
| Baseline/stress composition drift | Exact normalized-key matching; missing pair blocks | Critical | Fixed/covered |
| Isolated non-adjacent support | Only frozen adjacent pairs qualify | High | Fixed/covered |
| Panel/unit mixing | Panel cells are normalized by recorded initial equity and reconciled | High | Fixed/covered |
| Wrong long/short boundary | PnL uses prior target; sign-flip fixture covers it | Critical | Fixed/covered |
| Long-only masquerades as neutral | +1/-1/2/0 invariant blocks | Critical | Fixed/covered |
| New beta/turnover threshold | Turnover is descriptive only; no beta gate exists | High | Fixed/covered |
| Volatility-targeting exception | It uses the same gates as every family | High | Fixed/covered |
| Integrity becomes economic graveyard | Integrity is adjudicated as BLOCKED before FAIL | Critical | Fixed/covered |
| Real outcomes accessed | No execution/evaluator/ledger imports or calls; synthetic-only tests | Critical | Fixed/covered |
| Input order changes result | Canonical sorted receipt and deterministic means | High | Fixed/covered |

Disposition: no unresolved Critical/High findings. No targeted re-review is
required.
