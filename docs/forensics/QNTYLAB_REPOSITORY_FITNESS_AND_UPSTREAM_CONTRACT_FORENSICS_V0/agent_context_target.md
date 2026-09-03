# Agent Context Target — Cold-Start UX Packet (DESIGN ONLY)

Audit: `QNTYLAB_REPOSITORY_FITNESS_AND_UPSTREAM_CONTRACT_FORENSICS_V0`
HEAD: `be291300abb70f3ffc6ba0dd8b1bea570daf5377` (branch
`audit/qntylab-repository-fitness-and-upstream-contract-forensics-v0`)

**Status: design artifact. Nothing here is implemented, wired into
`qntylab/project_context.py`, or authorized for implementation.**

## 1. Why (measured, not assumed)

| Current surface | Measured size | Problem |
|---|---:|---|
| `python -m qntylab.project_context brief` stdout | **14,468 B / 118 lines, TRUNCATED** | canonical cold-start summary does not fully render (`raw/context_metrics.json: BRIEF_BYTES/BRIEF_TRUNCATED`) |
| `python -m qntylab.project_context spine` stdout | **50,150 B on a single line** | undiffable, unstreamable, all-or-nothing consumption (`raw/context_metrics.json: SPINE_LINES=1`) |
| `docs/state/projects.toml` (default context) | **576,993 B / 9,933 lines** | 149 records, 139 terminal (93.3%); 474 distinct authority-field names; frozen history dominates live state (`raw/projects_toml_metrics.json`) |
| AGENTS.md + README.md + docs/CURRENT_ROADMAP.md | **77,057 B combined** | authority invariants re-phrased three times (`raw/context_metrics.json: DUPLICATIVE_SIGNAL`) |

The cold-start surface that an agent must absorb before doing anything is
therefore ~0.5 MB of default context plus duplicated invariant prose, and even
the bounded summary (brief) overflows its own truncation bound. The target is a
**bounded, deterministic, self-describing packet** that fits in one context
window slice with headroom for task content.

## 2. Proposed byte budget: **8,192 B (8 KB) hard cap, ~7.0 KB target**

Justification from measured data:

1. **8 KB ≈ 56% of the truncated brief (14,468 B)** and **16% of the spine**
   (50,150 B) — i.e. the packet is guaranteed to fit where both current
   surfaces demonstrably do not (brief truncates today).
2. **8 KB ≈ 1.4% of `projects.toml`** (576,993 B): the packet carries
   *pointers* into canonical state, never the state itself.
3. **~7.0 KB working target** leaves ≥1 KB slack for a future task-payload
   echo (e.g. caller-supplied phase id) without breaching the cap.
4. Rough model: at ~4 chars/token the packet is ~2,000 tokens — small enough to
   be read whole by every downstream agent, cheap enough to re-emit per turn.
5. The cap is **enforced by construction**: the renderer fails closed
   (non-zero exit) if the packet exceeds 8,192 B, rather than truncating
   silently — the opposite of today's `BRIEF_TRUNCATED=true` behavior.
   (Rendering is NOT implemented in this audit.)

## 3. Packet field contract

The packet is a single deterministic document with exactly these fields, in
this order, each on one `KEY: value` block:

| Field | Content | Current-state source (measured) | Est. bytes |
|---|---|---|---:|
| `REPOSITORY` | repository identity | `qntylab.toml` `repository_id` (585 B file) | 40 |
| `HEAD` | full commit SHA | `git rev-parse HEAD` (today `be291300…`) | 45 |
| `WORKTREE` | clean/dirty + untracked count | `git status --porcelain` projection | 60 |
| `PHASE_ID` | current canonical project/phase id | `docs/state/projects.toml` non-terminal record (1 `BLOCKED` of 149) | 90 |
| `STATE` | that record's state, verbatim | `docs/state/projects.toml` state field (`STATE_VOCABULARY`) | 40 |
| `OBJECTIVE` | that record's `next_action`, capped at 500 B | `projects.toml` (median `next_action` = 319 B, p90 = 638 B, max = 2,640 B → cap needed) | 520 |
| `AUTHORITY_SOURCE` | pointer to canonical authority map | `qntylab.toml` `authority` section + `AGENTS.md` (2,805 B) by reference | 120 |
| `ALLOWED_OPERATIONS` | ≤5 enumerated ops for the phase | derived from the phase record's authorization fields | 250 |
| `FORBIDDEN_OPERATIONS` | ≤5 enumerated prohibitions (exploratory-only, no trading authority, no runtime-source mutation) | `AGENTS.md` invariant lines, single-sourced | 250 |
| `INPUT_CONTRACTS` | pointers to prereg/manifest inputs the phase consumes | `projects.toml` `authoritative_artifacts` for that record (hash-bound) | 300 |
| `OUTPUT_CONTRACTS` | pointers to frozen outputs + binding hashes | same source, output side | 300 |
| `LOAD_BEARING_INVARIANTS` | ≤7 invariant lines, single-sourced phrasing | distilled once from AGENTS.md/CURRENT_ROADMAP.md invariant prose (currently duplicated across 77,057 B) | 700 |
| `RELEVANT_CODE` | ≤6 file:line pointers | `module_inventory.json`-style classification (15 LIVE_RUNTIME_CODE modules) | 300 |
| `RELEVANT_TESTS` | ≤4 test file pointers | `tests/` map for the phase (215 test py files exist; only relevant listed) | 200 |
| `IMMUTABLE_PATHS` | explicit do-not-touch list (frozen evidence, `docs/state/`) | `deletion_matrix.json` `DELETE_BLOCKED_BY_FROZEN_BINDING` classes (28) | 250 |
| `OPEN_BLOCKERS` | blocker lines from the phase record | `projects.toml` non-terminal record (1 `BLOCKED`) | 200 |
| `REVIEW_LIFECYCLE` | current review stage + next gate | phase record lifecycle fields | 150 |
| `NEXT_ACTION` | one imperative sentence | phase record `next_action` (median 319 B → shortened) | 120 |
| `VERIFY_COMMAND` | the single canonical verify line | README.md:65 `python -m pytest -q` + doctor/render lines | 150 |
| *(envelope: keys, newlines, escaping)* | | | ~1,000 |
| **Total** | | | **≈ 5,090 B typical, ≤ 8,192 B hard cap** |

Notes on the mapping:

- `PHASE_ID`/`STATE`/`OBJECTIVE`/`OPEN_BLOCKERS`/`REVIEW_LIFECYCLE` come from
  the **single non-terminal** record in `docs/state/projects.toml` (measured:
  149 total records, 139 terminal, 9 planned, 1 non-terminal `BLOCKED`). This
  is the key reduction: today the default context loads all 149 records; the
  packet loads one.
- `LOAD_BEARING_INVARIANTS` is the single place invariant phrasing lives;
  AGENTS.md/README/roadmap keep their prose but are referenced, not restated
  (addresses CTX-4 duplication without touching canonical files).
- Every pointer field is a *path + line + hash* triple so the packet is
  verifiable against the frozen tree, not a summary that can silently drift
  (the failure mode that made PR #241's tests pass — fixture-assumes-contract,
  see `raw/test_gap_findings.json`).

## 4. Sizing rules

1. Fixed 20-field schema; renderer rejects unknown/missing fields.
2. Per-field byte caps (table above) are part of the schema; overflow is a
   render error, not silent truncation.
3. Pointer fields (`INPUT_CONTRACTS`, `OUTPUT_CONTRACTS`, `RELEVANT_CODE`,
   `RELEVANT_TESTS`, `IMMUTABLE_PATHS`) carry `path:line` + optional 12-hex
   prefix, never file contents.
4. The packet is additive: it does not replace `brief`, `spine`, or
   `projects.toml`; those remain canonical and untouched.

## 5. Non-implementation

This document is a design target produced by a forensics-only audit. It does
not authorize:

- changes to `qntylab/project_context.py` (110,441 B today),
- changes to `docs/state/projects.toml` or its rendering,
- changes to `brief`/`spine` output, or
- any new code in `qntylab/`.

Implementation, if ever proposed, must go through separate governance with a
`CANDIDATE_PROPOSED` research-ledger event and must preserve
`render --check` semantics unchanged.
