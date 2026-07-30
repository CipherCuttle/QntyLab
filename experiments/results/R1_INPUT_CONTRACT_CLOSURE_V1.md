# R1 pre-outcome input contract closure — v1

## Scope

This closes only the first of four dependencies blocking the bounded-evidence
retention architecture freeze: **the exact source-level normalized evidence
contract**. It does not build the independent reference parser, does not size
the audit reservoir, does not rebuild the retention candidate, and does not
acquire population data. Outcome embargo intact throughout: no factor value,
rank, weight, return, PnL, IC, or Sharpe was computed or inspected.

## Checkpoint

- Checkpoint commit: `81b8a67ae9186cd7a89f632bc58d7413a0206bde`
- Checkpoint manifest: `experiments/data/r1_preoutcome_checkpoint_v1.json`
- Checkpoint manifest sha256: `80ed752c7ea003ba354fe7f64c7f04eac300405ca4d60c6b5334cea95d1d50b0`
- 74 previously-untracked files (implementation code, tests, R1 data/receipt
  artifacts, result docs) were recorded. Excluded by policy: the 531MB raw
  `sprint_v2_results.json`, unrelated Binance sprint-v2 manifests under
  `data/manifests/`, operational logs, and the generated `.r1_input_cache/`.

## Contract artifacts (this closure)

| Artifact | sha256 |
|---|---|
| `r1_input_dependency_graph_v1.json` | `126ddd5fa2a1c05ab83cf70ab46defd231177613e9c02de97c58fdaacdf0b77b` |
| `r1_normalized_evidence_contract_v1.json` | `c199b9481285d80b34183b8a7681f75ef7e60e5aadad6e4e0ece3ef8f33d6c92` |
| `r1_information_loss_ledger_v1.json` | `7590ea9dd60b961dfc2fb64c5b099089662d6dead4c1cb3f91d3b87d67c5df02` |
| `r1_source_schema_registry_v1.json` | `02d2a75cdaa3d53a2708d2d20d5bf19f934fc68e6ee1b942404994d80ab94c4d` |

**Combined input-contract sha256** (sha256 of the concatenation of the four
hex digests above, in the order listed): `3277f808dbc0a91f2e4573455349d01b281b70e617f441b81e11e6544fc62499`

Regenerating these artifacts from the same checkpoint yields byte-identical
output (verified twice for the checkpoint manifest; the four contract files
are hand-authored static content with no wall-clock, disk, or host data).

## What is actually closed

- The four locked hypotheses (`R1-H012-30d`, `R1-H012-90d`, `R1-H014-24h`,
  `R1-H014-7d`) share one PIT-universe/breadth-gate input dependency and one
  daily-close/quote-turnover derivation; H012 additionally needs only `close`,
  H014 needs only realized funding settlements. No hypothesis needs a field
  the others don't already require.
- Four strategy-independent evidence layers (`DailyMarketEvidenceV1`,
  `FundingSettlementEvidenceV1`, `GapEvidenceV1`, `LifecycleEvidenceV1`) are
  fully field-specified: type, derivation, UTC timing, duplicate handling,
  missingness, precision, and provenance for every field, with no momentum,
  rank, weight, return, or PnL field admitted.
- The raw trade schema's redundant fields (`grossValue`, `homeNotional`,
  `foreignNotional`) are **not** globally declared safe to drop: they are
  `PRESERVED_DERIVABLY`/`PRESERVED_AS_DIAGNOSTIC` on the strength of a 5-object
  pilot cross-check only, re-verified per object via an anomaly trigger, never
  assumed for unchecked objects.
- The observed schema-drift `RPI` column is `UNRESOLVED`, explicitly not
  authorized for deletion.
- Operational sufficiency was demonstrated with synthetic fixtures
  (`tests/test_r1_normalized_evidence_contract.py`, 7 tests, all passing):
  PIT eligibility, H012 momentum, H014 funding, and the breadth gate each
  compute correctly from the normalized contract fields alone.

## What remains explicitly open (not closed here, not silently resolved)

1. `r1_semantic_issue_ledger.json:PIT-DAILY-BREADTH-UNMATERIALIZED`
   (`BLOCKING_AMBIGUITY`) — whether breadth >=10 actually holds on the
   required fraction of candidate dates over the *full acquired population*
   is unproven; this is a materialization proof over real data, reserved for
   the acquisition/reservoir gaps this task is explicitly forbidden from
   touching.
2. `r1_semantic_issue_ledger.json:INPUT-BUNDLE-COMPLETENESS`
   (`BLOCKING_AMBIGUITY`) — no complete, network-independent raw Bybit object
   set exists yet; the schema above is proven sufficient on synthetic
   fixtures, not yet proven sufficient against the full raw population.
3. `r1_semantic_issue_ledger.json:R1-JOINT-DECISION-CLASSIFIER` — a post-outcome
   classification-semantics gap, out of scope for an input contract by
   definition.
4. A dangling hash reference inside the (not-frozen) retention candidate:
   `required_acquisition_sha256` does not match any file in this checkpoint.
   Recorded in `r1_preoutcome_checkpoint_v1.json:known_dangling_reference`,
   not repaired here (repairing the retention candidate is out of scope).
5. The retention candidate's known nondeterminism bug (live disk-free bytes
   inside a hash-covered field) is unchanged. It affects only the *retention
   candidate* artifact, not the normalized evidence contract closed here; the
   fix belongs to the later retention-candidate rebuild.

## Raw deletion firewall

`RAW_DELETION_AUTHORIZED = false`. Unchanged by this task.

## Verify

- `python -m pytest --collect-only -q`: 119 tests collected, exit 0
- `python -m pytest -q`: 119 passed, exit 0
- `git diff --check`: exit 0
- Formal QNTY repository: zero tracked changes caused by this task
