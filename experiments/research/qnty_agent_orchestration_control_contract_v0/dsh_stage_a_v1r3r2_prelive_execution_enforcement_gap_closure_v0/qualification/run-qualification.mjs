import { spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'

const DRIVER = fileURLToPath(new URL('../driver/run-full-profile-offline.mjs', import.meta.url))

const cases = [
  { id: 'parent_success', behavior: 'success', wire: 1, exitCode: 0 },
  { id: 'parent_429', behavior: '429', wire: 1, exitCode: 1 },
  { id: 'parent_500', behavior: '500', wire: 1, exitCode: 1 },
  { id: 'parent_timeout', behavior: 'timeout', wire: 1, exitCode: 1 },
  { id: 'parent_connection', behavior: 'connection', wire: 1, exitCode: 1 },
  { id: 'claude_first', scenario: 'claude_first', wire: 2, native: { codex: 0, claude: 0 } },
  { id: 'codex_codex', scenario: 'codex_codex', wire: 3, native: { codex: 1, claude: 0 } },
  { id: 'clean_then_codex', scenario: 'clean_then_codex', wire: 4, native: { codex: 1, claude: 1 } },
  { id: 'double_repair', scenario: 'double_repair', wire: 5, native: { codex: 2, claude: 1 } },
  { id: 'double_rereview', scenario: 'double_rereview', wire: 6, native: { codex: 2, claude: 2 } },
  {
    id: 'attempt_nine', scenario: 'attempt_nine', wire: 8, exitCode: 1,
    native: { codex: 0, claude: 0 }, denial: 'ATTEMPT_CEILING',
  },
  {
    id: 'spend_exhaustion', scenario: 'spend_exhaustion', wire: 7, exitCode: 1,
    native: { codex: 0, claude: 0 }, denial: 'AUTHORIZED_SPEND_CAP',
  },
]

function controlledEnvironment(item) {
  return Object.fromEntries(Object.entries({
    PATH: process.env.PATH,
    HOME: process.env.HOME,
    LANG: process.env.LANG,
    TMPDIR: process.env.TMPDIR,
    QNTYLAB_QUALIFIED_DSH_HOME: process.env.QNTYLAB_QUALIFIED_DSH_HOME,
    QNTYLAB_MOCK_BEHAVIOR: item.behavior,
    QNTYLAB_CHILD_SCENARIO: item.scenario,
  }).filter(([, value]) => value !== undefined))
}

function execute(item) {
  const result = spawnSync(process.execPath, [DRIVER], {
    encoding: 'utf8',
    env: controlledEnvironment(item),
    maxBuffer: 100 * 1024 * 1024,
    timeout: 120_000,
  })
  if (result.error) throw result.error
  if (result.status !== 0) {
    throw new Error(`${item.id} qualification driver failed: ${result.stderr || result.stdout}`)
  }
  const receipt = JSON.parse(result.stdout)
  const expectedExit = item.exitCode ?? 0
  const denial = receipt.parentBudget?.denials?.at(-1)?.reason ?? null
  const native = receipt.nativeStubInvocationCounts
  if (
    receipt.exitCode !== expectedExit
    || receipt.mockParentWireRequests !== item.wire
    || receipt.parentBudget?.attempts_reserved !== item.wire
    || receipt.parentEnvironmentReceivedSentinel !== true
    || receipt.adapterMaxOutputTokens !== 4096
    || receipt.claimReceiptPresent !== true
    || receipt.nativeStubSentinelLeaks !== 0
    || receipt.secretSentinelLeaks.length !== 0
    || receipt.realSecretReads !== 0
    || receipt.realClaims !== 0
    || receipt.externalModelRequests !== 0
    || receipt.spendUsd !== 0
    || (item.native !== undefined && (
      native.codex !== item.native.codex || native.claude !== item.native.claude
    ))
    || (item.denial !== undefined && denial !== item.denial)
  ) throw new Error(`${item.id} qualification invariant failed`)
  return {
    id: item.id,
    dshExitCode: receipt.exitCode,
    logicalParentRequestsReserved: receipt.parentBudget.attempts_reserved,
    actualMockProviderWireAttempts: receipt.mockParentWireRequests,
    adapterMaxOutputTokens: receipt.adapterMaxOutputTokens,
    authorizedSpendUsd: receipt.parentBudget.authorized_spend_usd,
    denial,
    attemptedChildCalls: receipt.attemptedChildCalls,
    nativeStubInvocationCounts: native,
    parentEnvironmentReceivedSentinel: true,
    nativeChildSentinelLeaks: 0,
    persistedOrCapturedSentinelLeaks: 0,
  }
}

const results = cases.map(execute)
const output = {
  artifact_type: 'DSH_STAGE_A_V1R3R2_PRELIVE_EXECUTION_ENFORCEMENT_QUALIFICATION',
  schema_version: 'dsh-stage-a-v1r3r2-prelive-execution-enforcement-qualification-v0',
  project_id: 'DSH_STAGE_A_V1R3R2_PRELIVE_EXECUTION_ENFORCEMENT_GAP_CLOSURE_V0',
  qualification_run_count: 1,
  qualification_mode: 'FULL_PROFILE_LIVE_EQUIVALENT_OFFLINE',
  cases: results,
  summary: {
    verdict: 'PASS',
    cases_passed: results.length,
    cases_failed: 0,
    runtime_bytes_changed: false,
    launch_policy_changed: true,
    qualified_identity_covered_bytes_changed: true,
    old_qualified_digest_still_valid: false,
    real_secret_reads: 0,
    real_claims: 0,
    external_model_requests: 0,
    spend_usd: 0,
  },
}
process.stdout.write(`${JSON.stringify(output, null, 2)}\n`)
