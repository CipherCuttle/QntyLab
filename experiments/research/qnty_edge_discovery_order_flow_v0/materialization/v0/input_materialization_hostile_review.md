# Order-Flow V0 Input Materialization Authorization — Hostile Review

Review scope: exactly one independent hostile governance review of the
authorization contract. The CLOSED_BLOCKED R1 predecessor and frozen V0
identities were not reopened.

## Review result

`PASS` — zero Critical and zero High findings. No targeted re-review was
required.

## Attack surface and disposition

- **Scientific execution escalation:** PASS. The artifact authorizes only a later outcome-free materialization phase; feature/outcome relationships, returns, PnL, rankings, survivor metrics, and execution remain forbidden.
- **Universe or window drift:** PASS. The ordered 20-symbol panel, three exact temporal blocks, 60-window denominator, and 40 scientific-cell denominator are frozen; shrinkage, expansion, substitution, and survivorship selection are prohibited.
- **Source substitution:** PASS. Only the canonical Binance USD-M materializer contract is admitted; missing, replaced, checksum-invalid, or semantically inconsistent source objects fail closed.
- **Funding rescue:** PASS. Realized event-time funding is required, missing funding blocks, and zero-fill is prohibited; no-event and missing-data states must remain distinct.
- **Input identity:** PASS. Provider object identity, checksums, byte hashes, normalized integrity counts, manifest/snapshot/census digests, and the exact consumed snapshot are required.
- **Data minimization:** PASS. The scope prohibits unrelated exchanges, order books, options, extra symbols, years, intervals, and datasets.
- **Parameter selection:** PASS. The later phase cannot choose feature, direction, horizon, threshold, normalization, cost, or execution parameters.
- **Ledger and downstream authority:** PASS. No candidate/trial events, H010/JH01/JFPV3 mutation, Jigsaw, State Snapshot, Router, Qnty, trading, promotion, or capital authority is granted.
- **Automatic escalation:** PASS. `INPUT_READY` ends materialization only; historical execution requires a separate Git-backed authorization.

## Findings

`CRITICAL = 0`

`HIGH = 0`

`MEDIUM = 0`

`LOW = 0`

Conclusion: the authorization is safe to freeze as a governance-only,
separately Git-backed input-materialization permission.
