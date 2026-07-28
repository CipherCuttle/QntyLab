# QntyLab Sprint v2 — Cross-sectional factors

**EXPLORATORY ONLY · NONAUTHORITATIVE · NO SCIENTIFIC VALIDATION · NO HOLDOUT · NO PAPER/LIVE AUTHORITY · NO TRADING EXECUTION**

## PLAN / LITERATURE

The v2 spec was frozen at commit `b5c4f16` before any v2 performance outcome.
Liu, Tsyvinski, and Wu (2022) report cryptocurrency market, size, and momentum
factors and characteristic-sorted long-short portfolios. Chi et al. (2023)
study dated cryptocurrency futures from 2017--2021: basis is their strongest
cross-sectional signal, momentum is weaker, and daily effects are stronger than
weekly. These are priors only: USD-M perpetual premium is not dated-futures
basis, and the Binance archive has different liquidity, funding, listing, and
execution conditions.

## DATA / UNIVERSE / POINT-IN-TIME ELIGIBILITY

Archive-directory discovery found 827 historical `*USDT` candidate directories,
including retired candidates, without calling the current exchange symbol list.
The local checkout contains only three hourly perp panels: BTCUSDT, ETHUSDT,
and SOLUSDT. It contains no daily cross-sectional archive manifest or panels.

Eligibility is therefore not inferred from today's universe. The frozen rule is
90 prior days, 30-day trailing median daily quote volume through time *t*, top
20 eligible contracts, and minimum breadth 10. The evaluator accepts a per-date
eligibility matrix and excludes future listings before ranking; the missing
archive panel must construct that matrix.

## SPRINT V2 PREREGISTRATION / PORTFOLIO CONSTRUCTION

Frozen spec SHA-256:
`45aa1a5efd00aa839d4b84dfd0607cadd3fb2813761dcaecc1f32d062077dda7`.

It fixes H012 7d/30d/90d momentum, H013 1d/3d reversal, H014 24h/7d funding,
and H015 premium; daily primary and weekly robustness rebalances; 20%/20%
equal-weight long-short buckets; and 5/10/20 bps absolute-weight-change costs.
Ranks use a lexical symbol tie-break. Funding is reported separately using
`-weight * settled funding rate`.

## RUN MATRIX / INFORMATION COEFFICIENTS / ATTRIBUTION / ROBUSTNESS

No factor outcomes were run. Breadth is 3, below the preregistered minimum 10;
a 20% sort would produce one long and one short name and would not be a valid
cross-sectional factor result. Thus IC, long/short attribution, costs/turnover,
year/2024+ tables, beta, age/delisting checks, concentration, and random-null
distributions are all **not computed**, not passed.

## RANDOM-RANK NULL / RED TEAM

The evaluator provides deterministic seeded random scores for the same
eligibility matrix, including zero-cost and costed comparisons when a panel
exists. The hard stop prevents the dominant present-day-universe survivorship,
current-volume leakage, and insufficient-breadth failures. Other red-team
attacks remain pending rather than assumed clean.

## KILLS / SURVIVORS / RANKING

No factor is killed or survives: no valid v2 outcome was observed.

| Rank | Factor | Net 10bps | IC | 2024+ | Random-null | Breadth | Verdict |
|---|---|---:|---:|---:|---:|---:|---|
| — | H012-H015 | — | — | — | — | 3 (<10) | NOT RUN |

## CODE CHANGES / TESTS / FILES / RECEIPTS

`qntylab/cross_section.py` adds deterministic ranks, neutral weights, causal
next-period evaluation, turnover costs, funding attribution, Spearman IC,
seeded null scores, and deterministic receipt hashing. `qntylab/data.py` adds
archive-directory discovery. The v2 spec and this report are the sprint files.
`python -m pytest -q` passes 16 tests.

## COMMIT / WHAT WE LEARNED / NEXT EXPERIMENT

The preregistration commit is `b5c4f16`. The requested cross-sectional run is
blocked by absent dynamic daily archive panels, not by a factor outcome. The
next permitted action is a one-time, manifest-pinned acquisition of complete
historical daily kline/premium/funding panels from the discovered archive
universe, followed by the frozen matrix exactly as written. Do not begin v3.

## VERDICT

QNTYLAB_XS_SPRINT_BLOCKED
