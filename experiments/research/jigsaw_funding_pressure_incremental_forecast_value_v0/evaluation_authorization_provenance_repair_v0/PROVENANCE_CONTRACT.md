# Funding real-capable wrapper — evaluation-authorization provenance contract

Phase: `FUNDING_INCREMENTAL_EXECUTOR_EVALUATION_PROVENANCE_REPAIR_V0`

## Why

PR #233's hostile review (finding **M-1**) established that the REAL_CAPABLE
wrapper's step 1 accepted a caller-supplied `authorization_path` and validated
only JSON field *values*. Nothing bound those bytes to canonical QntyLab Git
provenance, so a caller could point step 1 at an arbitrary local JSON file.

PR #238's targeted re-review then found a **P1** in the first repair: it
resolved from `HEAD:<path>` and only required the historical anchors to be
ancestors of `HEAD` plus a canonical-looking `origin` URL. A local clone that
already contains the old anchors could forge a descendant commit, set `origin`
to the expected URL, add an authorization artifact, and pass. The root of
trust was effectively `HEAD`.

This phase repairs only that provenance boundary. It creates **no** evaluation
authorization and grants **no** scientific-execution authority.

## Repaired boundary

`qntylab/jigsaw_funding_pressure_incremental_forecast_value_evaluation_authorization_provenance_v1.py`
authenticates the authorization to canonical Git identity before the wrapper
may use it. The authorization document is **only ever read from the Git object
database** at an **explicitly pinned immutable commit**
(`EXPECTED_CANONICAL_AUTHORIZATION_COMMIT:<fixed path>`), never from caller
bytes, `HEAD`, a descendant of the historical anchors, a different branch or
tree, or a worktree-local file.

A request is accepted only when **all** of the following hold:

| Bound to | Mechanism |
|---|---|
| **Pinned resolution commit** (root of trust) | `EXPECTED_CANONICAL_AUTHORIZATION_COMMIT` is a full 40-hex commit id; the object is present and resolves (`git cat-file -t` == `commit`, `git rev-parse --verify …^{commit}`); it is the current checkout **or** an ancestor of it (`git merge-base --is-ancestor <pinned> HEAD`) |
| Canonical bytes | read from `<pinned commit>:<canonical path>` via `git ls-tree` + `git cat-file blob` — an immutable Git object |
| Repository identity (defence-in-depth) | both immutable anchor commits are ancestors of the **pinned commit** |
| Repository locator (contextual only, **not** the root of trust) | `remote.origin.url` canonicalises to `github.com/CipherCuttle/QntyLab` |
| Artifact path | fixed constant `CANONICAL_EVALUATION_AUTHORIZATION_RELATIVE_PATH`; a caller `authorization_path` must `realpath`-resolve to exactly that tracked path and can never select the resolution commit |
| Blob / tree | the pinned tree entry is a **blob**, mode is not `120000` (symlink); when the checkout is exactly at the pinned commit the on-disk copy must match it |
| Content digest | `sha256(blob bytes)` must equal `EXPECTED_CANONICAL_AUTHORIZATION_SHA256`, a reviewed source constant (a file cannot carry its own hash) |
| Preregistration | `governing_preregistration_digest == d7ec718…992ef` |
| Wrapper identity | `real_capable_wrapper_project_id == JIGSAW_FUNDING_PRESSURE_INCREMENTAL_FORECAST_VALUE_REAL_CAPABLE_WRAPPER_V1` |
| Self-attested binding (defence-in-depth) | `canonical_git_binding.{repository, artifact_path, preregistration_anchor_commit, historical_v0_oracle_anchor_commit}` must match the canonical constants |

### Immutable anchor commits

- `d2f1839c286ec0407eefd02d878a1b16572bd902` — funding-incremental preregistration commit
- `f6f12994d65c3dfeaf7839de560e58ad99547c62` — historical V0 executor oracle commit

An unrelated repository does not contain these object IDs; they are retained as
a lineage check against the pinned commit, not as the sole root of trust.

## Rejections (all fail closed with `UnauthorizedExecutionError`)

no pinned commit · a forged/divergent local descendant commit · a valid-looking
artifact on a different commit · an artifact present only in a non-pinned
commit · a wrong pinned commit · a missing pinned commit · a malformed pinned
commit constant · a pinned commit that is not the checkout and not an ancestor
of it · caller-supplied path substitution · a caller attempt to pass the
resolution commit · valid-looking JSON at the wrong path · changed blob bytes
(pinned digest mismatch) · wrong repository identity (non-canonical remote or
anchors not ancestors of the pinned commit) · symlink / `..` traversal on
`authorization_path` · canonical path committed as a symlink · worktree-local
replacement of the canonical file · missing canonical artifact · malformed
authorization · mismatched preregistration or wrapper identity · mismatched or
absent `canonical_git_binding`.

## Permanent fail-closed state at this phase

`EXPECTED_CANONICAL_AUTHORIZATION_COMMIT is None` **and**
`EXPECTED_CANONICAL_AUTHORIZATION_SHA256 is None`, and no canonical artifact
exists. Any one of these facts alone makes every call to
`authenticate_canonical_evaluation_authorization` raise. All hold today.
`HEAD` may legitimately advance beyond the pinned commit later; the pinned
blob remains the authenticated source.

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
