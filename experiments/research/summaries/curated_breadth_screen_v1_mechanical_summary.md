# Scope

Mechanical summary of CURATED_BREADTH_SCREEN_V1. No survivor, graveyard, follow-up, family, portfolio, or routing decision is made.

# Source Evidence

- Expected execution commit: 31d5c6f2a2b8672a28d53b09a892eb8190f74247
- Source digest: ee3a901f9d70769631dee4be5a57aa077b5ff4a8477535ef4d2e9ad681214aa8
- Source files hashed: 728

# Execution Integrity

- Planned trial IDs: 360
- Completed planned trial IDs: 360
- Missing: 0
- Duplicates: 0
- Unexpected: 0
- Receipt hash mismatches: 0
- Metrics hash mismatches: 0
- Integrity failures: 0

# Matrix Coverage

- Variants: 15
- Cells: 360
- Assets: {"BTCUSDT":120,"ETHUSDT":120,"SOLUSDT":120}
- Periods: {"2022":90,"2024":90,"2025":90,"2026YTD":90}
- Cost modes: {"baseline":180,"stress":180}
- 2023 cells present: false

# Variant Mechanical Results

| candidate_id | family | stress positive primary | supporting assets | supporting periods | stress erased |
| --- | --- | ---: | ---: | ---: | --- |
| CANDIDATE_H002_MOMENTUM_72_LONG_FLAT | time_series_momentum | 2/12 | 3 | 1 | false |
| CANDIDATE_H002_MOMENTUM_168_LONG_FLAT | time_series_momentum | 4/12 | 3 | 3 | false |
| CANDIDATE_H002_MOMENTUM_720_LONG_FLAT | time_series_momentum | 8/12 | 3 | 3 | false |
| CANDIDATE_H003_MA_12_48_LONG_FLAT | moving_average_trend | 6/12 | 3 | 2 | false |
| CANDIDATE_H003_MA_48_192_LONG_FLAT | moving_average_trend | 8/12 | 3 | 4 | false |
| CANDIDATE_H003_MA_168_720_LONG_FLAT | moving_average_trend | 9/12 | 3 | 4 | false |
| CANDIDATE_H005_DONCHIAN_168_LONG_FLAT | price_breakout | 5/12 | 3 | 3 | false |
| CANDIDATE_H005_DONCHIAN_720_LONG_FLAT | price_breakout | 7/12 | 3 | 3 | false |
| CANDIDATE_H006_REVERSAL_1_LONG_SHORT | short_horizon_reversal | 0/12 | 0 | 0 | false |
| CANDIDATE_H006_REVERSAL_3_LONG_SHORT | short_horizon_reversal | 0/12 | 0 | 0 | false |
| CANDIDATE_H006_REVERSAL_6_LONG_SHORT | short_horizon_reversal | 0/12 | 0 | 0 | false |
| CANDIDATE_H006_REVERSAL_12_LONG_SHORT | short_horizon_reversal | 0/12 | 0 | 0 | false |
| CANDIDATE_H007_VOL_SCALED_MA_24_96_RV24 | volatility_scaled_trend | / | 0 | 0 | H007_COMPARISON_LIMITED_BY_HISTORICAL_EVIDENCE |
| CANDIDATE_H007_VOL_SCALED_MA_24_96_RV72 | volatility_scaled_trend | / | 0 | 0 | H007_COMPARISON_LIMITED_BY_HISTORICAL_EVIDENCE |
| CANDIDATE_H007_VOL_SCALED_MA_24_96_RV168 | volatility_scaled_trend | / | 0 | 0 | H007_COMPARISON_LIMITED_BY_HISTORICAL_EVIDENCE |

# Frozen Gate Inputs

- Completion gate pass count: 15/15
- Integrity gate pass count: 15/15
- Stressed primary positivity deterministic threshold: 8 of 12 stressed cells
- Deterministic gate pass count excluding judgment-only gates and H007 limited comparisons: 3/15
- One-cell concentration gate: REQUIRES_RESEARCH_JUDGMENT
- Turnover gate: REQUIRES_RESEARCH_JUDGMENT

# Family-Neighborhood Evidence

| family | registered variants | deterministic gate-passing variants | adjacent pairs | judgment |
| --- | ---: | ---: | --- | --- |
| moving_average_trend | 3 | 2 | [["variant_546746242433ddc20c85b34e","variant_00eb140f03a5f6ab40600160"],["variant_00eb140f03a5f6ab40600160","variant_296a2973dfde57cec911715b"]] | REQUIRES_RESEARCH_JUDGMENT |
| price_breakout | 2 | 0 | [["variant_03c4724abe6c8715f5eaa727","variant_9537b83ca36824b3cd47adc1"]] | REQUIRES_RESEARCH_JUDGMENT |
| short_horizon_reversal | 4 | 0 | [["variant_66cfc915025fc7745f4c51e2","variant_c21463e36d437e98cf38698b"],["variant_c21463e36d437e98cf38698b","variant_1e859ceb2d7330750601ba1c"],["variant_1e859ceb2d7330750601ba1c","variant_b2704b638049f154fd8799bd"]] | REQUIRES_RESEARCH_JUDGMENT |
| time_series_momentum | 3 | 1 | [["variant_d145d2024811f49eea291a29","variant_f7167cdc0acf445a69f10b5c"],["variant_f7167cdc0acf445a69f10b5c","variant_f201cbb38819b1e09e763ac7"]] | REQUIRES_RESEARCH_JUDGMENT |
| volatility_scaled_trend | 3 | 0 | [["variant_622da030e9dacdf22315383b","variant_66992d55a7d8a402179ce209"],["variant_66992d55a7d8a402179ce209","variant_2ec6b5a20cd8e3181a6a46f0"]] | REQUIRES_RESEARCH_JUDGMENT |

# H007 Benchmark Comparison

- Status: H007_COMPARISON_LIMITED_BY_HISTORICAL_EVIDENCE
- Anchor evidence: experiments/research/summaries/h002_h003_followup_v1_summary_compact.csv
- Anchor evidence SHA-256: 9a560880923785d7236e58d17072c6816538f939c240a11e957eb2851f99b10b
- Limiting dimensions: ["candidate_id","input_sha256","parameters","receipt_sha256","relevant_source_sha256","variant_id"]

# Mechanical Observations

- 3 variants passed all deterministic gates that did not require research judgment or H007 anchor reconstruction.
- Several required gates remain inputs for a later explicit decision task, not decisions in this artifact.
- Baseline and stress cost modes are reported separately; positive-only observations are not averaged in place of all cells.

# Explicit Non-Decisions

- No candidate, variant, or family decision was appended.
- No survivor, graveyard, follow-up, family, portfolio, master-strategy, or regime-router decision is made.

# Reproduction

```bash
python -m qntylab.curated_breadth_summary
```
