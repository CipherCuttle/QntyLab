# Scope
Independent verification of committed halt-normalized 2023 holdout inputs, manifests, materialization receipts, causal semantics, and official-run provenance readiness. No holdout or production strategy trial executed; no 2023 positions, returns, or metrics inspected.

# Independent Hash Verification
- raw: {"BTCUSDT": "6dcc8c6293f24e2e91957b286a96d9b87fd646e4b57c846495bd41d1aa225b65", "ETHUSDT": "3584c161874dc3b8d8f9961901e5abaadebe32a1aaba6d321106b8ccb1f61187", "SOLUSDT": "c431aa068acbfedf3cb0c38845dfac275044a9cf83367075b47d47f06974e99d"}
- derived: {"BTCUSDT": "08d5649e86743e9485fb55a3978b96f7b0b5483b33223534d52d4fe0a745d10e", "ETHUSDT": "a3cfb7733aad701b43fd383ac32f52252d229d2275147698449b2007bdff0d40", "SOLUSDT": "62cee85e0a0f7b903fadc77a8f275e774f0ff3ecfff9fba9ea51a535376f70f1"}
- manifest: {"BTCUSDT": "eeed7e295a651ba9620ef1c425e5fc3795beac00a79121bb29aa442c458c0aee", "ETHUSDT": "1c8d871c79c5f696a02dc9874fd9dd5bbdf2058e2b986cb59beaa83573e3f75d", "SOLUSDT": "232b42f1d9d968faedc4fe86018cbc5767261af901391bb7e189fd1aa1a6e5af"}
- materialization_receipts: {"json": "cf75e96438c0da3ac27177b5c0bd49b394bef3564ea404369bc433d46c26823d", "markdown": "b4355b15307669b031f9e45f1914ab647b90a9e3793fae66be5c7b4527966077"}
- status: PASS

# Raw-Derived Comparison
- BTCUSDT: source_rows_compared=48821, source_mismatches=0, authorized_derived_rows=1, unexpected_derived_rows=0, total_derived_rows=48822
- ETHUSDT: source_rows_compared=48821, source_mismatches=0, authorized_derived_rows=1, unexpected_derived_rows=0, total_derived_rows=48822
- SOLUSDT: source_rows_compared=48821, source_mismatches=0, authorized_derived_rows=1, unexpected_derived_rows=0, total_derived_rows=48822

# Coverage Verification
- BTCUSDT: 2023_rows=8760, unique=8760, missing=0, duplicates=0, out_of_order=0, non_hour=0, non_finite=0, ohlc_failures=0, warmup_rows=720
- ETHUSDT: 2023_rows=8760, unique=8760, missing=0, duplicates=0, out_of_order=0, non_hour=0, non_finite=0, ohlc_failures=0, warmup_rows=720
- SOLUSDT: 2023_rows=8760, unique=8760, missing=0, duplicates=0, out_of_order=0, non_hour=0, non_finite=0, ohlc_failures=0, warmup_rows=720

# Deterministic Rematerialization
- csv_bytes_identical: true
- manifest_bytes_identical: true
- receipt_facts_identical: true
- derived_sha256_identical: true
- manifest_sha256_identical: true

# Causality Verification
- BTCUSDT: 12_close=28080.00000000, 13_close=28080.00000000, 12_to_13_return=0, 14_close=27989.06000000, 13_to_14_nonzero=true
- ETHUSDT: 12_close=1789.52000000, 13_close=1789.52000000, 12_to_13_return=0, 14_close=1763.12000000, 13_to_14_nonzero=true
- SOLUSDT: 12_close=21.73000000, 13_close=21.73000000, 12_to_13_return=0, 14_close=21.45000000, 13_to_14_nonzero=true

# Runner Provenance Readiness
- status: PASS
- supported_by: qntylab.strategy_test normalization_provenance config validation and run_receipt recording
- required_fields: ["authoritative_raw_path", "authoritative_raw_sha256", "derived_input_path", "derived_input_sha256", "derived_manifest_path", "derived_manifest_sha256", "normalization_id", "normalization_version", "normalized_timestamp", "reason_code", "source_resolution_artifact_path", "source_resolution_artifact_sha256"]
- fails_closed_on_mismatch: True
- raw_input_legacy_runs_unchanged: True
- derived_input_sha256_remains_trial_identity_input_sha256: True

# Planned Holdout Identities
- planned_trials: 18
- unique_trial_ids: 18
- variants: 3
- assets: 3
- cost_modes: 2
- periods: ["2023_UNTOUCHED_HOLDOUT"]
- research_intents: ["FOLLOW_UP"]
- collisions_with_completed_trials: 0
- trial_ids: recorded in JSON artifact only

# Status Semantics
- normalization_spec_status: REGISTERED_NOT_MATERIALIZED
- finding: Documentation/state-model inconsistency: materialization is committed but the frozen normalization spec remains REGISTERED_NOT_MATERIALIZED because no transition was defined; no transition was invented during verification.

# Explicit Non-Actions
- no holdout or production strategy execution
- no backtest invocation
- no 2023 strategy positions
- no 2023 strategy returns or metrics
- no trial-completion event
- no candidate event
- no decision event
- no raw CSV mutation
- no additional normalized timestamps
- no production run artifact creation

# Reproduction
- python -m pytest -q tests/test_materialize_halt_normalized_holdout.py tests/test_binance_spot_halt_normalization_v1.py tests/test_focused_trend_validation_v1.py tests/test_strategy_test.py tests/test_research_ledger.py
- python -m qntylab.research_ledger rebuild
- python -m qntylab.research_ledger doctor
- python -m qntylab.research_ledger context
- git diff --check
