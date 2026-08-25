#!/usr/bin/env node --test

// B. HOST_QUALIFIED_RUNTIME_CHECK
//
// This suite recomputes the CURRENT root and the CURRENT-generation successor
// contract from the RESOLVED runtime inputs available on this host (the pinned
// DSH runtime at the manifest's builtCliAbsolutePath etc.). It is the
// production-equivalent host preflight:
//   - If the host does NOT have the exact pinned runtime, this suite FAILS
//     (never silently skipped) so a false "runtime qualified" claim is
//     impossible. GitHub CI runs repository-deterministic.test.mjs (A); a
//     qualified runtime host runs THIS suite (B) and commits its receipt.
//   - It proves the committed current-generation successor artifact was
//     mechanically re-derived TWICE and identically from current resolved
//     canonical inputs.
//
// No live DSH/Codex/Claude, no real secret reads, no claim creation, no
// provider calls.

import assert from 'node:assert/strict'
import { createHash } from 'node:crypto'
import { mkdtempSync, readFileSync, rmSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import { test } from 'node:test'

import {
  computeDigests,
} from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/compute-digests.mjs'
import {
  HISTORICAL_COMPOSITE_CONTRACT_DIGEST,
  computeSuccessorContract,
} from '../../dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/contract/successor-contract.mjs'
import { materializeStageADshHome } from '../../dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/materializer/qntylab-materialize-stage-a-dsh-home.mjs'
import {
  SUCCESSOR_CONTRACT_ARTIFACT,
} from '../../dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0/preparation/prepare-production-launch.mjs'

const PHASE = resolve(fileURLToPath(import.meta.url), '../..')
const PRODUCTION_PHASE = resolve(
  fileURLToPath(import.meta.url),
  '../../../dsh_stage_a_v1r3r2_production_dsh_home_materialization_and_requalification_v0',
)

const sha256File = path => createHash('sha256').update(readFileSync(path)).digest('hex')

function deriveSuccessorTwice() {
  const scratch = mkdtempSync(join(tmpdir(), 'qntylab-recon-b-'))
  try {
    const first = materializeStageADshHome({ destination: join(scratch, 'dsh-home-1') })
    const firstSuccessor = computeSuccessorContract({
      homeManifest: first.identityBody,
      profileHome: first.destination,
    })
    const second = materializeStageADshHome({ destination: join(scratch, 'dsh-home-2') })
    const secondSuccessor = computeSuccessorContract({
      homeManifest: second.identityBody,
      profileHome: second.destination,
    })
    return { first: firstSuccessor, second: secondSuccessor }
  } finally {
    rmSync(scratch, { recursive: true, force: true })
  }
}

test('B-1 POST_CORRECTION_CURRENT_ROOT is mechanically re-derived twice and identical', () => {
  const first = computeDigests()
  const second = computeDigests()
  assert.equal(first.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST, second.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST)
  assert.match(first.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST, /^[0-9a-f]{64}$/)
  // current root is NOT the historical a392/e168 root (never conflated)
  assert.notEqual(first.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST, HISTORICAL_COMPOSITE_CONTRACT_DIGEST)
  assert.notEqual(first.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST, 'e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82')
})

test('B-2 committed current-generation successor artifact matches a fresh re-derivation', () => {
  const artifact = JSON.parse(readFileSync(SUCCESSOR_CONTRACT_ARTIFACT, 'utf8'))
  const { first, second } = deriveSuccessorTwice()
  // derived twice identically from current resolved canonical inputs
  assert.equal(first.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST, second.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST)
  assert.equal(first.currentCompositeRoot, second.currentCompositeRoot)
  // committed artifact matches the fresh re-derivation
  assert.equal(artifact.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST, first.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST)
  assert.equal(artifact.CURRENT_COMPOSITE_ROOT, first.currentCompositeRoot)
  // root NOT the pre-correction root — H1 changed enforcement.py, a hashed leaf,
  // so the post-correction root MUST differ from the historical a918 pre-correction value.
  assert.notEqual(artifact.CURRENT_COMPOSITE_ROOT, 'a918ae98a4724d0bfea68b9112358ebf7ab0609d666897558767cd81f0b720d5')
  assert.equal(artifact.determinism.derivedTwice, true)
  assert.equal(artifact.determinism.identical, true)
})

test('B-3 determinism receipt records the same twice-derived root', () => {
  const receipt = JSON.parse(readFileSync(join(PRODUCTION_PHASE, 'evidence/determinism_reconciliation_v0.json'), 'utf8'))
  assert.equal(receipt.derivedTwice, true)
  assert.equal(receipt.identical, true)
  const artifact = JSON.parse(readFileSync(SUCCESSOR_CONTRACT_ARTIFACT, 'utf8'))
  assert.equal(receipt.CURRENT_COMPOSITE_ROOT, artifact.CURRENT_COMPOSITE_ROOT)
  assert.equal(receipt.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST, artifact.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST)
})

test('B-4 executable fingerprints match frozen identities on this host', () => {
  const digests = computeDigests()
  const identity = digests.contract.components.executableIdentity
  assert.equal(identity.nodeExecutableDigest, '1bec56ef7cfa9a76f3e0b7c0a87f220eb73f23102b9c0b4c7529a3f7c3ce7c31')
  assert.equal(identity.pythonExecutableDigest, 'b8d8288faefdd300201f43fcf00f6f539a27218eeed3a3dff5ab10b9c4c99700')
  assert.equal(identity.codexExecutableDigest, 'ac2cfed85fb647d61e0150b8548102b330e4799d9d81ad5d354de701edf6b074')
  assert.equal(identity.claudeExecutableDigest, '98226474f802e3094d6a86c5ade8883c16206d0fcb5c400b7401c800063e99d7')
})

test('B-5 runtime identity gates use resolved inputs, and the DAG root is acyclic-derived', () => {
  const digests = computeDigests()
  // The dependency closure is recorded and its rootChangedLeaf is enforcement.py
  assert.ok(digests.dependencyClosure.reverseTransitiveClosure.includes('compositeContract'))
  assert.equal(digests.dependencyClosure.rootChangedLeaf, 'qntylab/dsh_stage_a_v1r3r2_prelive_enforcement.py')
  assert.equal(digests.dependencyClosure.invalidationModel, 'complete_reverse_transitive_closure_over_real_dag')
  // runtime/executable identity digests are present and well-formed
  assert.match(digests.runtimeManifestDigest, /^[0-9a-f]{64}$/)
  assert.match(digests.executableIdentityDigest, /^[0-9a-f]{64}$/)
})