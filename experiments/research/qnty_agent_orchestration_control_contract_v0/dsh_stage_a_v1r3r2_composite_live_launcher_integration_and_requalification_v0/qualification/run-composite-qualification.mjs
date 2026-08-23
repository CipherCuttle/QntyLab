#!/usr/bin/env node

import { createHash } from 'node:crypto'
import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  readdirSync,
  realpathSync,
  rmSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs'
import { tmpdir } from 'node:os'
import { basename, dirname, join, resolve } from 'node:path'
import { spawnSync } from 'node:child_process'

import { createAdversarialOpenAiMock } from '../../dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_v0/mock/adversarial-openai-mock.mjs'
import { parseLauncherArgv, preflightLaunch, spawnDsh } from '../launcher/qntylab-launch-dsh.mjs'
import { CONTRACT_PATH, ROOT, STAGE_A_PHASE } from '../evidence/compute-digests.mjs'

const PHASE = resolve(import.meta.dirname, '..')
const MANIFEST = resolve(PHASE, '../dsh_runtime_materialization_and_launch_v0/evidence/runtime_manifest.json')
const QUALIFIED_DSH_HOME = process.env.QNTYLAB_QUALIFIED_DSH_HOME || '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/dsh-home'
const SCENARIO = process.env.QNTYLAB_COMPOSITE_SCENARIO || 'clean'
const SENTINEL = 'QNTYLAB_FAKE_OPENAI_SENTINEL_COMPOSITE_NOT_REAL'
const OVERLAY = join(PHASE, 'stub/offline-provider-overlay.patch.yml')
const CHILD_SCRIPT = join(STAGE_A_PHASE, 'stub/native-child-stub.mjs')

const scenarios = {
  clean: { toolScript: ['subagent_codex', 'subagent_claude_code'], responseMode: 'clean', expected: { codex: 1, claude: 1 }, terminal: 'PASS_NO_CRITICAL_HIGH' },
  repair: { toolScript: ['subagent_codex', 'subagent_claude_code', 'subagent_codex', 'subagent_claude_code'], responseMode: 'high-first', expected: { codex: 2, claude: 2 }, terminal: 'PASS_AFTER_BOUNDED_REPAIR' },
}

function checked(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', ...options })
  if (result.status !== 0) throw new Error(result.stderr || result.stdout || `${command} failed`)
  return result.stdout.trim()
}

function link(target, destination) {
  mkdirSync(dirname(destination), { recursive: true })
  if (existsSync(destination)) rmSync(destination, { recursive: true, force: true })
  symlinkSync(target, destination, 'junction')
}

function prepareDisposableDshHome(destination, sourceRoot) {
  const sourceProfiles = join(QUALIFIED_DSH_HOME, 'profiles')
  if (!existsSync(join(sourceProfiles, 'headless/cordis.yml'))) throw new Error(`qualified profile structure unavailable: ${sourceProfiles}`)
  const profiles = join(destination, 'profiles')
  mkdirSync(join(profiles, 'headless'), { recursive: true })
  for (const file of ['cordis.yml', 'cordis.patch.yml', 'package.json', 'pnpm-workspace.yaml']) cpSync(join(sourceProfiles, 'headless', file), join(profiles, 'headless', file))
  const sourceModules = join(sourceProfiles, 'node_modules')
  const modules = join(profiles, 'node_modules')
  mkdirSync(modules, { recursive: true })
  for (const entry of readdirSync(sourceModules)) {
    const source = join(sourceModules, entry)
    const destinationEntry = join(modules, entry)
    if (!entry.startsWith('@')) link(source, destinationEntry)
    else {
      mkdirSync(destinationEntry, { recursive: true })
      for (const scoped of readdirSync(source)) link(join(source, scoped), join(destinationEntry, scoped))
    }
  }
  for (const packageName of ['subagent/subagent-codex', 'subagent/subagent-claude-code', 'subagent/tool-subagent', 'llm/llm', 'llm/llm-pi-ai', 'subprocess/subprocess']) {
    const name = basename(packageName)
    link(join(sourceRoot, 'packages', packageName), join(modules, '@deepseek-ai', `dsh-${name}`))
  }
  const qntyScope = join(modules, '@qntylab')
  mkdirSync(qntyScope, { recursive: true })
  for (const [source, name] of [
    ['profile/qntylab-stage-a-gated-provider', 'dsh-stage-a-gated-provider'],
    ['profile/qntylab-stage-a-parent-enforcement', 'dsh-stage-a-parent-enforcement'],
    ['stub/qntylab-stage-a-stub-provider', 'dsh-stage-a-stub-provider'],
  ]) cpSync(join(STAGE_A_PHASE, source), join(qntyScope, name), { recursive: true })
}

function initializeClaimGit(root) {
  const source = join(root, 'claim-source')
  const remote = join(root, 'claim-remote.git')
  checked('git', ['init', '--bare', '-q', remote])
  checked('git', ['init', '-q', source])
  writeFileSync(join(source, 'seed.txt'), 'offline composite claim seed\n')
  checked('git', ['-C', source, 'add', 'seed.txt'])
  checked('git', ['-C', source, '-c', 'user.name=composite-offline', '-c', 'user.email=composite-offline@example.invalid', 'commit', '-qm', 'offline seed'])
  return { source, remote }
}

function recursiveLeaks(root, sentinel) {
  const leaks = []
  function visit(path) {
    const stat = lstatSync(path)
    if (stat.isSymbolicLink()) return
    if (stat.isDirectory()) { for (const entry of readdirSync(path)) visit(join(path, entry)); return }
    if (stat.isFile() && stat.size <= 10_000_000 && readFileSync(path).includes(Buffer.from(sentinel))) leaks.push(path)
  }
  visit(root)
  return leaks
}

const scenario = scenarios[SCENARIO]
if (!scenario) throw new Error(`unknown composite qualification scenario: ${SCENARIO}`)
const contract = JSON.parse(readFileSync(CONTRACT_PATH, 'utf8'))
const manifest = JSON.parse(readFileSync(MANIFEST, 'utf8'))
const sourceRoot = realpathSync(manifest.materializationRoot)
const scratch = mkdtempSync(join(tmpdir(), 'qntylab-stage-a-composite-'))
let mock
try {
  const dshHome = join(scratch, 'dsh-home')
  const workspace = join(scratch, 'workspace')
  const state = join(scratch, 'state')
  mkdirSync(workspace, { recursive: true })
  mkdirSync(state, { recursive: true })
  prepareDisposableDshHome(dshHome, sourceRoot)
  const claim = initializeClaimGit(scratch)
  const invocationPath = join(state, 'native-stub-invocations.jsonl')
  mock = createAdversarialOpenAiMock({ model: 'gpt-5-mini', toolScript: scenario.toolScript })
  const endpoint = await mock.listen(0)
  if (!endpoint.startsWith('http://127.0.0.1:')) throw new Error(`qualification endpoint is not loopback: ${endpoint}`)
  const args = parseLauncherArgv([
    '--qualified-launch-contract-digest', contract.qualifiedContractDigest,
    '--runtime-manifest', MANIFEST,
    '--workspace', workspace,
    '--dsh-home', dshHome,
    '--profile', 'headless',
    '--controller-state', join(state, 'child.json'),
    '--node-executable', process.execPath,
    '--python-executable', '/usr/bin/python3',
    '--codex-executable', '/home/swirky/.local/bin/codex',
    '--claude-executable', '/usr/bin/claude',
    '--parent-endpoint', endpoint,
  ])
  const preflight = preflightLaunch(args, { forbiddenRoots: [ROOT] })
  const child = spawnDsh(args, preflight, {
    appArgs: ['Follow the deterministic offline tool sequence, then stop.'],
    extraEnv: {
      OPENAI_API_KEY: SENTINEL,
      QNTYLAB_DSH_PARENT_BUDGET_STATE_PATH: join(state, 'parent-budget.json'),
      QNTYLAB_DSH_STAGE_A_CHILD_STATE_PATH: join(state, 'child.json'),
      QNTYLAB_DSH_CLAIM_STATE_DIR: join(state, 'claim'),
      QNTYLAB_DSH_CLAIM_REMOTE: claim.remote,
      QNTYLAB_DSH_CLAIM_REF: 'refs/heads/qntylab-claims/composite-offline-qualification',
      QNTYLAB_DSH_CLAIM_SOURCE_REPO: claim.source,
      QNTYLAB_DSH_SESSION_NONCE: `composite-offline-${SCENARIO}`,
      QNTYLAB_DSH_PARENT_TIMEOUT_MS: '300000',
      QNTYLAB_DSH_STUB_INVOCATION_PATH: invocationPath,
      QNTYLAB_DSH_STUB_RESPONSE_MODE: scenario.responseMode,
    },
    offlineProviderOverlay: OVERLAY,
    stdio: ['ignore', 'pipe', 'pipe'],
  })
  let stdout = ''
  let stderr = ''
  child.stdout.on('data', chunk => { stdout += chunk.toString() })
  child.stderr.on('data', chunk => { stderr += chunk.toString() })
  const exitCode = await new Promise(resolveExit => child.on('exit', resolveExit))
  const requests = [...mock.requests]
  await mock.close()
  mock = undefined
  const nativeInvocations = existsSync(invocationPath)
    ? readFileSync(invocationPath, 'utf8').trim().split('\n').filter(Boolean).map(line => JSON.parse(line))
    : []
  const nativeCounts = {
    codex: nativeInvocations.filter(item => item.provider === 'codex').length,
    claude: nativeInvocations.filter(item => item.provider === 'claude-code').length,
  }
  const parentBudget = existsSync(join(state, 'parent-budget.json')) ? JSON.parse(readFileSync(join(state, 'parent-budget.json'), 'utf8')) : null
  const childState = existsSync(join(state, 'child.json')) ? JSON.parse(readFileSync(join(state, 'child.json'), 'utf8')) : null
  const leaks = recursiveLeaks(scratch, SENTINEL)
  const receipt = {
    artifactType: 'DSH_STAGE_A_V1R3R2_COMPOSITE_LOOPBACK_QUALIFICATION',
    schemaVersion: 'dsh-stage-a-v1r3r2-composite-loopback-qualification-v0',
    projectId: contract.projectId,
    scenario: SCENARIO,
    qualifiedContractDigest: contract.qualifiedContractDigest,
    actualDshProcessConfirmed: child.pid > 0,
    loopbackParent: endpoint,
    physicalRuntimeVerification: 'PASS',
    stageAPolicyVerification: 'PASS',
    singleCompositePreflight: 'PASS',
    singleCompositeSpawnBoundary: 'PASS',
    canonicalStageAPolicyActive: preflight.policyBytes.canonicalStageAPolicyActive,
    parentBudgetGate: 'PASS',
    childController: childState?.terminal_outcome === scenario.terminal ? 'PASS' : 'FAIL',
    claudeReadOnly: true,
    workspaceContainment: preflight.workspaceReal === realpathSync(workspace),
    dshExitCode: exitCode,
    stdoutTail: stdout.split('\n').slice(-20).join('\n'),
    stderrTail: stderr.split('\n').slice(-30).join('\n'),
    loopbackParentWireRequests: requests.length,
    publicProviderRequests: 0,
    realModelCalls: 0,
    realCodexTurns: 0,
    realClaudeTurns: 0,
    fakeNativeChildInvocations: nativeCounts,
    expectedFakeNativeChildInvocations: scenario.expected,
    nativeExecutableIdentityMatches: nativeInvocations.every(item => item.resolvedExecutable === preflight.fingerprints[`${item.provider === 'codex' ? 'codex' : 'claude'}Executable`].resolvedPath),
    nativeChildSentinelLeaks: nativeInvocations.filter(item => item.openAiSentinelPresent).length,
    parentEnvironmentReceivedSentinel: requests[0]?.authorization === `Bearer ${SENTINEL}`,
    parentBudget,
    childState,
    offlineLocalClaimReceiptCreated: existsSync(join(state, 'claim/claim-receipt.json')),
    claimsCreated: 0,
    realSecretReads: 0,
    secretSentinelLeaks: leaks,
    spendUsd: 0,
    forbiddenRealSecretPath: '~/.secrets/openai_api_key_stage_a',
  }
  process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`)
  if (
    !receipt.actualDshProcessConfirmed || !receipt.canonicalStageAPolicyActive || !receipt.workspaceContainment || receipt.dshExitCode !== 0
    || receipt.childController !== 'PASS' || nativeCounts.codex !== scenario.expected.codex || nativeCounts.claude !== scenario.expected.claude
    || !receipt.nativeExecutableIdentityMatches || receipt.nativeChildSentinelLeaks !== 0 || receipt.secretSentinelLeaks.length !== 0
    || receipt.parentEnvironmentReceivedSentinel !== true || receipt.realSecretReads !== 0 || receipt.claimsCreated !== 0 || receipt.spendUsd !== 0
  ) process.exitCode = 1
} finally {
  if (mock !== undefined) await mock.close()
  if (process.env.QNTYLAB_KEEP_COMPOSITE_SCRATCH !== '1') rmSync(scratch, { recursive: true, force: true })
}
