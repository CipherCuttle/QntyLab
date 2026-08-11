# Hostile review — Jigsaw Cross-Sectional Dispersion V0

Scope was limited to the frozen execution contract and the produced evidence.

- Canonical origin and contract digest are bound and match the requested gate.
- The prior BLOCKED decision remains immutable; exactly one reopen event targets it.
- Warm-up persistence is durable outside `/tmp`; 240 source objects, 20 normalized inputs, 20 manifests, and 240 receipts were byte-hash checked.
- The dispersion calculation uses the exact 20-member panel, sample standard deviation (`ddof=1`), and the imported PIT percentile/bin functions.
- Economic observations are DEV_2024 only. The 2023 material is used only for warm-up. No post-`SEALED_T0` input is read.
- CSMOM weights and portfolio accounting are called through the existing Breadth V2 runner and kernel. Stress is primary; baseline is secondary; funding is realized and fail-closed.
- The family statistic is the imported four-variant `consistent_count`; no pooled economic scalar or variant selection is produced.
- The result is killed mechanically because only 1/4 stress contrasts is negative. No rescue analysis was added.

Outcome: `NO_CRITICAL_OR_HIGH_FINDINGS`. No targeted re-review required.
