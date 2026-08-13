# JFP03 V0R1 Source-Contract Repair — Hostile Review V0

Review count: exactly one independent hostile review.

The frozen proposal was attacked for hidden scientific degrees of freedom, outcome-conditioned source choice, daily-versus-monthly mismatch, timestamp boundaries, OHLC field semantics, USD-M product identity, point-in-time leakage, silent sample alteration, evidence non-escalation, and reproducibility.

Findings:

- Monthly archive availability is not manufactured: the exact object and checksum remain recorded as 404 and are not rewritten.
- Daily archives are not accepted as a substitute because the required 2019-12-02 object is absent.
- The REST fallback is the exact Binance USD-M `/fapi/v1/klines` endpoint, not spot, COIN-M, continuous-contract, mark-price, index-price, vendor, or synthetic data.
- The proposal freezes the request before any later acquisition and binds the returned bytes by SHA-256; source choice cannot inspect AFI, HAR, targets, regression results, or p-values.
- The structural probe found 720 contiguous UTC 1h rows with 12 documented kline fields and exact close-time boundaries.
- The Binance-owned public-data README explicitly identifies USD-M archive kline data as sourced from `/fapi/v1/klines`, supporting raw proposition equivalence. It does not prove that a future REST response is immutable, so response-byte hashing is mandatory.
- No scientific computation, source comparison by outcome, row dropping, design change, original-object reacquisition, or closed-history mutation occurred.

Severity summary: Critical 0; High 0; Medium 0; Low 0.

Review verdict: PASS. No targeted re-review is required.
