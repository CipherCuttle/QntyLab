# DSH Stage-A V1R3R2 execution contract reconciliation CORRECTION authorization — evidence findings

Decision: `B — PR217_CORRECTION_AUTHORIZATION_REQUIRED`

## Canonical binding
- Canonical master: `a87ecfda105b84669f3fef862496045284d0a655` (PR #216 merge; parents `ded772d59c6135689ac4bda8878979721855a955`, `f73a15fb5cb84ace8c6ee1d58d60f4d39706fb49`)
- Prior candidate PR #217: `7fb7a70364727f99cd8f9da49552484e1b1aaea8` — OPEN draft, NOT merged
- prior candidate budget: CREATE_ONE_CANDIDATE_COMMIT_AND_ONE_DRAFT_IMPLEMENTATION_PR
  (consumed); terminal stop STOP_AFTER_ONE_CANDIDATE_COMMIT_AND_DRAFT_PR

## C1 — historical composite evidence mutated (PR #217 vs canonical master)
- enforcement.py digest: `5935aae551d1307d12e803a1caba52b83c7e7d19b53077e88f56d53210dc4555` -> `789a592f1da35b0afb07645947bc82696d361623a6150fc4ff37008b2961081f`
- COMPOSITE_LAUNCH_POLICY_DIGEST: `7345ab145a0c98696ce8b9e6d815f4da98092f7be680467278464fb098a51589` -> `fc4bbee747af5ef04ac20f87d22195f916f3736025e0f1c5e2a27fcfbd48c20a`
- qualifiedContractDigest: `a392f82efd5cf97e20a6ce4353597a8a7210e8638cc17e5a4209cc1003eee4be` -> `a918ae98a4724d0bfea68b9112358ebf7ab0609d666897558767cd81f0b720d5`

## H1 — moving-head claim source binding (PR #217 head)
- Path: `qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py:647`
- Line: `source_head = self._git("rev-parse", "HEAD").stdout.strip()`
- Only claim-source-model.md documents the future EXACT_IMMUTABLE_COMMIT model

## H2 — candidate-head CI reproducibility failure
- Missing built CLI: `/var/tmp/qntylab-dsh-runtime-v0-final/source/apps/cli/lib/bin0.js`
- Failing checks: ACCEPTANCE-1, ACCEPTANCE-7 (host ambient /var/tmp dependency)

## Authority decision chain
1. Canonical master a87ecfda105b84669f3fef862496045284d0a655 (PR #216 merge) is the frozen source of truth.
2. PR #217 candidate consumed its one-candidate/draft-PR budget and cannot self-repair:
   enforcement.py is outside FROZEN_FILES_ALLOWED_TO_CHANGE and
   effective_repair_authority = false.
3. BOUNDED AUTHORITY CHECK => AUTHORIZATION_DECISION = B (PR217_CORRECTION_AUTHORIZATION_REQUIRED).

## Live firewall counters (all zero)
real_secret_reads=0, production_claims=0, provider_calls=0, live_dsh_invocations=0,
real_codex_turns=0, real_claude_turns=0, spend_usd="0"
