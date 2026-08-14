# JFPV3 hostile preregistration review

Review count: 1 independent hostile review; targeted rereview: 1, used only after the High repair below.

## Initial findings

- Critical: none.
- High: the first draft could be misread as using the live `exchangeInfo` endpoint to reconstruct past status. That would violate PIT semantics.
- Medium: raw panel RV varies mechanically with `N_t`; this is a material estimand risk.
- Low: future membership churn could be mistaken for a reason to shrink an already sealed outcome panel.

## Required repair

The source contract now requires a raw official metadata response persisted before or at each origin, with `metadata_observed_at <= origin`; current metadata cannot be used as historical backfill. The same sealed `U_t` is explicitly required for future outcomes, and missing future bars block the origin. The scientific contract includes the fixed origin-time `N_t` control in both models.

## Targeted rereview

- PIT lookahead: PASS; membership uses only the pre-origin snapshot and structural fields.
- Variable-N validity: PASS with an explicit limitation; `N_t` controls scale but does not make composition invariant, so the estimand remains the eligible-universe mechanism.
- Adaptive leakage: PASS; 30 days, `N_MIN=15`, all-contract policy, 365 origins, and the materiality gate are justified without V2 outcome tuning.
- Operational fail-closed behavior: PASS; metadata/source/bar failures block and no fallback or shrink is permitted.
- Authority boundary: PASS; even support is capped at measurement survival.

Final open Critical: 0. Final open High: 0. Medium: 0. Low: 0.
