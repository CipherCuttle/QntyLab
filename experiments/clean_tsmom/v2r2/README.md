# Clean TSMOM EXP_V2 execution semantics R2

`experiment=EXP_V2` and `contract_revision=EXECUTION_SEMANTICS_R2`.

R1 repaired source discovery and authentication. R2 repairs execution and
evaluation semantics discovered before the first real EXP_V2 producer run.

No corrected EXP_V2 metrics existed or were inspected before the R2 freeze.
R2 does not claim that its newly explicit metric, benchmark or classification
rules were historically preregistered in EXP_V1. They are prospective EXP_V2
rules frozen before the corrected run.

The R2 producer and independent verifier accept synthetic fixtures only. A real
source bundle may be authenticated by the existing R1 binding verifier, but no
real evaluation is performed in this freeze.
