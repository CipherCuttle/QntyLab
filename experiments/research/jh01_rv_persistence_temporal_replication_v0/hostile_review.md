# Independent hostile review — JH01 temporal replication preregistration

Scientific review target SHA:
`5a7e2886bef10d7bb3e36306857df71fd1ef1001`

Scope: outcome-blindness; hidden post-discovery input access; temporal window
and coverage algebra; same-history mislabelling; panel/survivorship changes;
measurement, inference, multiplicity, magnitude-gate, and pooling drift;
independence proof; Jigsaw self-ingestion; execution/materialization and
downstream-authority leakage; and amendment loopholes.

Result: **CRITICAL 0, HIGH 0, MEDIUM 2, LOW 0.** No Critical or High repair
was required, so no targeted re-review is authorized or performed.

Medium observations retained for future hardening, not scientific changes:

1. The validator makes the contract digest and Git freeze the primary
   immutability anchors; it does not separately enumerate every textual
   inference/classification/amendment field as a validator equality check.
2. This record supplies the durable review-to-freeze chain absent from the
   review-target commit itself. The frozen preregistration bytes remain
   unchanged from that target.

The review did not inspect, download, materialize, or compute any
replication-period market data, features, outcomes, or regression.
