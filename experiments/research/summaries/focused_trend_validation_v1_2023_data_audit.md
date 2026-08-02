# Scope
Audit ID: AUDIT_2023_HOLDOUT_DATA_V1. This artifact audits whether the preregistered 2023 holdout can be materialized without fill, interpolation, cross-gap returns, provenance loss, or contamination. It does not contain strategy performance.

# Registered Holdout Contract
Period: 2023-01-01T00:00:00Z through 2023-12-31T23:00:00Z. Expected hourly rows per asset: 8760. Assets: BTCUSDT, ETHUSDT, SOLUSDT. Gap policy: REJECT.

# Raw Input Inventory
| asset | path | sha256 | provenance | source | market/source kind |
| --- | --- | --- | --- | --- | --- |
| BTCUSDT | data/raw/BTCUSDT-1h.csv | 6dcc8c6293f24e2e91957b286a96d9b87fd646e4b57c846495bd41d1aa225b65 | SUFFICIENT_FOR_AUTHORITATIVE_REPAIR | https://data-api.binance.vision/api/v3/klines | Binance Spot public market-data REST |
| ETHUSDT | data/raw/ETHUSDT-1h.csv | 3584c161874dc3b8d8f9961901e5abaadebe32a1aaba6d321106b8ccb1f61187 | SUFFICIENT_FOR_AUTHORITATIVE_REPAIR | https://data-api.binance.vision/api/v3/klines | Binance Spot public market-data REST |
| SOLUSDT | data/raw/SOLUSDT-1h.csv | c431aa068acbfedf3cb0c38845dfac275044a9cf83367075b47d47f06974e99d | SUFFICIENT_FOR_AUTHORITATIVE_REPAIR | https://data-api.binance.vision/api/v3/klines | Binance Spot public market-data REST |

# Timestamp Coverage
| asset | first | last | rows_2023 | unique_2023 | missing_count | missing |
| --- | --- | --- | --- | --- | --- | --- |
| BTCUSDT | 2023-01-01T00:00:00Z | 2023-12-31T23:00:00Z | 8759 | 8759 | 1 | 2023-03-24T13:00:00Z |
| ETHUSDT | 2023-01-01T00:00:00Z | 2023-12-31T23:00:00Z | 8759 | 8759 | 1 | 2023-03-24T13:00:00Z |
| SOLUSDT | 2023-01-01T00:00:00Z | 2023-12-31T23:00:00Z | 8759 | 8759 | 1 | 2023-03-24T13:00:00Z |

# Exact Gaps
All three assets miss the same timestamp: 2023-03-24T13:00:00Z. The gap is absent from each registered raw spot file, not duplicated elsewhere in those files, and not at the holdout start or end.

# Warmup Coverage
| asset | candidate | required_warmup_start | actual_available_warmup_start | missing_warmup | evaluation_gaps | affected_feature_timestamps | reject_blocks |
| --- | --- | --- | --- | --- | --- | --- | --- |
| BTCUSDT | CANDIDATE_H002_MOMENTUM_720_LONG_FLAT | 2022-12-02T00:00:00Z | 2021-01-01T00:00:00Z | 0 | 1 | 6059 | True |
| BTCUSDT | CANDIDATE_H003_MA_48_192_LONG_FLAT | 2022-12-24T00:00:00Z | 2021-01-01T00:00:00Z | 0 | 1 | 6587 | True |
| BTCUSDT | CANDIDATE_H003_MA_168_720_LONG_FLAT | 2022-12-02T00:00:00Z | 2021-01-01T00:00:00Z | 0 | 1 | 6059 | True |
| ETHUSDT | CANDIDATE_H002_MOMENTUM_720_LONG_FLAT | 2022-12-02T00:00:00Z | 2021-01-01T00:00:00Z | 0 | 1 | 6059 | True |
| ETHUSDT | CANDIDATE_H003_MA_48_192_LONG_FLAT | 2022-12-24T00:00:00Z | 2021-01-01T00:00:00Z | 0 | 1 | 6587 | True |
| ETHUSDT | CANDIDATE_H003_MA_168_720_LONG_FLAT | 2022-12-02T00:00:00Z | 2021-01-01T00:00:00Z | 0 | 1 | 6059 | True |
| SOLUSDT | CANDIDATE_H002_MOMENTUM_720_LONG_FLAT | 2022-12-02T00:00:00Z | 2021-01-01T00:00:00Z | 0 | 1 | 6059 | True |
| SOLUSDT | CANDIDATE_H003_MA_48_192_LONG_FLAT | 2022-12-24T00:00:00Z | 2021-01-01T00:00:00Z | 0 | 1 | 6587 | True |
| SOLUSDT | CANDIDATE_H003_MA_168_720_LONG_FLAT | 2022-12-02T00:00:00Z | 2021-01-01T00:00:00Z | 0 | 1 | 6059 | True |

# Gap Causal Impact
The missing timestamp is in evaluation, not warmup. H002 720 and H003 168/720 have 8,015 structurally affected rolling-feature timestamps after the gap; H003 48/192 has 8,543. Under the registered REJECT policy, each affected asset-period block is blocked before returns or metrics can be calculated.

# Provenance Assessment
Spot manifests match the raw file hashes and record Binance Spot public market-data REST as the source. The `*-perp-1h.json` manifests record USD-M perpetual archive data and do not correspond to the registered spot raw inputs.

# Holdout Contamination Search
Classification: NO_EVIDENCE_OF_PRIOR_2023_INSPECTION. Exact registered variant/candidate evidence paths with 2023 text: 0. Generic 2023 H002/H003 evidence was found separately and is not classified as exact-variant 2023 holdout inspection.

# Authoritative Repair Options
Route A: reacquire complete affected spot asset-periods from the recorded source. Route B: reacquire only exact missing bars from the same source with immutable provenance. Route C: use already-stored lower-level authoritative local data, not available for this spot input. Route D: declare unusable if authoritative repair cannot be performed.

# Recommended Repair Path
Reacquire complete affected spot 1h asset-periods from the recorded Binance Spot source; do not manually edit CSVs or borrow bars.

# Explicit Non-Actions
No data acquisition, raw CSV modification, manifest modification, interpolation, forward fill, synthetic candle construction, cross-venue substitution, strategy execution, performance calculation, trial event, or decision event was performed.

# Reproduction
Run `python -m qntylab.holdout_data_audit` from the repository root, then run the focused audit tests.
