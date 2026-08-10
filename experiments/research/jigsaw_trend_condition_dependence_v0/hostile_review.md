# Hostile review — Jigsaw Trend Condition Dependence V0

Reviewed independently from the result narrative after implementation.

- Future leakage: no Critical/High finding. State windows end at decision close; trailing percentiles are computed only over daily values through that decision.
- Full-sample normalization: no Critical/High finding. The inclusive-CDF implementation uses a 365-day trailing daily slice.
- Label alignment and overlap: no Critical/High finding. The fixed label contains exactly 24 hourly returns and adjacent 00:00 decisions do not overlap. It is correctly described as the continuing measurement strategy's utility, not a deployable gate.
- Gap handling: no Critical/High finding. Alignment selects a single contiguous common segment and never fills or bridges missing timestamps; excluded segments are reported unavailable.
- Costs: no Critical/High finding. Baseline and stress are separately recomputed from the same fixed position path using the existing 10/0 and 10/10 bps modes.
- Concentration and pseudo-replication: no Critical/High finding. Primary rows are equal-weight daily three-asset observations; year, leave-2024-out, per-asset, leave-one-asset-out, and top-five removal attacks are reported.
- Post-hoc interpretation / silent H003 resurrection: no Critical/High finding. The artifact consistently retains the fixed measurement, retrospective, non-authoritative boundary; it makes no alpha, sleeve, gate, or Router claim.

Outcome: `NO_CRITICAL_OR_HIGH_FINDINGS`. No rereview is required.
