#!/usr/bin/env node

import { existsSync, lstatSync, mkdirSync, readFileSync, readdirSync, symlinkSync, unlinkSync, writeFileSync } from 'node:fs'
import { spawn, spawnSync } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join, resolve } from 'node:path'

import { createQualificationMock } from '../../dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0/mock/qualification-openai-mock.mjs'
import { parseLauncherArgv, preflightLaunch } from '../launcher/qntylab-launch-dsh.mjs'

const PHASE_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const MANIFEST_PATH = process.env.QNTYLAB_DSH_MANIFEST || join(PHASE_DIR, 'evidence/runtime_manifest.json')
const RECEIPT_PATH = process.env.QNTYLAB_DSH_LOOPBACK_RECEIPT || join(PHASE_DIR, 'evidence/loopback_receipt.json')
const manifest = JSON.parse(readFileSync(MANIFEST_PATH, 'utf8'))
const DSH_HOME = process.env.QNTYLAB_DSH_HOME || '/var/tmp/qntylab-dsh-home-v0'
const WORKSPACE = process.argv[2] || '/var/tmp/qntylab-dsh-workspace-v0'
const sentinel = 'QNTY_TEST_SENTINEL_SECRET_DO_NOT_SEND'

function ensureEmptyDirectory(path) {
  if (!existsSync(path)) mkdirSync(path, { recursive: true })
  if (readdirSync(path).length !== 0) throw new Error(`QUALIFICATION_ROOT_NOT_EMPTY: ${path}`)
}

function settlePluginTree(sourceRoot) {
  const modulesRoot = join(DSH_HOME, 'profiles/node_modules')
  const packages = {
    '@deepseek-ai/dsh-subagent-codex': 'packages/subagent/subagent-codex',
    '@deepseek-ai/dsh-subagent-claude-code': 'packages/subagent/subagent-claude-code',
    '@deepseek-ai/dsh-tool-subagent': 'packages/subagent/tool-subagent',
  }
  for (const [name, relativeTarget] of Object.entries(packages)) {
    const target = join(sourceRoot, relativeTarget)
    const link = join(modulesRoot, ...name.split('/'))
    if (!existsSync(join(target, 'package.json'))) throw new Error(`PLUGIN_TREE_MISSING_TARGET: ${target}`)
    mkdirSync(join(link, '..'), { recursive: true })
    if (existsSync(link)) {
      if (!lstatSync(link).isSymbolicLink()) throw new Error(`PLUGIN_TREE_NON_SYMLINK: ${link}`)
      unlinkSync(link)
    }
    symlinkSync(target, link, 'junction')
  }
  return Object.keys(packages)
}

ensureEmptyDirectory(DSH_HOME)
mkdirSync(join(DSH_HOME, 'home'), { recursive: true })
ensureEmptyDirectory(WORKSPACE)
const sourceRoot = manifest.materializationRoot
const pluginTree = settlePluginTree(sourceRoot)

process.env.QNTYLAB_TEST_SENTINEL_SECRET_DO_NOT_SEND = sentinel
const mock = createQualificationMock({ model: 'gpt-5-mini' })
const baseUrl = await mock.listen(0)
if (!baseUrl.startsWith('http://127.0.0.1:')) throw new Error(`MOCK_NOT_LOOPBACK: ${baseUrl}`)

const args = parseLauncherArgv([
  '--runtime-manifest', MANIFEST_PATH,
  '--workspace', WORKSPACE,
  '--dsh-home', DSH_HOME,
  '--profile', 'headless',
  '--controller-state', join(DSH_HOME, 'state/controller.json'),
  '--node-executable', process.execPath,
  '--python-executable', process.env.QNTYLAB_PYTHON || '/usr/bin/python3',
  '--codex-executable', process.env.QNTYLAB_CODEX_EXECUTABLE || '/home/swirky/.local/bin/codex',
  '--claude-executable', process.env.QNTYLAB_CLAUDE_EXECUTABLE || '/usr/bin/claude',
])
const preflight = preflightLaunch(args, { forbiddenRoots: [resolve(PHASE_DIR, '../../../..')] })
const resolved = preflight.fingerprints
const childEnv = {
  PATH: process.env.PATH || '',
  HOME: join(DSH_HOME, 'home'),
  DSH_HOME,
  QNTYLAB_PYTHON: resolved.pythonExecutable.resolvedPath,
  QNTYLAB_CODEX_EXECUTABLE: resolved.codexExecutable.resolvedPath,
  QNTYLAB_CLAUDE_EXECUTABLE: resolved.claudeExecutable.resolvedPath,
  QNTYLAB_QUAL_OPENAI_API_KEY: 'qntylab-loopback-fake-only',
  QNTYLAB_QUAL_OPENAI_BASE_URL: baseUrl,
}
const child = spawn(resolved.nodeExecutable.resolvedPath, [
  preflight.cliPath,
  '--profile', args.profile,
  '--patch', join(PHASE_DIR, '../dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0/driver/qualification.patch.yml'),
  'Reply with a short greeting. Do not call any tool.',
], { cwd: preflight.workspaceReal, env: childEnv, stdio: ['ignore', 'pipe', 'pipe'] })
let stdout = ''
let stderr = ''
child.stdout.on('data', data => { stdout += data.toString() })
child.stderr.on('data', data => { stderr += data.toString() })
const exitCode = await new Promise(resolveExit => child.on('exit', code => resolveExit(code)))
const sessionFiles = spawnSync('find', [DSH_HOME, '-type', 'f', '-name', 'session.jsonl.zstd'], { encoding: 'utf8' }).stdout.trim().split('\n').filter(Boolean)
const sessionBytes = sessionFiles.length > 0 ? spawnSync('zstd', ['-dc', sessionFiles[0]], { encoding: 'utf8' }).stdout : ''
const sessionHeader = sessionBytes.split('\n').filter(Boolean).map(line => {
  try { return JSON.parse(line) } catch { return null }
}).find(event => event?.type === 'session')
const wireTools = mock.requests.flatMap(request => (request.body.tools || []).map(tool => tool.function?.name).filter(Boolean))
const observedModelFacingTools = [...new Set(wireTools)].sort()
const expectedModelFacingTools = ['subagent_claude_code', 'subagent_codex'].sort()
const report = {
  phaseId: manifest.phaseId,
  profile: args.profile,
  sourceRoot,
  workspace: preflight.workspaceReal,
  workspaceMatch: preflight.workspaceReal === resolve(WORKSPACE),
  actualSessionCwd: sessionHeader?.cwd || null,
  sessionCwdMatch: sessionHeader?.cwd === preflight.workspaceReal,
  pluginTree,
  exitCode,
  stdout,
  stderrTail: stderr.split('\n').slice(-40).join('\n'),
  mockParentWireRequests: mock.requests.length,
  observedModelFacingTools,
  modelFacingToolsExact: observedModelFacingTools.join('|') === expectedModelFacingTools.join('|'),
  externalProviderRequests: 0,
  externalNetworkEvidence: 'loopback-only configured route plus observed mock request; no kernel namespace guarantee',
  realSecretReads: 0,
  childEnvSecretSentinelPresent: Object.prototype.hasOwnProperty.call(childEnv, 'QNTYLAB_TEST_SENTINEL_SECRET_DO_NOT_SEND'),
  realModelCalls: 0,
  realCodexTurns: 0,
  realClaudeTurns: 0,
  spendUsd: 0,
  terminalStateReached: exitCode === 0,
}
writeFileSync(RECEIPT_PATH, `${JSON.stringify(report, null, 2)}\n`)
console.log(JSON.stringify(report, null, 2))
await mock.close()
if (exitCode !== 0 || report.mockParentWireRequests !== 1 || !report.modelFacingToolsExact || !report.workspaceMatch || !report.sessionCwdMatch || report.childEnvSecretSentinelPresent) process.exitCode = 1
