# Independent hostile review — PINNED_DSH_CODEX_WRITE_PATH_MATERIALIZATION_V0R1

REVIEW_COUNT = 1
REVIEW_INDEPENDENCE = YES
REVIEWER_SEPARATE_FROM_IMPLEMENTATION_AGENT = YES
READ_ONLY = YES
LIVE_PRODUCT_CALLS = 0
REVIEW_SCOPE = C1,H1,H2,H3,H5

CRITICAL = 0
HIGH = 4
MEDIUM = 0
LOW = 0
CRITICAL_HIGH_REMAINS = YES
CRITICAL_HIGH_FIX_PASS_REQUIRED = YES
TARGETED_REREVIEW_REQUIRED = YES

## High findings

1. `C1_WRONG_DSH_ROOT_ADMISSIBLE`: the caller-selected initial root was reused
   as the final expected root instead of being bound to the frozen exact root.
2. `H2_UNKNOWN_NESTED_LIFECYCLE_FIELDS_PASS`: lifecycle and lifecycle-end
   mappings did not enforce exact nested keys.
3. `H2_RUNNER_CREDENTIAL_SCHEMA_INCOMPATIBLE`: the sanitizer observation also
   carried `GITHUB_TOKEN` and `GH_TOKEN`, while the strict D4 receipt schema
   permits exactly the four pay-per-token API names.
4. `H2_EMPTY_CREDENTIAL_REPORTED_ABSENT`: inherited helpers used value
   truthiness instead of environment-key membership.

## Scope disposition

- C1: one High.
- H1: no Critical/High.
- H2: three High.
- H3: no Critical/High.
- H5: no Critical/High.
- Wrong runtime bytes: closure hashing passed; exact root binding remained open.
- Wrong materialization provenance: no additional Critical/High.
- Receipt laundering / false PASS: reproduced via unknown nested lifecycle keys.
- Invisible retry: no Critical/High.
- Fabricated target-mechanism execution: no additional Critical/High.

Focused tests before review: `60 passed`.

This is the one and only independent hostile review for V0R1.  The four High
findings require the single allowed Critical/High fix pass followed by exactly
one targeted re-review limited to these findings.
