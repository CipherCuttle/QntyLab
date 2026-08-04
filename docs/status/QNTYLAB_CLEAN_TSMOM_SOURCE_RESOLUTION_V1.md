# QNTYLAB CLEAN TSMOM SOURCE RESOLUTION V1

Status: `SOURCE_RESOLVED_BEFORE_CONTRACT_COMMIT`

Starting V0 head: `ffdab68f3c3db753ef1d764ee02143a2d4718f9b`.
Frozen V0 contract: `175b4a621936a79ffc44c299d9f21fc53fffd053`.
V0 blocked receipt: `ffdab68f3c3db753ef1d764ee02143a2d4718f9b`.

## Findings

The prior seven-symbol blocked panels contained 3,648 rows instead of the
3,672 expected 1h rows. Official June USD-M kline archives contain the full
month, while the corresponding official premium-index archives contain 696
rows and omit `2026-06-29T00:00:00Z` through `2026-06-29T23:00:00Z`. The old
adapter inner-joined klines with premium-index rows even though neither frozen
strategy consumes premium index. This is `UNUSED_PREMIUM_INDEX_OVERCONSTRAINT`.

The V0 contract still cannot be repaired: official MATICUSDT kline and
premium-index archives return HTTP 404 for March through July 2026, and bounded
USD-M REST returns an empty kline array. MATIC funding archives exist. POLUSDT
archives exist, but no futures-contract continuity with MATICUSDT was proven;
POL is therefore not substituted or spliced. Classification:
`MATIC_CONTRACT_UNAVAILABLE` and `SYMBOL_CONTRACT_UNAVAILABLE`.

AVAXUSDT independently resolves to 3,672 1h kline rows and 459 settled
funding events for the frozen period, with no remaining gap or duplicate.

## Decision

`PATH_B_SOURCE_RESOLVED_V1`

V0 remains permanently blocked. V1 removes only MATICUSDT, uses the original
ordered nine-symbol universe, changes only mechanical denominators from 10 to
9, and permits exact closed official REST gap resolution only with retained
request/response provenance and archive overlap equality. No returns or
strategy metrics were computed before the V1 contract commit.

No Qnty, DVOL, credentials, private endpoints, exchange orders, or alternate
exchange sources were used. This is exploratory and non-authoritative.
