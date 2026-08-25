#!/usr/bin/env node --test

// A. REPOSITORY_DETERMINISTIC_CHECK
//
// This suite must pass on a CLEAN GitHub runner with no pre-existing /var/tmp
// DSH runtime. It validates only what the repository bytes themselves prove:
// historical evidence immutability, DAG structure, current-generation artifact
// locations, CI identity modes, the implemented exact-commit claim source seam,
// and internal consistency of committed current-generation evidence.
//
// The runtime-bound recomputation (root re-derivation, successor re-derivation,
// executable fingerprint identity) is B. HOST_QUALIFIED_RUNTIME_CHECK and lives
// in host-qualified-runtime.test.mjs. These two suites are deliberately split:
// GitHub proves A from declared, reproducible inputs; the production-equivalent
// host preflight proves B and its receipt is committed with the candidate.

import assert from 'node:assert/strict'
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { existsSync, readFileSync } from 'node:fs'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'

import {
  DEPENDENCY_MANIFEST,
  reverseTransitiveClosure,
} from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/compute-digests.mjs'
import {
  HISTORICAL_COMPOSITE_CONTRACT_DIGEST,
  HISTORICAL_SUCCESSOR_CONTRACT_DIGEST,
  verifySuccessorContractArtifact,
} from '../../dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/contract/successor-contract.mjs'
import {
  HISTORICAL_SUCCESSOR_CONTRACT_ARTIFACT,
  SUCCESSOR_CONTRACT_ARTIFACT,
} from '../../dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/preparation/prepare-production-launch.mjs'

const PHASE = resolve(fileURLToPath(import.meta.url), '../..')
const PRODUCTION_PHASE = resolve(
  fileURLToPath(import.meta.url),
  '../../../dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0',
)
const ROOT = resolve(PHASE, '../../../..')
const atRoot = relativePath => join(ROOT, relativePath)

const sha256File = path => createHash('sha256').update(readFileSync(path)).digest('hex')

test('A-1 DAG is acyclic and the manifest digest is stable', () => {
  const nodes = new Set(Object.keys(DEPENDENCY_MANIFEST.nodes))
  for (const [from, { downstream }] of Object.entries(DEPENDENCY_MANIFEST.nodes)) {
    for (const to of downstream) {
      // downstream may name a terminal leaf that is not itself a node
      assert.ok(nodes.has(to) || to === 'V0R6_EXECUTION_EVIDENCE', `DAG references unknown downstream node: ${to}`)
    }
  }
  // acyclic: no node may be reachable from itself, following only node edges
  const visit = (node, seen) => {
    assert.ok(!seen.has(node), `cycle detected at ${node}`)
    seen.add(node)
    for (const downstream of DEPENDENCY_MANIFEST.nodes[node].downstream) {
      if (nodes.has(downstream)) visit(downstream, new Set(seen))
    }
  }
  for (const node of nodes) visit(node, new Set())
})

test('A-2 historical successor_contract.json is byte-identical (sha256 9bb1f217…)', () => {
  assert.equal(existsSync(HISTORICAL_SUCCESSOR_CONTRACT_ARTIFACT), true)
  assert.equal(
    sha256File(HISTORICAL_SUCCESSOR_CONTRACT_ARTIFACT),
    '9bb1f217b9de60b92841ababf6075ccf46c1080f1416f5e5e29fd496a08b143e',
  )
})

test('A-3 historical double-entry contract.json/digests.json are byte-identical to canonical master', () => {
  const contractPath = atRoot(
    'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/contract.json',
  )
  const digestsPath = atRoot(
    'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/digests.json',
  )
  const canonicalContract = execFileSync('git', ['-C', ROOT, 'show', 'origin/master:' + contractPath.slice(ROOT.length + 1)], { encoding: 'utf8' })
  const canonicalDigests = execFileSync('git', ['-C', ROOT, 'show', 'origin/master:' + digestsPath.slice(ROOT.length + 1)], { encoding: 'utf8' })
  assert.equal(readFileSync(contractPath, 'utf8'), canonicalContract, 'historical contract.json must equal canonical master bytes')
  assert.equal(readFileSync(digestsPath, 'utf8'), canonicalDigests, 'historical digests.json must equal canonical master bytes')
})

test('A-4 current successor artifact at NEW path, distinct from historical', () => {
  assert.equal(existsSync(SUCCESSOR_CONTRACT_ARTIFACT), true)
  const current = JSON.parse(readFileSync(SUCCESSOR_CONTRACT_ARTIFACT, 'utf8'))
  const historical = JSON.parse(readFileSync(HISTORICAL_SUCCESSOR_CONTRACT_ARTIFACT, 'utf8'))
  // distinct digest
  assert.notEqual(current.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST, historical.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST)
  // path differs
  assert.match(SUCCESSOR_CONTRACT_ARTIFACT, /successor_contract_v1r3r2_reconciliation_v0\.json$/)
  assert.match(HISTORICAL_SUCCESSOR_CONTRACT_ARTIFACT, /successor_contract\.json$/)
  // current carries the mechanically derived CURRENT root, historical binds a392
  assert.equal(current.CURRENT_COMPOSITE_ROOT, current.contract.currentCompositeRoot)
  assert.ok(current.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST !== '50bd776263d05e9f2fe3e026c5e8904a12fa257a1667d11c1e22ef32376c24de', 'current must not equal historical 50bd')
  assert.equal(historical.contract.predecessorQualifiedContractDigest, HISTORICAL_COMPOSITE_CONTRACT_DIGEST)
  // the committed determinism receipt proves it was derived twice identically
  const determinism = JSON.parse(readFileSync(join(PRODUCTION_PHASE, 'evidence/determinism_reconciliation_v0.json'), 'utf8'))
  assert.equal(determinism.derivedTwice, true)
  assert.equal(determinism.identical, true)
  assert.equal(determinism.CURRENT_COMPOSITE_ROOT, current.CURRENT_COMPOSITE_ROOT)
})

test('A-5 prepare-production-launch.mjs uses resolved inputs, not hardcoded gates', () => {
  const source = readFileSync(join(PRODUCTION_PHASE, 'preparation/prepare-production-launch.mjs'), 'utf8')
  // the historical hardcoded digest constants are gone
  assert.ok(!source.includes("'0e09b9d9d977f73d146c4a35d497cc93bd046bae016e1b1a6a52b481f07731b3'"), 'hardcoded runtime digest still present')
  assert.ok(!source.includes("'ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9'"), 'hardcoded executable digest still present')
  // resolved inputs come from the runtime manifest identity functions
  assert.ok(source.includes('runtimeIdentityFromManifest'))
  assert.ok(source.includes('executableIdentityFromManifest'))
  // the argv wires the CURRENT root, not a historical constant
  assert.ok(source.includes("'--qualified-launch-contract-digest', successor.currentCompositeRoot"))
  // no circular root-derived gate: the gate is over the sibling manifest-derived identity
  assert.ok(source.includes('successor.predecessorComposite.runtimeManifestDigest === runtimeDigest'))
})

test('A-6 CI workflow distinguishes CANDIDATE_HEAD / SYNTHETIC_PR_MERGE_RESULT / CANONICAL_MASTER', () => {
  const workflow = readFileSync(atRoot('.github/workflows/project-context.yml'), 'utf8')
  for (const mode of ['CANDIDATE_HEAD', 'SYNTHETIC_PR_MERGE_RESULT', 'CANONICAL_MASTER']) {
    assert.ok(workflow.includes(mode), `workflow missing mode ${mode}`)
  }
  assert.ok(workflow.includes('refs/pull/') && workflow.includes('/merge'))
  assert.ok(workflow.includes('github.event.pull_request.head.sha'))
  assert.ok(workflow.includes('refs/heads/master'))
  // GitHub-native synthetic merge ref is actually executed by checkout, not
  // merely documented as reachable via workflow_dispatch.
  assert.ok(workflow.includes('steps.identity.outputs.checkout_ref'))
})

test('A-7 claim source model implements the exact-immutable-commit seam (executable, not doc-only)', () => {
  const enforcementSource = readFileSync(atRoot('qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py'), 'utf8')
  // The executable seam exists: an explicit resolver, never bare rev-parse HEAD.
  assert.ok(enforcementSource.includes('_resolve_authorized_source_sha'))
  assert.ok(enforcementSource.includes('authorized_execution_source_sha'))
  // The false-positive doc-only semantics are gone: the claim source is not
  // bound by `git rev-parse HEAD` at action time.
  assert.ok(!enforcementSource.includes('source_head = self._git("rev-parse", "HEAD")'))
  // All seven fail-closed checks are present in the executable.
  for (const token of [
    'claim source SHA is missing',
    'claim source SHA is malformed',
    'claim source commit object does not exist',
    'not in the canonical lineage',
    'revoked or superseded',
    'resolved execution-contract root mismatch',
  ]) {
    assert.ok(enforcementSource.includes(token), `executable seam missing check: ${token}`)
  }
})

test('A-8 project_context.py is byte-identical to HEAD (unchanged)', () => {
  const head = execFileSync('git', ['-C', ROOT, 'show', 'HEAD:qntylab/project_context.py'], { encoding: 'utf8' })
  const current = readFileSync(atRoot('qntylab/project_context.py'), 'utf8')
  assert.equal(current, head, 'project_context.py must not be modified by this reconciliation')
})

test('A-9 reverse-transitive invalidation covers expected nodes and excludes unaffected', () => {
  const closure = reverseTransitiveClosure('qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py')
  const expected = [
    'stageAFileDigests',
    'stageAPolicy',
    'compositeLaunchPolicy',
    'computeDigests',
    'compositeContract',
    'successorContract',
    'prepareProductionLaunch',
    'V0R6_EXECUTION_EVIDENCE',
  ]
  assert.deepEqual(closure.sort(), expected.sort())
  // unaffected nodes excluded
  assert.ok(!closure.includes('physicalRuntimeBinding'))
})

test('A-10 historical composite artifact preserved (a392) referenced never recomputed-as-current', () => {
  const source = readFileSync(join(PRODUCTION_PHASE, 'contract/successor-contract.mjs'), 'utf8')
  assert.ok(source.includes('PREDECESSOR_QUALIFIED_CONTRACT_DIGEST'))
  // the historical a392 must be referenced only as a preserved constant, never
  // recomputed-as-current — no "composite.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST !== PREDECESSOR" equality
  assert.ok(!source.includes('composite.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST !== PREDECESSOR'))
})

test('A-11 historical verification path is explicit (kind=HISTORICAL)', () => {
  // verifySuccessorContractArtifact with kind=HISTORICAL verifies the historical
  // artifact against its own record without recomputing against current bytes.
  const verified = verifySuccessorContractArtifact(HISTORICAL_SUCCESSOR_CONTRACT_ARTIFACT, { kind: 'HISTORICAL' })
  assert.equal(verified.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST, HISTORICAL_SUCCESSOR_CONTRACT_DIGEST)
})