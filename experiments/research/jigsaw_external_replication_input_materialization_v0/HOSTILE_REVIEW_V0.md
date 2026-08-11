# Hostile Review — External Replication Input Materialization V0

Scope: outcome-dependent acquisition, dirty-WIP laundering, digest/provenance
errors, cohort mutation, date expansion, silent missingness, and state-reference
contamination only. No Jigsaw-piece review was reopened.

## Findings

- Critical: a committed, H003-compatible USD-M OHLC materializer with
  object-level raw provenance and checksum authentication does not exist.
  `qntylab.binance_um_archive` is trades-only.  Recasting its observations as
  candles would be a prohibited new adapter.
- High: `qntylab.data.fetch_premium_perp` has no fixed final-hour clipping and
  does not retain per-month source-object receipts or verify published
  checksums.  It cannot prove the frozen end date or required object-level
  provenance.  Using it would create date-expansion and provenance defects.
- High: active `master` contains unrelated dirty manifests/results, including
  the cohort symbols.  None were read as evidence, staged, copied, or modified.
- Pass: the declaration/report byte hashes and their canonical cohort/piece
  digests match the frozen values.
- Pass: the exposure receipt records the preview as non-authoritative and
  freezes its effect on future design to none.
- Pass: no market data were acquired and no H003 or state calculation ran, so
  no outcome-dependent source decision or state-reference contamination occurred.

## Disposition

The Critical capability gap is not repairable within this phase because a new
generic downloader/normalizer is explicitly out of scope.  Close as
`BLOCKED_BY_H003_INPUT_MATERIALIZATION_CAPABILITY`; do not classify this as a
replication failure.
