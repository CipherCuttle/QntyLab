# QntyLab Research Ledger

This directory contains the strategy-research memory used by fresh Codex sessions and official `qntylab.strategy_test` runs.

Start every strategy-research task with:

```bash
python -m qntylab.research_ledger context
```

Canonical evidence is stored as separate append-only JSON Lines streams:

```text
candidates.jsonl
decisions.jsonl
trials/*.jsonl
```

Generated lookup caches are:

```text
state.json
trial_index.json
```

The generated indexes are not independent sources of truth. They must be reproducible exactly with `python -m qntylab.research_ledger rebuild`.

## Streams

`candidates.jsonl` supports `CANDIDATE_PROPOSED` and `CANDIDATE_REOPENED`.

Candidate proposal fields:

```text
event_id, event_type, candidate_id, family_id, variant_id, strategy_id,
strategy_version, objective, origin, mechanism, prediction, required_data,
decision_time, execution_time, benchmark, parameters, mode, bar_interval,
required_input_kind, funding_boundary_mode, failure_condition, recorded_at_utc
```

Reopening fields:

```text
event_id, event_type, candidate_id, variant_id, previous_decision_event_id,
reason, material_change, recorded_at_utc
```

`decisions.jsonl` supports `DECISION_RECORDED`.

Decision fields:

```text
event_id, event_type, candidate_id, family_id, variant_id, status, scope,
reason_codes, decision_note, evidence_paths, evidence_sha256,
revisit_condition, recorded_at_utc
```

Allowed decision statuses are `FOLLOW_UP`, `SURVIVOR`, `GRAVEYARDED`, and `BLOCKED`. Allowed scopes are `EXACT_VARIANT` and `FAMILY`; omitted scope defaults to `EXACT_VARIANT` at event creation time, but stored events must include it.

`trials/*.jsonl` supports `TRIAL_COMPLETED`.

Trial fields:

```text
event_id, event_type, recorded_at_utc, candidate_id, family_id, variant_id,
trial_id, research_intent, symbol, evaluation_start, evaluation_end,
input_sha256, repository_commit, relevant_source_sha256, fee_bps,
slippage_bps, gap_policy, expected_interval, receipt_path, receipt_sha256,
compact_metrics
```

## Identity

`variant_id` is deterministic from canonical JSON containing:

```text
strategy_id, strategy_version, parameters, mode, bar_interval,
required_input_kind, funding_boundary_mode
```

`trial_id` is deterministic from canonical JSON containing:

```text
variant_id, symbol, input_sha256, evaluation_start, evaluation_end,
fee_bps, slippage_bps, gap_policy, expected_interval
```

Config filenames are not part of identity.

## Commands

```bash
python -m qntylab.research_ledger context
python -m qntylab.research_ledger rebuild
python -m qntylab.research_ledger doctor
python -m qntylab.research_ledger propose --event <json-path>
python -m qntylab.research_ledger decide --event <json-path>
python -m qntylab.research_ledger reopen --event <json-path>
python -m qntylab.research_ledger show-family <family-id>
python -m qntylab.research_ledger show-variant <variant-id>
python -m qntylab.research_ledger recent --limit 20
python -m qntylab.research_ledger graveyard --reason <reason-code>
```

Official strategy runs verify canonical streams and generated indexes before execution, then append compact factual `TRIAL_COMPLETED` events automatically. Decisions remain manual append-only research judgments.
