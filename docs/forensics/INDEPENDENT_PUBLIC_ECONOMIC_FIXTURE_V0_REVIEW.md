# Executive Verdict

Primary verdict: `INDEPENDENT_REVIEW_REQUIRES_CORRECTNESS_REPAIR`

Integration gate: `NOT_READY_FOR_INTEGRATION`

The arithmetic and public source chain for the pinned BTCUSDT funding event are independently confirmed. The implementation is not integration-ready because `verify_receipt()` accepts tampered verification metadata (`source_hashes_verified=false`) while still returning a passing claim verdict.

# Scope

Task: `INDEPENDENTLY_REVIEW_PUBLIC_ECONOMIC_FIXTURE_V0`

Lane: `ADMIN_LANE`. No protocol handoff receipt was created. No QNTY implementation or test files were modified. Review tooling was created only under `/tmp/independent-public-economic-fixture-review-v0/`.

# Repository Identity

QNTY root: `/home/swirky/DevHub/repos/Qnty`

QNTY branch: `chore/external-trust-root-dispatcher-repair-v046`

QNTY HEAD: `432d5326a7e0d63c704b170cf663d74929257df5`

Implementation parent: `8ebe61bdecd2d72239cf8d0618df87d6e1171c5a`

QntyLab root: `/home/swirky/DevHub/repos/QntyLab`

QntyLab branch: `master`

QntyLab observed starting HEAD: `0a07aa950ef31c71516cfd7a26dd9bc471102687`

Expected QntyLab HEAD in the task text was `5ba89e5c5f320391ee9321b1929bb079be590aa8`; the checkout did not match that expected baseline.

# Commit Isolation

Classification: `SELF_CONTAINED_BUT_WRONG_BRANCH`

Commit `432d5326` is exactly one parent after `8ebe61b` and adds only the five expected fixture files. The parent is not an ancestor of `main`; merging the whole repair branch would bring unrelated continuity and research-runner work. Main already contains the reused `quantbot.core.determinism` helpers, so the fixture commit appears cherry-pickable onto a dedicated branch.

# Source and Contract Chain

Classification: `SOURCE_CONTRACT_CHAIN_VALID`

Verified hashes:

| Artifact | SHA-256 |
| --- | --- |
| contract Markdown | `fd60173f71c9a7180ce0ce5c31023ae4b63ea6c8df6259620cc5646b8e6f347d` |
| contract JSON | `b6c9ad8f3b21c983952820c6bb05d4ca6e8a8695cc3b5b57db34413e7391b5c3` |
| raw REST response | `01d38d5b8c8581388621015a2bc618673cac1ff51ff88672aea52f9bdb31bafd` |
| selected event | `fcc0682d5a30976d860fbbefaf415b0e0c0d0585835a4a8ef089acd9c5376b59` |
| source receipt | `456e7918e3d9c7caeee67a8bde729867cbe0143f2002e7496ef5234382278c1c` |

Selected event: `BTCUSDT`, `fundingTime=1780272000001`, `fundingTimeUtc=2026-06-01T00:00:00.001Z`, `fundingRate="0.00005703"`, `markPrice="73653.56663043"`, `rateType="Regular"`, source index `0`. Raw row 0 exists as exact compact JSON bytes in the raw response. The selected-event artifact is enriched with metadata and is not byte-identical to the raw row. Source numeric fields remain strings. The source receipt binds the raw and selected-event hashes, and the contract binds the selected identity.

# Exact Diff

Changed paths:

| Status | Path |
| --- | --- |
| A | `docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_IMPLEMENTATION.md` |
| A | `quantbot/paper/public_funding_economic_fixture.py` |
| A | `tests/fixtures/public_funding_economic_v0/expected_receipt.json` |
| A | `tests/fixtures/public_funding_economic_v0/input.json` |
| A | `tests/test_public_funding_economic_fixture_v0.py` |

No hidden generated files, executable binaries, network calls, database writes, paper-engine edits, strategy edits, candidate/trial/decision changes, or unrelated code were present in the commit delta.

# Line-Count Decomposition

Exact insertion decomposition: module 831, tests 285, input fixture 51, expected receipt 1, documentation 163, total 1331.

Blank lines: module 85, tests 46, documentation 72.

Docstring/comment-marker lines: module 7 docstring lines, documentation 15 Markdown heading/comment-style lines, tests and fixtures 0.

Executable-code estimate: module 746 non-doc AST statement-span lines, tests 199 non-doc AST statement-span lines.

# Independent Arithmetic Oracle

Independent script: `/tmp/independent-public-economic-fixture-review-v0/review_oracle.py`

Result: `HOSTILE_PUBLIC_ECONOMIC_FIXTURE_ORACLE_PASS`

Independent vectors:

| Vector | Quantity | Notional | Transfer |
| --- | ---: | ---: | ---: |
| long | `0.001` | `73.65356663043` | `-0.0042004629049334229` |
| short | `-0.001` | `73.65356663043` | `0.0042004629049334229` |
| zero | `0` | `0` | `0` |

The long vector matches the committed expected receipt.

# Formula and Dimensions

Classification: `FORMULA_CONFIRMED`

Quantity unit is BTC, mark price is USDT/BTC, contract multiplier is `1`, notional is USDT, funding rate is dimensionless, and transfer is USDT. Notional uses absolute quantity. Transfer uses signed quantity. Positive funding makes the long pay and the short receive. A synthetic negative funding rate reverses direction. Multiplier is applied once and is honestly scoped as a bounded dimensional contract rule.

# Decimal and Canonicalization

Classification: `DECIMAL_POLICY_AMBIGUOUS`

Binary floats, malformed decimals, NaN, Infinity, non-positive mark prices, and global Decimal context mutation are covered. Negative zero serializes calculated amounts as canonical `0`.

Ambiguities: `_decimal_from_string()` accepts `+0.001`, `1E-3`, leading/trailing whitespace, and very large exponents. Semantically equivalent quantities such as `0.001`, `0.0010`, `1E-3`, and `+0.001` produce equivalent economic values but different receipt IDs. Extreme exponent input raised raw `decimal.Overflow`, not a typed fixture reason.

# Expected-Receipt Circularity

Classification: `PARTIAL_SNAPSHOT_CIRCULARITY`

The test suite has useful hard-coded arithmetic checks for long, short, and zero vectors. It also compares the committed expected receipt to bytes generated by the implementation and therefore cannot independently validate implementation-defined receipt identity or canonicalization. A shared generator/verifier bug in non-arithmetic receipt metadata could pass.

# Provenance

Classification: `LIVE_CROSS_REPOSITORY_SOURCE_VERIFICATION` for CLI/default `parse_fixture()`, and `SELF_CONTAINED_PINNED_VECTOR` when callers set `verify_source=False`.

The QNTY input fixture binds raw, selected-event, and source receipt hashes plus event identity fields. The CLI opens QntyLab source artifacts and verifies hashes by default. Tests frequently use `verify_source=False`, so those tests exercise the pinned vector, not live cross-repository verification.

# Receipt Identity

Classification: `IDENTITY_COMPLETE_AND_DETERMINISTIC`

The `receipt_id` binds contract id/version, claim scope, source hashes except source receipt hash, source event identity, symbol, funding time, funding rate, mark price, rate type, signed quantity, quantity unit, multiplier, formula version, and numeric policy. Non-identity receipt fields are still compared by `verify_receipt()`, but with one verification-metadata gap noted in finding F-001.

# Tamper Resistance

Classification: `REQUIRES_CORRECTNESS_REPAIR`

Temporary mutated receipts were rejected for calculated notional, calculated transfer, direction, account status, claim verdict, non-claims, research-state policy, implementation owner, evidence level, precision status, and receipt ID. However, `verification.source_hashes_verified=false` was accepted.

# Failure-State Reachability

20 reason codes inspected.

Counts: `DIRECTLY_REACHABLE_AND_TESTED=12`, `DIRECTLY_REACHABLE_NOT_TESTED=8`, `UNREACHABLE=0`, `MISCLASSIFIED=0`, `DUPLICATE_OF_ANOTHER_REASON=0`, `OUT_OF_SCOPE=0`.

Not directly tested: `SOURCE_FIXTURE_MISSING`, `SOURCE_EVENT_NOT_FOUND`, `EVENT_IDENTITY_MISMATCH`, `MARK_PRICE_MISSING`, `QUANTITY_UNIT_UNRESOLVED`, `CONTRACT_MULTIPLIER_UNRESOLVED`, `SIGN_CONVENTION_UNRESOLVED`, `QNTY_EXTENSION_BOUNDARY_UNSAFE`.

# Idempotency

Classification: `SOUND_BUT_NONESSENTIAL`

Same inputs produce the same receipt bytes and ID. Duplicate byte-identical receipts in one supplied batch are rejected deterministically. The implementation does not claim persistent exactly-once processing or SQLite/wallet idempotency. Equivalent decimal aliases are not treated as duplicates because representation is identity-bearing and `verify_receipt_batch()` verifies against one fixture quantity.

# CLI Review

Successful command run twice:

`.venv/bin/python -m quantbot.paper.public_funding_economic_fixture --fixture tests/fixtures/public_funding_economic_v0/input.json --verify`

Return code: 0 both runs. Stdout bytes stable. Stderr empty. Output proves the committed QNTY vector matches the committed QNTY receipt and that default source artifacts are available and hash-valid in the current checkout.

Missing and malformed fixture inputs exit nonzero through Python tracebacks. Unexpected extra fixture keys are accepted if they are not forbidden scope fields. No network access or file mutations were observed.

# Test-Quality Review

26 collected tests classified by parametrized case count:

| Classification | Count |
| --- | ---: |
| `INDEPENDENT_CORRECTNESS_ORACLE` | 0 |
| `MEANINGFUL_INVARIANT` | 13 |
| `MEANINGFUL_REGRESSION` | 10 |
| `SNAPSHOT_ONLY` | 1 |
| `IMPLEMENTATION_MIRROR` | 2 |
| `TRIVIAL_ASSERTION` | 0 |
| `UNREACHABLE_SETUP` | 0 |

The suite would catch obvious one-line arithmetic sign and multiplier defects, but it would miss shared bugs in receipt verification metadata and some canonicalization policy errors.

# Regression Results

New tests: `.venv/bin/python -m pytest tests/test_public_funding_economic_fixture_v0.py -q`; return code 0; 26 passed; 0 failed; 0 skipped; duration 0.15s. Proves focused implementation regression behavior, not independent source truth.

Focused regression: `.venv/bin/python -m pytest tests/test_paper_pnl.py tests/test_funding_source_snapshot_schema.py tests/test_funding_source_digest_window_semantics.py tests/test_funding_source_immutable_bundle_semantics.py tests/test_paper_sqlite_writer.py tests/test_paper_sqlite_verify.py tests/test_paper_sqlite_verify_report.py tests/test_paper_matched_null.py tests/test_receipt_schema.py -q`; return code 0; 413 passed; 0 failed; 0 skipped; duration 45.99s. Proves no regression in the selected offline paper/funding/sqlite receipt slice.

Full offline suite: not run.

# Static Review

`compileall` on the new module and test returned code 0.

`ruff` and `mypy` were not installed in the local venv, so no lint/type run was available without adding dependencies.

Import review found only standard-library imports plus `quantbot.core.determinism`. No import cycles, SQLite imports, network imports, strategy imports, or research-state mutation imports were found in the module.

# Scope and Non-Claims

Classification: `SCOPE_HONEST`

Required non-claims are present in the fixture and generated receipt. No changed file asserts exchange exactness, wallet exactness, real account verification, real position, real trade, profitability, alpha, strategy validity, or production readiness. `claim_verdict=PROVEN_FOR_PINNED_FIXTURE` is adjacent to bounded claim scope in CLI output and receipt verification.

# Architecture and Overbuild

Recommendation: `KEEP_WITH_SMALL_REDUCTION`

Load-bearing: Decimal arithmetic, source artifact verification, receipt construction, receipt verification, CLI.

Useful but nonessential: dataclass layering, batch duplicate verifier, large failure enum.

Reductions: remove or split `verify_receipt_batch()` if no V0 caller needs batch behavior; reduce unused/decorative reason codes or add tests for them; move CLI wiring out of the arithmetic module if this grows beyond V0.

# Security Boundary

Risks are bounded to offline fixture verification. Path traversal and symlink behavior are future-hardening concerns because artifact paths from fixture JSON are joined with a source root and not normalized against escape. JSON loading is unbounded and duplicate keys are accepted by Python JSON parsing. For the pinned small fixture, these are not load-bearing security failures.

# Findings

F-001 | `BLOCKER` | Verification metadata tamper is accepted | `quantbot/paper/public_funding_economic_fixture.py:371`

Evidence: changing `verification.source_hashes_verified` to `false` in a temporary receipt was accepted by `verify_receipt()`. Lines 371-386 inspect only `verification.claim_scope` and `verification.claim_verdict`.

Why it matters: a receipt can claim in top-level fields that source hashes are bound while nested verification metadata says they are not, yet verification still passes.

Minimal remediation: compare the complete `verification` object to the expected object, including `reason_codes`, `source_hashes_verified`, `source_event_identity_verified`, `arithmetic_verified`, and `account_posting`.

Blocks integration: yes.

F-002 | `MAJOR` | Decimal representation policy is under-specified and unbounded | `quantbot/paper/public_funding_economic_fixture.py:649`

Evidence: `+0.001`, `1E-3`, `0.0010`, and whitespace-wrapped strings are accepted. `1e1000000` raises raw `decimal.Overflow`.

Why it matters: economic value and receipt identity diverge for decimal aliases, and extreme inputs do not fail with a typed reason.

Minimal remediation: document representation-bearing identity explicitly and reject or canonicalize unsupported forms with typed errors; bound exponent/length.

Blocks integration: no, after F-001 is fixed this can be repaired as a major hardening item.

F-003 | `MAJOR` | Commit is on a semantically wrong repair branch | `docs/receipts/PUBLIC_ECONOMIC_FIXTURE_V0_IMPLEMENTATION.md:13`

Evidence: the implementation report and Git identity show the fixture was committed on `chore/external-trust-root-dispatcher-repair-v046`; the branch includes unrelated continuity/research changes relative to `main`.

Why it matters: merging the branch would integrate unrelated protocol repair work.

Minimal remediation: cherry-pick `432d5326` onto a dedicated fixture branch after correctness repair.

Blocks integration: no if cherry-picked; yes for whole-branch merge.

F-004 | `MINOR` | Expected-receipt test is partly circular | `tests/test_public_funding_economic_fixture_v0.py:261`

Evidence: the committed expected receipt is loaded and compared to receipt bytes generated by the same implementation.

Why it matters: useful for regression, but not an independent correctness oracle for canonicalization or implementation-defined metadata.

Minimal remediation: keep the snapshot but add independent expected fields or a small oracle that derives arithmetic and required verification metadata without calling the generator.

Blocks integration: no.

F-005 | `MINOR` | CLI error handling leaks tracebacks for routine bad inputs | `quantbot/paper/public_funding_economic_fixture.py:803`

Evidence: missing and malformed fixture paths exit nonzero via Python traceback rather than a concise typed failure.

Why it matters: operator-facing diagnostics are noisy and include absolute paths.

Minimal remediation: catch `PublicEconomicFixtureError` and `json.JSONDecodeError` in `main()` and print stable reason-coded stderr.

Blocks integration: no.

F-006 | `MINOR` | Unexpected fixture fields are mostly accepted | `quantbot/paper/public_funding_economic_fixture.py:151`

Evidence: adding `unexpected_extra` to a temporary fixture still produced a verified receipt when the expected receipt path was supplied.

Why it matters: strict schema expectations are weaker than the tests imply; future fields can become invisible identity/scope ambiguity.

Minimal remediation: reject unknown top-level fixture keys or explicitly document extension-tolerant parsing.

Blocks integration: no.

# Minimum Remediation

Fix F-001 before integration. Then add tests proving tampering of every `verification` subfield is rejected with the intended reason. Address F-002 either by canonicalizing decimal input representations or documenting and enforcing a source-representation identity grammar.

# Integration Gate

`NOT_READY_FOR_INTEGRATION`

# Verification

Report validation result: `INDEPENDENT_REVIEW_REPORT_VALIDATION_PASS`

QNTY diff remained empty. QntyLab canonical research streams remained unchanged. Pre-existing QntyLab tracked WIP manifest hashes remained unchanged.

# Final Verdict

`INDEPENDENT_REVIEW_REQUIRES_CORRECTNESS_REPAIR`

# Immediate Next Action

Repair `verify_receipt()` so all verification metadata is load-bearing, add focused tamper tests, then rereview and cherry-pick onto a dedicated fixture branch rather than merging the repair branch.
