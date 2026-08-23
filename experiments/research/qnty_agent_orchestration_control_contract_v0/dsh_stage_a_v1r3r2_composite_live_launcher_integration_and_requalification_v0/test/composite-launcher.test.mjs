import assert from 'node:assert/strict'
import { copyFileSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from 'node:fs'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import test from 'node:test'

import {
  parseLauncherArgv as parsePhysical,
  preflightLaunch as physicalPreflight,
} from '../../dsh_runtime_materialization_and_launch_v0/launcher/qntylab-launch-dsh.mjs'
import {
  CONTRACT_PATH,
  MANIFEST_DEFAULT,
  ROOT,
  computeDigests,
} from '../evidence/compute-digests.mjs'
import {
  parseLauncherArgv,
  selectedPolicyPatches,
  spawnDsh,
  verifyContractArtifact,
  verifyCompositeLauncherBytes,
  verifyPolicyBytes,
} from '../launcher/qntylab-launch-dsh.mjs'

const DSH_HOME = process.env.QNTYLAB_QUALIFIED_DSH_HOME || '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/dsh-home'
const manifest = JSON.parse(readFileSync(MANIFEST_DEFAULT, 'utf8'))
const contract = JSON.parse(readFileSync(CONTRACT_PATH, 'utf8'))

function physicalArgs(overrides = {}) {
  const scratch = mkdtempSync(join(tmpdir(), 'qntylab-composite-test-'))
  const workspace = join(scratch, 'workspace')
  const args = parsePhysical([
    '--runtime-manifest', overrides.runtimeManifest || MANIFEST_DEFAULT,
    '--workspace', overrides.workspace || workspace,
    '--dsh-home', overrides.dshHome || DSH_HOME,
    '--profile', 'headless',
    '--controller-state', join(scratch, 'child.json'),
    '--node-executable', overrides.nodeExecutable || process.execPath,
    '--python-executable', overrides.pythonExecutable || '/usr/bin/python3',
    '--codex-executable', overrides.codexExecutable || '/home/swirky/.local/bin/codex',
    '--claude-executable', overrides.claudeExecutable || '/usr/bin/claude',
  ])
  return { args, scratch }
}

function mutatedManifest(mutate) {
  const scratch = mkdtempSync(join(tmpdir(), 'qntylab-composite-manifest-'))
  const path = join(scratch, 'runtime_manifest.json')
  const copy = structuredClone(manifest)
  mutate(copy)
  writeFileSync(path, `${JSON.stringify(copy, null, 2)}\n`)
  return { path, scratch }
}

test('successor digest machinery binds current physical runtime without historical digest coupling', () => {
  const source = readFileSync(new URL('../evidence/compute-digests.mjs', import.meta.url), 'utf8')
  const result = computeDigests()
  assert.equal(result.predecessorQualifiedContractDigest, 'e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82')
  assert.equal(result.runtimeManifestDigest, '0e09b9d9d977f73d146c4a35d497cc93bd046bae016e1b1a6a52b481f07731b3')
  assert.equal(result.executableIdentityDigest, 'ae07ece34c88b3ebaebd7452df8d136c82935f9c8ec9df16a40e50a2582a2fd9')
  assert.doesNotMatch(source, /dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0\/evidence\/digests\.json/)
  assert.notEqual(result.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST, 'e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82')
})

test('contract artifact is reproducible and the historical e168 contract is preserved, not accepted as current', () => {
  const result = verifyContractArtifact(MANIFEST_DEFAULT, DSH_HOME)
  assert.equal(result.contract.qualifiedContractDigest, contract.qualifiedContractDigest)
  assert.equal(result.contract.predecessor.qualifiedContractDigest, 'e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82')
  assert.equal(result.contract.qualifiedContract.COMPOSITE_LAUNCH_POLICY_CHANGED, true)
  assert.notEqual(result.contract.qualifiedContractDigest, 'e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82')
  assert.equal(parseLauncherArgv(['--qualified-launch-contract-digest', 'e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82']).qualifiedLaunchContractDigest, 'e16872fc1f419e5253d633bbdf35e936bb58e34a7636decb8eda688113658e82')
})

for (const [label, mutate] of [
  ['wrong source commit', value => { value.sourceIdentity.commit = '0000000000000000000000000000000000000000' }],
  ['wrong tree', value => { value.sourceIdentity.tree = '0000000000000000000000000000000000000000' }],
  ['wrong lockfile', value => { value.lockfileDigest = '0'.repeat(64) }],
  ['wrong governed patch', value => { value.patchDigests[0].digest = '0'.repeat(64) }],
  ['wrong built CLI', value => { value.builtCliDigest = '0'.repeat(64) }],
  ['wrong runtime manifest', value => { value.phaseId = 'ARBITRARY_MOVING_BRANCH' }],
  ['arbitrary moving tag', value => { value.sourceIdentity.tag = 'main' }],
]) {
  test(`fails closed before spawn for ${label}`, () => {
    const copy = mutatedManifest(mutate)
    try {
      const { args, scratch } = physicalArgs({ runtimeManifest: copy.path })
      assert.throws(() => physicalPreflight(args, { forbiddenRoots: [ROOT] }), /unexpected|wrong|drifted|inconsistent|identity|phase|qualified/i)
      rmSync(scratch, { recursive: true, force: true })
    } finally { rmSync(copy.scratch, { recursive: true, force: true }) }
  })
}

test('fails closed for wrong action-time executable identity and workspace escape', () => {
  const executable = physicalArgs({ codexExecutable: '/usr/bin/false' })
  assert.throws(() => physicalPreflight(executable.args, { forbiddenRoots: [ROOT] }), /fingerprint mismatch/)
  rmSync(executable.scratch, { recursive: true, force: true })
  const escape = physicalArgs({ workspace: ROOT })
  assert.throws(() => physicalPreflight(escape.args, { forbiddenRoots: [ROOT] }), /inside a forbidden root/)
  rmSync(escape.scratch, { recursive: true, force: true })
})

test('fails closed for missing DSH_HOME profile identity and modified canonical/overlay policy bytes', () => {
  const missing = mkdtempSync(join(tmpdir(), 'qntylab-composite-missing-home-'))
  assert.throws(() => verifyContractArtifact(MANIFEST_DEFAULT, missing), /missing qualified DSH_HOME/)
  rmSync(missing, { recursive: true, force: true })
  const canonical = mkdtempSync(join(tmpdir(), 'qntylab-composite-policy-'))
  const canonicalPath = join(canonical, 'canonical.yml')
  const overlayPath = join(canonical, 'overlay.yml')
  copyFileSync(resolve(ROOT, contract.components.compositeLaunchPolicy.stageAPolicy.canonicalPolicy.path), canonicalPath)
  copyFileSync(resolve(ROOT, contract.components.compositeLaunchPolicy.stageAPolicy.offlineProviderOverlay.path), overlayPath)
  writeFileSync(canonicalPath, `${readFileSync(canonicalPath, 'utf8')}\n# tamper\n`)
  assert.throws(() => verifyPolicyBytes(contract, { canonicalPolicyPath: canonicalPath, offlineProviderOverlayPath: overlayPath }), /canonical Stage-A policy bytes drifted/)
  assert.throws(() => verifyPolicyBytes(contract, { canonicalPolicyPath: join(canonical, 'missing.yml'), offlineProviderOverlayPath: overlayPath }), /ENOENT/)
  rmSync(canonical, { recursive: true, force: true })
})

test('fails closed for substituted composite launcher bytes', () => {
  const scratch = mkdtempSync(join(tmpdir(), 'qntylab-composite-launcher-'))
  const candidate = join(scratch, 'launcher.mjs')
  copyFileSync(new URL('../launcher/qntylab-launch-dsh.mjs', import.meta.url), candidate)
  writeFileSync(candidate, `${readFileSync(candidate, 'utf8')}\n// tamper\n`)
  assert.throws(() => verifyCompositeLauncherBytes(contract, candidate), /composite launcher bytes are not the qualified launcher/)
  rmSync(scratch, { recursive: true, force: true })
})

test('offline substitution is loopback/sentinel-bound and composes canonical policy first', () => {
  const invocation = join(tmpdir(), 'qntylab-composite-invocations.jsonl')
  const args = { parentEndpoint: 'http://127.0.0.1:12345' }
  const env = { OPENAI_API_KEY: 'QNTYLAB_FAKE_TEST_NOT_REAL', QNTYLAB_DSH_STUB_INVOCATION_PATH: invocation, QNTYLAB_DSH_STUB_RESPONSE_MODE: 'clean' }
  const patches = selectedPolicyPatches(args, env, contract.components.compositeLaunchPolicy.stageAPolicy.offlineProviderOverlay.path)
  assert.equal(patches.length, 2)
  assert.throws(() => selectedPolicyPatches({ parentEndpoint: 'https://api.openai.com' }, env, patches[1]), /denied/)
  assert.throws(() => selectedPolicyPatches(args, { ...env, OPENAI_API_KEY: '/home/.secrets/openai_api_key_stage_a' }, patches[1]), /denied/)
  assert.throws(() => selectedPolicyPatches(args, env, '/tmp/alternate-overlay.yml'), /denied|ENOENT/)
})

test('spawn boundary rejects caller policy overrides and forged preflight receipts', () => {
  assert.throws(() => spawnDsh({}, {}, { appArgs: ['--patch', '/tmp/alternate.yml'] }), /cannot override the preflighted profile or policy patch/)
  const source = readFileSync(new URL('../launcher/qntylab-launch-dsh.mjs', import.meta.url), 'utf8')
  assert.match(source, /supplied preflight receipt does not match immediate composite verification/)
  assert.match(source, /const immediate = preflightLaunch\(args/)
})

test('parent, child, Claude, claim, secret, workspace, and alternate-route policies are explicitly identity-bound', () => {
  const policy = contract.components.compositeLaunchPolicy
  assert.deepEqual(policy.parentPolicy, {
    provider: 'openai', model: 'gpt-5-mini', route: 'llm-pi-ai', agentLoopOnly: true, auxiliaryRoutesDenied: true,
    maximumLogicalRequests: 8, maximumOutputTokens: 4096, providerInternalRetries: 0, automaticContinuation: false,
    authorizedSpendCapUsd: '1.00', priceScheduleId: 'openai-gpt-5-mini-2026-08-22-4x-authorization-reserve-v0',
    inputUsdPerMillion: '0.25', outputUsdPerMillion: '2.00', priceUncertaintyMultiplier: '4', nonTextModalitiesDenied: true,
    reservationBeforeAdapterIo: true,
  })
  assert.deepEqual(policy.childPolicy.modelFacingTools, ['subagent_codex', 'subagent_claude_code'])
  assert.equal(policy.childPolicy.codexMaximum, 2)
  assert.equal(policy.childPolicy.claudeMaximum, 2)
  assert.deepEqual(policy.claudePolicy.allowedTools, ['Read', 'Glob', 'Grep'])
  assert.equal(policy.claudePolicy.bashAllowed, false)
  assert.equal(policy.claudePolicy.mcpAllowed, false)
  assert.equal(policy.claudePolicy.persistence, false)
  assert.equal(policy.workspacePolicy.realpathSymlinkAware, true)
  assert.equal(policy.offlineQualification.canonicalStageAPolicyRemainsActive, true)
  assert.deepEqual(policy.stageAPolicy.alternateRoutes.providers, [])
  assert.deepEqual(policy.stageAPolicy.alternateRoutes.models, [])
  assert.deepEqual(policy.stageAPolicy.alternateRoutes.childTools, ['subagent_codex', 'subagent_claude_code'])
  assert.equal(policy.stageAPolicy.alternateRoutes.backgroundDelegation, false)
})
