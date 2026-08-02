# Executive Verdict

Primary verdict: INDEPENDENT_REVIEW_REQUIRES_CORRECTNESS_REPAIR. Integration gate: NOT_READY_FOR_INTEGRATION. The source chain and arithmetic are valid, but two blockers remain in receipt verification/identity.

# Scope

ADMIN_LANE read-only hostile review of commit 432d5326 only; no QNTY implementation or tests were modified, and no QntyLab candidate/trial/decision was registered.

# Repository Identity

QNTY chore/external-trust-root-dispatcher-repair-v046 at 432d5326a7e0d63c704b170cf663d74929257df5. QntyLab master started at 5ba89e5c5f320391ee9321b1929bb079be590aa8 and was at 5ba89e5c5f320391ee9321b1929bb079be590aa8 when reports were written.

# Commit Isolation

SELF_CONTAINED_BUT_WRONG_BRANCH. Parent is exactly 8ebe61bdecd2d72239cf8d0618df87d6e1171c5a; the commit adds only five expected files and imports helpers that existed at the parent. Use a dedicated branch/cherry-pick after repair.

# Source and Contract Chain

SOURCE_CONTRACT_CHAIN_VALID. Contract/source hashes match; raw JSON parses with 90 rows; selected index is 0; selected fields match raw row and expected BTCUSDT event; numeric source fields remain strings; source receipt and contract bind expected hashes.

# Exact Diff

Five added paths, 1331 insertions: implementation module, input fixture, expected receipt, test file, and implementation receipt. No binaries, network calls, SQLite writes, paper-engine edits, strategy code, or candidate/trial/decision changes found.

# Line-Count Decomposition

Inserted lines: module 831, tests 285, input fixture 51, expected receipt 1, documentation 163. Module profile: 85 blank, 7 docstring, 739 executable/content lines. Estimated responsible minimum: about 450-550 inserted lines after removing/deferring batch framework and tightening schema/identity paths.

# Independent Arithmetic Oracle

HOSTILE_PUBLIC_ECONOMIC_FIXTURE_ORACLE_PASS. Long transfer -0.0042004629049334229; short transfer 0.0042004629049334229; zero transfer 0. Expected receipt canonical SHA-256 d7a8827d8054ac2a843baf25dcc9dd547f4235ef10571e30d43cb69ef20b294f.

# Formula and Dimensions

FORMULA_CONFIRMED. Quantity is BTC, mark price is USDT/BTC, multiplier is 1, rate is dimensionless, transfer is USDT. Positive funding makes long pay and short receive; a negative synthetic rate reverses direction.

# Decimal and Canonicalization

DECIMAL_IDENTITY_MALLEABLE. Binary float, NaN, and Infinity are rejected and Decimal context is local, but exponent, leading-plus, leading whitespace, and trailing zeros are accepted and can create distinct receipt IDs for equivalent values.

# Expected-Receipt Circularity

PARTIAL_SNAPSHOT_CIRCULARITY. Hard-coded arithmetic values exist, but expected_receipt.json comparison is snapshot regression against the same implementation canonicalization and does not independently establish receipt identity correctness.

# Provenance

LIVE_CROSS_REPOSITORY_SOURCE_VERIFICATION for normal parsing with verify_source=True: the module opens QntyLab artifacts and verifies hashes. The QNTY fixture also works as a self-contained pinned vector when source verification is disabled, so claims should preserve that distinction.

# Receipt Identity

IDENTITY_MALLEABLE. The committed vector identity includes core source/economic fields, but decimal aliases bypass semantic duplicate identity, source_receipt_sha256 is present in receipt but omitted from receipt_id, and verification metadata is not fully checked.

# Tamper Resistance

FAILS_VERIFICATION_METADATA_TAMPER. Notional, transfer, direction, status, non-claims, evidence level, precision status, owner, and research policy mutations are rejected. Mutating verification.source_hashes_verified to false was accepted.

# Failure-State Reachability

20 reason codes reported. 18 directly reached in probe, 2 directly reachable but not covered by that probe (SOURCE_HASH_MISMATCH and SOURCE_EVENT_NOT_FOUND), 0 unreachable found. Some reason mapping is generic for receipt field mismatches.

# Idempotency

IDENTITY_ALIAS_BYPASS. Byte-identical duplicate receipts are rejected deterministically, but semantically equivalent decimal aliases can produce different receipt IDs. No persistent exactly-once or SQLite idempotency claim is made.

# CLI Review

Successful CLI runs returned rc=0 twice with identical stdout bytes and empty stderr. Missing and malformed fixtures return rc=1 with Python tracebacks; unexpected extra fixture fields are accepted when an expected receipt path is supplied. CLI proves committed vector/source/expected matching, not fresh Binance re-verification.

# Test-Quality Review

Counts: INDEPENDENT_CORRECTNESS_ORACLE 0, MEANINGFUL_INVARIANT 14, MEANINGFUL_REGRESSION 7, SNAPSHOT_ONLY 1, IMPLEMENTATION_MIRROR 4, TRIVIAL_ASSERTION 0, UNREACHABLE_SETUP 0. Missing hostile cases include decimal aliases and verification metadata tamper.

# Regression Results

New tests: 26 passed in 0.14s. Focused regression: 413 passed in 46.29s. compileall passed. ruff and mypy were unavailable; no dependencies were installed. Full offline suite was not run.

# Static Review

Import check passed. No network/database/write paths in production module were found. CLI concerns are mixed into the arithmetic module but remain bounded. json.loads does not detect duplicate keys; file reads are unbounded but acceptable for the pinned offline fixture.

# Scope and Non-Claims

SCOPE_HONEST. Required non-claims are present and adjacent enough to bounded PROVEN_FOR_PINNED_FIXTURE language in the receipt/CLI output. No profit/alpha/strategy authorization fields are emitted.

# Architecture and Overbuild

REQUIRES_CORRECTNESS_REPAIR. Keep additive Decimal/source/receipt core, but repair verification metadata and decimal lexical identity before integration. Batch verification, large reason enum, and CLI are useful but nonessential for V0.

# Security Boundary

Offline fixture risk only. Path traversal is partially constrained by rejecting absolute artifact paths but not ../ segments. Tracebacks disclose absolute paths on CLI failures. Duplicate JSON keys and Unicode-confusable keys are future hardening items.

# Findings

- F-001 BLOCKER Receipt verifier accepts tampered verification metadata (/home/swirky/DevHub/repos/Qnty/quantbot/paper/public_funding_economic_fixture.py:371): Mutation of verification.source_hashes_verified to false was accepted by verify_receipt; lines 371-387 only require verification to be a mapping and check claim_scope and claim_verdict. Minimal remediation: Require verification to exactly equal the expected verification block, or remove mutable verification booleans from the receipt and output them only as verifier return data. Blocks integration: True
- F-002 BLOCKER Decimal syntax aliases produce distinct receipt identities for equivalent quantities (/home/swirky/DevHub/repos/Qnty/quantbot/paper/public_funding_economic_fixture.py:649): Decimal("0.001"), Decimal("1E-3"), Decimal("+0.001"), and Decimal(" 0.001") are accepted; identity binds the raw string at line 641, producing different receipt_id values for the same economic quantity. Minimal remediation: Define and enforce a decimal lexical grammar for V0 source and quantity strings, or canonicalize decimal representation before identity and duplicate checks. Reject leading plus, surrounding whitespace, and exponent notation if the contract intends fixed decimal strings. Blocks integration: True
- F-003 MAJOR Correctness tests are partially snapshot-circular (/home/swirky/DevHub/repos/Qnty/tests/test_public_funding_economic_fixture_v0.py:261): test_committed_fixture_matches_committed_expected_receipt compares implementation output to expected_receipt.json using the same module canonicalization. It is useful regression coverage but not an independent oracle. Minimal remediation: Add a small independent test oracle for arithmetic and identity payload bytes, or mark expected_receipt.json as snapshot-only regression coverage. Blocks integration: False
- F-004 MINOR Fixture parser accepts unexpected extra fields (/home/swirky/DevHub/repos/Qnty/quantbot/paper/public_funding_economic_fixture.py:151): A fixture containing unexpected_extra_field was accepted when the expected receipt path was provided. parse_fixture reads expected keys and only rejects a small forbidden-field set. Minimal remediation: Reject unknown top-level fixture keys and unknown receipt keys, or document permissive-ignore behavior as non-load-bearing. Blocks integration: False
- F-005 MINOR Batch duplicate verifier is nonessential V0 framework code (/home/swirky/DevHub/repos/Qnty/quantbot/paper/public_funding_economic_fixture.py:390): verify_receipt_batch provides in-memory duplicate detection for supplied receipts only; the fixture makes no persistent exactly-once claim and does not integrate with a ledger. Minimal remediation: Remove batch verification from V0 or keep it explicitly labeled as optional regression utility after decimal identity is repaired. Blocks integration: False

# Minimum Remediation

1. Make verification metadata exact or remove it from receipt identity surface. 2. Enforce a V0 decimal lexical grammar or canonicalize before identity and duplicate checks. 3. Add hostile tests for both repairs. 4. Optionally reject unknown keys and remove/label batch verification as nonessential.

# Integration Gate

NOT_READY_FOR_INTEGRATION because blockers remain. Wrong-branch state alone would permit cherry-pick to a dedicated branch, but not until correctness repair is complete.

# Verification

Temporary tooling: /tmp/independent-public-economic-fixture-review-v0/hostile_review_probe.py and final_oracle.py. Final oracle printed HOSTILE_PUBLIC_ECONOMIC_FIXTURE_ORACLE_PASS.

# Final Verdict

INDEPENDENT_REVIEW_REQUIRES_CORRECTNESS_REPAIR.

# Immediate Next Action

Repair F-001 and F-002 in QNTY, regenerate expected receipt only after the policy is fixed, and rerun independent hostile review before integration.
