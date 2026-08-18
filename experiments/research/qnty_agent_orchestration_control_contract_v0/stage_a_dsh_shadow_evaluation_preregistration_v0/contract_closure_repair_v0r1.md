# Stage-A DSH shadow evaluation V0 — targeted closure repair re-review

review_type = "TARGETED_REREVIEW_AFTER_HIGH_REPAIR"
original_hostile_review_consumed = true
review_scope = "Only the H-01, H-02, and M-01 repair delta plus transitive digest and regression-test updates."
review_count = 1

## Targeted attack results

| Attack | Result |
| --- | --- |
| Worker contract self-prohibits the DSH treatment | PASS — the task input is explicitly scoped to a future admitted execution arm and contains no equivalent prohibition. |
| Worker contract self-prohibits Stage-A arm execution | PASS — the admitted arm may perform the task; present execution remains separately unauthorized. |
| Repair grants execution authority now | PASS — preregistration and closure remain `stage_a_execution_authorized = false` and `PREREGISTERED_NOT_EXECUTED`; the next phase still requires separate authorization. |
| DSH worker can self-upgrade or change the harness | PASS — arbitrary newer DSH fetch, self-upgrade/self-replacement, orchestration-substrate mutation, and pinned-harness alteration remain forbidden. |
| Prompt digest is computed from frozen prompt bytes | PASS — SHA-256 of the exact UTF-8 prompt string matches the resolved 64-character lowercase digest. |
| JSON formatting can change prompt digest | PASS — the declared digest scope excludes file formatting, dictionary ordering, and editor-dependent newlines. |
| Native and DSH task contracts differ | PASS — both task digests bind the same final task-contract bytes. |
| A copied/transitive digest is stale | PASS — task, scorer, intervention, gate, receipt, and arm-configuration digests recompute from their declared sources. |
| Placeholder identity survives | PASS — required frozen prompt/build identity fields are resolved or explicitly `NOT_EXPOSED`; no false build claim remains. |
| `gpt-5` is falsely represented as a provider build | PASS — it is only the requested selector; immutable provider build is `NOT_EXPOSED` and not claimed. |
| Observable arm identity mismatch can pass | PASS — receipt capture and source-identity comparison are fail-closed. |
| Missing provider-internal build ID makes execution impossible | PASS — absence is recorded as a known system-level limitation, while observable parity remains required. |
| Causal claim broadens beyond system comparison | PASS — `SYSTEM_LEVEL_COMPARISON` and `harness_attribution_allowed = false` remain unchanged. |
| Answer-key firewall, zero-write boundary, retries, tie policy, DSH pin, or authority ceiling weakened | PASS — all remain frozen and no arm was installed, executed, or scored. |

Critical findings = 0
High findings = 0
Medium findings = 0
Low findings = 0

## Verdict

TARGETED_REREVIEW_PASS. The bounded repair delta is internally consistent and
ready for the required deterministic verification and candidate freeze. No
additional review is authorized or consumed.
