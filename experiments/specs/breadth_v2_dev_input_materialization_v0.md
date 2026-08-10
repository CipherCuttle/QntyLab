# Breadth V2 development-input materialization V0

This contract is outcome-free. It enumerates 996 cost-independent market-input
records from the frozen 1,992 execution descriptors, derives history from each
registered candidate, and delegates READY admission to
`build_breadth_v2_input_bundle`. Baseline and stress executions reuse one bundle
identity; cost arithmetic is not part of acquisition.

Price source clips are `[T0 - required_price_closes hours, T1 - 1 hour]`,
inclusive. Funding sources begin no later than `T0 - 1 hour`, and carry warmup
walks authenticated settlement events by count, never by `N * 8 hours`.

HTTP 404 on the exact frozen archive is `SOURCE_OBJECT_ABSENT`. Timeouts, 408,
429, and 5xx remain `ACQUISITION_UNRESOLVED` after at most three attempts plus
one targeted retry pass. No transport state is scientific absence.

A panel is atomic in the census: one unavailable member blocks the synchronized
20-member record. Blocked records remain in the 996/1,992/3,360 denominators.
The coordinator never calls the runner, `PortfolioKernel`, strategy functions,
or ledger writers.
