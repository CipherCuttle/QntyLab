# Research Data Spine V0 — Frozen Implementation Contract

## Objective

Implement the smallest bounded data spine which proves the following
infrastructure proposition, and nothing about markets:

> The pre-certified Funding Pressure V1 OHLCV panel can be deterministically
> composed once into an immutable, digest-identified snapshot and reused by two
> bounded non-scientific consumers without reacquisition or requalification.

V0 is `BOUNDARY_C`: normalized immutable Parquet, a canonical manifest, and a
small verified reader.

## Non-goals

V0 does not acquire market data, normalize funding or premium-index data,
compose a lifecycle/universe, implement features or outcomes, provide a query
service or a global registry, run a Jigsaw hypothesis, or make a scientific,
causal, trading, or execution claim.  DuckDB is deliberately deferred: Polars
plus the verified reader satisfies the only frozen materialization and bounded
window-read requirements.

## Source evidence

The sole real source composition is the 20-symbol OHLCV panel certified by
`experiments/research/jigsaw_funding_pressure_volatility_v0/pit_coverage_certificate_v1.json`:

- source authority: Binance USD-M perpetual monthly 1h klines;
- source materializer: `BINANCE_USD_M_PERPETUAL_1H_MATERIALIZER_V0`;
- exact panel, 610 eligible decisions, and source evidence digests: the V1
  certificate; and
- normalized V0 CSVs and the V1 source-bar extension named by that certificate.

The materializer accepts only local source files whose SHA-256 values, source
certificate identity, and per-symbol membership match this frozen composition.
It has no network code and no fallback source path.  Missing or mismatched
evidence blocks materialization.

## Dataset composition and schema

One snapshot contains exactly one `market_bars` relation, partitioned one file
per frozen instrument identity.  Rows have this exact ordered logical schema:

| Column | Logical type / meaning |
| --- | --- |
| `instrument_instance_id` | UTF-8, V0-local frozen panel identity |
| `symbol` | UTF-8 Binance symbol |
| `bar_open_time` | UTF-8 canonical UTC timestamp |
| `bar_close_time` | UTF-8 canonical UTC timestamp |
| `open` | UTF-8 source numeric lexeme |
| `high` | UTF-8 source numeric lexeme |
| `low` | UTF-8 source numeric lexeme |
| `close` | UTF-8 source numeric lexeme |
| `volume` | UTF-8 source numeric lexeme |

Numeric source lexemes remain strings in V0.  This preserves the certified
normalization rather than silently introducing a floating-point interpretation.
The local identity is exactly
`binance-usdm-perpetual-funding-pressure-v1:<SYMBOL>`.  It distinguishes the
frozen source composition, venue, market and symbol, but makes no lifecycle or
relisting assertion beyond the certified panel.

## Time, PIT, coverage, and row policy

`bar_open_time` is the source bar-open identity.
`bar_close_time` is exactly `bar_open_time + 1 hour`.
`safe_known_after` is a semantic rule, not an extra row column:
`safe_known_after >= bar_close_time`.

No claim is made that historical archive or vendor availability is reconstructed
for the instant of bar close.  A consumer may use only a requested window wholly
inside the manifest's certified coverage and must itself apply its decision
timing after the stated safe-known-after boundary.

Rows are ordered by `(instrument_instance_id, bar_open_time)`.  Each partition
must have unique hourly opening times, exact expected schema, positive finite
OHLCV lexemes accepted by the existing source materializer, and no gap in its
declared inclusive coverage.  Duplicate rows, schema drift, a missing hour,
or a source substitution fail closed.

## Logical identity and storage-byte integrity

For each canonical partition identity, `logical_digest` is SHA-256 of canonical
UTF-8 JSON Lines containing: the schema identity, partition identity, and the
ordered logical rows.  It intentionally excludes Parquet metadata and storage
layout.

`parquet_byte_sha256` is SHA-256 of the stored Parquet file bytes.  It protects
the particular stored representation but never defines data identity.  Both are
required on every partition.

The canonical manifest is JSON encoded with sorted keys, compact separators,
and no execution-time, host, user, absolute-path, or random fields.  Its
`snapshot_digest` is SHA-256 of the manifest excluding `snapshot_digest` and
`snapshot_id`, and covers at least the dataset/schema IDs, ordered partition
identities and logical digests, row counts, coverage, schema, source certificate
and evidence identities, time semantics, and recipe identity/version.
`snapshot_id` is `rds-v0-<snapshot_digest>`.

Equivalent logical rows and semantics retain their snapshot identity even when
a compatible writer creates different Parquet bytes.  Writer/runtime details
are recorded for reproducibility but excluded from `snapshot_digest`.

## Immutability and reader contract

Snapshot creation writes to `snapshots/<snapshot_id>/`.  A pre-existing target
is verified and reused only when its manifest and all partition integrity checks
pass; a different or corrupted target fails closed.  No target is overwritten.

The verified reader requires an explicit snapshot path, expected snapshot
digest, requested symbols, and an inclusive UTC time window.  Before returning
rows it verifies the manifest digest and identity; selected partition identity,
logical digest, Parquet byte digest, schema and coverage; and requested symbols
and window bounds.  Out-of-contract requests reject.  It never accesses the
network, acquires data, requalifies sources, or substitutes sources.

## Reuse proof and kill criteria

Consumer A is a Funding Pressure frozen-input-shape OHLCV window adapter.
Consumer B is an independent generic panel/window consumer.  Both must report
the exact same `snapshot_id` and `snapshot_digest`; neither may emit a market
finding.

V0 is killed rather than weakened if certified evidence cannot bind, logical
identity is nondeterministic or depends on Parquet bytes, the stated time
semantics would need a stronger availability claim, the reader tolerates a
mutation/substitution, the two consumers cannot share one identity, or generic
infrastructure becomes necessary.

## Authority boundary

This document is the sole implementation authority for `RESEARCH_DATA_SPINE_V0`.
It authorizes only the files and behavior described here.  Git-backed Project
Context controls project activation; the research ledger continues to control
research state.  A snapshot is infrastructure evidence, not scientific
validation or trading authority.
