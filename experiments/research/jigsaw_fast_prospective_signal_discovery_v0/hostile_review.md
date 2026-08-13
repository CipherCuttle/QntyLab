# Hostile review — Jigsaw Fast Prospective Signal Discovery Preregistration V0

Review type: one bounded independent hostile review of the frozen design and
validator, before any data materialization.

## Findings

- CRITICAL: 0
- HIGH: 0
- MEDIUM: 0
- LOW: 0

## Attack checklist

Confirmed exactly three candidate IDs and no hidden fourth denominator; all
materially considered horizons/variants are recorded; feature and outcome
windows have explicit SAFE-KNOWN-AFTER semantics; overlapping outcomes use
fixed HAC; the three-candidate Holm family is explicit; sources include
archive replacement/checksum handling; the premium candidate cannot become a
funding trade; the flow candidate cannot become a return edge; no OI,
liquidation, order-book, L2, ML, or optimizer path exists; zero survivors is
allowed; no-rescue and no-optional-stopping rules are explicit; and every
authority boundary remains false/NONE.

The source contract intentionally permits JFP02 to be
`BLOCKED_BEFORE_EXECUTION` if official reproducible premium-index history is
not available. That is a truthful integrity disposition, not permission to
substitute weaker data.

Targeted re-review: not used; no Critical or High finding required a fix.
