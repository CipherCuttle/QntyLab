# Order-Flow V0 Blocked-Window Forensics Authorization — Hostile Review

Review type: exactly one independent hostile governance review for
`QNTY_EDGE_DISCOVERY_ORDER_FLOW_V0_BLOCKED_WINDOW_FORENSICS_AUTHORIZATION_V0`.

Verdict: `PASS`

The review attacked the authorization against the required failure modes:

1. Repairing the 14 rows is explicitly denied, including repair, interpolation, zero-fill, and rematerialization.
2. Alternate datasets, providers, products, source families, dates, symbols, intervals, and rescue paths are explicitly denied.
3. Only source and integrity metadata may be inspected; no feature values, future returns, PnL, strategy execution, rankings, or scientific results are authorized.
4. The original immutable 46/14 census is bound by path, digest, row count, and blocked-row identity and may not be rewritten.
5. Classification C requires proof of exact frozen-source absence; one failed acquisition is not sufficient.
6. Classification A requires evidence that the exact frozen source exists and satisfies the frozen contract.
7. Listing-date and source-absence claims must be grounded in official provider objects, checksums, metadata, or bounded exact-object probes.
8. The later phase is restricted to the exact 14 blocked symbol/period rows; no row may be silently dropped.
9. The frozen preregistration, candidate, universe, feature, cost, and source-contract identities are bound and cannot be rewritten.
10. The authorization creates no materialization run, scientific execution authority, or downstream authority.

Findings:

- Critical: 0
- High: 0
- Open critical: 0
- Open high: 0
- Targeted re-review: not used

The authorization is ready for canonicalization. The next phase is diagnosis only and must not repair the blocked windows or execute Order Flow V0.
