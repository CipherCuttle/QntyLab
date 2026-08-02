# Executive Verdict

evidence_verdict: `PUBLIC_SIDE_ONLY`

reconciliation_verdict: `ACCOUNT_RECEIPT_MISSING`

The local machine and the two repositories do not contain a complete authentic evidence tuple for exactly one finalized Binance USD-M perpetual funding settlement. The audit found normalized public funding-rate data, but found zero authentic Binance account-side `FUNDING_FEE` income records, zero matching authentic position records, and no non-synthetic funding-time mark-price evidence suitable for exact settlement reconciliation.

# Scope and Non-Claims

Task: `AUDIT_AUTHENTIC_BINANCE_FUNDING_SETTLEMENT_EVIDENCE_V0`.

Lane: `ADMIN_LANE`.

This audit did not modify QNTY production code, did not call Binance APIs, did not log in to Binance, did not inspect credential stores, did not implement a verifier, and did not start a funding-carry research branch.

# Repository Identity

QNTY:

| Field | Value |
|---|---|
| root | `/home/swirky/DevHub/repos/Qnty` |
| branch | `chore/external-trust-root-dispatcher-repair-v046` |
| HEAD | `8ebe61bdecd2d72239cf8d0618df87d6e1171c5a` |
| remote | `git@github.com:CipherCuttle/Qnty.git` |
| starting dirty state | untracked `plans/`, `qnty_ruleset_rollout.sh`; no tracked modifications observed |

QntyLab:

| Field | Value |
|---|---|
| root | `/home/swirky/DevHub/repos/QntyLab` |
| branch | `master` |
| starting HEAD | `282f09d2e798cf57c258b1d5dd53adc8964027b1` |
| remote | `https://github.com/CipherCuttle/QntyLab.git` |
| starting dirty state | unrelated manifest/result/run/log WIP already present |

Protection records were written under `$TMPDIR/binance-funding-settlement-evidence-audit-v0/`.

# Privacy Boundary

Search was bounded to:

- `/home/swirky/DevHub/repos/Qnty`
- `/home/swirky/DevHub/repos/QntyLab`
- `/home/swirky/Downloads`
- `/home/swirky/Documents`
- `/home/swirky/Desktop`

Prohibited browser profiles, keyrings, password stores, SSH material, shell histories, API keys, API secrets, cookies, tokens, and credential stores were not searched.

Private candidate paths in this report are redacted by scope label plus a short path hash. No raw private account export, complete transaction identifier, account identifier, email address, balance set, or unrelated trade row is included.

# Existing QNTY Capability

| Question | Answer | Evidence | Symbol/Test | Classification | Limitation | Confidence |
|---|---|---|---|---|---|---|
| Stores signed position quantity? | No authentic signed venue position; paper long-only `qty` exists. | `quantbot/paper/db.py` tables `open_positions.qty`, `position_snapshot_symbols.qty`; `quantbot/paper/engine.py` long-only engine. | `tests/test_paper_sqlite.py`, `tests/test_paper_sqlite_writer.py` | `PARTIALLY_SOLVED` | Paper quantity is positive long-only and not an authentic Binance account position. | High |
| Stores funding-time mark price? | Not as load-bearing settlement evidence. | `quantbot/paper/engine.py` uses OHLCV close or entry price as mark approximation; repository funding CSVs may have `markPrice` column but production-like rows sampled as `0.0`. | `tests/fixtures/edge_validation_golden/*funding*.csv` | `NOT_SOLVED` | Nonzero mark-price values found only in synthetic fixtures. | High |
| Calculates quantity x mark price x funding rate? | Paper engine calculates `notional_at * rate`; SQLite reconcile re-derives `notional_usd * funding_rate`. | `quantbot/paper/engine.py` `amount = notional_at * rate`; `quantbot/paper/sqlite_writer.py` funding arithmetic check; `quantbot/paper/reconcile.py` funding re-derivation. | `tests/test_paper_sqlite_writer.py`, `tests/test_paper_sqlite_verify.py` | `PARTIALLY_SOLVED` | Uses derived paper notional, not authentic settlement quantity x Binance funding mark price. | High |
| Distinguishes payer and receiver signs? | Partially in research diagnostics; paper ledger is long-only cost-positive. | `quantbot/experiment/offline_edge_real_validation.py` `long_cashflow_factor = -rate`, `short_cashflow_factor = rate`; `quantbot/paper/engine.py` long pays when positive rate. | `tests/experiment/test_offline_edge_real_validation.py` | `PARTIALLY_SOLVED` | No account receipt sign reconciliation and no authentic short/long account state. | High |
| Posts funding into wallet/account row? | No. | `quantbot/paper/db.py` has `funding`, `equity_snapshots`, and `ledger_state`, but no wallet/account-income table. | `tests/test_paper_sqlite.py` | `NOT_SOLVED` | Paper equity accumulator only, not Binance wallet/account income. | High |
| Reconciles expected funding against observed account record? | No. | `quantbot/paper/reconcile.py` only checks internal paper ledgers. | `tests/test_paper_sqlite_verify.py` | `NOT_SOLVED` | No observed account-income input or account-side verifier. | High |
| Preserves transaction identity/idempotency? | Paper idempotency exists; Binance transaction identity does not. | `quantbot/paper/db.py` `ledger_events` unique event keys; `quantbot/paper/engine.py` deterministic `funding_id`. | `tests/test_paper_sqlite_writer.py` | `PARTIALLY_SOLVED` | `funding_id` is synthetic (`symbol|bar_ts`), not Binance `tranId`. | High |
| Models venue precision/rounding? | Only paper numeric conventions. | `quantbot/paper/engine.py` rounds money to 8 dp and qty to 10 dp; `quantbot/paper/reconcile.py` tolerances. | `tests/test_paper_sqlite_writer.py`, `tests/test_paper_sqlite_verify.py` | `PARTIALLY_SOLVED` | No pinned Binance product precision, amount scale, contract multiplier, or settlement rounding policy. | High |
| Fixture proves bounded claim? | No. | No `FUNDING_FEE`, `incomeType`, `tranId`, authentic account export, or authentic position fixture found. | bounded `rg` over QNTY | `NOT_SOLVED` | Existing fixtures are synthetic or public/derived, not account-side receipts. | High |
| Would a new verifier duplicate existing functionality? | No exact duplicate found. | Existing verifier validates paper SQLite integrity and clean-carry source coverage. | `tests/test_paper_sqlite_verifier_clean_net_of_carry_gate.py` | `NOT_SOLVED` | A future settlement verifier would be distinct, but the evidence gate is not met. | High |

# Search Method

Filename/metadata discovery used the requested bounded patterns and formats under the allowed roots. For candidates, the audit recorded path, size, mtime, SHA-256, format, and only headers/schema/top-level keys. Candidate file inventory was built in temp as sanitized metadata.

One bounded content check for account-income markers across candidate files found no hits for `FUNDING_FEE`, `incomeType`, `tranId`, `income history`, `Income Type`, or `Transaction ID`.

# Candidate Evidence Inventory

candidate_file_count: `886`

Formats:

| Format | Count |
|---|---:|
| json | 595 |
| csv | 200 |
| md | 83 |
| xlsx | 4 |
| jsonl | 3 |
| pdf | 1 |

Authenticity classifications:

| Classification | Count |
|---|---:|
| `DERIVED_DATA` | 674 |
| `PUBLIC_BINANCE_MARKET_DATA` | 193 |
| `SYNTHETIC_TEST_DATA` | 10 |
| `IRRELEVANT` | 9 |
| `AUTHENTIC_ACCOUNT_EXPORT` | 0 |
| `AUTHENTIC_API_RESPONSE_PRESERVED_LOCALLY` | 0 |

Representative public candidates:

| Source | SHA-256 | Header | Classification |
|---|---|---|---|
| `QNTY/data/BTCUSDT_8h_funding.csv` | `2edd068c6a882d60b4f67204c4d7133931b8b098d639fccd9cb1b6d50abb3f90` | `symbol,fundingTime,fundingRate,markPrice` | `PUBLIC_BINANCE_MARKET_DATA`; `NORMALIZED_DERIVATIVE` |
| `QntyLab/data/raw/BTCUSDT-funding.csv` | `db8f5d1739a7b1271f915602854392875ef30384e943094b2f937ddffa672428` | `timestamp,funding_interval_hours,funding_rate` | `PUBLIC_BINANCE_MARKET_DATA`; `NORMALIZED_DERIVATIVE` |

Personal-area candidates were generic bank/accounting/receipt files and were classified `IRRELEVANT` from filename, metadata, format, and schema/first-heading inspection only. Their exact basenames are redacted in JSON.

# Authenticity Classification

No authentic Binance account receipt was found. No locally preserved authoritative Binance account API response was found. No account-side screenshot/PDF with Binance funding income fields was found. Public-side local market data exists, but it is normalized repository data rather than raw authoritative settlement evidence.

# Account Receipt Evidence

account_receipt_status: `MISSING`

authentic_account_side_records_found: `0`

No candidate contained the required account-side field set:

- `incomeType = FUNDING_FEE`
- observed signed income amount
- asset
- time
- symbol
- transaction identity where available
- account-side provenance

# Position Evidence

position_evidence_status: `MISSING`

matching_position_records_found: `0`

QNTY stores paper `open_positions.qty` and `position_snapshot_symbols.qty`, but those rows represent the paper engine state, not an authentic Binance account position. No authoritative position export, preserved account state response, or authentic fill set sufficient for deterministic reconstruction was found.

# Public Funding Event Evidence

public_event_status: `PUBLIC_SIDE_ONLY_NORMALIZED_DERIVATIVE`

matching_public_funding_events_found: `0`

Local repositories contain normalized public funding-rate rows for many USD-M symbols. They do not provide a selected event matched to an account receipt and authentic position record. QntyLab `data/raw/*-funding.csv` omits `markPrice`; QNTY `data/*_8h_funding.csv` has a `markPrice` column, but sampled production-like rows use `0.0`. Nonzero `markPrice` values found during the audit were in test fixtures only.

# Product and Unit Evidence

product_identity_status: `INCOMPLETE`

precision_status: `MISSING`

| Field | Status | Note |
|---|---|---|
| venue | `INFERRED` | Binance implied by filenames/data provenance, not pinned to a selected settlement tuple. |
| market | `INFERRED` | USD-M perpetual implied by symbols and filenames. |
| contract type | `INFERRED` | Perpetual not pinned for one selected event. |
| symbol | `PINNED_REPOSITORY_ARTIFACT` | Present in public funding files. |
| base/quote/margin/settlement asset | `MISSING` | Not authoritatively frozen for one selected event. |
| quantity unit | `MISSING` | No authoritative account position/product unit evidence. |
| contract multiplier | `MISSING` | Not pinned. |
| timestamp units | `PARTIALLY_PINNED_REPOSITORY_ARTIFACT` | Funding files use ISO or millisecond timestamps, but no matched account settlement. |
| price scale | `MISSING` | No authoritative mark-price evidence for a selected event. |
| amount scale | `MISSING` | No account income amount scale evidence. |
| rounding policy evidence | `MISSING` | QNTY paper rounding is not Binance settlement rounding. |

# Matching Analysis

No valid evidence tuple exists. Matching could not proceed because side A, authentic account funding receipt, is missing; side B, matching signed account position quantity, is missing; and side C is only normalized public funding data without an account-side event to match.

matching_keys: none.

tolerance_used: none.

ambiguities: all public rows are unmatched without an account receipt and position record.

# Manual Reconciliation

manual_reconciliation: not performed.

Reason: performing reconciliation would require circular inference from the observed funding amount or unsupported assumptions about account position/product precision. The audit froze no economic equation against a complete evidence tuple.

reconciliation_verdict: `ACCOUNT_RECEIPT_MISSING`

# Duplicate-Capability Assessment

duplicate_capability_assessment: `NO_DUPLICATE_EXACT_CAPABILITY`

QNTY already has paper funding accounting, public funding-source snapshots/bundles, SQLite writer/verifier checks, idempotent paper event identities, and paper numeric conventions. It does not already prove an authentic Binance funding settlement against an account income record and account position.

# Implementation Gate

implementation_gate: `CLOSED`

Required conditions not met:

- authentic account receipt exists: no
- matching signed position exists: no
- matching public funding event with mark price exists: no
- product identity pinned: no
- quantity units pinned: no
- precision policy pinned: no
- manual reconciliation informative: no
- existing QNTY duplicate: no

No implementation is recommended from the current evidence.

# Missing Evidence

Missing:

- authentic Binance USD-M account income record with `incomeType = FUNDING_FEE`
- observed signed funding amount and settlement asset from account side
- unique Binance transaction identity, if available
- matching signed account position quantity at settlement
- matching finalized public funding event with real associated `markPrice`
- authoritative product/unit/precision/rounding evidence for the selected symbol

# Immediate Next Action

`EXPORT_EXISTING_BINANCE_FUTURES_INCOME_HISTORY`

After that, independently locate matching position history and pin product/precision evidence before any implementation planning.

# Verification

Focused offline QNTY tests:

| Command | Return code | Passed | Failed | Skipped | What it proves | What it does not prove |
|---|---:|---:|---:|---:|---|---|
| `.venv/bin/python -m pytest -q tests/test_funding_source_snapshot_schema.py tests/test_funding_source_immutable_bundle_semantics.py tests/test_funding_timestamp_normalization_spec.py tests/test_paper_sqlite_writer.py tests/test_paper_sqlite_verify.py tests/test_paper_sqlite_verifier_clean_net_of_carry_gate.py tests/test_paper_sqlite_writer_funding_fail_closed_proof.py tests/test_paper_sqlite_writer_source_snapshot_emission.py tests/test_paper_sqlite_writer_snapshot_reference_transaction.py tests/test_paper_sqlite_verifier_source_path_resolution.py tests/test_paper_sqlite_verifier_db_linked_snapshot_selector.py tests/test_paper_sqlite.py` | 4 | 0 | 0 | 0 | Nothing; command had a bad filename and no tests ran. | Does not verify repository behavior. |
| `.venv/bin/python -m pytest -q tests/test_funding_source_snapshot_schema.py tests/test_funding_source_immutable_bundle_semantics.py tests/test_funding_timestamp_normalization_spec.py tests/test_paper_sqlite_writer.py tests/test_paper_sqlite_verify.py tests/test_paper_sqlite_verifier_clean_net_of_carry_gate.py tests/test_paper_sqlite_writer_funding_fail_closed_proof.py tests/test_paper_sqlite_writer_source_snapshot_emission.py tests/test_paper_sqlite_writer_snapshot_reference_transaction.py tests/test_paper_sqlite_verifier_db_linked_snapshot_selector.py tests/test_paper_sqlite.py` | 0 | 259 | 0 | 0 | Existing offline paper funding snapshot/bundle, timestamp normalization, SQLite writer/verifier, reconciliation, idempotency, and numeric checks pass. | Does not prove authentic Binance account income, position evidence, product precision, or exact funding settlement reconciliation. |

# Reproduction

From QNTY:

```bash
cd /home/swirky/DevHub/repos/Qnty
git rev-parse --show-toplevel
git branch --show-current
git rev-parse HEAD
git remote -v
git status --short --branch
git log -10 --oneline --decorate
```

From QntyLab:

```bash
git -C /home/swirky/DevHub/repos/QntyLab rev-parse --show-toplevel
git -C /home/swirky/DevHub/repos/QntyLab branch --show-current
git -C /home/swirky/DevHub/repos/QntyLab rev-parse HEAD
git -C /home/swirky/DevHub/repos/QntyLab status --short --branch
```

Candidate discovery was bounded to the allowed roots with the requested filename patterns and formats. The sanitized inventory temp artifact hash was:

`d8a4e91d0880db70fc5f2cf75c4abac342afd8b49a736aa571fe249402e12bf3`
