# Independent hostile review

Frozen target: `4131d9f84f4ada2d78f0232ca61adcd59afe5198`

Reviewer: a separate read-only agent that did not implement the target. No
subscription product call was made. The deterministic qualification suite
passed 34 tests during review.

## Findings

| Severity | Finding | Required disposition |
|---|---|---|
| High | The prelive manifest allowed required source, prompt, contract, and binary hashes to be omitted, while result gates were asserted true. | Require exact frozen path/binary sets and compute result gates. |
| High | Alternate driver argv could execute fake product bytes while receipts declared canonical product identity. | Remove alternate live argv/environment surfaces; bind executed bytes. |
| High | PASS receipts accepted incomplete nested evidence and were not reconciled with current filesystem state. | Enforce exact nested schemas and re-observe before persistence/aggregation. |
| High | Overall PASS ignored final fixture/path, marker, hash, prompt, and workspace gates. | Make every listed machine gate conjunctive and observed. |
| High | QntyLab mutation snapshots omitted ignored paths. | Add content-free full-tree metadata accounting to tracked Git evidence. |
| High | Builder policy accepted empty writable roots and ignored approval/unsupported protocol requests. | Require the exact root set and zero escalation/unsupported requests. |
| High | Checked source/product paths could be swapped between hash check and execution/import. | Load/execute hash-verified source bytes and product executable descriptors. |
| Medium | Timestamp strings were not format/order validated. | Recorded; not part of the single C/H repair pass. |
| Medium | A blocked result could report the ambient API-key gate PASS without a role receipt. | Recorded; not part of the single C/H repair pass. |

```text
CRITICAL = 0
HIGH = 7
MEDIUM = 2
LOW = 0
OPEN_CRITICAL = 0
OPEN_HIGH = 7
```

The phase therefore uses its single permitted Critical/High fix pass and must
perform exactly one targeted re-review of these seven High findings.
