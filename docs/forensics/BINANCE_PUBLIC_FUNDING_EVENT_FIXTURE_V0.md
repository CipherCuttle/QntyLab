# Executive Verdict

`BINANCE_PUBLIC_FUNDING_EVENT_FIXTURE_V0_COMPLETE`

Downstream gate: `READY_FOR_PUBLIC_ECONOMIC_FIXTURE`.

# Scope and Non-Claims

Claim scope: `PUBLIC_FINALIZED_FUNDING_EVENT_ONLY`. This is not an account receipt, not evidence of a real position, not evidence of wallet posting, not a strategy result, not evidence of execution, not evidence of solvency, and not evidence of profitability.

# Repository Identities

QntyLab root `/home/swirky/DevHub/repos/QntyLab`, branch `master`, HEAD `dc0b6cf4f51f44c30025685818a0e0c5f29dc688`.

QNTY root `/home/swirky/DevHub/repos/Qnty`, branch `chore/external-trust-root-dispatcher-repair-v046`, HEAD `8ebe61bdecd2d72239cf8d0618df87d6e1171c5a`. QNTY was inspected read-only.

# Existing Acquisition Capacity

- `binance_public_rest_acquisition`: EXTEND: qntylab.data has Binance REST helpers for spot klines, not this USD-M funding event fixture
- `raw_response_preservation`: REUSE: resolver and forensic reports preserve source hashes; this task preserves exact raw REST bytes in docs/forensics/evidence
- `raw_byte_hashing_helper`: REUSE: sha256_path/sha256_bytes patterns exist in qntylab.resolve_holdout_source and strategy_test tests
- `canonical_json_helper`: REUSE: canonical_bytes patterns exist in qntylab.resolve_holdout_source and research_ledger
- `receipt_schema`: EXTEND: existing run receipts/source-resolution receipts exist but no public funding-event receipt schema
- `data_path_convention`: NOT_APPLICABLE: production data/raw funding CSVs are normalized and intentionally not modified
- `public_fixture_convention`: EXTEND: forensic docs exist; evidence subdirectory is new and task-specific
- `funding_archive_loader`: REUSE_WITH_LIMITATION: qntylab.data.fetch_funding reads monthly fundingRate archives but normalizes to timestamp/funding_interval_hours/funding_rate only
- `fundingTime_markPrice_rateType_support`: ABSENT: no existing local public fixture preserves all REST fields plus raw source bytes

# Frozen Market and Period

Venue: Binance. Market: USD-M perpetual futures. Symbol: BTCUSDT. Period: `2026-06-01T00:00:00.000Z` through `2026-06-30T23:59:59.999Z`. Calculated milliseconds: `1780272000000` through `1782863999999`.

# Official REST Request

`GET https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&startTime=1780272000000&endTime=1782863999999&limit=1000`

Authentication: `NONE_PUBLIC_ENDPOINT`. Server time was fetched first from `https://fapi.binance.com/fapi/v1/time`.

# Raw Response Evidence

HTTP status: `200`. Content type: `application/json;charset=UTF-8`. Raw bytes: `11362`. Raw SHA-256: `01d38d5b8c8581388621015a2bc618673cac1ff51ff88672aea52f9bdb31bafd`. Row count: `90`.

# REST Schema Validation

Validation status: `REST_SCHEMA_VALID`. Fields observed: `fundingRate, fundingTime, markPrice, rateType, symbol`. Extra fields observed: `none`.

# Observed Event Intervals

Observed interval counts are recorded in the receipt. Intervals cluster around 8 hours with millisecond-level timestamp offsets; this task does not assume an eight-hour invariant.

# Monthly Archive Comparison

Classification: `ARCHIVE_MATCHES_RATE_AND_TIME_ONLY`. Archive HTTP `200`, checksum HTTP `200`. Archive SHA-256 `cff97ce688329592bccbbf5873b5c7021649e093f5f5806e332c5b4fb7fd6a00`. Official checksum verified: `True`. CSV header: `calc_time, funding_interval_hours, last_funding_rate`. The archive matched REST time/rate rows but did not include `markPrice` or `rateType`.

# Deterministic Selection Rule

Select the earliest ascending REST row where `symbol == BTCUSDT`, `rateType == Regular`, `markPrice > 0`, and all required fields validate. Funding-rate sign and magnitude were not selection inputs.

# Selected Public Funding Event

Source array index: `0`. Funding time: `1780272000001` / `2026-06-01T00:00:00.001Z`. Funding rate: `0.00005703`. Mark price: `73653.56663043`. Rate type: `Regular`.

# Local Capability Comparison

Overall classification: `NORMALIZED_RATE_AND_TIME_ONLY`. QntyLab contains normalized rate/time only for this event; QNTY contains no matching selected event. No conflicting local event was found.

# Evidence Added

The fixture adds associated nonzero `markPrice`, `rateType`, raw official REST response bytes, request provenance, source hashes, and archive comparison for one deterministic public funding event.

# Limitations

No personal Binance futures activity exists by user declaration. This fixture does not prove account settlement, position quantity, wallet posting, execution, solvency, profitability, venue precision, or any strategy result.

# Downstream Readiness

`READY_FOR_PUBLIC_ECONOMIC_FIXTURE` because REST status was 200, raw bytes and SHA-256 are preserved, schema validated, a Regular event with nonzero markPrice was selected deterministically, no local conflict exists, and non-claims are explicit.

# Verification

Focused offline tests and a temporary artifact validator are recorded in the final task response and receipt-adjacent validation output.

# Reproduction

Use the exact frozen URL above after fetching Binance server time. Hash the raw response bytes before parsing. Compare the monthly archive and its `.CHECKSUM` from data.binance.vision as supplemental evidence.

# Final Verdict

`BINANCE_PUBLIC_FUNDING_EVENT_FIXTURE_V0_COMPLETE`

# Immediate Next Action

`REVIEW_PUBLIC_ECONOMIC_FIXTURE_CONTRACT_V0`
