# Implementation Review Receipts — FUNDING_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_IMPLEMENTATION_V0

Terminal-closure durable evidence for the failed implementation lifecycle
(GOVERNING DECISION: `experiments/research/jigsaw_funding_pressure_incremental_forecast_value_v0/contract_integrity_hardening_decision_v0/decision.json`,
SHA-256 `712cda5d4e82414ab095deecabaa7d2af054bc7b97ab5cbd394c9fdbeda32a23`,
canonical parent `12202259845ada4f9876288426fed91aba5b6861`).

Common root cause across all findings: SELF-ATTESTATION MUST NOT BECOME
VERIFIED AUTHORITY OR VERIFIED PROVENANCE. No arrow may run backward from a
caller assertion to verified state.

## Review 1 — independent hostile review of the original candidate

- REVIEW_TYPE = INDEPENDENT_HOSTILE_REVIEW
- REVIEWED_COMMIT = a6200d3e3d1ae2cffc44cca1d1db5d626239452c
- GITHUB_REVIEW_ID = PRR_kwDOTo27Xs8AAAABMQI3yw
- REVIEW_COUNT = 1
- CRITICAL = 0
- HIGH = 4
- MEDIUM = 0
- LOW = 0
- VERDICT = REPAIR_REQUIRED
- TARGETED_REREVIEW_REQUIRED = YES

### H1 (thread PRRT_kwDOTo27Xs6fbIjW; HIGH) — Forgeable authorization token

`OfflineAuthorizationToken` could be directly instantiated with
attacker-controlled values, and the boundary treated
`isinstance(token, OfflineAuthorizationToken)` as proof of authority. Required:
authority independently authenticated at the admission point (canonical
Git-backed CI-3 model); the token demoted to a descriptive receipt that the
boundary independently re-verifies against canonical Git before any claim, row
or core activity.

### H2 (thread PRRT_kwDOTo27Xs6fbIjc; HIGH) — Caller-selected Git is not canonical authority

The authorization verifier accepted caller-supplied repository/commit/path/
expected digest, so a throwaway repository with self-consistent attacker bytes
satisfied it. Required: the trust root fixed by reviewed canonical state
(canonical repository identity, canonical artifact/path, canonical Git ancestry
constraints, expected digest, governing decision identity — the existing CI-3
pattern); the requester must never choose the trust root; the canonical/offline
positive control must work without network access.

### H3 (thread PRRT_kwDOTo27Xs6fbIjd; HIGH) — Synthetic provenance must come from fixture evidence

The factory accepted arbitrary `ForecastRow` values plus an arbitrary
caller-named `fixture_identity` and elevated them to `OFFLINE_SYNTHETIC_FIXTURE`
verified provenance; content hashing after labeling is not proof of synthetic
origin (provenance laundering). Required: no constructor promoting arbitrary
pre-existing rows; synthetic provenance issued only from fixture material
authenticated against a separately pinned fixture identity/contract.

### H4 (thread PRRT_kwDOTo27Xs6fbIjh; HIGH) — Git anchor must bind the actual rows

The Git-anchored receipt authenticated blob A and separately hashed
caller-presented rows B without establishing that A binds B. Required: the
authenticated artifact must itself carry the row/content digest (plus schema,
kind, batch/factory identity) and the boundary must require exact equality
between the digest authenticated inside the artifact bytes and the digest of
the presented rows.

## Bounded repair (the one permitted Critical/High repair)

- REPAIRED_CANDIDATE_SHA = db6a6c6ed5102019300066edfdf4d4d9402f111a
- Branch: `agent/funding-incremental-contract-integrity-hardening-implementation-v0` (PR #245)
- Scope: H1/H2 authority re-authentication against a source-pinned canonical
  CI-3 trust root; H3 pinned `SyntheticFixtureContract` fixture-bytes provenance;
  H4 artifact-internal row-digest binding. Frozen V0 bytes unchanged.
- The four original findings were NOT marked resolved by the repair.

## Review 2 — targeted Critical/High re-review of the repaired candidate

- REVIEW_TYPE = TARGETED_CRITICAL_HIGH_REREVIEW
- REVIEWED_COMMIT = db6a6c6ed5102019300066edfdf4d4d9402f111a
- GITHUB_REVIEW_ID = PRR_kwDOTo27Xs8AAAABMQ8rww
- CRITICAL = 0
- HIGH = 1
- VERDICT = REPAIR_REQUIRED
- The remaining High exhausts the lifecycle.

### R1 (thread PRRT_kwDOTo27Xs6fcsAd; HIGH) — Keep the implementation decision from granting execution

The repaired boundary authenticates the implementation-only governance decision
as if it were evaluation authority. That decision authorizes zero
scientific-evaluation phases and records `scientific_execution_authorized=false`;
therefore the execution path must remain fail-closed until a separately
governed canonical evaluation authorization exists.

## Terminal determination

```text
IMPLEMENTATION_STATE = CLOSED_BLOCKED

INITIAL_HOSTILE_REVIEW_COUNT = 1
INITIAL_HIGH_COUNT = 4

BOUNDED_REPAIR_USED = YES

TARGETED_CRITICAL_HIGH_REREVIEW_USED = YES
TARGETED_REREVIEW_HIGH_COUNT = 1

FURTHER_REPAIR_AUTHORIZED = NO
FURTHER_REREVIEW_AUTHORIZED = NO

PR245_MERGE_AUTHORIZED = NO
SCIENTIFIC_EXECUTION_AUTHORIZED = NO

FINAL_DISPOSITION = CLOSED_BLOCKED
```

No implementation source from PR #245 becomes canonical. The failed
implementation stays non-canonical source evidence reachable through Git/PR
history only. This record is durable bookkeeping evidence; it does not mark the
findings resolved and creates no scientific, real-data, provider, claim, or
downstream authority.
