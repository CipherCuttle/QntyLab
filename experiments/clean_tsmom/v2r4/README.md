# Clean TSMOM EXP_V2 independent verification R4

`experiment=EXP_V2` and `contract_revision=INDEPENDENT_VERIFICATION_R4`.

R4 is an additive, pre-experiment verification amendment. It preserves the
R3 implementation and records its recoverable independent-verification defect:
R3 did not recompute the complete result surface, derived controls, or actual
numeric differences, and its mutation fixtures changed bytes without updating
the artifact manifest.

R4 independently authenticates the R1 source bundle, reconstructs every frozen
artifact from source through final liquidation, derives controls and evidence,
and performs a manifest-preserving semantic comparison. It is synthetic-test
only during this freeze. No real source bundle, real metrics, market-data
network, or strategy evaluation is used.
