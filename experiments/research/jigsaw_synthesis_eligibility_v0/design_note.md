# Jigsaw Synthesis Eligibility V0 — design note

Phase: `QNTYLAB_JIGSAW_SYNTHESIS_ELIGIBILITY_V0` (F-03). Follows F-01 (terminal
decision integrity, CLOSED/PASS) and F-02 (Jigsaw discovery index,
CLOSED/PASS). Neither is reopened by this phase.

## Question this phase answers

Given the F-02 discovery index's five canonical Jigsaw evidence pieces, what
cross-piece synthesis is scientifically admissible, what is merely contextual
co-observation, and what apparent synthesis must be blocked? This is
implemented by `qntylab/jigsaw_synthesis.py`, generating
`eligibility.json` in this directory.

## Why the derivation code is generic, not a lookup table

The phase brief is explicit: "Do not hard-code the scientific analysis from
this prompt." Every pairwise fact (`same_source_artifact`,
`same_experiment`, `same_snapshot_identity`, `decision_window_relation`,
`same_data_history`, `same_feature`, `same_outcome`) is derived by comparing
fields already present on an indexed piece row (from
`qntylab.jigsaw_index`). No function inspects a `piece_identity` string.
The same code would classify a sixth future canonical piece without a code
change — it would just find explicit fields to compare or fall back to
UNKNOWN/NOT_ESTABLISHED.

`claim_relation` and `independence_status` are then derived from those
mechanical facts alone via small fixed decision tables (`_claim_relation`,
`_independence_status`, `_allowed_synthesis`), not by hand-classifying each
of the 10 current pairs. Which of the 10 pairs land in which bucket is an
*output* of running real data through generic code, not an input to it.

## Why `same_snapshot_identity` is `UNKNOWN`, not `NO`, for Funding-Pressure ↔ Harvest pairs

Manual inspection of
`experiments/research/jigsaw_funding_pressure_volatility_v0/pit_coverage_certificate_v1.json`
shows the funding-pressure piece's OHLCV input comes from a materially
different materializer chain (`BINANCE_USD_M_PERPETUAL_1H_MATERIALIZER_V0`
manifests) than Harvest's Research Data Spine snapshot
(`rds-v0-c0fa7dc0...`), and never references that RDS snapshot ID anywhere.
That would support a manually-asserted `NO`.

This module does not do that. It only reads
`frozen_binding` (`snapshot_binding`/`bound`) as already extracted by
`qntylab.jigsaw_index` — which is itself bound, digest-tracked input. The
extra provenance files above are *not* part of the index's digest binding
(`generated_from.source_files_sha256` covers only the two canonical
`result.json` files); deriving a mechanical field from them would create a
staleness blind spot — the eligibility artifact could go silently stale if
one of those un-tracked files changed, since `doctor()` never re-reads them.
So the mechanical field stays the more conservative `UNKNOWN`
(`frozen_binding` on the funding-pressure piece has no `snapshot_id` key at
all), and `same_data_history` resolves to `NOT_ESTABLISHED` rather than a
confident `NO`. This is *more* conservative than the manually-verified fact,
never less — it can only block synthesis it might otherwise (correctly)
also block, never license something the manual read would have forbidden.

## Why `same_outcome` is `NOT_ESTABLISHED`, not `NO`, for the two "RV24" outcomes

Reading the frozen preregistrations directly: Harvest's `RV24_future,t =
sqrt(sum_{h=t+1}^{t+24} r_m,h^2)` over equal-weight *log* returns, versus
funding-pressure's `RV24_t = sqrt((1/24) * sum_{h=1}^{24}(...)^2)` over
equal-weight *simple* returns with an explicit `1/24` mean normalization
Harvest's formula lacks. These are formally different statistics (return
type and normalization both differ), not just differently-scaled versions of
the same one — exactly the "equal panel size / similar name ≠ identity" trap
Section 9 of the phase brief calls out.

The code does not encode this reasoning (that would itself be "hard-coding
the scientific analysis"). It instead observes a purely structural fact:
Harvest pieces expose a top-level `outcome` field (e.g. `"RV24_future,t"`);
the funding-pressure piece has no top-level `outcome` field at all (only a
narrative label nested at `bound.outcome`, a different location with
different semantics). Two fields that are not even structurally comparable
in the same location produce `NOT_ESTABLISHED`, not a guessed `NO`. The
formula-level finding above is additional confirmation that `NOT_ESTABLISHED`
was the right conservative answer here, not a case where the mechanical
field undershot what the evidence actually supports.

## Why `CANONICAL_BASE_SHA` is a literal constant

Section 21 requires: same canonical base + same `jigsaw_index` bytes + same
source bytes + same implementation ⇒ byte-identical artifact. Reading
`git rev-parse HEAD` at generation time would violate that — the SHA changes
with every commit on this phase branch, including commits after the artifact
is generated. `CANONICAL_BASE_SHA` is fixed to the F-02 merge commit
(`ebdcc4e...`, PR #49) this synthesis module's discovery-index consumption
contract targets. It carries no scientific content and is not re-derived.

## Decision tables (exhaustive, so a reviewer can audit them directly)

`claim_relation(same_feature, same_outcome)`:

| same_feature | same_outcome | claim_relation |
|---|---|---|
| YES | YES | IDENTICAL_CLAIM |
| YES | NO | RELATED_DISTINCT_CLAIM |
| NO | YES | RELATED_DISTINCT_CLAIM |
| NO | NO | DIFFERENT_CLAIM |
| NOT_ESTABLISHED | * | CLAIM_RELATION_NOT_ESTABLISHED |
| * | NOT_ESTABLISHED | CLAIM_RELATION_NOT_ESTABLISHED |

`independence_status`: `SHARED_FROZEN_HISTORY` if `same_snapshot_identity ==
YES` or `same_source_artifact == YES` — checked *first*, unconditionally, so
it dominates everything else. Else `OVERLAPPING_HISTORY_INDEPENDENCE_NOT_ESTABLISHED`
if the decision windows are known to relate
(`EXACT`/`A_CONTAINS_B`/`B_CONTAINS_A`/`PARTIAL_OVERLAP`). Else
`INDEPENDENCE_NOT_ESTABLISHED`.

`INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED` is intentionally
**unreachable** from current indexed provenance, on purpose, not by
oversight. An earlier revision derived it from a self-declared
`explicit_independent_replication_of` field, checked *before* the
shared-history test — a post-review closure pass (see `hostile_review.md`)
found this fail-open: a piece could declare replication of another piece
while still demonstrably sharing that piece's exact frozen snapshot, and the
declaration would win. Declaration states *intended target identity*, not
*empirical data independence*, and `JIGSAW_INDEX_V0` currently exposes no
field that positively establishes independent data/history — only
presence/absence of a matching `snapshot_id`, which at best proves
non-identity, never independence. Per the phase contract this module does
not invent a new provenance field merely to make the state reachable, so it
is acceptable — and correct — for it to remain permanently unreachable in
V0 rather than derived from a bare self-assertion.

`allowed_synthesis(independence_status, claim_relation)`:

| independence_status | claim_relation | allowed_synthesis |
|---|---|---|
| INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED | IDENTICAL/RELATED_DISTINCT | INDEPENDENT_CONFIRMATION_ELIGIBLE |
| SHARED_FROZEN_HISTORY | any | SAME_HISTORY_MULTI_PROPOSITION_CONTEXT |
| OVERLAPPING_HISTORY_INDEPENDENCE_NOT_ESTABLISHED | IDENTICAL/RELATED_DISTINCT | JOINT_CONTEXT_ONLY |
| otherwise | — | SEPARATE_ONLY |

## Current result shape (5 pieces, 10 pairs)

* 6 pairs (all within Jigsaw Harvest V0, sharing its one frozen RDS
  snapshot) → `SHARED_FROZEN_HISTORY` → `SAME_HISTORY_MULTI_PROPOSITION_CONTEXT`,
  each with a deterministically templated synthesis statement.
* 4 pairs (each Harvest piece against the funding-pressure piece) →
  `OVERLAPPING_HISTORY_INDEPENDENCE_NOT_ESTABLISHED` +
  `CLAIM_RELATION_NOT_ESTABLISHED` → `SEPARATE_ONLY`, no statement.
* 0 pairs reach `INDEPENDENT_CONFIRMATION_ELIGIBLE`. No pair in the current
  canonical census establishes independent replication.

## What this module is not

Not a scoring system, not a second discovery mechanism (membership comes
entirely from `qntylab.jigsaw_index.build_index`), not a source-artifact
mutator, not State Snapshot/Router/Qnty/trading/promotion authority. See
`eligibility.json`'s `global_constraints` block, which states all of those
as `NONE` explicitly.
