# Jigsaw Harvest V0 — Hostile Implementation Review

Scope: the corrected preregistration, schedule arithmetic, frozen formulas,
runner, HAC/ Holm computation, classifications, receipt completeness, and
real-execution prohibition. This is a separate read-only hostile review pass;
no frozen snapshot bars or scientific outputs were accessed.

## Correction lineage

- Original activation/preregistration: `66aee2f5b7dfb665a70915aaaac9c7ea9ce0ec34`.
- Pre-execution arithmetic correction: `1c6ceb2b377cec456ca09f50d025426413dbaf3f`.
- The inclusive interval 2023-11-18T00:00:00Z through 2025-06-19T00:00:00Z
  contains 580 dates. The last future return ends at 2025-06-20T00:00:00Z,
  the close of the final source bar opened at 2025-06-19T23:00:00Z.
- No endpoint, hypothesis, recipe, direction, multiplicity rule, or scientific
  output changed. HAC remains 5 under the frozen rule at T=580.

## Initial hostile findings

- Critical: 0.
- High: 2.
  1. Synthetic receipts did not bind the frozen preregistration identity.
  2. Synthetic receipts did not explicitly state that no real snapshot was
     used or carry a deterministic receipt digest.
- Medium: 0.
- Low: 0.

## Repairs

- Added the corrected preregistration digest to every synthetic receipt.
- Added null snapshot fields plus `SYNTHETIC_FIXTURE_NO_REAL_SNAPSHOT` binding
  and a canonical self-excluding receipt digest.
- Added focused assertions for these fields. The runner still raises before any
  real snapshot data can enter its public seam.

## Targeted re-review

- Critical: 0.
- High: 0.
- Medium: 0.
- Low: 0.

The implementation remains bounded to JH01–JH04, rejects identity/universe/
coverage/schedule violations, has no network acquisition path, emits all four
ordered synthetic results, and confers no scientific or downstream authority.
