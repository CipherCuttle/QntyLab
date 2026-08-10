# PIT Instrument Catalog + Roster Completeness Contract V0

Gate A is an artificial, offline contract implemented by
`qntylab.pit_instrument_catalog`. It does not contact a venue, read archives,
construct a historical universe, or call PIT Admission/Universe Composition.

## Separation

| Question | V0 output | Explicitly not implied |
| --- | --- | --- |
| Identity discovery | exact `InstrumentIdentity` is positively known | lifecycle, tradability, admission, completeness |
| Catalog | exact identities knowable by `as_of` | an active-symbol list |
| Completeness | `ESTABLISHED_COMPLETE` / `UNRESOLVED` for one declared scope/time | admission or tradability |

Identity is the existing exact `InstrumentIdentity` (symbol, market,
contract_type, instrument_instance_id). Ticker-only matching and relist
continuity are absent: two `ABCUSDT` episodes can coexist; an ambiguous record
is `IDENTITY_UNRESOLVED` and has no identity to add.

## Source capabilities

`COMPLETE_SNAPSHOT_AT_INSTANT`, `SEQUENCED_DELTA`,
`POSITIVE_IDENTITY_DISCOVERY_ONLY`, and `OBSERVATION_ONLY` are a closed
vocabulary. Observation-only evidence cannot produce an identity-discovery
record. Positive discovery never proves completeness. A valid matching complete
snapshot proves completeness at its instant; a later proof requires it plus a
contiguous, non-conflicting sequenced delta chain. Scope mismatch, missing
anchor, gap, conflict, or unfinished chain is `UNRESOLVED`, never `INCOMPLETE`.

## PIT and provenance

Strict catalog snapshots accept only `STRICT_PIT` records with
`available_time <= as_of`; retrospective records are rejected, not silently
ignored. Later source revisions are separate records and cannot alter an
earlier snapshot. Discovery and roster-source objects bind source key, raw
payload digest, source-contract id/version/digest, available time, scope, and
derived SHA-256 receipts. Canonical ordering makes input order non-semantic.

The catalog is append-only knowledge: a source roster `REMOVE` may be relevant
to completeness derivation but cannot remove a previously discovered identity.
Correction/retraction precedence is intentionally deferred; preserved
revisions do not silently overwrite one another.
