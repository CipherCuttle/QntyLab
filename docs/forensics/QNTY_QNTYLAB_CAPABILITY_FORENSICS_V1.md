# FORENSIC_QNTY_QNTYLAB_CAPABILITY_REPORT_V1

# Executive Verdict
`THESIS_SURVIVES_AS_INFRASTRUCTURE_FEASIBILITY_ONLY` remains the correct bounded verdict for funding carry. The browser report underestimated current local QNTY capacity and partially underestimated QntyLab's current local research-governance state. QNTY already has substantial paper-accounting, SQLite ledger, funding-source snapshot, immutable funding bundle, and verifier primitives. QntyLab already has a canonical research ledger, official strategy runner, deterministic trial identity, gap/provenance gates, and focused holdout state.

The decisive current gap is not receipts, hashes, or basic funding-to-bars alignment. The gap is the missing economic state machine: two independent spot/perpetual legs, exact signed contract-quantity settlement, committed-capital accounting, historical rule versioning, margin path, liquidation, ADL, and opportunity-cost benchmark accrual.

Final status for this report: local forensic artifact only. No funding-carry implementation, experiment execution, backtest, live API call, Binance download, strategy event, ledger event, or QNTY modification was performed.

# Scope and Non-Claims
This report audits local repositories and the prior browser report at `/home/swirky/Documents/deep-research-report.md` (SHA-256 `9b7ad47f1ba6ecc03af0782d8069a3e31b0eb77e4d90bab7ceadb39fee818c57`). It does not claim scientific validation, trading authority, live readiness, exact historical exchange solvency, or funding-carry profitability.

# Repository Identity
QntyLab: `/home/swirky/DevHub/repos/QntyLab`, branch `master`, HEAD `53a06926b9985e11fc132a088eea4ca86510f4e4`, remote `https://github.com/CipherCuttle/QntyLab.git`.

QNTY: `/home/swirky/DevHub/repos/Qnty`, branch `chore/external-trust-root-dispatcher-repair-v046`, HEAD `8ebe61bdecd2d72239cf8d0618df87d6e1171c5a`, remote `git@github.com:CipherCuttle/Qnty.git`.

# Worktree and History State
QntyLab status: ahead 17; pre-existing modified data/manifests BTC/ETH/SOL perp and many untracked manifests/run artifacts/logs.

QNTY status: no upstream shown for current branch; pre-existing untracked plans/ and qnty_ruleset_rollout.sh; main/origin/main at 5cf88b9.

Remote visibility/divergence: QntyLab local `master` is ahead of `origin/master` by 17 commits at the inspected state. QNTY current branch is not tracking a remote branch in `git status --short --branch`; `main` and `origin/main` both point at `5cf88b9`, while the active branch is local HEAD `8ebe61bdecd2d72239cf8d0618df87d6e1171c5a`. Multiple QNTY worktrees/branches exist; the canonical active tree for this audit is `/home/swirky/DevHub/repos/Qnty` because its remote identity is `CipherCuttle/Qnty`.

# Audit Method
- Loaded QntyLab research ledger context before strategy/research-state analysis.
- Verified repository identity, branch, HEAD, remotes, status, and recent history for both repos.
- Captured pre-task state under TMPDIR/qnty-qntylab-capability-forensics-v1 with dirty/untracked paths and tracked dirty file SHA-256 where applicable.
- Read the browser report from /home/swirky/Documents/deep-research-report.md as claim input, not authority.
- Built rg inventories, symbol inventories, schema/config/test inventories, and keyword searches under TMPDIR.
- Inspected current source code, tests, docs, manifests, receipts, and selected history/search output.
- Ran focused offline tests only; no network fetches, no backtests, no experiments, no ledger events.
- Established absence claims through path inventory, rg keyword search, symbol search, test search, schema search, and selected docs/status search.

# Evidence Classification
Implementation classes used exactly as requested: PRODUCTION_IMPLEMENTED, IMPLEMENTED_AND_TESTED, IMPLEMENTED_UNTESTED, PARTIAL_IMPLEMENTATION, DIAGNOSTIC_ONLY, VALIDATION_ONLY, SCHEMA_ONLY, SYNTHETIC_ONLY, EXPERIMENT_SPEC_ONLY, DOCUMENTATION_ONLY, LEGACY_OR_RETIRED, ABSENT, UNKNOWN.

Claim-audit verdicts used exactly as requested: CONFIRMED_CURRENT, CONFIRMED_BUT_UNDERSTATED, PARTIALLY_CORRECT, OUTDATED, FALSE_FOR_CURRENT_LOCAL_STATE, UNVERIFIABLE, NOT_A_REPOSITORY_CLAIM.

# QNTY Mission
Documented mission: cleanroom crypto quant research harness for deterministic paper replay, falsification workflows, kill criteria, validation receipts, and shadow observation. README says it is not a trading bot, not investment advice, and not live-capital approved.

Actual implemented mission: QNTY is a larger research, validation, paper accounting, receipt, verifier, and continuity repository. The most funding-relevant current capacity is in `quantbot.paper`: deterministic paper PnL engine, SQLite ledger writer, read-only verifier, funding-source snapshots/bundles, and fail-closed clean-carry gates. QNTY also has offline-edge validation scaffolding that deliberately avoids PnL/trades in those diagnostic paths.

Legacy/active/future boundary: QNTY contains many branches/docs/status artifacts. The active audited tree implements paper/shadow and validation primitives but does not implement live trading, full margin reconstruction, two-leg spot/perp carry, liquidation, ADL, or historical exchange rule versioning.

# QntyLab Mission
Documented mission: standalone public-data strategy scratchpad, separate from QNTY, no execution code, no credentials, exploratory only.

Actual implemented mission: QntyLab owns exploratory strategy definitions, official `qntylab.strategy_test` runs, deterministic receipts, source/provenance gates, candidate/trial/decision research ledger, preregistered holdout lifecycle, and data acquisition/materialization for Binance public data. It also contains perpetual/funding diagnostics and normalized perpetual return evaluation.

Legacy/active/future boundary: QntyLab is suitable for candidate lifecycle and exploratory diagnostics. It is not the right owner for a paper-accounting ledger, margin engine, live/paper operational lane, or QNTY control state.

# QNTY Architecture
```text
LOCAL/FROZEN INPUTS AND FORWARD OBSERVATIONS
  -> data loaders and funding CSV loaders
  -> paper engine: next-bar fills, qty, fees, funding, positions, equity
  -> SQLite writer: typed event rows, batch/event chain, reconciliation
  -> read-only verifier: arithmetic, digests, funding clean-carry gates
  -> reports/receipts/status docs
  -> research/control/continuity governance diagnostics
```

# QntyLab Architecture
```text
PUBLIC BINANCE ARCHIVES / NORMALIZED INPUTS
  -> data validation and manifests
  -> strategy definitions and official strategy_test runner
  -> single-series backtest metrics and receipts
  -> append-only research ledger candidates/trials/decisions
  -> summaries/holdout reviews/decision artifacts
```

# Combined Architecture Boundary
```text
QNTY ends at paper/replay/accounting/verifier/operational diagnostics.
QntyLab begins at exploratory candidate definition, official trial execution, and research lifecycle.
Overlap exists in source hashing, manifests, deterministic receipts, funding timestamp/alignment diagnostics, and fail-closed gates.
Neither repository currently implements the full two-leg funding-carry economic state machine.
```

# Capability Matrix
| Domain | Capability | QNTY | QntyLab | Overlap | Gap | Owner | Notes |
|---|---|---|---|---|---|---|---|
| A Data ingestion | Spot klines | PARTIAL_IMPLEMENTATION (MEDIUM) | IMPLEMENTED_AND_TESTED (HIGH) | LOW | No tick/order-book execution convention | QntyLab | QNTY has loaders for OHLCV in multi_asset_loader but not audited as spot archive ingestion owner. |
| A Data ingestion | USD-M futures/perp klines | PARTIAL_IMPLEMENTATION (MEDIUM) | IMPLEMENTED_AND_TESTED (HIGH) | MEDIUM | QntyLab downloader exists; QNTY consumes local bars for paper engine | SHARED CONTRACT | Do not rebuild QntyLab archive downloader unless QNTY needs same contract. |
| A Data ingestion | Premium-index data | UNKNOWN (LOW) | IMPLEMENTED_UNTESTED (MEDIUM) | LOW | No historical methodology versioning | QntyLab | QntyLab stores premium close only. |
| A Data ingestion | Funding history | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | QntyLab schema lossy; QNTY richer source snapshot layer | SHARED CONTRACT | Existing primitives should be reused rather than new blank receipt layer. |
| A Data ingestion | Trades/aggregate trades | VALIDATION_ONLY (MEDIUM) | EXPERIMENT_SPEC_ONLY (MEDIUM) | LOW | No general trade ingestion pipeline for execution simulation | QNTY | QntyLab only uses trades to justify specific halt normalization. |
| A Data ingestion | Order book/depth | ABSENT (HIGH) | ABSENT (HIGH) | NONE | No order book data ingestion | NEITHER | Do not claim executable bid/ask/depth. |
| B Provenance | Source URL/endpoint identity | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | Rule endpoints not versioned historically | SHARED CONTRACT | Existing source/provenance primitives overlap. |
| B Provenance | Raw byte hashes | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | Event-level raw hashes absent in QntyLab funding rows | SHARED CONTRACT | Do not rebuild sha256/canonical JSON helpers. |
| B Provenance | Checksum validation | PARTIAL_IMPLEMENTATION (MEDIUM) | PARTIAL_IMPLEMENTATION (MEDIUM) | MEDIUM | Not universal across all archive kinds | QntyLab | QntyLab checksum only in daily perp archive path. |
| B Provenance | Input/derived manifests | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | Carry-specific combined deterministic root incomplete | SHARED CONTRACT | Report proposes deterministic root; analogues already exist. |
| B Provenance | Deterministic materialization | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | Not a full carry dataset materializer | SHARED CONTRACT | Reusable primitive exists. |
| C Integrity | Duplicate/missing/malformed row detection | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | Coverage differs per file type | SHARED CONTRACT | Use existing validators. |
| C Integrity | Timestamp ordering/gap/frequency validation | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | Per-file semantics differ | SHARED CONTRACT | Funding-to-bars alignment is solved as a diagnostic primitive, not full settlement. |
| C Integrity | OHLC/non-finite validation | VALIDATION_ONLY (MEDIUM) | IMPLEMENTED_AND_TESTED (HIGH) | LOW | QNTY paper verifier does not rederive OHLCV marks | QntyLab | QNTY verifier explicitly disclaims price mark rederivation. |
| C Integrity | Retired symbol preservation | DIAGNOSTIC_ONLY (MEDIUM) | IMPLEMENTED_AND_TESTED (HIGH) | MEDIUM | Contract replacements/relist identity still partial | SHARED CONTRACT | Existing identity diagnostics should be reused. |
| D Temporal | Event-time vs observation-time distinction | PARTIAL_IMPLEMENTATION (MEDIUM) | PARTIAL_IMPLEMENTATION (MEDIUM) | MEDIUM | Historical estimated funding observation tape absent | SHARED CONTRACT | Settlement timing exists; pre-settlement information timing does not. |
| D Temporal | Funding settlement alignment | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | Alignment solved at bar/window level, not exchange wallet posting exactness | SHARED CONTRACT | Do not rebuild from scratch. |
| D Temporal | Next-bar causality | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | No bid/ask simultaneous execution | SHARED CONTRACT | Existing conventions differ; contract needed before carry. |
| D Temporal | No-gap return bridging | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | QNTY paper marks not independently rederived | SHARED CONTRACT | Do not weaken fail-closed gap semantics. |
| E Funding | Funding schema | IMPLEMENTED_AND_TESTED (HIGH) | PARTIAL_IMPLEMENTATION (HIGH) | HIGH | QntyLab schema loses markPrice/rateType; QNTY snapshot richer but paper engine uses rate/notional | SHARED CONTRACT | Browser report understated QNTY. |
| E Funding | Funding rate/time/interval | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | Historical interval rule versioning absent | SHARED CONTRACT | Existing timestamp normalization should be reused. |
| E Funding | Funding mark price | SCHEMA_ONLY (MEDIUM) | ABSENT (HIGH) | LOW | No quantity*markPrice exact settlement accounting | QNTY | QNTY has source field but not exact venue settlement. |
| E Funding | Finalized vs estimated funding | PARTIAL_IMPLEMENTATION (MEDIUM) | PARTIAL_IMPLEMENTATION (MEDIUM) | HIGH | No prospective estimate archive or historical estimate tape | SHARED CONTRACT | Browser report remains correct for pre-settlement timing. |
| E Funding | Funding cash-flow calculation | PARTIAL_IMPLEMENTATION (HIGH) | SYNTHETIC_ONLY (HIGH) | MEDIUM | Exact venue quantity*mark settlement/rounding not solved | QNTY | QNTY should own extension from paper ledger. |
| E Funding | Raw funding event receipts | IMPLEMENTED_AND_TESTED (HIGH) | PARTIAL_IMPLEMENTATION (MEDIUM) | MEDIUM | QntyLab lacks per-event raw schema receipts | QNTY | Do not create new layer without reusing QNTY snapshot schema. |
| E Funding | Funding settlement ledger | PARTIAL_IMPLEMENTATION (HIGH) | ABSENT (HIGH) | LOW | No exact spot/perp settlement ledger | QNTY | Extend QNTY paper ledger if funding carry proceeds. |
| F Strategy | Strategy registry/variant identity | DIAGNOSTIC_ONLY (MEDIUM) | IMPLEMENTED_AND_TESTED (HIGH) | LOW | Different governance vocabularies | QntyLab | QntyLab owns exploratory candidate lifecycle. |
| F Strategy | Position generation/fractional/long-short | PARTIAL_IMPLEMENTATION (MEDIUM) | IMPLEMENTED_AND_TESTED (HIGH) | MEDIUM | QNTY paper is long-only; QntyLab normalized positions not fills | QntyLab | Carry strategy proposal should start in QntyLab only after concept approval. |
| G Backtest/accounting | Single-series return evaluation | IMPLEMENTED_AND_TESTED (MEDIUM) | IMPLEMENTED_AND_TESTED (HIGH) | MEDIUM | Not a funding-carry economic ledger | QntyLab | Existing exploratory engine sufficient for price-only diagnostics. |
| G Backtest/accounting | Fees/slippage/turnover | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | No historical maker/taker/VIP/versioned fee engine | QNTY | Do not confuse fixed bps with venue fee reconstruction. |
| G Backtest/accounting | Spot inventory | ABSENT (HIGH) | ABSENT (HIGH) | NONE | No spot inventory for carry | QNTY | Genuinely missing. |
| G Backtest/accounting | Perpetual quantity | IMPLEMENTED_AND_TESTED (HIGH) | ABSENT (HIGH) | LOW | QNTY qty is single product, not Binance perp contract settlement exactness | QNTY | Partially reusable. |
| G Backtest/accounting | Two independent legs/fills | ABSENT (HIGH) | ABSENT (HIGH) | NONE | Two-leg spot/perp ledger absent | QNTY | Genuine missing economic state machine. |
| G Backtest/accounting | Capital ledger/committed capital | PARTIAL_IMPLEMENTATION (MEDIUM) | ABSENT (HIGH) | LOW | No reserve cash/transfers/two-account capital denominator | QNTY | Extend paper ledger. |
| G Backtest/accounting | Benchmark accrual | DIAGNOSTIC_ONLY (MEDIUM) | PARTIAL_IMPLEMENTATION (MEDIUM) | LOW | No SOFR/cash benchmark ledger | UNRESOLVED | Needs external benchmark choice and local adapter. |
| H Margin | Isolated/cross margin, wallet, initial/maintenance margin | ABSENT (HIGH) | ABSENT (HIGH) | NONE | Full margin path absent | QNTY | Genuine missing. |
| H Margin | Liquidation/bankruptcy/insurance/ADL | ABSENT (HIGH) | ABSENT (HIGH) | NONE | No liquidation or ADL model | QNTY | Genuine missing; likely fail-state interface first. |
| I Governance | Candidate/trial/decision streams | DIAGNOSTIC_ONLY (MEDIUM) | IMPLEMENTED_AND_TESTED (HIGH) | LOW | Do not port QntyLab lifecycle into QNTY blindly | QntyLab | QntyLab research lifecycle is solved for its scope. |
| I Governance | Append-only behavior | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | Different append-only domains | SHARED CONTRACT | Reuse concept, not internals. |
| I Governance | Holdout/preregistration | VALIDATION_ONLY (MEDIUM) | IMPLEMENTED_AND_TESTED (HIGH) | LOW | Carry-specific preregistration absent | QntyLab | QntyLab owns strategy lifecycle. |
| J Evaluation | Primary metrics/cost stress/breadth/holdout | VALIDATION_ONLY (MEDIUM) | IMPLEMENTED_AND_TESTED (HIGH) | LOW | No carry-specific economic/stat gates | QntyLab | No scientific validation claim. |
| J Evaluation | Walk-forward/PBO/statistical corrections | PARTIAL_IMPLEMENTATION (MEDIUM) | ABSENT (MEDIUM) | LOW | Carry statistical plan absent | UNRESOLVED | Future reviewers should audit QNTY stats separately. |
| K Reporting | Run/metrics receipts | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | Carry settlement receipt absent but primitives exist | SHARED CONTRACT | Browser report understated QNTY receipts. |
| K Reporting | Machine-readable deterministic outputs | IMPLEMENTED_AND_TESTED (HIGH) | IMPLEMENTED_AND_TESTED (HIGH) | HIGH | Combined carry root absent | SHARED CONTRACT | Extend existing deterministic artifact style. |
| L Operations | Live market access/order submission | ABSENT (HIGH) | ABSENT (HIGH) | NONE | No live trading capability | NEITHER | Do not infer live trading from exchange data. |
| L Operations | Paper trading/mock execution | IMPLEMENTED_AND_TESTED (HIGH) | ABSENT (HIGH) | LOW | QNTY paper is single product, long-only | QNTY | Funding carry accounting extension belongs near QNTY paper. |
| L Operations | Scheduling/monitoring/alerts | DOCUMENTATION_ONLY (MEDIUM) | ABSENT (HIGH) | LOW | Operational scripts not funding-carry evidence | QNTY | Do not treat as live order authority. |

# Data and Provenance Capacity
QntyLab implements Binance spot/perp archive ingestion and manifests. QNTY implements richer funding-source snapshot and bundle primitives. Both have deterministic hashes and receipts. QNTY should not rebuild QntyLab's strategy/research ledger; QntyLab should not rebuild QNTY's paper ledger/verifier.

Positive evidence:
- `qntylab_spot_fetch_validate`: QntyLab `qntylab/data.py` `fetch, validate` lines 11-82; test `tests/test_strategy_test.py; tests/test_materialize_halt_normalized_holdout.py` / `test_gap_free_fixture_succeeds_and_missing_hour_fails; test_source_raw_hashes_are_enforced`; executed now: True (QntyLab focused subset: 131 passed in 50.74s); limitation: REST path only; no order book, spot trades execution, or historical fee/rule state.
- `qntylab_perp_fetch_funding`: QntyLab `qntylab/data.py` `fetch_premium_perp, fetch_funding, fetch_perp` lines 118-146,202-217; test `tests/test_lab.py; tests/test_sprint_v2_execute.py` / `perp/funding behavior tests in focused subset`; executed now: True (QntyLab focused subset: 131 passed in 50.74s); limitation: Funding schema discards markPrice/rateType/venue/contract identity fields; downloader uses network if executed, not run now.
- `qntylab_funding_to_bars`: QntyLab `qntylab/perp.py` `funding_to_bars, causal` lines 4-13; test `tests/test_lab.py; tests/test_sprint_v2_execute.py` / `funding assignment/sign/compiled funding tests`; executed now: True (QntyLab focused subset: 131 passed in 50.74s); limitation: Bar diagnostic alignment only; no raw settlement ledger, information publication tape, or quantity settlement.
- `qntylab_perp_eval`: QntyLab `qntylab/perp.py` `evaluate_perp` lines 52-67; test `tests/test_lab.py; tests/test_sprint_v2_execute.py` / `test_forced_gap_funding_sign_costs_and_objective_classification; test_compiled_funding_and_optimized_execution_are_byte_equal_to_oracle`; executed now: True (QntyLab focused subset: 131 passed in 50.74s); limitation: Normalized exposure approximation; no signed contract quantity, wallet, collateral, two-leg spot/perp fills, mark-price notional, rounding, margin, liquidation, or ADL.
- `qntylab_strategy_runner`: QntyLab `qntylab/strategy_test.py` `load_config, run_strategy, preflight integration` lines 29-79,216-262,462-579; test `tests/test_strategy_test.py` / `test_receipt_binds_input_config_code_and_results; test_funding_boundary_mode_is_explicit; test_gap_free_fixture_succeeds_and_missing_hour_fails`; executed now: True (QntyLab focused subset: 131 passed in 50.74s); limitation: Price-only strategies in official runner; no funding strategy is registered in STRATEGIES; no execution simulation beyond single close series.
- `qntylab_research_ledger`: QntyLab `qntylab/research_ledger.py` `compute_variant_id, compute_trial_id, replay, doctor, preflight, append_canonical_event` lines 384-588,656-737; test `tests/test_research_ledger.py` / `research ledger unit tests; doctor command`; executed now: True (QntyLab focused subset: 131 passed; doctor returned ledger ok); limitation: Governance for QntyLab strategy research only; not a QNTY control-state system and not trading authorization.
- `qntylab_halt_normalization`: QntyLab `qntylab/materialize_halt_normalized_holdout.py` `materialization functions` lines file inventory, tests bound behavior; test `tests/test_materialize_halt_normalized_holdout.py; tests/test_binance_spot_halt_normalization_v1.py` / `test_committed_raw_derived_manifest_and_receipt_hashes_match_frozen_values; test_source_raw_hashes_are_enforced`; executed now: True (QntyLab focused subset: 131 passed); limitation: Narrow normalization for specified spot halt rows, not a general exchange-rule registry.
- `qnty_funding_loader`: QNTY `quantbot/data/funding_loader.py` `load_funding_csv, load_all_funding, build_funding_lookup` lines 20-143; test `tests/test_funding_coverage.py; paper tests` / `funding coverage and paper writer/verifier tests`; executed now: True (QNTY focused suite: 337 passed in 21.32s); limitation: Loads local CSVs; missing files are skipped by loader, with fail-closed behavior enforced downstream in writer/verifier gates.
- `qnty_paper_engine`: QNTY `quantbot/paper/engine.py` `run_engine, funding_in_interval, canonical_net_pnl` lines 90-134,168-453; test `tests/test_paper_sqlite_writer.py; tests/test_paper_matched_null.py; tests/lab/test_replay_cross_check.py` / `test_engine_applies_costs_and_funding_through_same_path; writer close-position tests; cross-check tests`; executed now: True (QNTY focused suite: 337 passed in 21.32s); limitation: Single product paper engine; long-only; fixed-notional; no spot-plus-perp matched legs, margin wallet, liquidation, ADL, or venue order book.
- `qnty_sqlite_schema`: QNTY `quantbot/paper/db.py` `_SCHEMA_SQL, _build_trigger_sql` lines 150-383,391-458; test `tests/test_paper_sqlite.py; tests/test_paper_additive_lane_schema.py; tests/test_paper_ledger_batch_lane_stamping.py` / `schema/additive lane/batch stamping tests`; executed now: True (QNTY focused suite included sqlite writer/verifier tests; broader schema tests inspected but not all executed now); limitation: Mutable ledger_state/open_positions by design; this is paper accounting, not exchange account state.
- `qnty_sqlite_writer`: QNTY `quantbot/paper/sqlite_writer.py` `run_sqlite_accounting, _insert_typed_rows_for_bar, _reconcile_batch_inside_tx` lines 1-21,341-555,730-900; test `tests/test_paper_sqlite_writer.py; tests/test_paper_sqlite_writer_funding_coverage.py` / `writer funding fail-closed and trade/position tests`; executed now: True (QNTY focused suite: 337 passed in 21.32s); limitation: Writes paper ledger, not live orders. Funding source CSV/snapshot gates are separate.
- `qnty_sqlite_verifier`: QNTY `quantbot/paper/sqlite_verify.py` `verify_database, _validate_arithmetic, _validate_trades, _validate_equity_cumulative, clean-carry gate` lines 1-58,725-940; test `tests/test_paper_sqlite_verify.py; tests/test_paper_sqlite_verifier_clean_net_of_carry_gate.py` / `test_fabricated_funding_is_corrupt; clean-carry gate tests`; executed now: True (QNTY focused suite: 337 passed in 21.32s); limitation: Verifier disclaimer states it does not independently rederive OHLCV marks/unrealized PnL/exposure from source price data.
- `qnty_funding_source_snapshot`: QNTY `quantbot/paper/funding_source_snapshot.py` `build_funding_source_snapshot_payload_v1, build_canonical_row_subset_digest, clean_mode_decision_from_snapshot_v1` lines 27-82,266-278,515-620; test `tests/test_funding_source_snapshot_schema.py; tests/test_funding_source_digest_window_semantics.py` / `snapshot schema/digest/window tests`; executed now: True (QNTY focused suite: 337 passed in 21.32s); limitation: Snapshot proves source row identity/coverage, not full exchange account state or publication timing before settlement.
- `qnty_funding_time`: QNTY `quantbot/paper/funding_time.py` `canonicalize_funding_timestamp, classify_funding_timestamp_for_window` lines 16-184; test `tests/test_funding_timestamp_normalization_spec.py` / `funding timestamp normalization spec tests`; executed now: True (QNTY focused suite: 337 passed in 21.32s); limitation: Normalizes observed source rows; does not reconstruct historical estimate observation tape.
- `qnty_funding_bundle`: QNTY `quantbot/paper/funding_source_bundle.py` `build_funding_source_bundle_v1, resolve_funding_source_bundle` lines 1-26,159-260; test `tests/test_funding_source_immutable_bundle_semantics.py` / `immutable bundle semantics tests`; executed now: True (QNTY focused suite: 337 passed in 21.32s); limitation: Funding-source identity primitive only; not an economic two-leg or margin model.
- `qnty_cross_check`: QNTY `quantbot/lab/cross_check.py` `cross_check, compare, classify_disagreement` lines 1-23,94-125,151-265; test `tests/lab/test_replay_cross_check.py` / `row-by-row cross-check tests`; executed now: True (QNTY focused suite: 337 passed in 21.32s); limitation: Diagnostic lane only; clean comparison does not validate alpha or exchange completeness.
- `qnty_offline_edge_validation`: QNTY `quantbot/experiment/offline_edge_validation_cli.py` `offline edge validation CLI diagnostics` lines 130-369 (key non-PnL boundaries found by search); test `tests/experiment/test_offline_edge_validation_cli.py; tests/experiment/test_offline_edge_data_quality.py` / `offline-edge validation CLI and data-quality tests`; executed now: True (QNTY focused suite: 337 passed with TMPDIR=/tmp; prior run failed because agent TMPDIR was outside literal /tmp); limitation: Validation scaffold, not strategy execution or funding-carry accounting.

Absence methodology for missing market-data/execution items: `rg` path/symbol/test/schema searches over both repositories for order book/depth, two-leg, spot/perp matched legs, margin, liquidation, ADL, SOFR, exchangeInfo/rule versioning, leverage bracket, wallet, collateral, and benchmark terms; inventory of Python packages, tests, docs, schemas, receipts; selected source inspection of QntyLab `qntylab/*` and QNTY `quantbot/paper`, `quantbot/experiment`, `quantbot/lab`.

# Temporal and Funding Capacity
Funding-to-bars alignment is already solved as a bounded primitive: QntyLab assigns settled events to containing hourly bars and delays signal use; QNTY classifies funding timestamps/windows and accrues funding over held intervals. Exact funding settlement accounting is not solved because neither repository reconstructs Binance wallet postings with signed contract quantity, mark-price notional, venue rounding, margin state, and historical rule versions.

# Strategy and Backtest Capacity
QntyLab owns strategy registry, deterministic variant/trial identity, official runner, and exploratory lifecycle. QNTY has strategy and experiment code, but its funding-carry-relevant implemented surface is paper accounting and validation scaffolding, not QntyLab-style candidate streams.

# Accounting Capacity
QNTY has a meaningful one-product paper ledger: fills, qty, fees, funding rows, trades, positions, equity, SQLite append-only tables, and read-only verifier. This is not a two-leg same-venue carry ledger. QntyLab has normalized single-series evaluation and is not an accounting owner.

# Margin, Liquidation and ADL Capacity
No margin-path reconstruction, maintenance tiers, liquidation, bankruptcy, insurance fund, or ADL implementation was found after path inventory, symbol search, keyword search, test search, schema search, and docs/status search. Mentions are docs, omissions, diagnostics, or tests asserting omissions, not engines.

# Research Governance Capacity
QntyLab research lifecycle governance is implemented and tested for its scope. Current canonical state: 19 variants, 378 completed trials, 0 FOLLOW_UP, 15 GRAVEYARDED, 3 BLOCKED, 1 SURVIVOR. The three focused 2023 trend holdout variants named in the prompt are GRAVEYARDED. Ledger doctor result: `ledger ok`.

QNTY governance is distinct: control/continuity, receipts, paper verifier authority, and offline-edge gates. Do not force QNTY into QntyLab's candidate/trial vocabulary.

# Evaluation and Statistics Capacity
QntyLab has primary metrics, cost stress, breadth/holdout lifecycle for existing exploratory screens. QNTY has validation/statistical modules and PBO/walkforward surfaces, but funding-carry economic/statistical gates are not defined. Neither repo has a SOFR/cash benchmark accrual ledger.

# Reporting and Receipt Capacity
The browser report's proposed receipt layer is partially redundant. QNTY already has funding-source snapshots, immutable bundles, SQLite verifier reports/receipts, and clean-carry refusal reason codes. QntyLab already has run receipts, source/normalization provenance, relevant source digest, and research ledger streams. New work should extend these surfaces, not rebuild them.

# Operational Capacity
QNTY has paper/shadow ops scripts and systemd docs, but README and code boundaries say no live trading approval. QntyLab has no execution code or credentials. Live market access/order submission is absent in both for this audit's purposes.

# Funding-Carry Ten-Question Readiness
| Question | Current Answer | QNTY Capacity | QntyLab Capacity | Missing | Duplicate Risk | Recommended Owner |
|---|---|---|---|---|---|---|
| Funding information timing | PARTIAL | QNTY settlement/source windows and funding snapshots; no historical estimate tape. | QntyLab settled funding plus causal delay; no estimate observation tape. | Prospective estimate archive or fail-closed rule for pre-settlement decisions. | HIGH | SHARED CONTRACT |
| Product identity | PARTIAL | QNTY instance diagnostics and lane identity, but no full Binance historical symbol master. | QntyLab filename/manifest symbol identity and retired-symbol archive discovery. | Versioned venue/product/rule identity schema. | MEDIUM | SHARED CONTRACT |
| Two-leg executable-price convention | NO | QNTY has one-product next-bar fill model. | QntyLab has single-series next-bar return accounting. | Two independent spot/perp fill convention with legging policy. | HIGH | QNTY |
| Exact funding cash-flow reconstruction | PARTIAL | QNTY has notional*rate funding rows and source snapshots; no venue exact mark/rounding wallet settlement. | QntyLab has normalized -position*rate approximation. | Signed contract quantity, markPrice notional, rounding, wallet posting. | HIGH | QNTY |
| Full margin-path reconstruction | NO | No margin engine. | No margin engine. | Wallet, margin balance, brackets, collateral, maintenance, liquidation state. | LOW | QNTY |
| Liquidation and ADL representation | NO | No liquidation/ADL model. | No liquidation/ADL model. | Fail-state interface and model/rule registry. | LOW | QNTY |
| Total committed-capital accounting | PARTIAL | QNTY has initial_equity/notional/equity snapshots. | QntyLab initial_capital only. | Reserve cash, transfers, two accounts, opportunity cash denominator. | MEDIUM | QNTY |
| Opportunity-cost benchmark | NO | Docs/tests show null benchmark diagnostics but no SOFR ledger. | Buy-and-hold metric only. | Benchmark rate adapter and accrual ledger. | MEDIUM | UNRESOLVED |
| Historical exchange-rule versioning | NO | No historical rule registry found. | No historical rule registry found. | Versioned rule snapshots and source policy. | LOW | SHARED CONTRACT |
| Frozen non-selected dataset support | PARTIAL | QNTY immutable funding bundles and offline-edge diagnostics. | QntyLab frozen holdout/aux datasets and manifests. | Carry-specific frozen non-selected universe/data contract. | HIGH | SHARED CONTRACT |

# Browser-Report Claim Audit
| Claim | Section | Verdict | Corrected Statement | Importance |
|---|---|---|---|---|
| QntyLab can build infrastructure but not scientific exact retrospective carry validation | Executive verdict | CONFIRMED_CURRENT | Current local state supports infrastructure feasibility only; QNTY adds paper/funding-source primitives but not full carry validation. | HIGH |
| Current funding schema is timestamp, funding_interval_hours, funding_rate | Repository capability map | CONFIRMED_CURRENT | Correct for QntyLab only; false if generalized to QNTY. | HIGH |
| Funding ingestion exists but lossy | Capability map | CONFIRMED_BUT_UNDERSTATED | Understated cross-repo capacity: QNTY has richer source receipt capacity. | HIGH |
| Funding-to-hour alignment exists | Capability map | CONFIRMED_BUT_UNDERSTATED | Alignment primitive exists in both; QNTY is stronger for settlement windows. | HIGH |
| Causal delay of settled funding as signal exists | Capability map | CONFIRMED_CURRENT | Correct for QntyLab; still no pre-settlement estimate history. | HIGH |
| Simplified perpetual PnL only normalized single-series | Capability map | PARTIALLY_CORRECT | Correct for QntyLab, outdated/false if used as a two-repo statement. | HIGH |
| Two independent product legs absent | Capability map | CONFIRMED_CURRENT | Still absent. | HIGH |
| Basis ledger partial | Capability map | PARTIALLY_CORRECT | Partial only as diagnostic basis inputs, not ledger. | MEDIUM |
| Full capital ledger absent | Capability map | PARTIALLY_CORRECT | Capital ledger partially exists in QNTY paper accounting but not carry-complete. | HIGH |
| Margin state absent | Capability map | CONFIRMED_CURRENT | Confirmed absent. | HIGH |
| Maintenance tiers absent | Capability map | CONFIRMED_CURRENT | Confirmed absent. | HIGH |
| Liquidation absent | Capability map | CONFIRMED_CURRENT | Confirmed absent. | HIGH |
| ADL absent | Capability map | CONFIRMED_CURRENT | Confirmed absent. | HIGH |
| Fee accounting partial fixed bps | Capability map | CONFIRMED_BUT_UNDERSTATED | QNTY has stronger fill-level fixed-fee accounting; historical venue fee versioning still absent. | HIGH |
| Slippage absent/fixed bps only | Capability map | PARTIALLY_CORRECT | Fixed-bps slippage exists; order-book/depth slippage absent. | HIGH |
| Product identity partial | Capability map | CONFIRMED_BUT_UNDERSTATED | Understated QNTY diagnostics but historical product rule identity remains partial. | MEDIUM |
| Historical rule versioning absent | Capability map | CONFIRMED_CURRENT | Confirmed absent. | HIGH |
| Benchmark ledger absent | Capability map | CONFIRMED_CURRENT | Confirmed for SOFR/opportunity-cost ledger. | HIGH |
| Provenance and receipts strong | Capability map | CONFIRMED_BUT_UNDERSTATED | Understated because QNTY current local capacity is materially stronger. | HIGH |
| Frozen-universe support exists for prior work | Capability map | CONFIRMED_CURRENT | Frozen support exists in bounded contexts, not carry dataset freeze. | MEDIUM |
| Retired-symbol preservation exists | Capability map | CONFIRMED_CURRENT | Confirmed as diagnostic/partial, not complete contract lineage. | MEDIUM |
| Fail-closed handling partial | Capability map | CONFIRMED_BUT_UNDERSTATED | Understated QNTY fail-closed behavior; economic fail states still incomplete. | HIGH |
| Research-state verification absent on remote | Repository identity | OUTDATED | Remote connector absence is not current local absence. | HIGH |
| Proposed new receipt layer required | Proposal | PARTIALLY_CORRECT | Need extension, not greenfield receipt layer. | HIGH |
| Proposed event schemas required | Proposal | PARTIALLY_CORRECT | Only carry-specific settlement/margin events are new. | HIGH |
| Proposed deterministic root required | Proposal | PARTIALLY_CORRECT | Need a carry-specific root built from existing primitives. | HIGH |
| Proposed failure states required | Proposal | PARTIALLY_CORRECT | New economic failure states needed, but terminal-state primitives exist. | HIGH |
| Proposed ledger boundary required | Proposal | PARTIALLY_CORRECT | Carry ledger boundary should extend QNTY paper/accounting, not rebuild QntyLab research ledger. | HIGH |

Claim verdict counts: `{"CONFIRMED_BUT_UNDERSTATED": 6, "CONFIRMED_CURRENT": 12, "OUTDATED": 1, "PARTIALLY_CORRECT": 9}`.

# Existing Capacity the Browser Report Understated
1. QNTY funding-source snapshot schema, deterministic source-file and row-subset hashes, snapshot scopes, and reason codes.
2. QNTY immutable funding-source bundles for frozen funding rows.
3. QNTY SQLite paper ledger with fills, trades, funding rows, position snapshots, equity snapshots, append-only triggers, and read-only verifier.
4. QNTY funding clean-carry gates and refusal states.
5. QntyLab current local research ledger state and official strategy runner, because the browser report only saw remote absence/divergence.

# Genuine Missing Capacity
- two-leg spot/perpetual ledger -> owner: QNTY; reason: QNTY owns paper fills/ledger/accounting; QntyLab owns research registry only.
- exact signed-quantity funding settlement receipt -> owner: QNTY; reason: QNTY already has funding rows, qty, source snapshots and verifier.
- capital ledger with reserve cash/transfers/two accounts -> owner: QNTY; reason: Closest to QNTY paper ledger/equity state.
- margin verdict interface and rule-version registry -> owner: shared schema/contract then QNTY implementation; reason: Stable cross-project contract needed; implementation belongs near accounting.
- liquidation/ADL unresolved state -> owner: QNTY; reason: Accounting failure state, not strategy-research lifecycle.
- SOFR/opportunity-cost benchmark adapter -> owner: UNRESOLVED; reason: Requires browser research for benchmark source, licensing, and investment interpretation.
- carry-specific frozen non-selected dataset contract -> owner: shared schema/contract; reason: Both repos have freeze primitives but neither has the carry contract.
- prospective funding-estimate archive -> owner: QNTY; reason: Operational/public-data collection adjacent to QNTY data/paper lane; not QntyLab experiment runner.

# Duplicate-Build Risks
| Proposed Component | Existing QNTY Analogue | Existing QntyLab Analogue | Reuse Quality | Missing Delta | Do Not Rebuild | Decision |
|---|---|---|---|---|---|---|
| immutable event schemas | SQLite ledger_events; funding snapshot schema | research ledger JSONL streams | HIGH | carry-specific event names | YES | EXTEND |
| funding-event schema | funding_source_snapshot_v1; funding table | timestamp/funding_interval/rate CSV | HIGH | markPrice/rateType/versioned product binding | YES | EXTEND |
| funding-to-bars alignment | funding_in_interval/open-closed funding_time | funding_to_bars/causal | HIGH | publication/estimate tape | YES | EXTEND |
| temporal joinability | funding timestamp/window diagnostics; cross-check | lifecycle/strategy gap rejection | HIGH | carry-specific join report | YES | EXTEND |
| raw-source hashing | source_file_sha256; bundles | sha256 manifests and provenance | HIGH | unified carry root | YES | EXTEND |
| dataset manifests | artifact/funding snapshots | data/manifests and derived manifests | HIGH | carry dataset freeze | YES | EXTEND |
| terminal failure states | verifier statuses and funding refusal reasons | BLOCKED/GRAVEYARDED and fail-closed errors | HIGH | economic margin/rule failure states | YES | EXTEND |
| trial identity | QNTY research/control differs | compute_trial_id | MEDIUM | cross-repo mapping not needed | YES | DO NOT REBUILD |
| research ledger | QNTY control state not same model | research_ledger.py | HIGH | none for QntyLab strategy research | YES | DO NOT REBUILD |
| strategy runner | QNTY experiment CLIs/paper engine | qntylab.strategy_test | MEDIUM | carry concept approval and strategy spec | YES | EXTEND QntyLab only |
| funding settlement accounting | notional*rate funding ledger partial | normalized approximation | MEDIUM | exact mark/quantity/rounding/wallet | NO | EXTEND QNTY |
| two-leg ledger | absent | absent | NONE | full component | NO | NEW COMPONENT REQUIRED |
| capital ledger | equity snapshots partial | initial_capital only | MEDIUM | two-account committed capital | NO | EXTEND QNTY |
| benchmark ledger | diagnostic/null absent | buy-and-hold metric | LOW | SOFR/accrual ledger | NO | NEW COMPONENT REQUIRED |
| margin engine | absent | absent | NONE | full component | NO | NEW COMPONENT REQUIRED |
| rule registry | absent | absent | NONE | historical rule versions | NO | NEW COMPONENT REQUIRED |
| liquidation model | absent | absent | NONE | full component | NO | NEW COMPONENT REQUIRED |
| ADL state | absent | absent | NONE | state/fail representation | NO | NEW COMPONENT REQUIRED |

Confirmed duplicate-build risks: 11 high/medium reuse components should not be rebuilt from scratch: event schemas, funding-event schema, funding-to-bars alignment, temporal joinability, raw-source hashing, manifests, deterministic receipts, terminal states, trial identity, research ledger, and funding source snapshots/bundles.

# Recommended Component Ownership
QNTY should own accounting extensions: signed-quantity settlement receipt, two-leg ledger, capital ledger, margin verdict interface implementation, liquidation/ADL unresolved state, and prospective funding-estimate capture. QntyLab should own any exploratory strategy candidate lifecycle only after explicit concept approval. Shared contracts are appropriate only for stable cross-project schemas: raw funding source schema, product identity schema, carry dataset freeze root, and historical rule-version record shape.

# Minimal Extension Boundaries
Do not add funding-carry implementation to QntyLab's existing `strategy_test` path before concept approval. Do not create a new receipt layer that bypasses QNTY funding-source snapshots or QntyLab research receipts. Do not treat QNTY paper ledger as exact exchange accounting without adding two-leg, margin, rule-version, and settlement details.

# Test Evidence
QntyLab focused passing command: `python -m pytest -q tests/test_lab.py tests/test_sprint_v2_execute.py tests/test_strategy_test.py tests/test_research_ledger.py tests/test_lifecycle.py tests/test_materialize_halt_normalized_holdout.py tests/test_binance_spot_halt_normalization_v1.py tests/test_free_census.py` -> 131 passed in 50.74s.

QntyLab broader focused command including holdout audit: `python -m pytest -q tests/test_lab.py tests/test_sprint_v2_execute.py tests/test_strategy_test.py tests/test_research_ledger.py tests/test_lifecycle.py tests/test_holdout_data_audit.py tests/test_materialize_halt_normalized_holdout.py tests/test_binance_spot_halt_normalization_v1.py tests/test_free_census.py` -> 140 passed, 1 failed in 57.12s. Failure: `tests/test_holdout_data_audit.py::test_contamination_search_records_evidence_paths` expected `NO_EVIDENCE_OF_PRIOR_2023_INSPECTION`, actual `CONFIRMED_CONTAMINATION`; this reflects current local research exposure state, not a report-generation mutation.

QNTY first focused command using system Python failed collection because pandas was unavailable. QNTY rerun with venv and literal `/tmp`: `TMPDIR=/tmp .venv/bin/python -m pytest -q tests/test_funding_source_snapshot_schema.py tests/test_funding_timestamp_normalization_spec.py tests/test_funding_source_immutable_bundle_semantics.py tests/test_paper_sqlite_writer_funding_coverage.py tests/test_paper_sqlite_verifier_clean_net_of_carry_gate.py tests/test_paper_sqlite_verify.py tests/test_paper_sqlite_writer.py tests/lab/test_replay_cross_check.py tests/experiment/test_offline_edge_data_quality.py tests/experiment/test_offline_edge_validation_cli.py` -> 337 passed in 21.32s.

# Evidence Validation
VALIDATION_OK: evidence_entries=17 capabilities=47 claims=28; checked repo paths, commits, symbols, line ranges, tests, test-output summaries, evidence repo separation, and IMPLEMENTED_AND_TESTED confidence presence. Validator path: $TMPDIR/qnty-qntylab-capability-forensics-v1/validate_report.py (not committed).

# Repository Divergence and Remote Visibility
The browser report's remote claim that QntyLab paths were absent is outdated for current local state. The local QntyLab tree has `qntylab/strategy_test.py`, `qntylab/research_ledger.py`, and canonical research streams. QNTY has many local and remote branches/worktrees; active audited tree is local branch `chore/external-trust-root-dispatcher-repair-v046` at `8ebe61bdecd2d72239cf8d0618df87d6e1171c5a`.

# Unresolved Questions
- Which historical Binance rule sources are legally and technically usable for margin/fee/leverage/funding interval versioning?
- Which benchmark series and compounding convention should represent USD opportunity cost for a Sweden-based public-data study?
- Whether a prospective funding-estimate archive can be collected without violating API/rate/terms constraints.
- Whether historical product-listing/delisting/relisting identity can be sourced from official exchange records sufficiently for carry eligibility.

# Questions for Browser Reviewers
- Do not recommend rebuilding funding-source snapshots, bundle hashes, research ledger identity, or deterministic receipt primitives without explaining why the existing QNTY/QntyLab versions are insufficient.
- Challenge whether QNTY's one-product paper ledger can be extended to two legs without distorting existing paper-lane authority boundaries.
- Find official sources for historical Binance USD-M margin brackets, fee schedules, funding interval changes, liquidation/ADL rules, and product identity changes.
- Determine whether SOFR/T-bill benchmark use is appropriate for the intended capital denominator.

# Final Verdict
`QNTY_QNTYLAB_CAPABILITY_FORENSICS_V1_COMPLETE` for local forensic inventory and report artifacts. The future funding-carry work, if approved, should treat QNTY as accounting owner, QntyLab as research lifecycle owner, and shared schemas only where cross-project stability is real.

# Reproduction
1. `python -m qntylab.research_ledger context`
2. Verify identities with the git commands in the prompt.
3. Read `/home/swirky/Documents/deep-research-report.md`.
4. Run the static searches stored under `$TMPDIR/qnty-qntylab-capability-forensics-v1/`.
5. Run the test commands listed in `# Test Evidence`.
6. Validate evidence with `$TMPDIR/qnty-qntylab-capability-forensics-v1/validate_report.py`.
