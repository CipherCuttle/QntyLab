# R1 bounded-evidence retention candidate v1

## VERDICT

R1_BOUNDED_EVIDENCE_RETENTION_CANDIDATE_READY_FOR_REVIEW

Not scientifically frozen. A fresh independent agent should falsify/freeze this before it governs any real acquisition.

## PROVENANCE

- BOM v3 SHA-256: 2f2d61a80bf283a26023ee5cee19df01de9202afd0061d1781dd5926b3b96dff
- required_acquisition SHA-256: d9d8875592a2a19672372b88fa46aadcec36b7f6b58df5af17028e6bca1dc16b
- Storage footprint SHA-256 (recomputed at authoring time): matches `experiments/data/r1_raw_storage_footprint_v1.json` on disk
- Candidate implementation: `qntylab/r1_retention_candidate.py`
- Candidate tests: `tests/test_r1_retention_candidate.py` (26 tests, all passing)

## WHY FULL RAW RETENTION DOES NOT FIT

`r1_raw_storage_footprint_v1.json` (verdict `R1_FULL_RAW_RETENTION_DOES_NOT_FIT`) is metadata-only (HEAD, 0 bytes transferred), sampled 782 real objects across 894 streams, and reports point estimate 4,811,961,308,917 bytes / conservative P90 13,558,238,467,450 bytes for 419,486 planned structural market objects, against roughly 9.2e10 bytes locally free. Funding is not included in that estimate. All of these numbers were independently recomputed from the artifact in this task and match exactly.

## BOUNDED PILOT (real, small, no bulk acquisition)

Five real objects were fetched by GET (not just HEAD), one per calendar era 2021-2026, all under 250KB (total ~287KB): ILVUSDT 2022-12-31, BATUSDT 2023-01-01, USDEUSDT 2025-01-01, DOLOUSDT 2026-06-30, LTCUSDT 2021-07-03. Their compressed sizes matched the footprint sample's HEAD-derived `compressed_bytes` exactly, i.e. the source had not mutated since that probe. Findings:

- Raw schema (verified): `timestamp,symbol,side,size,price,tickDirection,trdMatchID,grossValue,homeNotional,foreignNotional`. The 2026 object additionally carries an `RPI` column — **real, observed schema drift**, not a hypothetical.
- `homeNotional == size` and `foreignNotional == size*price` exactly, and `grossValue == foreignNotional*1e8` with **zero** reconstruction error, on every row of every pilot object. These three columns are semantically redundant and can be dropped and reconstructed, but this is a semantic-equivalence claim, not a byte-identical-CSV claim.
- Struct-packing the 6 non-redundant fields and gzip-recompressing yielded 0.57-0.62 of the raw compressed size (essential-only); packing all 10 fields losslessly yielded 0.85-0.90 (Bybit's CSV.gz was already reasonably well compressed, so naive transcoding is not a large win). Best case, Model A alone still leaves the population multiple TB above local free storage.

## THREE ARCHITECTURES

- **Model A (lossless semantic transcode)** — rejected as sufficient on its own: pilot-measured compression is far too small to fit the population locally (see above). Retained as the *normalization layer* inside Model C.
- **Model B (pure stream/reduce/delete)** — rejected: a single parser pass with no anomaly channel and no independent validation cannot survive the schema drift already observed in this pilot, a later-discovered parser bug, or a reanalysis need. It also has no defined behavior for source mutation, duplicate conflicts, or timestamp-boundary attacks.
- **Model C (hybrid bounded evidence)** — selected. Every object gets a normalized daily primitive + provenance receipt, permanently. Raw bytes are retained only for anomalous objects and a predeclared, strategy-blind, fixed-byte-budget audit reservoir; ordinary validated objects have raw deleted only after receipt + normalized primitive are durably committed.

## NORMALIZED EVIDENCE PRIMITIVE

Fields: `open, high, low, close, base_volume, quote_turnover, trade_count, first_source_timestamp_utc, last_source_timestamp_utc, first_source_trade_id, last_source_trade_id, duplicate_count, rejected_row_count, schema_id`. Derived from `qntylab/sprint_v2.py`'s proven consumption pattern (`close`, `funding_rate`, `premium`) plus the R1-locked hypothesis subset (`R1-H012-30d/90d`, `R1-H014-24h/7d`) in `sprint_v2_r1_origin_receipt.json`. R1's own trade-to-daily aggregation code does not exist yet, so this list is a conservative carried-over design assumption, explicitly flagged as such, not a frozen R1 contract.

## PROVENANCE RECEIPT / RETENTION STATES / REPRODUCIBILITY LEVELS

Receipt fields extend BOM v3's already-frozen `mechanical_receipt_contract.required_fields` (`source_url_or_query, retrieval_timestamp_utc, http_or_result_state, byte_size, sha256, parser_schema_result, stream_id, cache_key, retry_count`) with retention-specific fields: container validation, schema id/known flag, `parser_implementation_sha256`, `normalization_contract_sha256`, row/duplicate/rejected counts, normalized-primitive identity and SHA-256, anomaly list, `raw_retention_state`, `raw_retention_reason`, `rehydration_state`, `audit_reservoir_member`, `commit_stage`, and an append-only `predecessor_receipt_sha256` chain.

Raw retention states: `RAW_RETAINED`, `RAW_DELETED_AFTER_VERIFIED_DERIVATION`, `RAW_UNAVAILABLE_SOURCE_ABSENT`, `RAW_QUARANTINED_ANOMALY`.

Reproducibility claim levels: `PRESERVATION_REPRODUCIBLE` (raw bytes retained), `REHYDRATION_REPRODUCIBLE` (raw deleted, source SHA currently reconfirmed), `DERIVATION_AUDITABLE` (raw neither retained nor currently rehydratable). This candidate itself, as a document, is `DERIVATION_AUDITABLE` — no bulk raw was retained while authoring it.

## CRASH CONSISTENCY

Commit stages: `RETRIEVED_UNHASHED -> HASHED -> PARSED -> NORMALIZED_WRITTEN -> RECEIPT_WRITTEN -> RAW_ELIGIBLE_FOR_DELETION -> RAW_DELETED`. Raw deletion is permitted only at `RECEIPT_WRITTEN` or later (`raw_deletion_permitted`), enforced in code and tested for every earlier stage.

## SOURCE MUTATION

`record_rehydration_attempt` never overwrites the original receipt `sha256`; a mismatching rehydration is appended as a `SOURCE_MUTATION_DETECTED` attempt and forces `RAW_QUARANTINED_ANOMALY`, tested explicitly.

## INDEPENDENT VALIDATION

Every object gets a free, always-on, per-row check: Bybit's redundant columns (`homeNotional`, `foreignNotional`, `grossValue`) must equal derived values from `(size, price)`. This pilot found zero mismatches across all sampled rows. Anomaly-pool and audit-reservoir objects additionally require an independent reference re-parse before Model C is frozen; that second implementation is not yet built.

## AUDIT RESERVOIR

Deterministic, strategy-blind, fixed-byte-budget selection over `(stream_id, calendar_year, size_stratum, schema_variant)` only — no return, momentum, funding-signal, or outcome field is representable in the selection key (enforced by the function signature and tested). Selection is order-invariant (hash of the dimension key, not arrival order or size).

## FUNDING

Not folded into Model C's market-object policy. `r1_population_funding_plan_v2.json` estimates 7,238 funding API requests; at a conservative ~20KB/page that is roughly 145MB raw, negligible against local free storage. Recommendation: retain **all** funding raw responses in full.

## STORAGE BUDGET (bounded, not exhaustive)

Reserved (proposal, not measured): normalized population ~2GB, receipts/provenance ~1GB, raw anomaly pool ~5GB, raw audit reservoir ~5GB, funding raw ~150MB. This leaves the large majority of local free storage (~92GB at authoring time) unused, deliberately.

## RED TEAM / WHAT WOULD FALSIFY THIS

- If R1's real execution code needs a field not in the daily primitive (e.g. taker-side volume split), this primitive is insufficient and must be revised before freeze.
- If a second independent parser implementation is never built, the "independent validation" claim for anomaly/reservoir objects remains unmet and Model C should not be frozen as-is.
- The audit-reservoir byte budget (5GB) is asserted, not derived from a real per-cell sizing pass; a fresh agent should check it against `frozen_structural_object_count` per stream before freeze.

## LITERATURE

Sandve et al. 2013 (PLOS Comp Bio, 10.1371/journal.pcbi.1003285), Peng 2011 (Science, 10.1126/science.1213847), Wilkinson et al. 2016 (FAIR, Sci Data, 10.1038/sdata.2016.18), W3C PROV-O, RFC 8493 (BagIt fetch.txt / holey bags), FIPS 180-4, Halchenko et al. 2021 (DataLad, JOSS 10.21105/joss.03262) motivate the receipt/normalized-artifact/raw-availability split used here; none of them certify this specific design as correct. Current Bybit archive availability was checked at authoring time and is not assumed permanent.

## OUTCOME EMBARGO

No H012/H014 values, factor rankings, weights, forward returns, PnL, IC, Sharpe, or replication outcomes were produced or used. Only source mechanics and pre-outcome pilot data.
