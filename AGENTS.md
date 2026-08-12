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
