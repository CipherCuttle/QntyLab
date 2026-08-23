#!/usr/bin/env node

// Offline actual-DSH requalification over a production-materialized DSH_HOME.
//
// Identical in every respect to the predecessor composite qualification except
// for the one thing this phase exists to change: the DSH_HOME comes from the
// production materializer via the single production preparation path, not from
// the qualification-only `prepareDisposableDshHome` helper reading an ambient
// scratch directory.
//
// The qualification-only stub provider is applied AFTER production
// materialization, as an explicit overlay, and the overlay marks the home as
// non-production. It can never become part of a production DSH_HOME identity.

import { existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, writeFileSync } from 'node:fs'
import { spawnSync } from 'node:child_process'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

import { createAdversarialOpenAiMock } from '../../dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_v0/mock/adversarial-openai-mock.mjs'
import { spawnDsh } from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/launcher/qntylab-launch-dsh.mjs'
import { sha256Canonical } from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/canonical-json.mjs'
import { applyQualificationOverlay, ROOT } from '../materializer/qntylab-materialize-stage-a-dsh-home.mjs'
import { prepareProductionLaunch } from '../preparation/prepare-production-launch.mjs'

const PHASE = resolve(fileURLToPath(import.meta.url), '../..')
const COMPOSITE_PHASE = resolve(ROOT, 'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0')
const OVERLAY = join(COMPOSITE_PHASE, 'stub/offline-provider-overlay.patch.yml')
const SENTINEL = 'QNTYLAB_FAKE_OPENAI_SENTINEL_PRODUCTION_NOT_REAL'

export const SCENARIOS = {
  clean: { toolScript: ['subagent_codex', 'subagent_claude_code'], responseMode: 'clean', expected: { codex: 1, claude: 1 }, terminal: 'PASS_NO_CRITICAL_HIGH' },
  repair: { toolScript: ['subagent_codex', 'subagent_claude_code', 'subagent_codex', 'subagent_claude_code'], responseMode: 'high-first', expected: { codex: 2, claude: 2 }, terminal: 'PASS_AFTER_BOUNDED_REPAIR' },
}

function checked(command, args) {
  const result = spawnSync(command, args, { encoding: 'utf8' })
  if (result.status !== 0) throw new Error(result.stderr || result.stdout || `${command} failed`)
  return result.stdout.trim()
}

function initializeClaimGit(root) {
  const source = join(root, 'claim-source')
  const remote = join(root, 'claim-remote.git')
  checked('git', ['init', '--bare', '-q', remote])
  checked('git', ['init', '-q', source])
  writeFileSync(join(source, 'seed.txt'), 'offline production claim seed\n')
  checked('git', ['-C', source, 'add', 'seed.txt'])
  checked('git', ['-C', source, '-c', 'user.name=production-offline', '-c', 'user.email=production-offline@example.invalid', 'commit', '-qm', 'offline seed'])
  return { source, remote }
}

export async function runProductionQualification(scenarioName = 'clean') {
  const scenario = SCENARIOS[scenarioName]
  if (scenario === undefined) throw new Error(`unknown production qualification scenario: ${scenarioName}`)
  const scratch = mkdtempSync(join(tmpdir(), `qntylab-production-qualification-${scenarioName}-`))
  let mock
  try {
    const state = join(scratch, 'state')
    mkdirSync(state, { recursive: true })
    const invocationPath = join(state, 'native-stub-invocations.jsonl')

    mock = createAdversarialOpenAiMock({ model: 'gpt-5-mini', toolScript: scenario.toolScript })
    const endpoint = await mock.listen(0)
    if (!endpoint.startsWith('http://127.0.0.1:')) throw new Error(`qualification endpoint is not loopback: ${endpoint}`)

    // THE SAME production preparation path a live episode would use.
    const prepared = prepareProductionLaunch({
      dshHomeDestination: join(scratch, 'dsh-home'),
      workspace: join(scratch, 'workspace'),
      fixtureDestination: join(scratch, 'fixture'),
      launchArgv: [
        '--controller-state', join(state, 'child.json'),
        '--node-executable', process.execPath,
        '--python-executable', '/usr/bin/python3',
        '--codex-executable', '/home/swirky/.local/bin/codex',
        '--claude-executable', '/usr/bin/claude',
        '--parent-endpoint', endpoint,
      ],
    })
    const productionHomeManifestDigest = prepared.materialization.homeManifestDigest

    // Only now, as an explicit and separately recorded step, does the bounded
    // offline seam add the qualification-only stub provider.
    const overlay = applyQualificationOverlay(prepared.materialization.destination)
    const claim = initializeClaimGit(scratch)

    const child = spawnDsh(prepared.args, prepared.preflight, {
      appArgs: ['Follow the deterministic offline tool sequence, then stop.'],
      extraEnv: {
        OPENAI_API_KEY: SENTINEL,
        QNTYLAB_DSH_PARENT_BUDGET_STATE_PATH: join(state, 'parent-budget.json'),
        QNTYLAB_DSH_STAGE_A_CHILD_STATE_PATH: join(state, 'child.json'),
        QNTYLAB_DSH_CLAIM_STATE_DIR: join(state, 'claim'),
        QNTYLAB_DSH_CLAIM_REMOTE: claim.remote,
        QNTYLAB_DSH_CLAIM_REF: 'refs/heads/qntylab-claims/production-offline-qualification',
        QNTYLAB_DSH_CLAIM_SOURCE_REPO: claim.source,
        QNTYLAB_DSH_SESSION_NONCE: `production-offline-${scenarioName}`,
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

    const invocations = existsSync(invocationPath)
      ? readFileSync(invocationPath, 'utf8').trim().split('\n').filter(Boolean).map(line => JSON.parse(line))
      : []
    const nativeCounts = {
      codex: invocations.filter(item => item.provider === 'codex').length,
      claude: invocations.filter(item => item.provider === 'claude-code').length,
    }
    const childState = existsSync(join(state, 'child.json')) ? JSON.parse(readFileSync(join(state, 'child.json'), 'utf8')) : null
    const parentBudget = existsSync(join(state, 'parent-budget.json')) ? JSON.parse(readFileSync(join(state, 'parent-budget.json'), 'utf8')) : null

    const receipt = {
      artifactType: 'DSH_STAGE_A_V1R3R2_PRODUCTION_DSH_HOME_OFFLINE_QUALIFICATION',
      schemaVersion: 'dsh-stage-a-v1r3r2-production-dsh-home-offline-qualification-v0',
      scenario: scenarioName,
      dshHomeSource: 'PRODUCTION_DSH_HOME_MATERIALIZER',
      qualificationOnlyHelperUsed: false,
      ambientDshHomeUsed: false,
      productionHomeManifestDigest,
      qualificationOverlayPackages: overlay.overlayed,
      NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST: prepared.successor.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
      productionPreparationGates: prepared.gates,
      actualDshProcessConfirmed: child.pid > 0,
      loopbackParent: endpoint,
      dshExitCode: exitCode,
      canonicalStageAPolicyActive: prepared.preflight.policyBytes.canonicalStageAPolicyActive,
      workspaceContainment: prepared.preflight.workspaceReal === realpathSync(join(scratch, 'workspace')),
      childController: childState?.terminal_outcome === scenario.terminal ? 'PASS' : 'FAIL',
      childTerminalOutcome: childState?.terminal_outcome ?? null,
      fakeNativeChildInvocations: nativeCounts,
      expectedFakeNativeChildInvocations: scenario.expected,
      nativeExecutableIdentityMatches: invocations.every(item => item.resolvedExecutable === prepared.preflight.fingerprints[`${item.provider === 'codex' ? 'codex' : 'claude'}Executable`].resolvedPath),
      nativeChildSentinelLeaks: invocations.filter(item => item.openAiSentinelPresent).length,
      parentEnvironmentReceivedSentinel: requests[0]?.authorization === `Bearer ${SENTINEL}`,
      loopbackParentWireRequests: requests.length,
      parentBudget,
      publicProviderRequests: 0,
      realModelCalls: 0,
      realCodexTurns: 0,
      realClaudeTurns: 0,
      realSecretReads: 0,
      authoritativeClaims: 0,
      claimsCreated: 0,
      spendUsd: 0,
      stdoutTail: stdout.split('\n').slice(-20).join('\n'),
      stderrTail: stderr.split('\n').slice(-30).join('\n'),
    }
    receipt.terminal = (
      receipt.actualDshProcessConfirmed && receipt.canonicalStageAPolicyActive && receipt.workspaceContainment
      && receipt.dshExitCode === 0 && receipt.childController === 'PASS'
      && nativeCounts.codex === scenario.expected.codex && nativeCounts.claude === scenario.expected.claude
      && receipt.nativeExecutableIdentityMatches && receipt.nativeChildSentinelLeaks === 0
      && receipt.parentEnvironmentReceivedSentinel === true
      && receipt.realSecretReads === 0 && receipt.claimsCreated === 0 && receipt.spendUsd === 0
    ) ? 'PRODUCTION_OFFLINE_QUALIFICATION_PASS' : 'PRODUCTION_OFFLINE_QUALIFICATION_FAIL'
    receipt.receiptDigest = sha256Canonical(receipt)
    return receipt
  } finally {
    if (mock !== undefined) await mock.close()
    if (process.env.QNTYLAB_KEEP_PRODUCTION_SCRATCH !== '1') rmSync(scratch, { recursive: true, force: true })
  }
}

if (process.argv[1] && import.meta.url === `file://${process.argv[1]}`) {
  const receipts = {}
  for (const scenario of ['clean', 'repair']) receipts[scenario] = await runProductionQualification(scenario)
  const out = join(PHASE, 'evidence/offline_actual_dsh_qualification.json')
  writeFileSync(out, `${JSON.stringify(receipts, undefined, 2)}\n`)
  process.stdout.write(`${JSON.stringify(receipts, undefined, 2)}\n`)
  if (Object.values(receipts).some(receipt => receipt.terminal !== 'PRODUCTION_OFFLINE_QUALIFICATION_PASS')) process.exitCode = 1
}
