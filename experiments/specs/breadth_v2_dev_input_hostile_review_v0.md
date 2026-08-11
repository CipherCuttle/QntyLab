# Hostile review: BREADTH_V2_DEV_INPUT_MATERIALIZATION_V0

Review allocation: one pre-acquisition review, 2026-08-10. No live source
objects were consulted during this review.

1. Profile-specific clips use the candidate-derived history; a missing long
   profile cannot block a shorter profile.
2. Parent source reuse is independent from bundle admissibility; each bundle
   still validates its own exact clip and event-count warmup.
3. Kline materialization sorts validated unique source-open timestamps; raw CSV
   order is not treated as an economic invariant.
4. Funding admission is computed from exact event milliseconds, so an event just
   before T0 admits at T0 while one just after T0 admits at the next boundary.
5. Carry warmup is event-count based, not `N * 8 hours`.
6. Transient transport errors remain `ACQUISITION_UNRESOLVED`; only exact 404 is
   scientific source absence.
7. Panel input is atomic and preserves all 20 frozen members and their order.
8. Blocked rows remain in the 996/1,992/3,360 denominators and never become
   outcomes or zero returns.
9. Both cost modes map to the same collapsed input key and bundle identity.
10. Source bytes are content addressed by the acquisition layer; the
    coordinator does not overwrite evidence or collapse provenance into
    economics.
11. The coordinator imports no runner execution entry point and calls neither
    `PortfolioKernel` nor the ledger.
12. Candidate parameters, periods, asset membership, and `SEALED_T0` are read
    from the frozen contracts and not inferred from availability.
13. Terminal MDD includes the final liquidation equity in both compact paths;
    trade-count remains the count of non-zero rebalance boundaries.
14. Scope is limited to this coordinator, tests, documentation, and the
    authorized terminal-MDD correction; no generic data platform is created.

Disposition: no Critical or High findings. Targeted re-review: not used.
