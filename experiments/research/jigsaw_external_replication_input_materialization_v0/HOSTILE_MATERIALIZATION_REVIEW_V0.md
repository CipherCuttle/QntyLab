# Hostile materialization review V0

Scope: frozen-input acquisition only.  No H003 signal, return, drawdown,
state-bin, replication-result, bootstrap, or outcome comparison code was run.

| Attack | Finding | Severity | Disposition |
| --- | --- | --- | --- |
| Source-object omission / silent month skip | The request declares 473 month objects; the receipt index contains 473 terminal receipts and its terminal counts sum to 473. | None | Closed |
| Unverified bytes entering output | Each non-null normalized SHA is associated only with a symbol whose every source object is `MATERIALIZED_VERIFIED`; ZIP and published checksum digests are recorded per object. | None | Closed |
| Date or symbol expansion | The request digest fixes 3 state symbols, 20 cohort members, explicit starts, and the 2026-06-30T23 end. The report verifies exactly 23 symbols. | None | Closed |
| Dirty-WIP laundering | Acquisition occurred in the clean dedicated worktree. The dirty primary worktree was neither read as a source nor modified. | None | Closed |
| Gap hiding / member substitution | Gaps are adapter-reported. XLMUSDT has one explicit `SOURCE_AUTHENTICATION_UNAVAILABLE` object and remains the frozen member with `INPUT_PARTIAL`; it was not replaced. | None | Closed |
| Non-determinism / adapter drift | The execution branch contains qualified commit `2167a3b`; a second normalization from cached authenticated bytes reproduced all manifest bytes and SHA256 values. | None | Closed |
| Scientific outcome inspection | The controller imports the qualified input adapter only, not the Jigsaw analysis module. | None | Closed |

Verdict: `PASS_NO_CRITICAL_OR_HIGH_FINDING`.
