# Scope

Review of committed `CURATED_BREADTH_SCREEN_V1` evidence at `2fbe6765fe173224c4d187161d72eee2c2ba180b`. This is an exploratory research decision review only. No strategy, parameter, trial, portfolio, master strategy, regime router, Formal QNTY promotion, or trading authority is introduced.

# Evidence Reviewed

Measured facts:

- `experiments/specs/curated_breadth_screen_v1.json` SHA-256 `ab72d96e5c3e4e0e133530f0ad936248b32fd06f8b210e50901f9423dea7586d`
- `experiments/research/summaries/curated_breadth_screen_v1_cells.csv` SHA-256 `d1b3af9e46b6815c4b97913726cc3ee20455f86244e6a8f021b2131b6b589386`
- `experiments/research/summaries/curated_breadth_screen_v1_variants.csv` SHA-256 `c47880a1a1c8a10a78e62227bf85f86535661c8b734ecc2cb1033f19531be0af`
- `experiments/research/summaries/curated_breadth_screen_v1_mechanical_summary.md` SHA-256 `3290f8edc62a34c4535f41d97ef3402483fe2a06ceceba2ae7b1e737e9c6ff71`
- `experiments/research/summaries/first_batch_summary_compact.csv` SHA-256 `958558f68e69051fb134657840dd79d29f3ee40155012b53b693b9b2294f6a03`
- `experiments/research/summaries/h002_h003_followup_v1_summary_compact.csv` SHA-256 `9a560880923785d7236e58d17072c6816538f939c240a11e957eb2851f99b10b`

Primary metric contract:

- H002, H003, and H005 are market-timing overlays with `BUY_AND_HOLD_PRIMARY_AND_CASH_SECONDARY`; the committed summary uses `excess_return_vs_buy_and_hold`.
- H006 is `CASH_PRIMARY_AND_BUY_AND_HOLD_SECONDARY`; the committed summary uses `net_return`.
- H007 is registered against `H003_24_96_UNSCALED_PRIMARY_AND_BUY_AND_HOLD_SECONDARY`; the committed summary fails closed as `H003_24_96_ANCHOR_DELTA_LIMITED` because historical H003 24/96 evidence lacks required comparability dimensions.

All 15 variants completed 24 scheduled cells, passed receipt/metrics integrity, and preserve frozen candidate order. Deterministic gates excluding judgment-only gates and H007 limited comparisons passed for 3 of 15 variants.

# Exact Plausible Variants

Measured facts:

| candidate_id | variant_id | family | parameters |
| --- | --- | --- | --- |
| CANDIDATE_H002_MOMENTUM_720_LONG_FLAT | variant_f201cbb38819b1e09e763ac7 | time_series_momentum | `{"lookback":720,"mode":"long_flat"}` |
| CANDIDATE_H003_MA_48_192_LONG_FLAT | variant_00eb140f03a5f6ab40600160 | moving_average_trend | `{"fast":48,"mode":"long_flat","slow":192}` |
| CANDIDATE_H003_MA_168_720_LONG_FLAT | variant_296a2973dfde57cec911715b | moving_average_trend | `{"fast":168,"mode":"long_flat","slow":720}` |

All 15 deterministic gate inputs in frozen candidate order:

| candidate_id | completion | integrity | stressed positivity | asset breadth | period breadth | concentration evidence | turnover evidence | stress-cost evidence |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| CANDIDATE_H002_MOMENTUM_72_LONG_FLAT | pass | pass | 2/12 fail | 3 pass | 1 fail | best cell 0.604 | trades median 434 total 4789; stress cost total 9.578 | baseline primary -2.645; stress -5.338 |
| CANDIDATE_H002_MOMENTUM_168_LONG_FLAT | pass | pass | 4/12 fail | 3 pass | 3 pass | best cell 0.284 | trades median 286 total 3162; stress cost total 6.324 | baseline primary -1.484; stress -3.544 |
| CANDIDATE_H002_MOMENTUM_720_LONG_FLAT | pass | pass | 8/12 pass | 3 pass | 3 pass | best cell 0.249 | trades median 109 total 1235; stress cost total 2.470 | baseline primary 2.151; stress 0.925 |
| CANDIDATE_H003_MA_12_48_LONG_FLAT | pass | pass | 6/12 fail | 3 pass | 2 pass | best cell 0.326 | trades median 226.5 total 2435; stress cost total 4.870 | baseline primary -1.317; stress -3.016 |
| CANDIDATE_H003_MA_48_192_LONG_FLAT | pass | pass | 8/12 pass | 3 pass | 4 pass | best cell 0.202 | trades median 54.5 total 624; stress cost total 1.248 | baseline primary 1.347; stress 0.729 |
| CANDIDATE_H003_MA_168_720_LONG_FLAT | pass | pass | 9/12 pass | 3 pass | 4 pass | best cell 0.229 | trades median 12 total 150; stress cost total 0.300 | baseline primary 1.842; stress 1.692 |
| CANDIDATE_H005_DONCHIAN_168_LONG_FLAT | pass | pass | 5/12 fail | 3 pass | 3 pass | best cell 0.289 | trades median 270 total 3096; stress cost total 6.192 | baseline primary -1.725; stress -3.661 |
| CANDIDATE_H005_DONCHIAN_720_LONG_FLAT | pass | pass | 7/12 fail | 3 pass | 3 pass | best cell 0.286 | trades median 111 total 1326; stress cost total 2.652 | baseline primary -0.311; stress -1.329 |
| CANDIDATE_H006_REVERSAL_1_LONG_SHORT | pass | pass | 0/12 fail | 0 fail | 0 fail | no positive primary cells | trades median 4600 total 49499; stress cost total 196.936 | baseline primary -11.973; stress -12.000 |
| CANDIDATE_H006_REVERSAL_3_LONG_SHORT | pass | pass | 0/12 fail | 0 fail | 0 fail | no positive primary cells | trades median 2493 total 27284; stress cost total 108.448 | baseline primary -11.732; stress -11.989 |
| CANDIDATE_H006_REVERSAL_6_LONG_SHORT | pass | pass | 0/12 fail | 0 fail | 0 fail | no positive primary cells | trades median 1736.5 total 19094; stress cost total 75.976 | baseline primary -11.338; stress -11.936 |
| CANDIDATE_H006_REVERSAL_12_LONG_SHORT | pass | pass | 0/12 fail | 0 fail | 0 fail | no positive primary cells | trades median 1219.5 total 13043; stress cost total 51.856 | baseline primary -10.488; stress -11.746 |
| CANDIDATE_H007_VOL_SCALED_MA_24_96_RV24 | pass | pass | limited | 0 fail | 0 fail | H003 anchor delta limited | trades median 1963.5 total 22104; stress cost total 3.188 | H007 comparison limited |
| CANDIDATE_H007_VOL_SCALED_MA_24_96_RV72 | pass | pass | limited | 0 fail | 0 fail | H003 anchor delta limited | trades median 1916 total 21426; stress cost total 2.625 | H007 comparison limited |
| CANDIDATE_H007_VOL_SCALED_MA_24_96_RV168 | pass | pass | limited | 0 fail | 0 fail | H003 anchor delta limited | trades median 1947 total 22072; stress cost total 2.426 | H007 comparison limited |

# Concentration Review

Measured facts and judgment for mechanically plausible variants:

| candidate_id | strongest cell | strongest asset contribution | strongest period contribution | remaining cells | without best cell | judgment |
| --- | ---: | ---: | ---: | --- | ---: | --- |
| CANDIDATE_H002_MOMENTUM_720_LONG_FLAT | ETHUSDT 2025, 0.856 | ETHUSDT 1.754; BTCUSDT -0.119; SOLUSDT 0.516 | 2022 1.489; 2024 -1.295; 2025 1.029; 2026YTD 0.929 | 8/11 positive after removing best cell | 1.294 | ACCEPTABLE |
| CANDIDATE_H003_MA_48_192_LONG_FLAT | SOLUSDT 2025, 0.420 | SOLUSDT 0.962; ETHUSDT 0.555; BTCUSDT -0.170 | 2022 1.026; 2024 -0.592; 2025 0.536; 2026YTD 0.378 | 8/11 positive after removing best cell | 0.927 | ACCEPTABLE |
| CANDIDATE_H003_MA_168_720_LONG_FLAT | ETHUSDT 2025, 0.645 | ETHUSDT 1.267; SOLUSDT 0.770; BTCUSDT -0.194 | 2022 0.907; 2024 -0.700; 2025 0.772; 2026YTD 0.863 | 8/11 positive after removing best cell | 1.197 | ACCEPTABLE |

Judgment:

- Each plausible variant stays positive after removing the strongest cell.
- Each has at least two positive asset contributions or broad period support, but all three share BTCUSDT weakness and 2024 weakness.
- These are acceptable for exact follow-up, not for validation or family-wide promotion.

# Turnover Review

Measured facts and judgment:

| candidate_id | intended horizon | median trades | total trades | stress total cost | judgment |
| --- | --- | ---: | ---: | ---: | --- |
| CANDIDATE_H002_MOMENTUM_720_LONG_FLAT | 720h lookback, long horizon | 109 | 1235 | 2.470 | COMPATIBLE |
| CANDIDATE_H003_MA_48_192_LONG_FLAT | 48/192h moving-average trend | 54.5 | 624 | 1.248 | COMPATIBLE |
| CANDIDATE_H003_MA_168_720_LONG_FLAT | 168/720h moving-average trend | 12 | 150 | 0.300 | COMPATIBLE |

Judgment:

- H002 720 is materially less turnover-intensive than shorter H002 variants and keeps positive stressed primary evidence, so cost sensitivity is compatible with its long-horizon intent.
- H003 48/192 and H003 168/720 have trade counts consistent with their trend horizons; H003 168/720 has especially low cost drag.
- H006 variants are incompatible despite short-horizon intent: 0/12 stressed positive net cells, near-total capital loss under stress, and stress costs from 51.856 to 196.936 across 12 cells make the unfiltered exact variants economically unusable.

# Stress-Survival Review

Measured facts and judgment:

| candidate_id | baseline primary | stressed primary | stressed positive cells | stress effect | judgment |
| --- | ---: | ---: | ---: | --- | --- |
| CANDIDATE_H002_MOMENTUM_720_LONG_FLAT | 2.151 | 0.925 | 8/12 | sign preserved; magnitude reduced; breadth preserved across 3 assets and 3 periods | survives |
| CANDIDATE_H003_MA_48_192_LONG_FLAT | 1.347 | 0.729 | 8/12 | sign preserved; magnitude reduced; breadth preserved across 3 assets and 4 periods | survives |
| CANDIDATE_H003_MA_168_720_LONG_FLAT | 1.842 | 1.692 | 9/12 | sign preserved with small cost drag; breadth preserved across 3 assets and 4 periods | survives |

Judgment:

- Stress costs reduce magnitude but do not erase the exact plausible variants.
- H002 72, H002 168, H003 12/48, H005 168, H005 720, and all H006 variants have negative stressed aggregate primary results or complete breadth failure and do not survive as exact variants.
- H007 stress survival against the registered H003 24/96 benchmark cannot be adjudicated from the committed historical anchor evidence.

# H007 Evidence Limitation

Measured facts:

- Mechanical status: `H007_COMPARISON_LIMITED_BY_HISTORICAL_EVIDENCE`.
- Missing comparability dimensions in the historical H003 24/96 anchor: `candidate_id`, `input_sha256`, `parameters`, `receipt_sha256`, `relevant_source_sha256`, `variant_id`.
- Existing supported ledger state for insufficient or non-comparable evidence is `BLOCKED`.

Judgment:

- This is not evidence that H007 failed economically.
- It is insufficient evidence to adjudicate whether volatility scaling improves H003 24/96.
- The smallest scientifically valid next step is to preregister a controlled H003 24/96 benchmark reconstruction, because the committed compact historical evidence lacks the provenance fields needed for non-rerun enrichment.

# Exact-Variant Decisions

Measured facts, judgment, and appended canonical decision intent:

| candidate_id | variant_id | status | reason codes |
| --- | --- | --- | --- |
| CANDIDATE_H002_MOMENTUM_72_LONG_FLAT | variant_d145d2024811f49eea291a29 | GRAVEYARDED | `FAILED_STRESSED_PRIMARY_BREADTH`, `PERIOD_BREADTH_FAIL`, `NEGATIVE_AGGREGATE_PRIMARY_UNDER_STRESS` |
| CANDIDATE_H002_MOMENTUM_168_LONG_FLAT | variant_f7167cdc0acf445a69f10b5c | GRAVEYARDED | `FAILED_STRESSED_PRIMARY_BREADTH`, `NEGATIVE_AGGREGATE_PRIMARY_UNDER_STRESS` |
| CANDIDATE_H002_MOMENTUM_720_LONG_FLAT | variant_f201cbb38819b1e09e763ac7 | FOLLOW_UP | `PASSED_DETERMINISTIC_GATES`, `CONCENTRATION_ACCEPTABLE`, `TURNOVER_COMPATIBLE`, `STRESS_SURVIVED` |
| CANDIDATE_H003_MA_12_48_LONG_FLAT | variant_546746242433ddc20c85b34e | GRAVEYARDED | `FAILED_STRESSED_PRIMARY_BREADTH`, `NEGATIVE_AGGREGATE_PRIMARY_UNDER_STRESS` |
| CANDIDATE_H003_MA_48_192_LONG_FLAT | variant_00eb140f03a5f6ab40600160 | FOLLOW_UP | `PASSED_DETERMINISTIC_GATES`, `CONCENTRATION_ACCEPTABLE`, `TURNOVER_COMPATIBLE`, `STRESS_SURVIVED` |
| CANDIDATE_H003_MA_168_720_LONG_FLAT | variant_296a2973dfde57cec911715b | FOLLOW_UP | `PASSED_DETERMINISTIC_GATES`, `CONCENTRATION_ACCEPTABLE`, `TURNOVER_COMPATIBLE`, `STRESS_SURVIVED` |
| CANDIDATE_H005_DONCHIAN_168_LONG_FLAT | variant_03c4724abe6c8715f5eaa727 | GRAVEYARDED | `FAILED_STRESSED_PRIMARY_BREADTH`, `NEGATIVE_AGGREGATE_PRIMARY_UNDER_STRESS`, `NO_POSITIVE_NET_RETURN_CELLS` |
| CANDIDATE_H005_DONCHIAN_720_LONG_FLAT | variant_9537b83ca36824b3cd47adc1 | GRAVEYARDED | `FAILED_STRESSED_PRIMARY_BREADTH`, `NEGATIVE_AGGREGATE_PRIMARY_UNDER_STRESS`, `NO_POSITIVE_NET_RETURN_CELLS` |
| CANDIDATE_H006_REVERSAL_1_LONG_SHORT | variant_66cfc915025fc7745f4c51e2 | GRAVEYARDED | `ZERO_STRESSED_POSITIVE_PRIMARY_CELLS`, `ASSET_BREADTH_FAIL`, `PERIOD_BREADTH_FAIL`, `TURNOVER_INCOMPATIBLE`, `NEGATIVE_AGGREGATE_PRIMARY_UNDER_STRESS` |
| CANDIDATE_H006_REVERSAL_3_LONG_SHORT | variant_c21463e36d437e98cf38698b | GRAVEYARDED | `ZERO_STRESSED_POSITIVE_PRIMARY_CELLS`, `ASSET_BREADTH_FAIL`, `PERIOD_BREADTH_FAIL`, `TURNOVER_INCOMPATIBLE`, `NEGATIVE_AGGREGATE_PRIMARY_UNDER_STRESS` |
| CANDIDATE_H006_REVERSAL_6_LONG_SHORT | variant_1e859ceb2d7330750601ba1c | GRAVEYARDED | `ZERO_STRESSED_POSITIVE_PRIMARY_CELLS`, `ASSET_BREADTH_FAIL`, `PERIOD_BREADTH_FAIL`, `TURNOVER_INCOMPATIBLE`, `NEGATIVE_AGGREGATE_PRIMARY_UNDER_STRESS` |
| CANDIDATE_H006_REVERSAL_12_LONG_SHORT | variant_b2704b638049f154fd8799bd | GRAVEYARDED | `ZERO_STRESSED_POSITIVE_PRIMARY_CELLS`, `ASSET_BREADTH_FAIL`, `PERIOD_BREADTH_FAIL`, `TURNOVER_INCOMPATIBLE`, `NEGATIVE_AGGREGATE_PRIMARY_UNDER_STRESS` |
| CANDIDATE_H007_VOL_SCALED_MA_24_96_RV24 | variant_622da030e9dacdf22315383b | BLOCKED | `H007_BENCHMARK_COMPARISON_NOT_COMPARABLE`, `MISSING_H003_ANCHOR_PROVENANCE` |
| CANDIDATE_H007_VOL_SCALED_MA_24_96_RV72 | variant_66992d55a7d8a402179ce209 | BLOCKED | `H007_BENCHMARK_COMPARISON_NOT_COMPARABLE`, `MISSING_H003_ANCHOR_PROVENANCE` |
| CANDIDATE_H007_VOL_SCALED_MA_24_96_RV168 | variant_2ec6b5a20cd8e3181a6a46f0 | BLOCKED | `H007_BENCHMARK_COMPARISON_NOT_COMPARABLE`, `MISSING_H003_ANCHOR_PROVENANCE` |

# Family Decisions

Measured facts and judgment:

| family | tested variants | plausible variants | directional neighborhood coherence | family-wide evidence sufficient |
| --- | ---: | ---: | --- | --- |
| time_series_momentum | 3 | 1 | only 720h passes; shorter 72h and 168h fail stressed breadth and aggregate stress | no |
| moving_average_trend | 3 | 2 | adjacent 48/192 and 168/720 pass; 12/48 fails | no family decision; evidence supports exact follow-up only |
| price_breakout | 2 | 0 | both longer variants fail stressed breadth and aggregate stress; historical 72h was graveyarded separately | no |
| short_horizon_reversal | 4 | 0 | all unfiltered exact variants fail with 0/12 stressed positive primary cells | no |
| volatility_scaled_trend | 3 | 0 adjudicable | benchmark comparison is non-comparable, not economic failure | no |

No family-wide decision is appended.

# Explicit Non-Decisions

- No `SURVIVOR` decision is appended for any new variant.
- No family-wide `FOLLOW_UP`, `SURVIVOR`, `GRAVEYARDED`, or `BLOCKED` decision is appended.
- No H007 economic failure is inferred.
- No master-strategy, regime-router, portfolio, paper-trading, live-trading, or Formal QNTY decision is made.
- No new candidate event or trial event is added.

# Next Registered Work

Because the appended exact decisions leave follow-up candidates in two distinct families, the immediate next work should be a preregistered follow-up design for the exact follow-up variants:

- `CANDIDATE_H002_MOMENTUM_720_LONG_FLAT`
- `CANDIDATE_H003_MA_48_192_LONG_FLAT`
- `CANDIDATE_H003_MA_168_720_LONG_FLAT`

Separately, any H007 adjudication requires a preregistered controlled H003 24/96 benchmark reconstruction before volatility-scaled variants can be compared.
