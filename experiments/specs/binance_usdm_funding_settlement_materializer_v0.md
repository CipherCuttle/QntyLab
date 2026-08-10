# Binance USD-M funding settlement materializer V0

Status: implemented as `BINANCE_USDM_FUNDING_SETTLEMENT_MATERIALIZER_V0`.

This narrow, exploratory-only source adapter authenticates monthly Binance
USD-M funding archives using the sibling publisher checksum, validates the
frozen three-column schema, and emits exact millisecond settlement events plus
separate provenance receipts. The archive is the sole causal economic source.
The official USD-M `/fapi/v1/fundingRate` endpoint is an independent coverage
witness: its paginated, raw-byte-bound pages must reconcile exactly on
`fundingTime` plus canonical Decimal `fundingRate`. REST never overwrites or
fills archive economics, and unavailable or non-matching REST coverage blocks
certification.

The causal JSONL contains only `symbol`, `funding_time_ms`,
`funding_time_utc`, and canonical decimal `funding_rate`. ZIP and CHECKSUM
objects are retained content-addressed; source revisions therefore remain
distinct provenance even when normalized economics are identical.

`funding_interval_hours` is retained as source metadata and diagnostics only;
it is not a completeness law. Exact source timestamps are never rounded,
snapped, or replaced by an expected schedule.
