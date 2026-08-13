# Hostile Materialization Review V0

One independent review was performed after acquisition and qualification.

## Attacks and disposition

- Source substitution: PASS. The request contains only the frozen Binance source families; JFP01 is blocked on the missing 2026-08 monthly objects and no daily, REST, websocket, or vendor substitute was admitted.
- Checksum and local digest: PASS. Every `MATERIALIZED_VERIFIED` object has a published SHA-256 equal to the independently computed local SHA-256; cache promotion is content-addressed.
- Replacement and partial download: PASS. The receipt binds URL, checksum identity, byte digest, size, archive member, and structural receipt. Partial responses cannot pass checksum or ZIP validation.
- Timestamp/schema/continuity: PASS for JFP03; JFP02 2021-07 fails closed on an exact coverage endpoint mismatch. Headerless older Binance files are admitted only through their explicit 12-column positional schema.
- Candidate-local/global semantics: PASS. JFP01 and JFP02 remain ordered candidate-local blocks; JFP03 is independently READY. No global block or candidate replacement was emitted.
- Hidden science and authority escalation: PASS. No feature, outcome, regression, p-value, ranking, PnL, Jigsaw, shadow, State Snapshot, Router, Qnty, or trading operation exists in this materializer or receipt.
- Snapshot binding and later byte identity: PASS. The deterministic snapshot digest includes ordered source identities, official/local hashes, qualification digest, and both frozen contract digests.
- Reacquisition: PASS. A frozen receipt makes subsequent materializer invocation fail closed; project state records `input_reacquisition_authorized = false`.
- Raw file handling: PASS. Raw archives are retained only in the existing ignored content-addressed cache; Git contains manifests and receipts, not multi-gigabyte market-data files.

## Finding

No Critical or High finding. No targeted re-review is required. Medium/Low findings: none material to the frozen input evidence or authority boundary.
