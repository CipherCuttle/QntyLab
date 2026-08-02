# Scope
Materialized the three deterministic Binance Spot halt-normalized holdout inputs only.

# Frozen Normalization Contract
- normalization_version: BINANCE_SPOT_HALT_NORMALIZATION_V1
- normalized_timestamp: 2023-03-24T13:00:00Z
- gap_policy: NORMALIZE_ONLY_PREREGISTERED_AUTHORITATIVE_HALT; REJECT_ALL_OTHER_GAPS

# Source Hash Verification
- BTCUSDT: data/raw/BTCUSDT-1h.csv 6dcc8c6293f24e2e91957b286a96d9b87fd646e4b57c846495bd41d1aa225b65
- ETHUSDT: data/raw/ETHUSDT-1h.csv 3584c161874dc3b8d8f9961901e5abaadebe32a1aaba6d321106b8ccb1f61187
- SOLUSDT: data/raw/SOLUSDT-1h.csv c431aa068acbfedf3cb0c38845dfac275044a9cf83367075b47d47f06974e99d

# Derived Input Range
- warmup_start: 2022-12-02T00:00:00Z
- evaluation_start: 2023-01-01T00:00:00Z
- evaluation_end: 2023-12-31T23:00:00Z

# Authorized Derived Rows
- BTCUSDT: 2023-03-24T13:00:00Z,28080.00000000,28080.00000000,28080.00000000,28080.00000000,0.00000000
- ETHUSDT: 2023-03-24T13:00:00Z,1789.52000000,1789.52000000,1789.52000000,1789.52000000,0.00000000
- SOLUSDT: 2023-03-24T13:00:00Z,21.73000000,21.73000000,21.73000000,21.73000000,0.00000000

# Raw-to-Derived Comparison
- BTCUSDT: source_rows_compared=48821, source_mismatches=0, authorized_derived_rows=1, unexpected_derived_rows=0
- ETHUSDT: source_rows_compared=48821, source_mismatches=0, authorized_derived_rows=1, unexpected_derived_rows=0
- SOLUSDT: source_rows_compared=48821, source_mismatches=0, authorized_derived_rows=1, unexpected_derived_rows=0

# Derived File Hashes
- BTCUSDT: data/derived/focused_trend_validation_v1/BTCUSDT-spot-1h-2023-halt-normalized.csv 08d5649e86743e9485fb55a3978b96f7b0b5483b33223534d52d4fe0a745d10e
- ETHUSDT: data/derived/focused_trend_validation_v1/ETHUSDT-spot-1h-2023-halt-normalized.csv a3cfb7733aad701b43fd383ac32f52252d229d2275147698449b2007bdff0d40
- SOLUSDT: data/derived/focused_trend_validation_v1/SOLUSDT-spot-1h-2023-halt-normalized.csv 62cee85e0a0f7b903fadc77a8f275e774f0ff3ecfff9fba9ea51a535376f70f1

# Manifest Hashes
- BTCUSDT: data/derived/focused_trend_validation_v1/BTCUSDT-spot-1h-2023-halt-normalized.manifest.json eeed7e295a651ba9620ef1c425e5fc3795beac00a79121bb29aa442c458c0aee
- ETHUSDT: data/derived/focused_trend_validation_v1/ETHUSDT-spot-1h-2023-halt-normalized.manifest.json 1c8d871c79c5f696a02dc9874fd9dd5bbdf2058e2b986cb59beaa83573e3f75d
- SOLUSDT: data/derived/focused_trend_validation_v1/SOLUSDT-spot-1h-2023-halt-normalized.manifest.json 232b42f1d9d968faedc4fe86018cbc5767261af901391bb7e189fd1aa1a6e5af

# Coverage Validation
- BTCUSDT: rows=8760, unique=8760, missing=0, first=2023-01-01T00:00:00Z, last=2023-12-31T23:00:00Z
- ETHUSDT: rows=8760, unique=8760, missing=0, first=2023-01-01T00:00:00Z, last=2023-12-31T23:00:00Z
- SOLUSDT: rows=8760, unique=8760, missing=0, first=2023-01-01T00:00:00Z, last=2023-12-31T23:00:00Z

# Determinism Check
- byte_identical: true

# Causality Sanity Check
- BTCUSDT: 12_close=28080.00000000, 13_close=28080.00000000, 14_close=27989.06000000, 12_to_13_return=0
- ETHUSDT: 12_close=1789.52000000, 13_close=1789.52000000, 14_close=1763.12000000, 12_to_13_return=0
- SOLUSDT: 12_close=21.73000000, 13_close=21.73000000, 14_close=21.45000000, 12_to_13_return=0

# Explicit Non-Actions
- no strategy execution
- no backtest invocation
- no 2023 performance calculation
- no trial event
- no decision event
- no candidate event
- no raw CSV mutation
- no perpetual manifest mutation

# Reproduction
- python -m qntylab.materialize_halt_normalized_holdout
