# Targeted re-review closure - PINNED_DSH_CODEX_WRITE_PATH_MATERIALIZATION_V0

PHASE = PINNED_DSH_CODEX_WRITE_PATH_MATERIALIZATION_V0
TARGET_SHA = e07ba32812722fdd50702be33dbd1ed6a2c62aa6
PRELIVE_SHA = 9e21d19ba230aafca7f0a6e554e5b23fb5184e97
REVIEW_INDEPENDENCE = YES
LIVE_PRODUCT_CALLS = 0

## Historical observation preserved

LIVE_ATTEMPTS_OBSERVED = 1
DSH_PROVIDER_ENTERED_RECORDED = YES
CODEX_CHILD_SPAWNED_RECORDED = YES
TURN_TERMINAL_OBSERVED = YES
STOP_REASON = error
TIMED_OUT = NO
CHANGED_PATHS = []
FIXTURE_TARGET_MATCH = NO

OBSERVED_RESULT = PINNED_DSH_CODEX_WRITE_PATH_FAIL
CLOSURE_AUTHORITY_OF_D4_RESULT = NO
CLOSURE_VERDICT = CLOSED_BLOCKED_BY_EVIDENCE_INTEGRITY

The historical live observation remains preserved and immutable. This closure
does not establish fabrication, a DSH pass, a fully verified exact-byte DSH
failure, or an exact root cause.

## Authoritative targeted re-review result

C1_RUNTIME_ARTIFACT_BINDING = FAIL
H1_MATERIALIZATION_EVIDENCE = FAIL
H2_RECEIPT_INTEGRITY = FAIL
H3_SINGLE_EPISODE = FAIL
H4_TIMEOUT_CLASSIFICATION = PASS
H5_UNPARSEABLE_DRIVER_OUTPUT = FAIL
H6_PROCESS_GROUP_TERMINATION = PASS
H7_EFFECTIVE_CONFIG_OBSERVABILITY = PASS

OPEN_CRITICAL = 1
OPEN_HIGH = 4

TARGETED_REREVIEW = FAIL
PR136_TARGETED_REREVIEW = FAIL
PHASE_CLOSURE_GATE = UNSATISFIED

## Findings

### C1 - CRITICAL

The generated DSH runtime artifacts were not rebound immediately before live
execution.

The runner hashed artifacts during initial observation only. No final rehash
occurred immediately before the live call. Replacement/TOCTOU and symlink
retargeting therefore remained possible.

This means the phase cannot establish that the exact previously-attested
gitignored generated DSH runtime bytes were the bytes actually executed.

### H1 - HIGH

The runner records the materialization-record lockfile digest but does not
validate that recorded digest as part of the authoritative materialization
evidence.

A stale/mismatched materialization record can therefore still report install
and build success under some conditions.

### H2 - HIGH

receipt_integrity accepts bridgeExitCode=None, and malformed lifecycle entries
can be ignored.

Deterministic attacks produced PASS for malformed cases.

### H3 - HIGH

The single-episode guard checks an existing d4_receipt.json but does not treat
a pre-existing d4_attempts.jsonl episode as permanently consumed.

A crash after the pre-call append but before receipt creation could therefore
permit another live invocation.

### H5 - HIGH

The runner accepts unrelated JSON as a receipt.

Deterministic classification produced a product-level FAIL with
target_mechanism_exercised=true despite absence of the real D4 route marker.

## Closure state

EXECUTION_STATE = CONSUMED
LIVE_EPISODE = PRESERVED_IMMUTABLE
TARGETED_REREVIEW = FAIL
OPEN_CRITICAL = 1
OPEN_HIGH = 4
CLOSURE_STATUS = CLOSED_BLOCKED_BY_EVIDENCE_INTEGRITY
D4_V0_RERUN_AUTHORITY = NO
NEXT_PHASE_AUTHORITY = NONE
V0R1_CREATED = NO
V0R1_AUTHORIZED = NO
V2_CREATED = NO
V2_AUTHORIZED = NO

No D4 retry, D0-D3 retry, Stage-A V1 run, V0R1 creation, V2 creation, repair,
merge, or retargeting was performed by this closure.
