# Clean TSMOM EXP_V2 real execution implementation R3

`experiment=EXP_V2` and `contract_revision=REAL_EXECUTION_IMPLEMENTATION_R3`.

R3 is an additive implementation amendment. It makes the producer capable of
reading the authenticated external R1 source bundle and adds an independent
source-to-result verifier. R1 source bytes and R2 scientific, timeline,
window, metric, benchmark, and classification semantics remain unchanged.

No real producer or full-result verifier was run while freezing R3; no real
signals, weights, PnL, benchmarks, metrics, or classifications were observed.

The old R2 implementation remains preserved as audit history.
