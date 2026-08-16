# ADR 0007: Ecosystem Role Boundary and Context Spine Governance

**Status:** `CURRENT_GLOBAL_ECOSYSTEM_ROLE_BOUNDARY_NO_IMPLEMENTATION_AUTHORIZATION`

## Context

ADR-0005 remains the QntyLab scientific north star. This ADR makes its
cross-repository ownership boundary operationally explicit after a canonical
documentation conflict was found in Qnty. It defines architecture and
provenance semantics only. It does not authorize implementation of a Context
Spine, QNTY_HANDOFF transport, downstream acceptance code, scientific
execution, live operation, or capital deployment.

The distinction between current implementation, target durable ownership,
current authority, future capability, and migration status is mandatory. A
repository may contain code that is preserved during a transition without
that code deciding the target ownership boundary.

## Decision

### Ecosystem role contract

#### QntyLab

QntyLab is the exploratory scientific research and evidence-production
repository. It owns:

```text
mechanism / hypothesis registration
→ outcome-blind data capability qualification
→ scientific contract definition
→ bounded discovery / falsification
→ research ledger
→ Jigsaw / evidence scope
→ economic survivor qualification
→ sealed or prospective confirmation when earned
→ immutable promotion-candidate construction
→ optional QNTY_HANDOFF construction
```

QntyLab does not thereby own Qnty downstream acceptance, live execution,
capital deployment, external-effect authority, or any Qnty runtime action.

#### Qnty

Qnty is the intended downstream consumer and target durable owner of:

```text
downstream acceptance / rejection
→ deterministic replay
→ accounting
→ execution realism
→ paper controls
→ shadow controls
→ live / external-effect controls only when separately authorized
```

Qnty currently contains historical and current research/falsification
machinery. That machinery is preserved and is not silently declared deleted,
migrated, or obsolete by this ADR. The overlap classification is recorded in
the Qnty project-boundary documentation.

#### QntyAgentEval

QntyAgentEval remains an `EXTERNAL_DETERMINISTIC_AGENT_EVALUATOR`. It owns its
task and result contracts and scoring only. It has no scientific authority,
next-action authority, Qnty or QntyLab mutation authority, economic
authority, promotion authority, or live-trading authority.

#### QntyPolicyGate

QntyPolicyGate remains an `EXTERNAL_GIT_GOVERNANCE_POLICY_BOUNDARY`. It owns
its independent policy root and policy evaluation only. It does not prove
scientific validity, economic truth, Qnty acceptance, or runtime authority.
Deployment remains outside this phase.

### QNTY_HANDOFF_V0 semantic contract

`QNTY_HANDOFF_V0` is a normative immutable artifact contract, not a transport
or acceptance implementation. A valid handoff is:

```text
immutable
content-addressable
source-repository-bound
source-commit-bound
authority-ceiling-bound
non-escalating
```

The canonical representation is UTF-8 canonical JSON: recursively sorted
object keys, deterministic array ordering where an array is a set, explicit
nullability, ASCII escaping, and no trailing newline. The handoff digest is
the SHA-256 of those exact bytes. No timestamp, machine path, mutable URL,
ambient environment, or undocumented field may affect identity.

The minimum semantic field set is below. Every field named here is a required
key of the canonical object; a field that does not apply is present with an
explicit `null`. Which keys must carry a non-null value is fixed by the
handoff-class matrix and the economic-survivor binding rule that follow the
table, never by producer judgement.

| Field | Semantic owner | Meaning and required rule | Identity / canonicalization | Authority and non-authority |
|---|---|---|---|---|
| `handoff_contract_version` | joint QntyLab/Qnty contract | Required version of this contract. | Fixed enum, currently `QNTY_HANDOFF_V0`. | Selects semantics; grants no acceptance or operational authority. |
| `handoff_class` | joint QntyLab/Qnty contract | Structural discriminator declaring what the artifact carries. Required and never null. | Fixed enum for this contract version: `EVIDENCE_ONLY`, `RESULT_BEARING`, `PROMOTION_CANDIDATE_BEARING`. | Decides which fields must be non-null; carries no scientific, economic, acceptance, or operational authority. |
| `handoff_digest` | QntyLab artifact producer | Content address of the complete handoff bytes. Required. | SHA-256 over the exact canonical representation. | Binds bytes only; never means accepted or approved. |
| `source_repository` | QntyLab | Repository that produced the handoff. Required. | Canonical repository identity, not a display name. | Establishes provenance; cannot grant Qnty authority. |
| `source_commit` | QntyLab | Git commit whose canonical source produced the handoff. Required. | Full immutable commit ID bound to `source_repository`. | Binds source bytes; does not certify their scientific or runtime meaning. |
| `candidate_id` | QntyLab research ledger | Exact candidate represented by the artifact. Required. | Ledger-owned stable candidate identity. | Identifies research history; cannot grant downstream authority. |
| `candidate_family_id` | QntyLab research ledger | Family identity when the candidate belongs to a registered family. Optional only when no family applies. | Ledger-owned stable family identity. | Groups evidence; cannot broaden a candidate claim. |
| `scientific_contract_digest` | QntyLab | Digest of the governing scientific contract. Requiredness is fixed by the class matrix and the survivor-binding rule. | SHA-256 of canonical contract bytes. | Binds the question and scope; does not prove truth or permanence. |
| `qualified_input_manifest_digest` | QntyLab | Digest of the qualified input manifest used by the candidate. Requiredness is fixed by the class matrix. | SHA-256 of canonical manifest bytes. | Binds inputs; does not grant data, execution, or economic authority. |
| `data_capability_digest` | QntyLab | Digest of the data-capability qualification. Requiredness is fixed by the class matrix. | SHA-256 of canonical qualification bytes. | States capability qualification only; not outcome evidence. |
| `implementation_identity` | Producing repository | Implementation identity used to create the result. Requiredness is fixed by the class matrix. | Explicit binding to commit, declared implementation path/version, and implementation digest; no ambient path. | Reprovenance only; does not authorize execution. |
| `runtime_identity` | Producing runtime owner | Runtime/dependency identity. Requiredness is fixed by the class matrix. | Canonical runtime or lockfile digest plus declared identity. | Reprovenance only; no environment authority. |
| `result_digest` | QntyLab result producer | Digest of the immutable result artifact. Requiredness is fixed by the class matrix. | SHA-256 of exact result bytes. | States what was produced; does not turn a result into truth or acceptance. |
| `evidence_digest` | QntyLab Jigsaw/evidence owner | Digest of the bounded evidence set supporting the handoff. Requiredness is fixed by the class matrix. | SHA-256 of canonical ordered evidence-set manifest. | Preserves evidence scope; cannot escalate the claim. |
| `economic_survivor_decision` | QntyLab | Bounded decision such as `NOT_ASSESSED`, `BLOCKED`, `INCONCLUSIVE`, `NOT_SURVIVOR`, or `SURVIVOR_WITHIN_SCOPE`. Required and never null. | Fixed enum only; no free-form authority wording and no inline decision record. The decision artifact is bound by `economic_survivor_decision_artifact_digest`. | Describes QntyLab's bounded research decision only. |
| `economic_survivor_decision_artifact_digest` | QntyLab | Digest of the immutable artifact that establishes `economic_survivor_decision` and the scope that decision was made within. Non-null exactly when `economic_survivor_decision` is not `NOT_ASSESSED`; otherwise null. | SHA-256 over the exact canonical decision-artifact bytes. Never a candidate ID, ledger reference, path, URL, or query resolved at consumption time. | Binds the decision and its scope to independently inspectable bytes; never means the survivor is profitable, durable, or accepted. |
| `prospective_confirmation_status` | QntyLab scientific contract | Confirmation status, such as `NOT_REQUESTED`, `NOT_EARNED`, `IN_PROGRESS`, `CONFIRMED_WITHIN_SCOPE`, or `BLOCKED`. Optional when the contract has no prospective lane. | Fixed enum bound to the governing contract/evidence when present. | Never implies live, capital, or Qnty acceptance. |
| `promotion_candidate_digest` | QntyLab | Digest of the immutable promotion-candidate artifact. Requiredness is fixed by the class matrix. | SHA-256 of exact candidate artifact bytes. | Candidate construction only; never approval or deployment. |
| `authority_ceiling` | QntyLab contract owner | Maximum proposition the handoff may communicate, never beyond `EVIDENCE_ONLY` or `PROMOTION_CANDIDATE_FOR_DOWNSTREAM_REVIEW`. Required. | Fixed enum; a lower ceiling is valid and cannot be raised downstream by inference. | Explicit upper bound; never live, capital, or automatic Qnty authority. |
| `explicit_non_authorities` | QntyLab contract owner | Required list of authority classes not granted by this artifact. | Canonically sorted fixed tokens. | Must include live trading, capital, automatic Qnty acceptance, scientific permanence, PolicyGate passage, and AgentEval passage unless separately established. |
| `prohibited_interpretations` | Joint contract | Required list of interpretations a consumer must reject. | Canonically sorted fixed tokens. | Fail-closed guard against authority laundering. |
| `downstream_target_repository` | QntyLab contract owner | Intended downstream consumer, normally Qnty. Required for a downstream handoff. | Canonical repository identity. | Routes review only; does not mean that repository accepted it. |
| `downstream_acceptance_contract_version` | Qnty | Version of the downstream contract against which Qnty may evaluate the artifact. Required for a downstream handoff. | Fixed version token, independently interpreted by Qnty. | Declares an expected contract, never an acceptance result. |
| `created_from_canonical_git_identity` | QntyLab | Canonical Git identity used when creating the artifact, including repository and source commit binding. Required. | Canonical object whose bytes participate in the handoff digest. | Proves creation provenance only; it cannot override a later acceptance decision. |

The handoff must never mean `approved for live trading`, `approved for
capital`, `scientifically true forever`, `accepted by Qnty`, `PolicyGate
passed`, or `AgentEval passed` unless a separate authoritative artifact
explicitly establishes that proposition within its own domain.

### Handoff class and mechanical field presence

`handoff_class` is the structural discriminator that makes conditional
requiredness decidable from the artifact bytes alone:

```text
EVIDENCE_ONLY                 carries a bounded evidence set only
RESULT_BEARING                additionally carries an immutable result
PROMOTION_CANDIDATE_BEARING   additionally carries a promotion-candidate binding
```

The classes form a monotone ladder: each class requires everything the class
before it requires. The enum is closed for `QNTY_HANDOFF_V0`. An absent, null,
or unrecognized `handoff_class` is `UNSUPPORTED_CONTRACT`, never a permissive
default and never inferred from which other fields happen to be populated.

#### Field-presence matrix

`MUST` means the key is present and non-null. `MUST NOT` means the key is
present and explicitly `null`. `MAY` means either is valid, and is itself a
decided answer about requiredness rather than producer discretion over it.

| Field | `EVIDENCE_ONLY` | `RESULT_BEARING` | `PROMOTION_CANDIDATE_BEARING` |
|---|---|---|---|
| `scientific_contract_digest` | MAY, and MUST under the survivor-binding rule | MUST | MUST |
| `qualified_input_manifest_digest` | MAY | MUST | MUST |
| `data_capability_digest` | MAY | MAY | MAY |
| `implementation_identity` | MAY | MUST | MUST |
| `runtime_identity` | MAY | MUST | MUST |
| `result_digest` | MUST NOT | MUST | MUST |
| `evidence_digest` | MUST | MUST | MUST |
| `promotion_candidate_digest` | MUST NOT | MUST NOT | MUST |

Every handoff carries a bounded evidence set, so `evidence_digest` is
unconditional and there is no separate evidence-bearing discriminator. A result
is only meaningful if it can be re-provenanced and replayed, so a result-bearing
class binds inputs, implementation, and runtime rather than leaving them to the
producer's reading of whether they "affect interpretation". A class must not
carry the payload of a higher class: `MUST NOT` rows are what stop a
promotion-candidate binding from riding along inside an artifact that declares
itself evidence-only.

`handoff_contract_version`, `handoff_class`, `handoff_digest`,
`source_repository`, `source_commit`, `candidate_id`,
`economic_survivor_decision`, `authority_ceiling`, `explicit_non_authorities`,
`prohibited_interpretations`, and `created_from_canonical_git_identity` are
non-null in every class. `candidate_family_id` and
`prospective_confirmation_status` are `MAY` in every class.

#### Economic survivor binding

```text
IF economic_survivor_decision != NOT_ASSESSED
THEN scientific_contract_digest                 MUST be non-null
 AND economic_survivor_decision_artifact_digest MUST be non-null

IF economic_survivor_decision == NOT_ASSESSED
THEN economic_survivor_decision_artifact_digest MUST be null
```

A bounded decision such as `SURVIVOR_WITHIN_SCOPE` is meaningless without the
scope that defines it. `scientific_contract_digest` binds the question and
scope; `economic_survivor_decision_artifact_digest` binds the immutable artifact
that recorded the decision within that scope. Both are content digests over
exact canonical bytes.

`candidate_id` alone is never sufficient. It names research history, not the
decision or the scope the decision was made within, and it is a ledger-owned
identity rather than inspectable content.

The artifact must remain independently inspectable: a consumer evaluates it from
its own bytes plus the referenced immutable artifacts. A handoff must never
require resolving QntyLab-local mutable state — working-tree contents, ledger
head, index rebuilds, or any lookup answered at consumption time.

A handoff asserting an `economic_survivor_decision` other than `NOT_ASSESSED`
while either required digest is null is `INVALID` under this contract. Contract
validity is decided before the downstream acceptance outcomes below apply, is
decided from bytes, and has no producer-intent exemption.

#### Class is not authority

```text
HANDOFF_CLASS != AUTHORITY
HANDOFF_CLASS != ACCEPTANCE
HANDOFF_CLASS != SCIENTIFIC_TRUTH
```

`handoff_class = PROMOTION_CANDIDATE_BEARING` means only that the artifact
structurally carries a promotion-candidate binding. It never means
scientifically valid, economically profitable, accepted by Qnty, approved for
paper, approved for shadow, approved for live, approved for capital, PolicyGate
passed, or AgentEval passed.

`authority_ceiling` remains independently required and is the only field that
bounds what the artifact may communicate. Class and ceiling are separate domains
and must not be collapsed, including where their tokens look alike:
`handoff_class = EVIDENCE_ONLY` is a statement about payload structure, while
`authority_ceiling = EVIDENCE_ONLY` is a bound on the proposition. Equal-looking
strings are not equal identities.

A class never raises a ceiling. A ceiling lower than the class permits is valid:
`handoff_class = PROMOTION_CANDIDATE_BEARING` with `authority_ceiling =
EVIDENCE_ONLY` structurally carries the binding while communicating evidence
only. The reverse is fail-closed — `authority_ceiling =
PROMOTION_CANDIDATE_FOR_DOWNSTREAM_REVIEW` requires `handoff_class =
PROMOTION_CANDIDATE_BEARING`, so a promotion ceiling can never be claimed
without the promotion-candidate binding it depends on.

### Downstream acceptance

`QNTY_HANDOFF_CREATED` is not `QNTY_HANDOFF_ACCEPTED`. Qnty independently
validates identity, contract support, authority ceiling, artifact availability,
and its own downstream criteria. Abstract outcomes are:

```text
ACCEPTED
REJECTED
BLOCKED
UNSUPPORTED_CONTRACT
INVALID_IDENTITY
INSUFFICIENT_AUTHORITY
```

Acceptance is a separate immutable Qnty-owned decision artifact with its own
identity. It may authorize only the downstream scope that its own contract
states; it cannot upgrade QntyLab evidence into scientific truth, live
authority, or capital authority. Rejection or blocking does not mutate the
source handoff, candidate, result, ledger, or promotion artifact. QntyLab's
artifact remains evidence of what QntyLab produced, while the Qnty artifact
remains evidence of what Qnty decided.

### Shared identity vocabulary

These identities are explicit bindings, not a universal identifier:

| Identity | Owner and scope | Mutability / canonical representation | Cross-repository and authority rule |
|---|---|---|---|
| `REPOSITORY_IDENTITY` | Each repository; repository namespace. | Stable owner/name and provider identity. | May cross repositories for provenance; grants no authority. |
| `GIT_COMMIT_IDENTITY` | The repository containing the commit; exact source state. | Immutable full commit ID. | May cross repositories; binds bytes only. |
| `IMPLEMENTATION_IDENTITY` | Producing repository; code used for a result. | Immutable explicit commit/path/version/digest binding. | May cross repositories; grants no execution authority. |
| `RUNTIME_IDENTITY` | Runtime/dependency owner; environment relevant to a result. | Immutable declared runtime/lock digest for the artifact. | May cross repositories; grants no runtime authority. |
| `CANDIDATE_IDENTITY` | QntyLab research ledger; one registered candidate. | Append-only ledger identity. | May cross as evidence reference; cannot grant authority. |
| `CANDIDATE_FAMILY_IDENTITY` | QntyLab research ledger; candidate family. | Append-only family identity. | May cross for grouping; cannot broaden a candidate claim. |
| `SCIENTIFIC_CONTRACT_IDENTITY` | QntyLab; one scientific question and scope. | Canonical contract digest and declared version. | May cross for review; cannot authorize execution. |
| `DATA_CAPABILITY_IDENTITY` | QntyLab qualification record; capability proposition. | Canonical qualification digest. | May cross as qualification evidence; not outcome truth. |
| `INPUT_MANIFEST_IDENTITY` | Input-manifest owner; exact qualified inputs. | Canonical manifest digest. | May cross for replay; cannot authorize data access. |
| `RESULT_IDENTITY` | Result producer; exact immutable result artifact. | Canonical result digest. | May cross as evidence; cannot grant promotion or live authority. |
| `EVIDENCE_IDENTITY` | QntyLab Jigsaw/evidence owner; bounded evidence set. | Canonical evidence-piece or set digest. | May cross as evidence; cannot escalate claim scope. |
| `PROMOTION_CANDIDATE_IDENTITY` | QntyLab; immutable candidate package. | Canonical candidate-artifact digest. | May cross for downstream review; is not approval. |
| `QNTY_HANDOFF_IDENTITY` | QntyLab producer; exact handoff bytes. | Canonical handoff digest. | May cross for review; never means accepted. |
| `QNTY_ACCEPTANCE_IDENTITY` | Qnty; one acceptance decision for one handoff. | Immutable Qnty decision digest bound to handoff identity. | May cross as downstream evidence; authority is limited to Qnty's contract. |
| `EVALUATOR_REQUEST_IDENTITY` | QntyAgentEval; one evaluator task request. | Immutable request digest bound to task and base commit. | May cross for observation; cannot mutate or authorize repositories. |
| `EVALUATOR_RESULT_IDENTITY` | QntyAgentEval; one deterministic result. | Immutable result digest bound to request. | May cross for scoring evidence; cannot create scientific truth or next action. |
| `POLICY_ROOT_IDENTITY` | QntyPolicyGate; trusted external policy root. | Immutable root version/digest under its own rotation rules. | May cross for policy provenance; authorizes only policy evaluation. |
| `POLICY_DECISION_IDENTITY` | QntyPolicyGate or its declared evaluator; one policy decision. | Immutable decision digest bound to root and target Git identity. | May cross as governance evidence; cannot create economic, scientific, or runtime authority. |

An identity may be referenced by another repository only through an explicit
binding. Equal-looking strings must not be treated as equal identities across
domains.

### Context Spine ownership

The QntyLab `project_context`-style architecture is the future **Context Spine
compiler owner**. It produces a small read-only ecosystem orientation view.
It does not own the canonical state it summarizes and this ADR does not
implement the compiler or its schemas.

```text
QntyLab       → reads its own canonical sources directly
Qnty          → retains canonical continuity and artifact state;
                 future Context Spine access is a narrow read-only adapter
QntyAgentEval → retains evaluator-owned task/result state;
                 only observer status may be summarized
QntyPolicyGate→ retains external policy state;
                 only governance status may be summarized
```

The Context Spine is read-only and must not mutate any repository. It is not
another authority plane, project registry, research ledger, continuity state
machine, evaluator, policy engine, vector database, RAG server, or
LLM-authored encyclopedia. Repository-owned canonical data remains the owner
of history and state.

### Context source precedence and conflicts

Precedence is applied only within a source's legitimate authority domain:

```text
1. current canonical Git identity
2. repository-owned machine-readable authority state
3. current registered ADR / architecture contract
4. append-only ledgers / immutable receipts / artifact manifests
5. validated implementation + tests
6. deterministic generated views
7. README / orientation prose
8. historical artifacts
9. chat / memory / handoff claims
```

Git identity selects the canonical bytes being inspected; it does not allow
one repository to overrule another repository's domain authority. QntyLab's
ADR cannot authorize a Qnty runtime action. Qnty's task state cannot rewrite
QntyLab scientific evidence. AgentEval output cannot create scientific truth.
PolicyGate output cannot create economic truth.

If two primary or canonical sources within their legitimate domains materially
disagree, the compiler must report:

```text
CONTEXT_STATUS = ARCHITECTURE_CONFLICT
```

Architecture-affecting mutation must stop. The conflict must not be resolved
by LLM inference, README preference, or temporal guesswork. A scoped
cross-domain disagreement is surfaced as separate domain statuses rather than
silently collapsed into one authority.

### Architecture Relevance Gate

The default is `ARCHITECTURE_RELEVANCE = NOT_REQUIRED` for local, reversible
work. It is `REQUIRED` for durable architecture-affecting work.

The following deterministic triggers require the smallest relevant canonical
context before mutation:

| Trigger | Why required | Context to load | Fail-closed behavior |
|---|---|---|---|
| New top-level component/package or difficult-to-reverse dependency | Changes ownership or dependency topology. | Current global ADR, repository boundaries, package manifest, relevant project state. | Stop until ownership and dependency direction are explicit. |
| Cross-repository API/interface, QNTY_HANDOFF, or downstream acceptance | Changes a repository boundary or authority transfer. | This ADR, source/consumer contracts, identity vocabulary, relevant repository control docs. | Stop; no implicit interface or authority transfer. |
| Webhook/GitHub integration | Adds an external trust and mutation boundary. | Policy boundary, repository identity contract, integration contract, deployment status. | Stop unless trust root, identity binding, and mutation scope are explicit. |
| Public CLI/API contract | Creates durable consumer semantics. | Current ADR, command/API contract, compatibility policy, tests. | Stop; do not ship an undocumented public contract. |
| Durable JSON/TOML/schema/manifest format | Creates durable identity and compatibility semantics. | Canonicalization rules, owning repository state, relevant ADR, artifact contract. | Stop unless bytes, versioning, and owner are explicit. |
| Candidate, artifact, provenance, or identity semantics | Can change evidence lineage or cross-repository meaning. | Research ledger, artifact registry, identity vocabulary, current ADR. | Stop on ambiguous identity or claim scope. |
| Authority/control/NEXT_ACTION semantics | Can grant or remove operational authority. | Repository control state, continuity contract, policy root, relevant ADR. | Stop; never infer a new authority transition. |
| Scientific execution, promotion, or data-source contract | Can change scientific evidence or downstream eligibility. | Scientific contract, research ledger, input/data capability records, promotion boundary. | Stop; governance alone does not authorize execution. |
| Persistence backend | Changes durability and trust assumptions. | Artifact/continuity contract, storage ownership, threat model, relevant ADR. | Stop without failure-domain and recovery semantics. |
| State Snapshot / Forecaster / Router seam | Changes downstream composition and evidence scope. | ADR-0005 research architecture, project state, component contract. | Stop until composition and non-escalation are explicit. |
| AgentEval or PolicyGate integration | Can be mistaken for scientific or runtime authority. | External contract, identity binding, trust boundary, deployment status. | Stop; observer/governance output cannot be promoted by inference. |

For obvious architecture paths, the path/schema/component mapping is
deterministic; LLM judgment may resolve only genuinely ambiguous cases. A
changed path matching a trigger cannot be exempted merely because the diff is
small. If required context is unavailable or materially conflicting, the
gate fails closed with `ARCHITECTURE_RELEVANCE = REQUIRED` and no mutation.

### Anti-entropy and human orientation invariants

Generic Context Spine code must not hard-code project IDs, candidate IDs,
experiment SHAs, result digests, historical next actions, phase-transition
names, scientific outcomes, evaluator fixture identities, or individual policy
decisions. Generic code interprets schemas and source classifications;
repository-owned canonical data stores history.

Generated views remain derived and are never an authority source.

The future human-facing output remains first class and must eventually answer:

```text
what is this ecosystem?
what does each repository do?
what have I built and why does it exist?
how do I use it and what does it not do?
what is active, blocked, and protected?
what changed recently?
what is the next legitimate action?
which future architecture is relevant to this task?
```

## Consequences and non-goals

This ADR resolves the target role boundary and the semantic contracts needed
before a permanent Context Spine. It does not delete or refactor Qnty
research machinery, migrate continuity state, create handoff bytes, implement
acceptance, execute experiments, deploy PolicyGate, expand AgentEval, or
create any live, paper, shadow, capital, or external-effect authority.

Historical evidence remains interpreted under the contract and scope that
created it. This ADR does not rewrite historical results or turn current
target ownership into a retroactive claim about prior implementation.

## Relationship to ADR-0005

ADR-0005 remains the scientific and research-design north star. This ADR
supersedes only its previously underspecified cross-repository role,
handoff/acceptance, identity, Context Spine, source-precedence, and
architecture-relevance semantics. ADR-0005's research integrity, evidence
non-escalation, and no-implementation-authority constraints remain in force.

That surviving role is machine-readable rather than prose-only. ADR-0005 is
registered as `CURRENT_GLOBAL_COMPANION` with authority scope
`GLOBAL_SCIENTIFIC_NORTH_STAR`, so it stays visible to the context compiler
alongside this ADR. This ADR holds `CURRENT_GLOBAL` and `GLOBAL_ARCHITECTURE`.
The two scopes are disjoint: being the scientific north star confers no
architecture, implementation, or operational authority, and holding the global
architecture confers no scientific truth.
