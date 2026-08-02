# Executive Verdict

`PUBLIC_ECONOMIC_FIXTURE_CONTRACT_V0_REVIEWED`.

The smallest scientifically honest contract is additive and narrow: given one verified public Binance USD-M BTCUSDT finalized funding event and one clearly synthetic signed BTC quantity, compute the hypothetical economic funding transfer with `decimal.Decimal`. It is not account evidence, not a strategy trial, and not a profitability or execution claim.

# Scope and Non-Claims

Claim scope: `HYPOTHETICAL_PUBLIC_FUNDING_ECONOMIC_RECONSTRUCTION_ONLY`.

Allowed claim: given one authentic public finalized funding event and a synthetic signed position quantity, calculate the corresponding hypothetical economic funding transfer using pinned product units, sign conventions, and Decimal arithmetic.

Non-claims: not an account receipt; not a real wallet posting; not a real position; not a real trade; not evidence of execution; not evidence of a spot hedge; not evidence of capital efficiency; not evidence of margin survival; not evidence of liquidation survival; not evidence about ADL; not evidence of profitability; not evidence of alpha; not a strategy trial; not a research candidate.

# Repository Identities

QntyLab:

| Field | Value |
| --- | --- |
| root | `/home/swirky/DevHub/repos/QntyLab` |
| branch | `master` |
| starting HEAD | `72835944af9fb00b9729e9528adb3e949b77adda` |
| remote | `origin https://github.com/CipherCuttle/QntyLab.git` |
| status | ahead of `origin/master` by 20, with unrelated manifest/run WIP |

QNTY:

| Field | Value |
| --- | --- |
| root | `/home/swirky/DevHub/repos/Qnty` |
| branch | `chore/external-trust-root-dispatcher-repair-v046` |
| HEAD | `8ebe61bdecd2d72239cf8d0618df87d6e1171c5a` |
| status | untracked `plans/`, `qnty_ruleset_rollout.sh`; no tracked dirty paths observed |

# Source Fixture Integrity

Fixture directory: `docs/forensics/evidence/binance_public_funding_event_v0/`.

| Artifact | SHA-256 | Status |
| --- | --- | --- |
| `BTCUSDT-fundingRate-2026-06.raw.json` | `01d38d5b8c8581388621015a2bc618673cac1ff51ff88672aea52f9bdb31bafd` | verified |
| `BTCUSDT-fundingRate-2026-06.selected-event.json` | `fcc0682d5a30976d860fbbefaf415b0e0c0d0585835a4a8ef089acd9c5376b59` | verified |
| `BTCUSDT-fundingRate-2026-06.receipt.json` | `456e7918e3d9c7caeee67a8bde729867cbe0143f2002e7496ef5234382278c1c` | verified |
| `BTCUSDT-fundingRate-2026-06.archive.CHECKSUM` | `b16df2145a1acd03de19335dcd416e3f9dd85d4dd252ce8a60b205668d23f4a4` | verified |

Selected event identity is verified as raw response array index `0`:

```json
{"symbol":"BTCUSDT","fundingTime":1780272000001,"fundingRate":"0.00005703","markPrice":"73653.56663043","rateType":"Regular"}
```

The selected-event file adds `fundingTimeUtc = 2026-06-01T00:00:00.001Z`, preserves source decimal strings, and links to the raw response hash. The receipt links to both raw and selected-event hashes.

# Official Funding Semantics

Official sources used:

- Binance USD-M Futures market-data REST docs: `https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data`
- Binance funding-rate support FAQ: `https://www.binance.com/en/support/faq/detail/360033525031`
- Binance public API definitions: `https://developers.binance.com/en/docs/products/derivatives-trading-portfolio-margin/common-definition`
- Public endpoint snapshot: `https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&startTime=1780272000001&endTime=1780272000001&limit=1`

Load-bearing official semantics:

| Rule | Classification |
| --- | --- |
| `fundingRate` is the public funding-rate field returned by USD-M funding-rate history | `OFFICIAL_AND_LOAD_BEARING` |
| `fundingTime` is the public funding event timestamp | `OFFICIAL_AND_LOAD_BEARING` |
| `markPrice` is the mark price associated with the funding fee charge | `OFFICIAL_AND_LOAD_BEARING` |
| funding amount equals nominal position value times funding rate | `OFFICIAL_AND_LOAD_BEARING` |
| nominal value equals mark price times contract size | `OFFICIAL_AND_LOAD_BEARING` |
| positive funding means longs pay shorts; negative funding reverses | `OFFICIAL_AND_LOAD_BEARING` |

Public formula semantics are sufficient. Account posting precision, wallet rounding, actual position snapshot semantics, and private income reconciliation remain unresolved and outside this fixture.

# Product and Quantity Semantics

Current public `exchangeInfo` for BTCUSDT was captured under `$TMPDIR/public-economic-fixture-contract-v0/` only.

| Field | Value | Classification |
| --- | --- | --- |
| venue | Binance | `HISTORICALLY_PINNED_FOR_EVENT` |
| market type | USD-M Futures | `HISTORICALLY_PINNED_FOR_EVENT` |
| contract type | PERPETUAL | `CURRENT_OFFICIAL_ONLY` |
| symbol | BTCUSDT | `HISTORICALLY_PINNED_FOR_EVENT` |
| base asset | BTC | `CURRENT_OFFICIAL_ONLY` |
| quote asset | USDT | `CURRENT_OFFICIAL_ONLY` |
| margin asset | USDT | `CURRENT_OFFICIAL_ONLY` |
| settlement asset | USDT | `INFERRED` |
| quantity unit | BTC base asset units | `CURRENT_OFFICIAL_ONLY` |
| price unit | USDT per BTC | `CURRENT_OFFICIAL_ONLY` |
| notional unit | USDT | `CURRENT_OFFICIAL_ONLY` |
| contract multiplier | `1` | `INFERRED` |
| quantity precision | `3` | `CURRENT_OFFICIAL_ONLY` |
| price precision | `2` | `CURRENT_OFFICIAL_ONLY` |
| settlement amount precision | unresolved | `UNRESOLVED` |
| minimum quantity | `0.001` | `CURRENT_OFFICIAL_ONLY` |
| step size | `0.001` | `CURRENT_OFFICIAL_ONLY` |

Current product metadata is not treated as historically effective at `2026-06-01T00:00:00.001Z`. Historical order eligibility is not required because this contract does not claim the synthetic quantity was actually tradable or executed.

# Existing QNTY Accounting Semantics

| Question | File path | Symbol | Test path | Current behavior | Limitation | Classification | Confidence |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Position-sign convention | `quantbot/paper/engine.py` | `run_engine open_positions qty` | `tests/test_paper_pnl.py::test_long_only_invariant` | Entries are BUY, exits are SELL, qty is positive, no short path | no native signed quantity | `ADAPT_WITH_WRAPPER` | high |
| Signed quantity vs absolute notional | `quantbot/paper/engine.py` | `notional_at = pos["qty"] * mark` | `tests/test_paper_pnl.py::test_round_trip_fill_and_pnl` | positive qty times mark gives notional | signed quantity must be explicit fixture input | `NEW_ADDITIVE_CONTRACT` | high |
| Paper funding calculation | `quantbot/paper/engine.py` | `amount = notional_at * rate` | `tests/test_paper_pnl.py::test_funding_gap_flagged_not_silently_zeroed` | summed held-interval rate times notional; positive funding is subtracted from simulated equity | uses paper close marks and float, not public event markPrice Decimal | `ADAPT_WITH_WRAPPER` | high |
| Numeric representation | `quantbot/paper/engine.py` | `_round8`, `float(row["fundingRate"])` | `tests/test_paper_netpnl_canonicalization.py` | Python floats and SQLite `REAL` | cannot be exact Decimal authority | `NEW_ADDITIVE_CONTRACT` | high |
| Rounding or quantization | `quantbot/paper/engine.py` | `round(amount, 8)` | `tests/test_paper_pnl.py` | rounds money fields to 8 decimals and rates to 12 | not Binance account-posting precision | `DO_NOT_REUSE` | high |
| Account balance posting | `quantbot/paper/db.py` | `ledger_state.funding_cum`, `equity_snapshots.equity` | `tests/test_paper_sqlite.py`, `tests/test_paper_sqlite_writer.py` | simulated equity and funding accumulators only | no wallet/account posting | `DO_NOT_REUSE` | high |
| Duplicate prevention | `quantbot/paper/db.py` | `UNIQUE(event_type, event_key)` | `tests/test_paper_pnl.py::test_idempotent_rerun_identical_digests` | append-only event identity prevents duplicate event rows | fixture id must include event hash and synthetic signed quantity | `EXTEND_EXISTING` | high |
| Row or receipt reuse | `quantbot/core/receipts.py`, `quantbot/paper/funding_source_snapshot.py` | `TrialReceipt`, `canonical_json`, `sha256_text` | `tests/test_receipt_schema.py`, `tests/test_funding_source_snapshot_schema.py` | receipt and canonical hash patterns exist | trial receipt should not represent this non-trial contract | `EXTEND_EXISTING` | medium |
| Meaning of existing paper results | `docs/paper_pnl_v1_schema.md`, `docs/ADR/0001-paper-sqlite-ledger.md` | `paper_pnl_v1` | `tests/test_paper_pnl.py`, `tests/test_paper_sqlite_verify.py` | fixed-notional active-symbol simulation only | new fixture must not reinterpret prior paper results | `REUSE_UNCHANGED` | high |
| Extension safety | `quantbot/paper/db.py`, `quantbot/paper/sqlite_writer.py`, `quantbot/paper/sqlite_verify.py` | append-only ledgers, read-only verifier | `tests/test_paper_sqlite_verify.py`, `tests/test_paper_sqlite_writer.py` | additive transactional architecture exists | implement separate Decimal fixture receipt, not mutation of paper funding tables | `EXTEND_EXISTING` | high |

# Duplicate-Build Analysis

Future implementation should be `ONE_ADDITIVE_QNTY_FIXTURE`.

Reuse QNTY’s canonical hashing, receipt/verifier discipline, append-only idempotency patterns, and funding-source provenance conventions. Do not create a new repository, shared executable package, general ledger, spot leg, two-leg execution engine, capital ledger, SOFR adapter, margin engine, liquidation engine, ADL model, historical rule registry, carry candidate, or carry backtest.

# Quantity Policy

Selected policy: `B. exactly 0.001 BTC`.

Rationale: current official product metadata expresses BTCUSDT quantity in BTC base units, no additional multiplier is needed for the dimensional formula, and `0.001` is exact under Decimal. The report does not claim historical order eligibility.

Rejected alternatives: `1 BTC` is dimensionally clear but more likely to be mistaken for a real large position; smallest current increment overstates current metadata if framed as historical eligibility; symbolic `q` avoids ambiguity but weakens test readability.

# Sign Convention

`SIGN_CONVENTION_CONFIRMED`.

Internal convention: `signed_position_quantity > 0` means long, `signed_position_quantity < 0` means short.

Transfer convention: positive transfer means the hypothetical account receives funding; negative transfer means it pays funding.

Formula:

```text
economic_funding_transfer =
  -signed_position_quantity
  * funding_mark_price
  * finalized_funding_rate
  * contract_multiplier
```

With a positive funding rate, `+q` yields a negative transfer and `-q` yields a positive transfer, matching Binance’s public long-pays/short-receives statement.

# Numeric Policy

Use Python `decimal.Decimal` from source decimal strings with explicit context precision 50 or greater. Binary floating point is forbidden. Implicit scientific-notation conversion is forbidden. Tolerances must not be selected after calculation.

QNTY’s current paper path uses floats and SQLite `REAL`, so it is not the arithmetic authority for this exact fixture. This is not a blocker if the future implementation is a new additive Decimal fixture path.

# Precision Boundary

Required statuses:

| Status | Contract position |
| --- | --- |
| `EXACT_DECIMAL_ECONOMIC_AMOUNT` | supported |
| `QUANTIZED_HYPOTHETICAL_AMOUNT` | unresolved, not included |
| `ACCOUNT_POSTING_NOT_APPLICABLE` | required; no real position/account receipt |

Do not label any amount exchange-exact or account-posted without account-side rounding evidence.

# Golden Vectors

Inputs: `fundingRate = "0.00005703"`, `markPrice = "73653.56663043"`, `contract_multiplier = "1"`, `q = "0.001" BTC`.

| Vector | Signed quantity | Notional | Transfer | Direction |
| --- | ---: | ---: | ---: | --- |
| `VECTOR_LONG_POSITIVE_RATE` | `0.001` | `73.65356663043` | `-0.0042004629049334229` | `PAYS` |
| `VECTOR_SHORT_POSITIVE_RATE` | `-0.001` | `73.65356663043` | `0.0042004629049334229` | `RECEIVES` |
| `VECTOR_ZERO_QUANTITY` | `0` | `0` | `0` | `NONE` |

Synthetic falsifiers without fixture mutation: funding rate sign reversed, quantity sign reversed, mark price omitted, mark price zero, funding rate malformed, quantity malformed, rateType missing, event hash mutated, fundingTime changed, duplicate application attempted.

# Failure-State Model

The contract defines 19 failure states:

`SOURCE_FIXTURE_MISSING`, `SOURCE_HASH_MISMATCH`, `SOURCE_EVENT_NOT_FOUND`, `EVENT_IDENTITY_MISMATCH`, `SYMBOL_MISMATCH`, `MARK_PRICE_MISSING`, `MARK_PRICE_NON_POSITIVE`, `FUNDING_RATE_INVALID`, `FUNDING_TIME_INVALID`, `RATE_TYPE_INVALID`, `QUANTITY_INVALID`, `QUANTITY_UNIT_UNRESOLVED`, `CONTRACT_MULTIPLIER_UNRESOLVED`, `SIGN_CONVENTION_UNRESOLVED`, `NUMERIC_POLICY_VIOLATION`, `PRECISION_RULE_UNRESOLVED`, `ACCOUNT_POSTING_NOT_APPLICABLE`, `DUPLICATE_APPLICATION`, `QNTY_EXTENSION_BOUNDARY_UNSAFE`.

For public economic reconstruction, missing account receipt is `NOT_APPLICABLE`. For account-posting reconciliation, missing account receipt is `UNRESOLVED`.

# Minimal Contract

The machine-readable contract is frozen in `docs/forensics/PUBLIC_ECONOMIC_FIXTURE_CONTRACT_V0.json`.

Required fields are present: `contract_id`, `contract_version`, `claim_scope`, `source_event_identity`, `source_raw_sha256`, `source_receipt_sha256`, `venue`, `market`, `symbol`, `funding_time`, `funding_time_utc`, `funding_rate`, `funding_mark_price`, `rate_type`, `quantity_policy`, `signed_position_quantity`, `quantity_unit`, `contract_multiplier`, `notional_formula`, `transfer_formula`, `sign_convention`, `numeric_policy`, `precision_policy`, `calculated_notional`, `calculated_transfer`, `transfer_direction`, `evidence_level`, `non_claims`, `failure_reasons`, `determinism_requirements`, `idempotency_identity`, `implementation_owner`, and `research_state_policy`.

Evidence level: `AUTHORITATIVE_PUBLIC_EVENT_PLUS_SYNTHETIC_POSITION`.

Account status: `ACCOUNT_POSTING_NOT_APPLICABLE_NO_REAL_POSITION`.

# Implementation Ownership

Implementation owner: `QNTY`.

QntyLab owns preserving the source fixture and this contract-review report only. Research-state policy is `DO_NOT_REGISTER_AS_CANDIDATE_TRIAL_OR_DECISION`.

# Maximum Future Changeset

Maximum future implementation boundary:

- QNTY consumes or references the existing public event fixture.
- QNTY accepts one synthetic signed quantity.
- QNTY computes deterministic Decimal notional and transfer.
- QNTY emits one additive economic reconstruction receipt.
- QNTY verifies source identity, sign, arithmetic, idempotency, non-claims, and no account-posting claim.

No production implementation is performed by this review.

# Falsification Results

| Attack | Result |
| --- | --- |
| dimensional | `REFUTED`: BTC times USDT/BTC times dimensionless rate times multiplier `1` resolves to USDT |
| sign | `REFUTED`: long positive-rate vector pays; short positive-rate vector receives |
| precision | `REFUTED_FOR_EXACT_AMOUNT`: Decimal source strings only; no invented rounding |
| product | `REFUTED_WITH_BOUNDARY`: quantity is BTC base units under current official metadata; no historical executability claim |
| historical semantics | `REFUTED_WITH_BOUNDARY`: current metadata is not represented as historical effective-dated metadata |
| provenance | `REFUTED`: raw or selected-event hash mutation invalidates the contract |
| idempotency | `REFUTED_BY_REQUIRED_IDENTITY`: event hash plus synthetic quantity identity is required |
| scope | `REFUTED_BY_NON_CLAIMS` |
| architecture | `REFUTED_BY_ONE_ADDITIVE_QNTY_FIXTURE` |
| research governance | `REFUTED_BY_RESEARCH_STATE_POLICY` |

# Unresolved Questions

Historical BTCUSDT order filters exactly effective at `2026-06-01T00:00:00.001Z` are not pinned and are not required for this bounded calculation.

Binance account-side funding posting precision and wallet rounding are unresolved and out of scope without authenticated account evidence.

Whether `rateType` has future non-Regular arithmetic branches is unresolved; this contract accepts only `Regular` for this fixture.

# Implementation Gate

`READY_FOR_ONE_ADDITIVE_QNTY_FIXTURE`.

Gate basis: source fixture integrity passes; official public funding semantics are sufficient; quantity unit is sufficiently pinned for dimensional calculation; contract multiplier is resolved as `1` for this formula; sign convention is confirmed; Decimal policy is viable; golden vectors recompute exactly; QNTY extension boundary is identified; implementation would not duplicate current paper capability; all non-claims are explicit; no account receipt is required for the bounded claim; contract validator passes.

# Verification

Commands run included repository identity checks, research-ledger context, source SHA-256 checks, public Binance `exchangeInfo`/`fundingRate`/`time` captures under `$TMPDIR`, QNTY source inspection, focused offline QNTY tests, contract validation, repository immutability checks, and staged diff checks before commit.

Focused tests prove QNTY’s current paper funding/idempotency/verifier assumptions for existing offline paths. They do not prove Binance account posting, real execution, real wallet settlement, margin survival, liquidation survival, ADL behavior, profitability, or alpha.

# Reproduction

Recompute the fixture economics with:

```python
from decimal import Decimal, getcontext
getcontext().prec = 50
q = Decimal("0.001")
mark = Decimal("73653.56663043")
rate = Decimal("0.00005703")
transfer = -q * mark * rate * Decimal("1")
assert str(transfer) == "-0.0042004629049334229"
```

Run the temporary validator from `$TMPDIR/public-economic-fixture-contract-v0/validate_contract.py`. It is intentionally not committed.

# Final Verdict

`PUBLIC_ECONOMIC_FIXTURE_CONTRACT_V0_REVIEWED`.

# Immediate Next Action

`IMPLEMENT_PUBLIC_ECONOMIC_FIXTURE_V0`.
