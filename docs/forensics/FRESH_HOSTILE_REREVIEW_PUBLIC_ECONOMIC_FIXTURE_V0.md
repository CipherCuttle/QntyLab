# Executive Verdict

Primary verdict: `FRESH_HOSTILE_REREVIEW_PASS_WITH_MINOR_REDUCTIONS`

Integration gate: `READY_TO_PREPARE_DEDICATED_INTEGRATION_BRANCH`

The correctness repair closes the original blocker and the decimal/CLI correctness findings. Remaining issues are non-blocking: unexpected non-forbidden fixture keys are still accepted, and the V0 architecture can be reduced later.

# Scope

Task: `FRESH_HOSTILE_REREVIEW_PUBLIC_ECONOMIC_FIXTURE_V0`

Lane: `ADMIN_LANE`. QNTY source, tests, fixtures, and docs were not modified. Temporary hostile tooling was confined to `/home/swirky/.cache/agent-tmp/codex/fresh-hostile-rereview-public-economic-fixture-v0`. No protocol handoff receipt was created.

# Repository Identity

QNTY: `chore/external-trust-root-dispatcher-repair-v046` at `45bda3eb037d34d324433c5da867d466386c00ba`.

QntyLab: `master` starting at `7f65d858074846697586d12449606540922fcdb3`.

# Commit Chain

Verified chain: `8ebe61bdecd2d72239cf8d0618df87d6e1171c5a -> 432d5326a7e0d63c704b170cf663d74929257df5 -> 45bda3eb037d34d324433c5da867d466386c00ba`.

# Prior Review

Prior review commit `7f65d858074846697586d12449606540922fcdb3` is reachable and contains both prior report files. Actual prior finding counts: `BLOCKER=1`, `MAJOR=2`, `MINOR=3`, `OBSERVATION=0`.

# Repair Diff

Changed paths are limited to `quantbot/paper/public_funding_economic_fixture.py`, `tests/test_public_funding_economic_fixture_v0.py`, and `docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_REPAIR.md`.

Repair delta: `592` insertions, `60` deletions. Module grew by `68` lines to `899`; tests grew by `238` lines to `523`; repair documentation adds `226` lines. Total two-commit addition versus parent is `1,863` lines.

No hidden changes to paper engine, SQLite schemas, strategy code, network code, candidate/trial/decision state, fixture input, expected receipt, or QntyLab were found.

# Prior-Finding Dispositions

| Finding | Prior severity | Status | Evidence |
| --- | --- | --- | --- |
| F-001 | BLOCKER | CLOSED | Original accepts `source_hashes_verified=false`; repaired HEAD rejects with `VERIFICATION_METADATA_MISMATCH`. |
| F-002 | MAJOR | CLOSED | Decimal aliases/exponents/non-finite/overlength inputs now fail typed; source trailing zeros remain allowed. |
| F-003 | MAJOR | STILL_OPEN | Current branch is still semantically wrong, but the two commits are self-contained and cherry-pickable. |
| F-004 | MINOR | CLOSED | Snapshot is now regression-only because independent arithmetic, identity, and verification oracles are present. |
| F-005 | MINOR | CLOSED | Bad decimal CLI input returns concise typed JSON error with no traceback. |
| F-006 | MINOR | STILL_OPEN | Unexpected non-forbidden fixture fields remain accepted. |

# Original Blocker Reproduction

`ORIGINAL_BLOCKER_REPRODUCED`: true.

`REPAIR_BLOCKER_CLOSED`: true.

# Verification-Metadata Attack

Classification: `VERIFICATION_METADATA_REPAIR_CONFIRMED`.

The current tamper matrix generated `25` verification metadata mutations. All were rejected with `VERIFICATION_METADATA_MISMATCH`.

# Decimal Lexical Policy

Classification: `DECIMAL_POLICY_SOUND_AND_ENFORCED`.

Accepted synthetic examples: `4`. Rejected synthetic/boundary invalid cases: `20`. Source decimal cases accepted: `4`; rejected: `8`. Raw Decimal exceptions did not escape.

# Decimal Identity

Classification: `IDENTITY_POLICY_SOUND`.

Receipt identity stayed `3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b`. Canonical receipt SHA-256 stayed `d7a8827d8054ac2a843baf25dcc9dd547f4235ef10571e30d43cb69ef20b294f`. Global Decimal context remained unchanged.

# Independent Arithmetic Oracle

Classification: `FRESH_HOSTILE_ARITHMETIC_ORACLE_PASS`.

Long notional `73.65356663043`, long transfer `-0.0042004629049334229`.

Short notional `73.65356663043`, short transfer `0.0042004629049334229`.

Zero transfer `0`.

# Independent Identity Oracle

Classification: `INDEPENDENT_IDENTITY_ORACLE_PASS`.

Independent receipt ID: `3833f2fb83a0c59031236cf5bb29b2de0ad2122765f03074f219a2c24bf5bd9b`. Mutating each independently constructed identity field changed the digest; receipt-only load-bearing mutations were rejected by `verify_receipt()`.

# Test-Oracle Independence

Current fixture test-quality counts: `INDEPENDENT_CORRECTNESS_ORACLE=3`, `MEANINGFUL_INVARIANT=35`, `MEANINGFUL_REGRESSION=12`, `SNAPSHOT_ONLY=1`, `IMPLEMENTATION_MIRROR=2`, `TRIVIAL_ASSERTION=0`.

# Expected-Receipt Circularity

Classification: `CIRCULARITY_RESOLVED_TO_REGRESSION_ONLY`.

The committed snapshot remains useful regression evidence but no longer carries correctness alone.

# CLI Review

Two good CLI runs returned `0`, produced identical stdout bytes, stable empty stderr, and no file mutation. A malformed decimal fixture returned `1` with reason `QUANTITY_INVALID`, no traceback.

# Failure-State Review

Reason count: `21`. Reachability counts: `{'DIRECTLY_REACHABLE_AND_TESTED': 18, 'DIRECTLY_REACHABLE_NOT_TESTED': 3}`. New reason `VERIFICATION_METADATA_MISMATCH` exists and is directly reached.

# Scope and Non-Claims

Classification: `SCOPE_HONEST`.

Claim scope remains bounded, account posting is `NOT_APPLICABLE`, and candidate/trial/decision registration remains forbidden. No profitability, alpha, production readiness, real account, real wallet, real position, or real trade claim was introduced.

# Architecture and Overbuild

Recommendation: `KEEP_WITH_SMALL_REDUCTION_LATER`.

Load-bearing: `reconstruct_transfer`, `verify_source_artifacts`, `verify_receipt`, `_expected_verification_metadata`, `_parse_plain_decimal`, `_identity_payload`.

Useful but nonessential: CLI, batch verification, broad failure enum. Redundant: `_decimal_from_string`.

# Branch and Integration

Classification: `TWO_COMMIT_SERIES_SELF_CONTAINED_WRONG_BRANCH`.

Do not merge the current branch wholesale. Prepare a dedicated branch later and cherry-pick `432d5326a7e0d63c704b170cf663d74929257df5` then `45bda3eb037d34d324433c5da867d466386c00ba`.

# Test Results

| Command | RC | Passed | Failed | Skipped | Duration | What it proves | What it does not prove |
| --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `env -u TMPDIR .venv/bin/python -m pytest tests/test_public_funding_economic_fixture_v0.py -q` | 0 | 53 | 0 | 0 | 0.288s | Focused fixture behavior and oracles pass. | Full suite or live correctness. |
| `env -u TMPDIR .venv/bin/python -m pytest tests/test_paper_pnl.py ... tests/test_receipt_schema.py -q` | 0 | 413 | 0 | 0 | 19.117s | Selected offline regression slice passes. | Full suite or live correctness. |
| `env -u TMPDIR .venv/bin/python -m compileall quantbot/paper/public_funding_economic_fixture.py` | 0 | 1 | 0 | 0 | 0.036s | Module compiles. | Runtime correctness beyond syntax. |
| `env -u TMPDIR .venv/bin/python -m pytest -q` | 1 | 7625 | 1 | 1 | 135.586s | Full suite has one unrelated control failure. | That the reviewed fixture failed. |

Full-suite failure: `tests/control/test_no_self_hash_source_binding.py::test_no_new_self_hash_source_binding_in_repo`, for an unrelated continuity pinned-hash allowlist issue.

# Findings

`R-F-001` | `MINOR` | Unexpected non-forbidden fixture fields remain accepted | `quantbot/paper/public_funding_economic_fixture.py:155`

Evidence: `parse_fixture()` loads JSON and rejects only forbidden scope fields before reading known keys; no exact top-level fixture schema check exists.

Why it matters: future fixture extensions can be silently ignored.

Minimal remediation: reject unknown top-level fixture keys or document extension-tolerant parsing.

Blocks integration: no.

`R-F-002` | `OBSERVATION` | Batch verifier and broad enum remain more architecture than V0 needs | `quantbot/paper/public_funding_economic_fixture.py:377`

Evidence: `verify_receipt_batch()` and several non-core reason paths are useful but not necessary for the single pinned V0 fixture.

Why it matters: later maintenance can be simpler if nonessential surfaces are reduced after integration.

Minimal remediation: defer a small cleanup pass.

Blocks integration: no.

# Minimum Remediation

No correctness remediation is required before preparing the dedicated integration branch. Optional later reductions: decide whether unexpected fixture keys should be rejected, and trim or split nonessential batch/enum surfaces.

# Integration Gate

`READY_TO_PREPARE_DEDICATED_INTEGRATION_BRANCH`

# Verification

Report validation result: `FRESH_HOSTILE_REREVIEW_REPORT_VALIDATION_PASS` after local validator execution.

# Final Verdict

`FRESH_HOSTILE_REREVIEW_PASS_WITH_MINOR_REDUCTIONS`

# Immediate Next Action

`PREPARE_DEDICATED_INTEGRATION_BRANCH_AND_CHERRY_PICK_V0`
