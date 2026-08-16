# Order-Flow V0 Blocked-Window Forensics — Hostile Review

Review type: exactly one independent hostile review of
`QNTY_EDGE_DISCOVERY_ORDER_FLOW_V0_BLOCKED_WINDOW_FORENSICS_V0`.

Verdict: `PASS`

The review attacked the actual A/B/C/D classifications and the evidence chain:

1. No C classification relies only on a failed local download. The six continuity rows bind provider-published monthly object hashes, row counts, and checksums; the seven pre-onboard rows bind official `onboardDate` values plus exact 404 object/checksum records; REEF binds the authenticated final funding event and exact missing later objects.
2. No A classification was asserted without source-existence evidence; `A_COUNT=0`.
3. Instrument nonexistence is separated from missing data. The seven newer contracts have provider `onboardDate` after the required frozen prefix.
4. Provider-object absence is separated from local-cache absence through the canonical object index and `data.binance.vision` object/checksum URLs.
5. No funding event was zero-filled. Pre-onboard funding absence is treated as lifecycle/source absence; REEF funding ends at the observed provider event boundary.
6. Required price and funding ranges are read from the immutable input snapshot, including warm-up and terminal tail requirements.
7. No probe downloaded replacement scientific data or modified a source artifact.
8. No alternate provider, market, product, interval, symbol, or source family was used.
9. The 46 `INPUT_READY` rows and immutable 46/14 census are preserved.
10. The source manifest, input snapshot, qualification, receipt, and implementation manifest are unchanged and hash-bound.
11. No feature, return, PnL, strategy, ranking, or scientific result was calculated.
12. Each of the 14 rows has exactly one C classification and reproducible provider/lifecycle evidence.
13. The common-root-cause groups follow the per-window evidence and do not collapse row identity.
14. Proposed next actions are diagnosis-only; reaching 60/60 requires a separately authorized scientific-contract decision.

Findings:

- Critical: 0
- High: 0
- Open critical: 0
- Open high: 0
- Targeted re-review: not used
