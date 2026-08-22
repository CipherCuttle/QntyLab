import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import test from 'node:test'
import { fileURLToPath } from 'node:url'

import {
  CANDIDATE_CONTRACT_DIGEST,
  HISTORICAL_CONTRACT_DIGEST,
  buildArtifacts,
} from '../driver/compute-contract-digests.mjs'
import { sha256Canonical } from '../../dsh_stage_a_v1r3r1_real_runtime_qualification_v0/evidence/canonical-json.mjs'

const PHASE = fileURLToPath(new URL('../', import.meta.url))
const qualification = JSON.parse(readFileSync(`${PHASE}/qualification.json`, 'utf8'))
const contractReceipt = JSON.parse(readFileSync(`${PHASE}/evidence/contract.json`, 'utf8'))
const digestReceipt = JSON.parse(readFileSync(`${PHASE}/evidence/digests.json`, 'utf8'))
const differential = JSON.parse(readFileSync(`${PHASE}/evidence/contract_diff.json`, 'utf8'))

test('historical e3b contract remains immutable historical evidence', () => {
  const artifacts = buildArtifacts()
  assert.equal(artifacts.summary.oldQualifiedDigest, HISTORICAL_CONTRACT_DIGEST)
  assert.equal(artifacts.summary.oldContractRecomputedDigest, HISTORICAL_CONTRACT_DIGEST)
  assert.equal(artifacts.summary.oldContractPreserved, true)
  assert.equal(artifacts.contract.predecessor.historicalContractPreserved, true)
  assert.notEqual(artifacts.summary.newQualifiedDigest, HISTORICAL_CONTRACT_DIGEST)
})

test('successor binds the exact pinned source and toolchain', () => {
  const physical = contractReceipt.components.launchPolicy.physicalLaunch
  assert.deepEqual(physical.source, {
    remote: 'https://github.com/deepseek-ai/deepseek-harness.git',
    commit: '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca',
    tree: '3bc8f89fe494a4755c188be354add4e8b1e7b188',
    tag: 'dsh-v0.1.0-rc.7',
  })
  assert.equal(physical.toolchain.declaredPackageManager, 'pnpm@11.7.0')
  assert.equal(physical.toolchain.actualPackageManager, '11.7.0')
  assert.equal(physical.toolchain.node, 'v22.22.0')
  assert.equal(physical.toolchain.corepack, '0.34.0')
  assert.equal(physical.toolchain.lockfileDigest, 'f517dc3978d57531cda747df62a2abdde1df5b9f25415fcf1fc5d51f8b7547ea')
})

test('successor binds both governed patches, build, runtime, executable, and launch identities', () => {
  const physical = contractReceipt.components.launchPolicy.physicalLaunch
  assert.deepEqual(physical.governedPatches.map(patch => patch.digest), [
    'f89bf5833956f3c4202ca88a9285e39658976b29605fc1b63b7c62ebdd07fcb3',
    '2b8277bf13e077651046e2527dc7aa092c3c9669cedc61eac1f742d9364a17e3',
  ])
  assert.equal(physical.build.entrypoint, 'apps/cli/lib/bin.js')
  assert.equal(physical.build.entrypointDigest, 'c0226687bb20f45c603ec6fe50f3de16d1c3510c3a803304ec575ef9bc366c62')
  assert.equal(digestReceipt.runtimeManifestDigest, '0e09b9d9d977f73d146c4a35d497cc93bd046bae016e1b1a6a52b481f07731b3')
  assert.equal(digestReceipt.executableIdentityDigest, 'ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9')
  assert.equal(digestReceipt.launchPolicyDigest, '00336402a7b34757ba05194ae083805b84f699f1f706990278b9aaf121e973b4')
  assert.equal(sha256Canonical(contractReceipt.components.runtimeIdentity), digestReceipt.runtimeManifestDigest)
  assert.equal(sha256Canonical(contractReceipt.components.executableIdentity), digestReceipt.executableIdentityDigest)
  assert.equal(sha256Canonical(contractReceipt.components.launchPolicy), digestReceipt.launchPolicyDigest)
})

test('candidate c98 is deterministic but the complete successor digest is different', () => {
  const artifacts = buildArtifacts()
  assert.equal(artifacts.summary.candidateRecomputedDigest, CANDIDATE_CONTRACT_DIGEST)
  assert.equal(artifacts.summary.candidateMatch, true)
  assert.equal(artifacts.summary.newQualifiedDigest, 'e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82')
  assert.notEqual(artifacts.summary.newQualifiedDigest, CANDIDATE_CONTRACT_DIGEST)
  assert.equal(sha256Canonical(artifacts.contract.qualifiedContract), artifacts.summary.newQualifiedDigest)
})

test('source and launcher substitutions change the successor digest', () => {
  const artifacts = buildArtifacts()
  for (const mutate of [
    contract => { contract.components.launchPolicy.physicalLaunch.source.commit = 'substituted' },
    contract => { contract.components.launchPolicy.physicalLaunch.launcher.digest = 'substituted' },
  ]) {
    const mutated = structuredClone(artifacts.contract)
    mutate(mutated)
    mutated.qualifiedContract.LAUNCH_POLICY_DIGEST = sha256Canonical(mutated.components.launchPolicy)
    assert.notEqual(sha256Canonical(mutated.qualifiedContract), artifacts.summary.newQualifiedDigest)
  }
})

test('old contract cannot satisfy the exact new physical package-manager identity', () => {
  const artifacts = buildArtifacts()
  const historical = artifacts.contract.components.launchPolicy.stageA
  assert.equal(historical.parentPolicy.maximumLogicalRequests, 8)
  assert.notEqual('11.22.0', artifacts.contract.components.launchPolicy.physicalLaunch.toolchain.actualPackageManager)
  assert.notEqual(
    historical.projectId,
    artifacts.contract.components.launchPolicy.projectId,
  )
})

test('successor preserves parent, child, claim, and Claude hard-read-only constraints', () => {
  const policy = contractReceipt.components.launchPolicy
  assert.equal(policy.stageA.parentPolicy.maximumLogicalRequests, 8)
  assert.equal(policy.stageA.parentPolicy.maximumOutputTokens, 4096)
  assert.equal(policy.stageA.parentPolicy.providerInternalRetries, 0)
  assert.equal(policy.stageA.parentPolicy.authorizedSpendCapUsd, '1.00')
  assert.deepEqual(policy.stageA.childPolicy.exactOrder, [
    'codex_initial', 'claude_review', 'codex_repair_if_critical_high', 'claude_rereview_if_repaired',
  ])
  assert.equal(policy.stageA.childPolicy.codexMaximum, 2)
  assert.equal(policy.stageA.childPolicy.claudeMaximum, 2)
  assert.equal(policy.stageA.claimPolicy.createOnlyRemoteGitRef, true)
  assert.deepEqual(policy.stageA.claudePolicy.allowedTools, ['Read', 'Glob', 'Grep'])
  assert.equal(policy.stageA.claudePolicy.writeAllowed, false)
  assert.equal(policy.stageA.claudePolicy.bashAllowed, false)
  assert.equal(policy.stageA.claudePolicy.delegationAllowed, false)
})

test('contract differential has no removed bindings or weakening', () => {
  assert.deepEqual(differential.REMOVED_BINDINGS, [])
  assert.ok(Object.values(differential.weakeningChecks).every(Boolean))
  assert.ok(differential.ADDED_BINDINGS.includes('components.launchPolicy.physicalLaunch'))
})

test('successor contract creates no execution authority', () => {
  const firewall = contractReceipt.components.launchPolicy.authorityFirewall
  assert.equal(firewall.liveExecutionAuthorized, false)
  assert.equal(firewall.claimAuthorized, false)
  assert.equal(firewall.realSecretReadAuthorized, false)
  assert.equal(firewall.realProviderIoAuthorized, false)
  assert.equal(firewall.stageBAuthorized, false)
  assert.equal(firewall.qntyRuntimeAuthority, 'NONE')
  assert.equal(firewall.scientificExecutionAuthorized, false)
  assert.equal(firewall.tradingAuthority, 'NONE')
  assert.equal(firewall.capitalAuthority, 'NONE')
})

test('ACTIVE_PROJECT remains NONE and no live counters are introduced', () => {
  assert.equal(qualification.active_project_after, 'NONE')
  assert.equal(qualification.authority_firewall.live_execution_authorized, false)
  assert.equal(qualification.authority_firewall.claim_authorized, false)
  assert.equal(qualification.authority_firewall.real_secret_read_authorized, false)
  assert.equal(qualification.authority_firewall.real_provider_io_authorized, false)
  assert.equal(qualification.authority_firewall.stage_b_authorized, false)
  assert.deepEqual(qualification.counters, {
    real_secret_reads: 0,
    real_provider_requests: 0,
    real_model_calls: 0,
    real_child_turns: 0,
    claims_created: 0,
    spend_usd: 0,
  })
})

test('loopback qualification is reused and no rebuild is claimed', () => {
  assert.equal(qualification.evidence_reuse.loopback_reused, true)
  assert.equal(qualification.evidence_reuse.rebuild_required, false)
  assert.equal(JSON.parse(readFileSync(`${PHASE}/evidence/physical_consistency.json`, 'utf8')).physicalEvidencePass, true)
})
