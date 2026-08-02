# Scope
MECHANICAL FACT: This review covers exactly three registered FOLLOW_UP variants and 18 focused 2023 holdout cells.
# Holdout Contract
MECHANICAL FACT: 3 variants x 3 assets x 2 cost modes; 2023-01-01T00:00:00Z through 2023-12-31T23:00:00Z.
# Trial Integrity
MECHANICAL FACT: {"completed_expected_trials":18,"duplicates":[],"expected_trials":18,"failed":[],"missing":[],"normalization_provenance":"18/18","per_asset":{"BTCUSDT":6,"ETHUSDT":6,"SOLUSDT":6},"per_cost_mode":{"baseline":9,"stress":9},"per_variant":{"variant_00eb140f03a5f6ab40600160":6,"variant_296a2973dfde57cec911715b":6,"variant_f201cbb38819b1e09e763ac7":6},"receipt_validation":"18/18","required_finite_metrics":"18/18","unexpected":[]}
# Primary Metric Contract
MECHANICAL FACT: primary metric is excess_return_vs_buy_and_hold; aggregation is the preregistered variant-level sum by cost mode; positivity is strict > 0.
# Cell-Level Results
MECHANICAL FACT: Cell CSV contains 18 deterministic rows at experiments/research/summaries/focused_trend_validation_v1_2023_holdout_cells.csv.
# Variant-Level Results
MECHANICAL FACT: CANDIDATE_H002_MOMENTUM_720_LONG_FLAT baseline [BTCUSDT=-0.68433946315, ETHUSDT=-0.760808673031, SOLUSDT=-6.51551247283], stress [BTCUSDT=-0.802416089459, ETHUSDT=-0.934010083185, SOLUSDT=-6.80823036172], stress aggregate=-8.54465653437, stress positive assets=0, gate=False.
MECHANICAL FACT: CANDIDATE_H003_MA_48_192_LONG_FLAT baseline [BTCUSDT=-0.909684427565, ETHUSDT=-0.864397321133, SOLUSDT=-4.93145878717], stress [BTCUSDT=-1.00895468109, ETHUSDT=-0.921500892931, SOLUSDT=-5.21777957848], stress aggregate=-7.1482351525, stress positive assets=0, gate=False.
MECHANICAL FACT: CANDIDATE_H003_MA_168_720_LONG_FLAT baseline [BTCUSDT=-1.17138213315, ETHUSDT=-0.91928630974, SOLUSDT=-7.48669028865], stress [BTCUSDT=-1.19205481606, ETHUSDT=-0.932113793314, SOLUSDT=-7.53742402752], stress aggregate=-9.66159263689, stress positive assets=0, gate=False.
# Frozen Gate Evaluation
MECHANICAL FACT: The frozen gate requires completion, zero integrity failures, stress aggregate > 0, and at least two stress-positive assets.
# Baseline Versus Stress
MECHANICAL FACT: Baseline results are reported as context only and do not override stress gate failures.
# Asset Breadth
MECHANICAL FACT: Stress asset breadth uses strict primary metric positivity per asset and requires at least two of three assets.
# Trade and Cost Context
MECHANICAL FACT: Trade counts and total costs are summarized mechanically in the variant CSV.
# Drawdown Context
MECHANICAL FACT: Worst maximum drawdown by cost mode is reported mechanically and is not a continuation gate.
# Mechanical Findings
MECHANICAL FACT: CANDIDATE_H002_MOMENTUM_720_LONG_FLAT failure_reasons=AGGREGATE_STRESS_GATE_FAIL,STRESS_ASSET_BREADTH_GATE_FAIL.
MECHANICAL FACT: CANDIDATE_H003_MA_48_192_LONG_FLAT failure_reasons=AGGREGATE_STRESS_GATE_FAIL,STRESS_ASSET_BREADTH_GATE_FAIL.
MECHANICAL FACT: CANDIDATE_H003_MA_168_720_LONG_FLAT failure_reasons=AGGREGATE_STRESS_GATE_FAIL,STRESS_ASSET_BREADTH_GATE_FAIL.
# Research Judgment Boundary
RESEARCH JUDGMENT: This review does not claim validation, robustness, production readiness, profitability, independence, or diversification.
# Proposed Exact-Variant Decisions
MECHANICAL FACT: {"candidate_id":"CANDIDATE_H002_MOMENTUM_720_LONG_FLAT","current_state":"FOLLOW_UP","evidence_artifact":"experiments/research/summaries/focused_trend_validation_v1_2023_holdout_review.md","mechanical_gate_result":false,"proposed_state":"GRAVEYARDED","reason_code":"FAILED_2023_HOLDOUT_MULTIPLE_GATES","variant_id":"variant_f201cbb38819b1e09e763ac7"}
MECHANICAL FACT: {"candidate_id":"CANDIDATE_H003_MA_48_192_LONG_FLAT","current_state":"FOLLOW_UP","evidence_artifact":"experiments/research/summaries/focused_trend_validation_v1_2023_holdout_review.md","mechanical_gate_result":false,"proposed_state":"GRAVEYARDED","reason_code":"FAILED_2023_HOLDOUT_MULTIPLE_GATES","variant_id":"variant_00eb140f03a5f6ab40600160"}
MECHANICAL FACT: {"candidate_id":"CANDIDATE_H003_MA_168_720_LONG_FLAT","current_state":"FOLLOW_UP","evidence_artifact":"experiments/research/summaries/focused_trend_validation_v1_2023_holdout_review.md","mechanical_gate_result":false,"proposed_state":"GRAVEYARDED","reason_code":"FAILED_2023_HOLDOUT_MULTIPLE_GATES","variant_id":"variant_296a2973dfde57cec911715b"}
# Family-Level Status
MECHANICAL FACT: time_series_momentum has one exact variant tested in the holdout.
MECHANICAL FACT: moving_average_trend has two exact variants tested in the holdout.
RESEARCH JUDGMENT: No family-wide decision is made.
# Explicit Non-Actions
NOT TESTED: distinctness diagnostics
NOT TESTED: forward validation
NOT TESTED: portfolio construction
NOT TESTED: additional backtests
NOT TESTED: family-wide decision
# Reproduction
MECHANICAL FACT: Run `python -m qntylab.focused_trend_holdout_review` from the repository root.
