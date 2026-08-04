# ADR 0006: Clean TSMOM source-resolved V1

Status: `ACCEPTED_FOR_ONE_SOURCE_RESOLVED_POST_SELECTION_EVALUATION`

V0 remains frozen and blocked. MATICUSDT is removed only because its exact
Binance USD-M kline source is unavailable over the frozen period. POLUSDT is not
substituted and no histories are spliced. Dates, signal, causal t+1 execution,
weighting concepts, costs, funding semantics and classifications remain fixed;
only the universe cardinality changes mechanically from 10 to 9. Exact closed
official Binance USD-M REST rows may resolve archive gaps only with overlap
verification and row-level provenance. No result was inspected before this
contract was frozen.
