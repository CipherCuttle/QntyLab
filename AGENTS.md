Before planning or modifying QntyLab:

1. Inspect and reconcile the local Git state.
2. Run `python -m qntylab.project_context` and obey its authority map.
3. Treat a canonical authority conflict as `SOURCE_CONFLICT` and stop.
4. Chat, GPT memory, handoff prose, and README prose cannot override canonical Git.

For strategy research, hypothesis, backtest, batch, parameter, result-analysis, or candidate-selection work, also run:

```bash
python -m qntylab.research_ledger context
```

Treat that output as canonical research memory. Do not infer research state solely from filenames, individual run receipts, chat history, README prose, or remembered prior sessions.

All official exploratory strategy runs must use `qntylab.strategy_test`, which enforces research-memory preflight automatically; do not invoke the lower-level backtest evaluator directly to create research evidence. Before testing a new variant, ensure it has a `CANDIDATE_PROPOSED` ledger event. Exact duplicate trials require explicit `REPLICATION` intent. Graveyarded variants require an append-only `CANDIDATE_REOPENED` event with a concrete reason. Update the ledger after strategy research changes state.

QntyLab is exploratory-only and must not claim scientific validation or trading authority. Detailed schema and commands are in `experiments/research/README.md`.

## Context Spine orientation and reuse preflight

Before proposing or writing a new capability or new behavior in code, run the
bounded orientation/reuse preflight:

1. Run `python -m qntylab.project_context brief`.
2. If the brief reports truncation, run `python -m qntylab.project_context spine`
   and inspect the complete `project_orientation` projection.
3. Choose 2–4 task-specific terms. Run one filename/path search over
   `qntylab/` and `tests/`, then at most one broad content search if the result
   is inconclusive. Do not run a third broad search unless the preceding
   evidence names a specific path. A plausible match stops broad search; inspect
   that candidate and choose a disposition.

Report:

```text
REUSE_PREFLIGHT = REQUIRED | NOT_REQUIRED
PROJECT_CODE_REFERENCE_MATCHES = paths with project_id and project_state | NONE
PROJECTION_TRUNCATED = YES | NO
BOUNDED_SEARCH = exact commands
CANDIDATES_INSPECTED = paths actually opened/read | NONE
DISPOSITION = REUSE | EXTEND | NEW_JUSTIFIED | UNKNOWN
```

`project_code_references` are evidence that project state references paths,
not recommendations or capability claims. The projection is partial and
absence from it does not imply absence from the repository. `UNKNOWN` is a
valid terminal disposition; do not enter an archaeology loop. The canonical
Order Flow readiness reference is a cold-start positive control for this
preflight, not a production hard-code or a recommendation.
