# Funding real-capable wrapper — evaluation-authorization provenance contract

Phase: `FUNDING_INCREMENTAL_EXECUTOR_EVALUATION_PROVENANCE_REPAIR_V0`

## Why

PR #233's hostile review (finding **M-1**) established that the REAL_CAPABLE
wrapper's step 1 accepted a caller-supplied `authorization_path` and validated
only JSON field *values*. Nothing bound those bytes to canonical QntyLab Git
provenance, so a caller could point step 1 at an arbitrary local JSON file.

This phase repairs only that provenance boundary. It creates **no** evaluation
authorization and grants **no** scientific-execution authority.

## Repaired boundary

`qntylab/jigsaw_funding_pressure_incremental_forecast_value_evaluation_authorization_provenance_v1.py`
authenticates the authorization to canonical Git identity before the wrapper
may use it. The authorization document is **only ever read from the Git object
database** (`git cat-file blob`), never from caller-supplied bytes.

A request is accepted only when **all** of the following hold:

| Bound to | Mechanism |
|---|---|
| Repository identity | `remote.origin.url` canonicalises to `github.com/CipherCuttle/QntyLab` **and** both immutable anchor commits are ancestors of `HEAD` |
| Canonical commit | bytes come from `HEAD^{commit}:<canonical path>` (an immutable Git object) |
| Artifact path | fixed constant `CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH`; a caller `authorization_path` must `realpath`-resolve to exactly that tracked path |
| Blob / tree | `git rev-parse --verify` resolves the path to a **blob**; the path is tracked at `HEAD`; the canonical path is not a symlink |
| Content digest | `sha256(blob bytes)` must equal `EXPECTED_CANONICAL_AUTHORIZATION_SHA256`, a reviewed source constant (a file cannot carry its own hash) |
| Preregistration | `governing_preregistration_digest == d7ec718…992ef` |
| Wrapper identity | `real_capable_wrapper_project_id == JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_REAL_CAPABLE_WRAPPER_V1` |
| Self-attested binding | `canonical_git_binding.{repository, artifact_path, preregistration_anchor_commit, historical_v0_oracle_anchor_commit}` must match the canonical constants |

### Immutable anchor commits

- `d2f1839c286ec0407eefd02d878a1b16572bd902` — funding-incremental preregistration commit
- `f6f12994d65c3dfeaf7839de560e58ad99547c62` — historical V0 executor oracle commit

An unrelated repository does not contain these object IDs, so the ancestry
proof is also the repository-identity proof — deterministic and offline.

## Rejections (all fail closed with `UnauthorizedExecutionError`)

caller-supplied path substitution · valid-looking JSON at the wrong path ·
valid-looking JSON only in a non-`HEAD` commit · changed blob bytes (pinned
digest mismatch) · wrong repository identity (non-canonical remote or missing
anchors) · symlink / `..` traversal on `authorization_path` · canonical path
committed as a symlink · worktree-local replacement of the canonical file ·
missing canonical artifact · malformed authorization · mismatched
preregistration or wrapper identity · mismatched or absent
`canonical_git_binding`.

## Permanent fail-closed state at this phase

`EXPECTED_CANONICAL_AUTHORIZATION_SHA256 is None` and the canonical artifact
does not exist in canonical history. Either fact alone makes every call to
`authenticate_canonical_evaluation_authorization` raise. Both hold today.

State assertions (unchanged by this phase):

```
implementation_authorized        = false
scientific_execution_authorized  = false
evaluation_origins_consumed      = 0
real_outcome_access              = false
claim_consumed                   = false
downstream_authority             = NONE
```

## Tests

`tests/test_funding_incremental_evaluation_authorization_provenance_v0.py` —
adversarial coverage of every rejection above, a disposable-clone positive
control proving the verifier is not vacuously failing, and proof that
provenance failure precedes claim consumption, frozen-evidence access, real
`ForecastRow` construction, shared-core invocation, and result recording.
