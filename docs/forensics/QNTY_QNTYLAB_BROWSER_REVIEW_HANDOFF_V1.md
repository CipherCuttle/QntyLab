# QNTY / QntyLab Browser Review Handoff V1

## Verified Repository Identities
- QNTY: `/home/swirky/DevHub/repos/Qnty`, branch `chore/external-trust-root-dispatcher-repair-v046`, HEAD `8ebe61bdecd2d72239cf8d0618df87d6e1171c5a`, remote `git@github.com:CipherCuttle/Qnty.git`.
- QntyLab: `/home/swirky/DevHub/repos/QntyLab`, branch `master`, HEAD `53a06926b9985e11fc132a088eea4ca86510f4e4`, remote `https://github.com/CipherCuttle/QntyLab.git`.

## Verified Missions
- QNTY: research, falsification, paper/replay accounting, receipts, verifier, shadow observation. Not live-capital approved.
- QntyLab: standalone exploratory strategy scratchpad with public data, official strategy runner, candidate/trial/decision research ledger. No execution code or credentials.

## What QNTY Already Does
- Paper engine: `quantbot/paper/engine.py::run_engine` lines 168-453 creates next-bar fills, qty, fees, funding rows, positions, equity.
- SQLite ledger: `quantbot/paper/db.py` lines 150-383 defines typed ledger tables; lines 391-458 append-only triggers and snapshot reference columns.
- SQLite writer/verifier: `quantbot/paper/sqlite_writer.py` and `quantbot/paper/sqlite_verify.py` write and verify event/typed-row consistency, fills, trades, funding, equity, and funding clean-carry gates.
- Funding source identity: `quantbot/paper/funding_source_snapshot.py`, `funding_time.py`, and `funding_source_bundle.py` implement snapshot schema, timestamp classification, hashes, and immutable bundles.
- Test evidence: `TMPDIR=/tmp .venv/bin/python -m pytest -q ...` focused QNTY suite passed 337 tests in 21.32s.

## What QntyLab Already Does
- Binance spot/perp/funding data ingestion and manifests: `qntylab/data.py`.
- Funding-to-bars and normalized perpetual PnL diagnostics: `qntylab/perp.py`.
- Official strategy runner with source/provenance/ledger preflight: `qntylab/strategy_test.py`.
- Research ledger: `qntylab/research_ledger.py` with candidates, decisions, trials, deterministic variant/trial ids, doctor/preflight.
- Current state: 19 variants, 378 completed trials, 0 FOLLOW_UP, 15 GRAVEYARDED, 3 BLOCKED, 1 SURVIVOR; ledger doctor `ledger ok`.
- Test evidence: focused QntyLab subset passed 131 tests in 50.74s.

## What Both Do
- Deterministic hashes, receipts/manifests, fail-closed data/source checks, funding timestamp/alignment diagnostics, and exploratory/non-authoritative wording.

## What Neither Does
- Two-leg spot/perpetual ledger, exact signed contract-quantity Binance funding settlement, full committed capital ledger, margin path, maintenance tiers, liquidation, ADL, historical exchange-rule registry, SOFR/cash benchmark ledger, live trading.

## Browser Report Corrections
- It was correct that QntyLab alone lacks full carry accounting.
- It understated QNTY: current local QNTY has funding source snapshots, immutable bundles, SQLite paper ledger, verifier, clean-carry gates, and paper accounting primitives.
- Proposed receipt/event/root/failure-state layers are only partially new. Existing QNTY/QntyLab primitives should be extended.
- Remote absence of QntyLab research files is outdated for the local tree.

## Funding-Carry Ten Questions
- Funding information timing: PARTIAL; owner SHARED CONTRACT; missing Prospective estimate archive or fail-closed rule for pre-settlement decisions.
- Product identity: PARTIAL; owner SHARED CONTRACT; missing Versioned venue/product/rule identity schema.
- Two-leg executable-price convention: NO; owner QNTY; missing Two independent spot/perp fill convention with legging policy.
- Exact funding cash-flow reconstruction: PARTIAL; owner QNTY; missing Signed contract quantity, markPrice notional, rounding, wallet posting.
- Full margin-path reconstruction: NO; owner QNTY; missing Wallet, margin balance, brackets, collateral, maintenance, liquidation state.
- Liquidation and ADL representation: NO; owner QNTY; missing Fail-state interface and model/rule registry.
- Total committed-capital accounting: PARTIAL; owner QNTY; missing Reserve cash, transfers, two accounts, opportunity cash denominator.
- Opportunity-cost benchmark: NO; owner UNRESOLVED; missing Benchmark rate adapter and accrual ledger.
- Historical exchange-rule versioning: NO; owner SHARED CONTRACT; missing Versioned rule snapshots and source policy.
- Frozen non-selected dataset support: PARTIAL; owner SHARED CONTRACT; missing Carry-specific frozen non-selected universe/data contract.

## Genuine Missing Components
- two-leg spot/perpetual ledger: QNTY
- exact signed-quantity funding settlement receipt: QNTY
- capital ledger with reserve cash/transfers/two accounts: QNTY
- margin verdict interface and rule-version registry: shared schema/contract then QNTY implementation
- liquidation/ADL unresolved state: QNTY
- SOFR/opportunity-cost benchmark adapter: UNRESOLVED
- carry-specific frozen non-selected dataset contract: shared schema/contract
- prospective funding-estimate archive: QNTY

## Recommended Ownership
- QNTY: accounting extensions, two-leg ledger, settlement receipt, capital ledger, margin/liquidation/ADL failure state, funding estimate archive.
- QntyLab: exploratory candidate proposal/trial/decision lifecycle after explicit concept approval.
- Shared contract: raw funding schema, product identity schema, historical rule record shape, carry dataset freeze root.
- Unresolved: SOFR/opportunity-cost benchmark adapter pending external source/legal/convention research.

## High-Confidence Facts
- Funding-to-bars/window alignment exists in both repositories.
- Exact funding settlement accounting is not solved.
- Two-leg spot/perp ledger is not solved.
- Total committed-capital accounting is partial only in QNTY.
- Margin-path reconstruction is absent.
- QntyLab research lifecycle governance is solved for its own scope.

## Medium-Confidence Inferences
- QNTY is the better owner for funding-carry accounting because it already owns paper accounting and verifier authority.
- QntyLab should not own margin/capital/accounting state because its design is a research scratchpad.

## Unresolved Questions Requiring Web Research
- Official historical Binance rule/version sources.
- Historical margin tiers, fee schedules, liquidation/ADL rules, funding interval changes.
- Benchmark source and convention.
- Prospective funding estimate collection constraints.

## Questions for Hostile Reviewers
- Which proposed components are genuinely new after accounting for QNTY `quantbot.paper`?
- Is QNTY's paper ledger extensible to two legs without breaking authority boundaries?
- What official historical exchange records are sufficient for rule versioning?
- What should be treated as fail-closed rather than modeled approximately?

## Strict Non-Claims
- No scientific validation.
- No funding-carry strategy approval.
- No live/paper trading authorization beyond existing QNTY paper diagnostics.
- No exact historical margin, liquidation, ADL, or account-state reconstruction.

## Evidence Validation
- VALIDATION_OK: 17 evidence entries, 47 capabilities, 28 browser-report claims checked by temporary validator under `$TMPDIR`; validator not committed.
