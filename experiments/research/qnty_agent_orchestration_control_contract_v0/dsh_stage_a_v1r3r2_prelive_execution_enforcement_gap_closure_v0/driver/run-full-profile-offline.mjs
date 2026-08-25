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

import {
  parseLauncherArgv,
  preflightLaunch,
  spawnDsh,
} from '../launcher/qntylab-launch-dsh.mjs'
import { createAdversarialOpenAiMock } from '../mock/adversarial-openai-mock.mjs'

const ROOT = resolve(import.meta.dirname, '../../../../..')
const PHASE = resolve(import.meta.dirname, '..')
const OFFLINE_STUB_PATCH = join(PHASE, 'stub/offline-stub.patch.yml')
const QUALIFIED_IDENTITY = JSON.parse(readFileSync(join(PHASE, 'evidence/digests.json'), 'utf8'))
const MANIFEST = resolve(
  PHASE,
  '../dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0/evidence/runtime_manifest.json',
)
const QUALIFIED_DSH_HOME = process.env.QNTYLAB_QUALIFIED_DSH_HOME
  || '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/dsh-home'
const SENTINEL = 'QNTYLAB_FAKE_OPENAI_SENTINEL_7f6a9151_NOT_REAL'
const MOCK_BEHAVIOR = process.env.QNTYLAB_MOCK_BEHAVIOR || 'success'
const CHILD_SCENARIO = process.env.QNTYLAB_CHILD_SCENARIO
const CHILD_SCENARIOS = {
  codex_codex: {
    tools: ['subagent_codex', 'subagent_codex'],
    responseMode: 'clean',
    expected: { codex: 1, claude: 0 },
  },
  claude_first: {
    tools: ['subagent_claude_code'],
    responseMode: 'clean',
    expected: { codex: 0, claude: 0 },
  },
  clean_then_codex: {
    tools: ['subagent_codex', 'subagent_claude_code', 'subagent_codex'],
    responseMode: 'clean',
    expected: { codex: 1, claude: 1 },
  },
  double_repair: {
    tools: ['subagent_codex', 'subagent_claude_code', 'subagent_codex', 'subagent_codex'],
    responseMode: 'high-first',
    expected: { codex: 2, claude: 1 },
  },
  double_rereview: {
    tools: [
      'subagent_codex', 'subagent_claude_code', 'subagent_codex',
      'subagent_claude_code', 'subagent_claude_code',
    ],
    responseMode: 'high-first',
    expected: { codex: 2, claude: 2 },
  },
  attempt_nine: {
    tools: Array(8).fill('subagent_claude_code'),
    responseMode: 'clean',
    expected: { codex: 0, claude: 0 },
    expectedWireRequests: 8,
    expectedExitCode: 1,
    expectedDenialReason: 'ATTEMPT_CEILING',
  },
  spend_exhaustion: {
    tools: Array(8).fill('subagent_claude_code'),
    responseMode: 'clean',
    expected: { codex: 0, claude: 0 },
    expectedWireRequests: 7,
    expectedExitCode: 1,
    expectedDenialReason: 'AUTHORIZED_SPEND_CAP',
    largePromptChars: 44_000,
  },
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
  if (!existsSync(join(sourceProfiles, 'headless/cordis.yml'))) {
    throw new Error(`qualified profile structure unavailable: ${sourceProfiles}`)
  }
  const profiles = join(destination, 'profiles')
  mkdirSync(join(profiles, 'headless'), { recursive: true })
  for (const file of ['cordis.yml', 'cordis.patch.yml', 'package.json', 'pnpm-workspace.yaml']) {
    const source = join(sourceProfiles, 'headless', file)
    if (existsSync(source)) cpSync(source, join(profiles, 'headless', file))
  }
  const sourceModules = join(sourceProfiles, 'node_modules')
  const modules = join(profiles, 'node_modules')
  mkdirSync(modules, { recursive: true })
  for (const entry of readdirSync(sourceModules)) {
    const source = join(sourceModules, entry)
    const destinationEntry = join(modules, entry)
    if (!entry.startsWith('@')) {
      link(source, destinationEntry)
      continue
    }
    mkdirSync(destinationEntry, { recursive: true })
    for (const scoped of readdirSync(source)) link(join(source, scoped), join(destinationEntry, scoped))
  }
  for (const packageName of [
    'subagent/subagent-codex',
    'subagent/subagent-claude-code',
    'subagent/tool-subagent',
  ]) {
    const name = basename(packageName)
    link(join(sourceRoot, 'packages', packageName), join(modules, '@deepseek-ai', `dsh-${name}`))
  }
  const qntyScope = join(modules, '@qntylab')
  mkdirSync(qntyScope, { recursive: true })
  cpSync(
    join(PHASE, 'profile/qntylab-stage-a-gated-provider'),
    join(qntyScope, 'dsh-stage-a-gated-provider'),
    { recursive: true },
  )
  cpSync(
    join(PHASE, 'profile/qntylab-stage-a-parent-enforcement'),
    join(qntyScope, 'dsh-stage-a-parent-enforcement'),
    { recursive: true },
  )
  cpSync(
    join(PHASE, 'stub/qntylab-stage-a-stub-provider'),
    join(qntyScope, 'dsh-stage-a-stub-provider'),
    { recursive: true },
  )
}

function initializeClaimGit(root) {
  const source = join(root, 'claim-source')
  const remote = join(root, 'claim-remote.git')
  checked('git', ['init', '--bare', '-q', remote])
  checked('git', ['init', '-q', source])
  writeFileSync(join(source, 'seed.txt'), 'offline claim seed\n')
  checked('git', ['-C', source, 'add', 'seed.txt'])
  checked('git', [
    '-C', source, '-c', 'user.name=prelive-offline',
    '-c', 'user.email=prelive-offline@example.invalid', 'commit', '-qm', 'offline seed',
  ])
  // The exact immutable scratch source commit the offline claim binds to. The
  // offline claim lineage (refs/remotes/origin/master in the source repo)
  // resolves this exact commit; the operational claim seam verifies it.
  const sourceSha = checked('git', ['-C', source, 'rev-parse', 'HEAD'])
  return { source, remote, sourceSha }
}

function recursiveSentinelLeaks(root, sentinel) {
  const leaks = []
  function visit(path) {
    const stat = lstatSync(path)
    if (stat.isSymbolicLink()) return
    if (stat.isDirectory()) {
      for (const entry of readdirSync(path)) visit(join(path, entry))
      return
    }
    if (!stat.isFile() || stat.size > 10_000_000) return
    const body = readFileSync(path)
    if (body.includes(Buffer.from(sentinel))) leaks.push(path)
  }
  visit(root)
  return leaks
}

const scratch = mkdtempSync(join(tmpdir(), 'qntylab-stage-a-full-profile-'))
let mock
try {
  const manifest = JSON.parse(readFileSync(MANIFEST, 'utf8'))
  const sourceRoot = realpathSync(manifest.materializationRoot)
  const dshHome = join(scratch, 'dsh-home')
  const workspace = join(scratch, 'workspace')
  const state = join(scratch, 'state')
  mkdirSync(workspace, { recursive: true })
  mkdirSync(state, { recursive: true })
  prepareDisposableDshHome(dshHome, sourceRoot)
  const claim = initializeClaimGit(scratch)
  const scenario = CHILD_SCENARIO === undefined ? undefined : CHILD_SCENARIOS[CHILD_SCENARIO]
  if (CHILD_SCENARIO !== undefined && scenario === undefined) {
    throw new Error(`unknown child scenario: ${CHILD_SCENARIO}`)
  }
  const invocationPath = join(state, 'native-stub-invocations.jsonl')

  mock = createAdversarialOpenAiMock({
    model: 'gpt-5-mini',
    behavior: MOCK_BEHAVIOR,
    toolScript: scenario?.tools ?? [],
  })
  const endpoint = await mock.listen(0)
  const args = parseLauncherArgv([
    '--qualified-launch-contract-digest', QUALIFIED_IDENTITY.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
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
  // The offline full-profile qualification supplies a SCRATCH claim binding:
  // exact scratch source commit SHA (the seed commit pushed to the scratch
  // bare remote) plus an explicit scratch revocation state. It never invents a
  // future live source SHA and never defaults NOT_REVOKED; the values are
  // transported by the launcher exactly as supplied.
  const claimBinding = {
    authorizedExecutionSourceSha: claim.sourceSha,
    executionContractRoot: QUALIFIED_IDENTITY.NEW_QUALIFIED_LAUNCH_CONTRACT_DIGEST,
    runtimeIdentityDigest: QUALIFIED_IDENTITY.NEW_RUNTIME_MANIFEST_DIGEST,
    executableIdentityDigest: QUALIFIED_IDENTITY.NEW_EXECUTABLE_IDENTITY_DIGEST,
    revocationState: 'NOT_REVOKED',
  }
  const child = spawnDsh(args, preflight, {
    appArgs: [
      scenario === undefined
        ? 'Return one short offline confirmation. Do not call any tool.'
        : scenario.largePromptChars === undefined
          ? 'Follow the offline mock tool requests. This is a hostile sequence test.'
          : `Offline spend exhaustion input. ${'x'.repeat(scenario.largePromptChars)}`,
    ],
    extraEnv: {
      OPENAI_API_KEY: SENTINEL,
      QNTYLAB_DSH_PARENT_BUDGET_STATE_PATH: join(state, 'parent-budget.json'),
      QNTYLAB_DSH_STAGE_A_CHILD_STATE_PATH: join(state, 'child.json'),
      QNTYLAB_DSH_CLAIM_STATE_DIR: join(state, 'claim'),
      QNTYLAB_DSH_CLAIM_REMOTE: claim.remote,
      QNTYLAB_DSH_CLAIM_REF: 'refs/heads/qntylab-claims/offline-test-full-profile',
      QNTYLAB_DSH_CLAIM_SOURCE_REPO: claim.source,
      QNTYLAB_DSH_SESSION_NONCE: 'offline-full-profile-session',
      QNTYLAB_DSH_PARENT_TIMEOUT_MS: MOCK_BEHAVIOR === 'timeout' ? '200' : '300000',
      ...(scenario === undefined ? {} : {
        QNTYLAB_DSH_STUB_INVOCATION_PATH: invocationPath,
        QNTYLAB_DSH_STUB_RESPONSE_MODE: scenario.responseMode,
      }),
    },
    offlineProfilePatch: scenario === undefined ? undefined : OFFLINE_STUB_PATCH,
    claimBinding,
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
  const parentBudgetPath = join(state, 'parent-budget.json')
  const parentBudget = existsSync(parentBudgetPath)
    ? JSON.parse(readFileSync(parentBudgetPath, 'utf8'))
    : null
  const leaks = [
    ...recursiveSentinelLeaks(scratch, SENTINEL),
    ...(stdout.includes(SENTINEL) ? ['<stdout>'] : []),
    ...(stderr.includes(SENTINEL) ? ['<stderr>'] : []),
  ]
  const nativeInvocations = existsSync(invocationPath)
    ? readFileSync(invocationPath, 'utf8').trim().split('\n').filter(Boolean).map(line => JSON.parse(line))
    : []
  const nativeCounts = {
    codex: nativeInvocations.filter(item => item.provider === 'codex').length,
    claude: nativeInvocations.filter(item => item.provider === 'claude-code').length,
  }
  const nativeExecutableIdentityMatches = nativeInvocations.every(item => (
    item.resolvedExecutable === preflight.fingerprints[`${item.provider === 'codex' ? 'codex' : 'claude'}Executable`].resolvedPath
  ))
  const receipt = {
    mockBehavior: MOCK_BEHAVIOR,
    childScenario: CHILD_SCENARIO ?? null,
    exitCode,
    stdout,
    stderrTail: stderr.split('\n').slice(-30).join('\n'),
    mockParentWireRequests: requests.length,
    modelFacingTools: (requests[0]?.body?.tools ?? []).map(tool => tool.function?.name),
    observedToolResultMessages: requests.flatMap(request =>
      (request.body?.messages ?? [])
        .filter(message => message.role === 'tool')
        .map(message => String(message.content))),
    parentEnvironmentReceivedSentinel: requests[0]?.authorization === `Bearer ${SENTINEL}`,
    adapterMaxOutputTokens:
      requests[0]?.body?.max_completion_tokens
      ?? requests[0]?.body?.max_tokens
      ?? requests[0]?.body?.max_output_tokens
      ?? null,
    parentBudget,
    claimReceiptPresent: existsSync(join(state, 'claim/claim-receipt.json')),
    attemptedChildCalls: scenario?.tools.length ?? 0,
    nativeStubInvocationCounts: nativeCounts,
    nativeStubExecutableIdentityMatches: nativeExecutableIdentityMatches,
    nativeStubSentinelLeaks: nativeInvocations.filter(item => item.openAiSentinelPresent).length,
    childState: existsSync(join(state, 'child.json'))
      ? JSON.parse(readFileSync(join(state, 'child.json'), 'utf8'))
      : null,
    sentinelSha256: createHash('sha256').update(SENTINEL).digest('hex'),
    secretSentinelLeaks: leaks,
    realSecretReads: 0,
    realClaims: 0,
    externalModelRequests: 0,
    spendUsd: 0,
  }
  const expectedWireRequests = scenario?.expectedWireRequests
    ?? (scenario === undefined ? 1 : scenario.tools.length + 1)
  const expectedExitCode = scenario?.expectedExitCode
    ?? (MOCK_BEHAVIOR === 'success' ? 0 : 1)
  process.stdout.write(`${JSON.stringify(receipt, null, 2)}\n`)
  if (
    exitCode !== expectedExitCode
    || receipt.mockParentWireRequests !== expectedWireRequests
    || receipt.parentEnvironmentReceivedSentinel !== true
    || receipt.adapterMaxOutputTokens > 4096
    || receipt.adapterMaxOutputTokens === null
    || parentBudget?.attempts_reserved !== expectedWireRequests
    || !receipt.claimReceiptPresent
    || leaks.length !== 0
    || (scenario !== undefined && (
      nativeCounts.codex !== scenario.expected.codex
      || nativeCounts.claude !== scenario.expected.claude
      || !nativeExecutableIdentityMatches
      || receipt.nativeStubSentinelLeaks !== 0
      || (scenario.expectedDenialReason !== undefined
        && parentBudget?.denials?.at(-1)?.reason !== scenario.expectedDenialReason)
    ))
  ) {
    process.exitCode = 1
  }
} finally {
  if (mock !== undefined) await mock.close()
  if (process.env.QNTYLAB_KEEP_OFFLINE_SCRATCH !== '1') {
    rmSync(scratch, { recursive: true, force: true })
  }
}
