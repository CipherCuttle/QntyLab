# One Hostile Review: Order-Flow V0 Preregistration

## Scope

One bounded static review of
`qnty_edge_discovery_order_flow_v0_preregistration.json` and its Markdown
rendering. No new feature value, return, PnL, ranking, plot, regression, or
trial was computed.

## Findings

| Attack | Finding | Severity | Disposition |
|---|---|---:|---|
| Secret H010 rerun | V0 uses one raw signed-notional formula, one fixed lag, one prior-median scale, and continuation only. H010’s six coordinates and 18 rows are disclosed and not recreated. | — | Pass |
| Algebraic collapse | `total - taker_buy` is admitted only after a source partition check; the signed raw numerator, lag, and prior median scale differ from H010 OFI. | — | Pass |
| Direction hindsight | Continuation is frozen from the stated mechanism; H010 reversal positives are explicitly barred from selection. | — | Pass |
| Same-bar leakage | Source bar ends at `t-1h`; decision and execution are at target open `t`; outcome ends at `t+1h`. Unfinished and overlapping bars are forbidden. | — | Pass |
| SAFE-KNOWN timing | A completed source bar and one-bar embargo are required; publication/closure ambiguity blocks execution. | — | Pass |
| Unrealistic execution | The contract uses target-open to following-open taker semantics and explicitly rejects free-close fills. Existing close-to-close `bar_path` incompatibility is documented as an execution-phase block. | — | Pass |
| Cost understatement | Baseline and stress both charge 10 bps fee; stress adds 10 bps slippage. No H010 5/10/20 bps search or rescue is allowed. | — | Pass |
| Funding timing | Realized event-time funding is mandatory, not forward-filled or zero-filled; coverage gaps block cells. | — | Pass |
| Asset-selection hindsight | The exact canonical Breadth V2 20-symbol order and digest are frozen before V0 outcomes; no coverage-based deletion is permitted. | — | Pass |
| Denominator omission | V0 counts one eligible variant, two cost modes, 20 assets, three blocks, two controls, and retains H010’s six-coordinate/18-row prior denominator. | — | Pass |
| Hidden alternate search | No alternate horizon, threshold, normalization, direction, universe, or execution assumption is eligible. | — | Pass |
| Benchmark inadequacy | Flat/cash is eligible; fixed prior-1h continuation is diagnostic-only and required for incremental utility. | — | Pass |
| Universe survivorship | Panel membership is inherited from canonical prior selection; missing cells block and remain counted. | — | Pass |
| Multiplicity | Low-dimensional denominator and prior H010 ancestry are explicit; no generic inference or post-result correction path is introduced. | — | Pass |
| Rescue pathways | Cheap-kill rule explicitly prohibits every listed rescue dimension. | — | Pass |

## Review verdict

No Critical or High finding remains. No targeted re-review is required. This
review authorizes only the static preregistration handoff, not scientific
execution or any downstream system mutation.
