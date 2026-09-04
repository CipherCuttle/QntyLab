# Implementation Hostile Review Receipt — FUNDING_INCREMENTAL_CONTRACT_INTEGRITY_HARDENING_IMPLEMENTATION_V0

- REVIEW_TYPE = INDEPENDENT_HOSTILE_REVIEW
- REVIEWED_COMMIT = a6200d3e3d1ae2cffc44cca1d1db5d626239452c
- GITHUB_REVIEW_ID = PRR_kwDOTo27Xs8AAAABMQI3yw
- REVIEW_COUNT = 1
- CRITICAL = 0
- HIGH = 4
- MEDIUM = 0
- LOW = 0
- H1 thread = PRRT_kwDOTo27Xs6fbIjW
- H2 thread = PRRT_kwDOTo27Xs6fbIjc
- H3 thread = PRRT_kwDOTo27Xs6fbIjd
- H4 thread = PRRT_kwDOTo27Xs6fbIjh
- VERDICT = REPAIR_REQUIRED
- TARGETED_REREVIEW_REQUIRED = YES

## Common root cause

Self-attestation must not become verified authority or verified provenance:
no arrow may run backward from a caller assertion to verified state.

## Finding summaries (faithful, concise)

### H1 — Forgeable authorization token (thread PRRT_kwDOTo27Xs6fbIjW; HIGH)

`OfflineAuthorizationToken` can be directly instantiated with attacker-controlled
values, and the hardened boundary's admission step treats
`isinstance(token, OfflineAuthorizationToken)` as proof of authority. Class
identity plus caller-supplied token fields are self-attestation, not
authentication; a forged in-memory object therefore passes the authorization
stage. Required: authority must be independently authenticated at the point
execution is admitted (canonical Git-backed CI-3 model); the token must be
demoted to a descriptive receipt that the boundary independently re-verifies
against canonical Git before any claim/row/core activity.

### H2 — Caller-selected Git is not canonical authority (thread PRRT_kwDOTo27Xs6fbIjc; HIGH)

The boundary's authorization verifier accepts a caller-supplied repository,
commit, artifact path, and expected digest; an attacker can therefore create a
throwaway repository, commit a self-consistent authorization blob, and supply
the matching SHA/path/digest to satisfy it. The requester must never choose the
trust root: the canonical repository identity, canonical authorization
artifact/path, canonical Git ancestry/commit constraints, expected artifact
digest, and governing decision identity must be fixed by reviewed canonical
state (existing CI-3 pattern of
`qntylab/jigsaw_funding_pressure_incremental_forecast_value_evaluation_authorization_provenance_v1.py`).
The canonical/offline positive control must still work without network access.

### H3 — Synthetic provenance must come from fixture evidence (thread PRRT_kwDOTo27Xs6fbIjd; HIGH)

`make_offline_synthetic_fixture_receipt` accepts arbitrary `ForecastRow`
values plus an arbitrary caller-named `fixture_identity` and elevates them to
`OFFLINE_SYNTHETIC_FIXTURE` verified provenance. Hashing the rows after
labeling them is not proof of synthetic origin — it is provenance laundering
(CI-23 class). Required: no constructor that promotes arbitrary pre-existing
rows; synthetic provenance must be issued only from authenticated fixture
bytes validated against a separately pinned fixture identity/contract
(bytes digest, schema, resulting row content digest), with hostile coverage
for all mismatch directions.

### H4 — Git anchor must bind the actual rows (thread PRRT_kwDOTo27Xs6fbIjh; HIGH)

The `GIT_ANCHORED` receipt authenticates blob A (bytes digest at a pinned
commit) and separately hashes the caller-presented rows B, without ever
establishing that A binds B. Blob A and rows B are unrelated facts joined by a
Python receipt. Required: the authenticated artifact must itself contain the
row/content digest (plus schema/version, provenance kind, batch/factory
identity) and the boundary must require exact equality between the digest
authenticated inside the artifact bytes and the digest computed from the
presented rows; merely storing both digests in one receipt is insufficient.

## Disposition

- VERDICT = REPAIR_REQUIRED (4 High).
- Findings are NOT marked resolved merely because code has changed; resolution
  is decided by the one targeted Critical/High re-review.
- TARGETED_REREVIEW_REQUIRED = YES; exactly one targeted re-review is permitted
  by the governing decision's review lifecycle.
