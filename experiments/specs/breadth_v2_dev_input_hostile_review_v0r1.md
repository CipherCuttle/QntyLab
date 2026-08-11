# Targeted hostile review: BREADTH_V2_DEV_INPUT_MATERIALIZATION_V0R1

Review allocation: one targeted review, post-implementation, pre-census-regeneration
(then confirmed against the real regenerated census). Scope restricted to the
funding-parent and scientific-cell corrections and their interaction with the
frozen V0 contract; no broad architecture review was reopened.

1. **Does non-carry funding request only required economic history?** Pass.
   `funding_parent_start(period_id)` returns `T0 - 1h` and is the sole funding
   start for `required_funding_signal_events == 0` rows; the prefetch envelope
   uses the same floor, not `180` days.
2. **Can carry actually discover N real events without cadence assumptions?**
   Pass. `discover_funding_carry_start` counts checksum-verified archive rows
   with `admission_boundary <= T0` and extends by whole calendar months on
   an authenticated count deficit only. No interval arithmetic appears in the
   stopping condition.
3. **Can missing carry history contaminate non-carry inputs?** Pass. Ordinary
   and carry funding parents are cached under distinct keys
   `(symbol, funding_start, period_end)`; a carry backscan for one candidate
   never mutates or degrades the ordinary parent used by another.
4. **Is T0-edge funding still available correctly?** Pass. `funding_admission_boundary`
   and the `[start, end]` admission clip in `build_breadth_v2_input_bundle` are
   untouched; an event at `T0 - 2ms` still admits at `T0` and one at `T0 + 2ms`
   still admits at the next boundary.
5. **Does raw-cache reuse remain provenance-safe?** Pass. `EvidenceCache` stays
   content-addressed by request URL; discovery itself verifies each month's
   checksum via `receipt_from_bytes` before counting (a bad/unauthenticated
   month is treated as history-termination, never silently counted). Parent
   materialization stays profile-specific even when raw bytes are shared.
6. **Can status transitions be hidden?** Pass. The V0-to-V0R1 transition
   artifact (`experiments/data/breadth_v2_dev_input_v0_to_v0r1_transitions.json`)
   records old/new status, reason, and bundle SHA for all 996 keys and
   classifies bundle-SHA-only changes as `READY_IDENTITY_CORRECTED` rather
   than hiding them inside `READY_TO_READY`.
7. **Are scientific cells correctly doubled for two cost modes?** Pass.
   `ready_mapped_scientific_cells` moved from `976` to `1952` (exactly `2x`)
   on the real regenerated census with an unchanged READY set, confirming the
   fix is a pure accounting correction independent of any status change.
8. **Do totals reconcile to 1992 / 3360?** Pass, verified on the real census:
   `1496 + 496 = 1992`; `1952 + 1408 = 3360`.
9. **Did any strategy outcome execute?** Pass. `qntylab/breadth_v2_dev_inputs.py`
   contains no reference to `PortfolioKernel.execute`, `prepare_breadth_v2_evaluation`,
   `record_breadth_v2_evaluation`, or `target_weights` (grep-verified and
   covered by `test_outcome_guard_no_execution_or_ledger_symbols_imported`).
10. **Did any frozen scientific rule change?** Pass. `required_history_for_variant`,
    price clip semantics, `FUNDING_CARRY` window values, panel order, cost
    modes, and `SEALED_T0` are byte-identical to V0; only the two named
    implementation defects were touched.

## Finding discipline

No Critical or High finding survived review. One observation, not acted on
because it is neither Critical nor High: `discover_funding_carry_start`
accepts `t1` but does not use it in the backward walk (the walk only needs
`T0` and each candidate month); this is inert, not a correctness defect, and
is left as-is per the "no additional generic tests / no refactor" stop
condition.

Disposition: no Critical/High findings. Targeted re-review: not used.
