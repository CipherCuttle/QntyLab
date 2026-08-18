# Stage-A DSH shadow evaluation preregistration V0 — one independent hostile review

review_identity = "ONE_INDEPENDENT_HOSTILE_GOVERNANCE_REVIEW"
review_scope = "frozen preregistration candidate only"
candidate_pre_review_index_tree_sha = "2872e8b068e5270bc387463c2d6514a35731f1ed"
review_count = 1

## Review method

This review attacks the preregistration documents, task firewall, model and
harness identities, scorer semantics, receipt and intervention schemas, gate
operationalization, isolation rules, authority ceiling, and protected-path
boundary. It does not execute either arm, install DSH, run a dry run, or inspect
unofficial Stage-A outcomes. The canonical OC-B answer references were used only
as sealed historical provenance for reconstructing the task and are not worker
inputs.

## Findings

| ID | Target | Severity | Finding |
| --- | --- | --- | --- |
| H01 | Answer-key leakage | None | Reviewed and post-merge references, diffs, review findings, final patch, and solution hints are explicitly sealed from workers; release to scorer is post-termination only. |
| H02 | Outcome contamination | None | No unofficial Stage-A outcome was inspected and no arm was executed or dry-run. |
| H03 | Baseline straw-manning | None | Native baseline is the actual bounded repository-native OC-B completion doctrine and is not intentionally crippled. |
| H04 | Harness confounding | None | Provider/model/roles/review/retry/scoring boundaries are matched where possible; unavoidable tool and controller differences are disclosed and cap the claim at SYSTEM_LEVEL_COMPARISON. |
| H05 | DSH identity drift | None | Official owner/repository, commit, tag, package, version, license, branch, and source tree ID are frozen. |
| H06 | Model drift | None | Both arms use the same preregistered provider/model/revision and missing or changed receipt identity fails closed. |
| H07 | Scoring subjectivity | None | Required propositions have deterministic objective checks and binary all-required semantics; subjective preference is not a score. |
| H08 | Score gaming | None | Weights, propositions, comparator, and arm exceptions are frozen before dispatch and cannot be changed after outcomes. |
| H09 | Intervention gaming | None | Intervention event types, exclusions, material-effect rule, append-only fields, and FAIL_CLOSED ambiguity rule are frozen. |
| H10 | Unlimited retries | None | Machine retry, restart, review-loop, verifier, and timeout ceilings are finite and DSH internal retries must be visible and consume the same budget. |
| H11 | Cross-arm leakage | None | Fresh workspaces, separate processes, separate traces/ledgers/scratch, no cross-arm state, and answer-key firewall are explicit. |
| H12 | Stale state | None | Exact BASE SHA and fresh workspace admission are hard-gated; stale or dirty admission fails closed. |
| H13 | Duplicate dispatch | None | Initial dispatch identity is unique per experiment/arm/task/workspace and duplicate dispatch rate is a hard gate. |
| H14 | Trace gaps | None | Receipt schema names admission, dispatch, worker, tool, retry, intervention, review, verification, termination, artifact, and scoring events. |
| H15 | Review non-independence | None | BUILDER, HOSTILE_REVIEWER, and VERIFIER identities are mechanically distinct; recursive review is forbidden. |
| H16 | Network/credential escape | None | Worker network is limited to declared model API transport; GitHub writes and write credentials are zero/NONE; scorer is local-only. |
| H17 | Tie laundering | None | Exact ties classify PASS_NO_INCREMENTAL_VALUE and never authorize runtime implementation. |
| H18 | Post-hoc metric promotion | None | Resource/cost diagnostics are explicitly secondary and cannot become promotion criteria after outcomes. |
| H19 | Authority leakage | None | Preregistration authorizes no execution, DSH installation, runtime, science, Qnty NEXT_ACTION, trading, capital, publication, merge, or auto-merge. |
| H20 | Order-flow contamination | None | No protected order-flow path is in the allowed surface or preregistration changeset. |

Critical = 0
High = 0
Medium = 0
Low = 0

## Verdict

PASS. No Critical or High finding remains. No repair round and no targeted
rereview are consumed. The final candidate may be frozen only after deterministic
tests, project-context/roadmap checks, ledger doctor, final digest binding, and
clean-worktree verification. This review does not authorize experiment
execution or any later runtime implementation.
