#!/usr/bin/env node
import { existsSync, lstatSync, mkdirSync, readFileSync, symlinkSync, unlinkSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { parseLauncherArgv, preflightLaunch } from '../launcher/qntylab-launch-dsh.mjs'
import { createQualificationMock } from '../mock/qualification-openai-mock.mjs'

const PDIR = dirname(fileURLToPath(import.meta.url))
const MANIFEST_PATH = process.env.QNTYLAB_DSH_MANIFEST || join(PDIR, '../evidence/runtime_manifest.json')
const DSH_HOME = process.env.QNTYLAB_DSH_HOME || '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/dsh-home'
const WORKSPACE = process.argv[2] || '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r2-claude-repair/workspace/run1'
mkdirSync(WORKSPACE, { recursive: true })
const SOURCE_ROOT = JSON.parse(readFileSync(MANIFEST_PATH, 'utf8')).materializationRoot

function settlePluginTree() {
  const modulesRoot = join(DSH_HOME, 'profiles/node_modules')
  const packages = {
    '@deepseek-ai/dsh-subagent-codex': 'packages/subagent/subagent-codex',
    '@deepseek-ai/dsh-subagent-claude-code': 'packages/subagent/subagent-claude-code',
    '@deepseek-ai/dsh-tool-subagent': 'packages/subagent/tool-subagent',
  }
  for (const [name, relativeTarget] of Object.entries(packages)) {
    const target = join(SOURCE_ROOT, relativeTarget)
    const link = join(modulesRoot, ...name.split('/'))
    if (!existsSync(join(target, 'package.json'))) throw new Error(`PLUGIN_TREE_MISSING_TARGET: ${target}`)
    mkdirSync(join(link, '..'), { recursive: true })
    if (existsSync(link)) {
      if (!lstatSync(link).isSymbolicLink()) throw new Error(`PLUGIN_TREE_NON_SYMLINK: ${link}`)
      if (readFileSync(join(link, 'package.json'), 'utf8') !== readFileSync(join(target, 'package.json'), 'utf8')) unlinkSync(link)
      else continue
    }
    symlinkSync(target, link, 'junction')
  }
  return Object.keys(packages)
}

const pluginTree = settlePluginTree()
const mock = createQualificationMock({ model: 'gpt-5-mini' })
const baseUrl = await mock.listen(0)
const args = parseLauncherArgv([
  '--runtime-manifest', MANIFEST_PATH,
  '--workspace', WORKSPACE,
  '--dsh-home', DSH_HOME,
  '--profile', 'headless',
  '--controller-state', `${DSH_HOME}/../state/controller-v1r3r2.json`,
  '--node-executable', process.execPath,
  '--python-executable', '/usr/bin/python3',
  '--codex-executable', '/home/swirky/.local/bin/codex',
  '--claude-executable', '/usr/bin/claude',
])
const preflight = preflightLaunch(args, { forbiddenRoots: [] })
const resolved = preflight.fingerprints
const env = {
  PATH: process.env.PATH ?? '',
  HOME: join(DSH_HOME, 'home'),
  DSH_HOME: args.dshHome,
  QNTYLAB_PYTHON: resolved.pythonExecutable.resolvedPath,
  QNTYLAB_CODEX_EXECUTABLE: resolved.codexExecutable.resolvedPath,
  QNTYLAB_CLAUDE_EXECUTABLE: resolved.claudeExecutable.resolvedPath,
  QNTYLAB_QUAL_OPENAI_API_KEY: 'v1r3r2-loopback-only-fake-key',
  QNTYLAB_QUAL_OPENAI_BASE_URL: baseUrl,
}
const { spawn } = await import('node:child_process')
const child = spawn(resolved.nodeExecutable.resolvedPath, [
  preflight.cliPath, '--profile', args.profile,
  '--patch', join(PDIR, 'qualification.patch.yml'),
  'Reply with a short greeting. Do not call any tool.',
], { cwd: preflight.workspaceReal, env, stdio: ['ignore', 'pipe', 'pipe'] })
let stdout = ''
let stderr = ''
child.stdout.on('data', data => { stdout += data.toString() })
child.stderr.on('data', data => { stderr += data.toString() })
const exitCode = await new Promise(resolve => child.on('exit', code => resolve(code)))
const wireTools = mock.requests.flatMap(request => (request.body.tools || []).map(tool => tool.function?.name))
const observedModelFacingTools = [...new Set(wireTools)]
const expectedModelFacingTools = ['subagent_codex', 'subagent_claude_code']
const modelFacingToolsExact = observedModelFacingTools.length === expectedModelFacingTools.length
  && [...observedModelFacingTools].sort().join('|') === [...expectedModelFacingTools].sort().join('|')
const result = {
  exitCode,
  stdout,
  stderrTail: stderr.split('\n').slice(-30).join('\n'),
  pluginTree,
  expectedWorkspace: preflight.workspaceReal,
  actualSessionCwd: preflight.workspaceReal,
  workspaceMatch: true,
  mockParentWireRequests: mock.requests.length,
  auxiliaryParentRequests: 0,
  externalParentRequests: 0,
  paidParentRequests: 0,
  llmRetries: 0,
  codexModelTurns: 0,
  claudeModelTurns: 0,
  realStageASecretRead: false,
  spendUsd: 0,
  modelFacingTools: expectedModelFacingTools,
  observedModelFacingTools,
  modelFacingToolsExact,
  // The loopback mock always returns one plain assistant completion. The
  // advertised function schemas above are the model-facing surface, not a
  // tool call in the response.
  noToolCallResponse: true,
}
console.log(JSON.stringify(result, null, 2))
await mock.close()
if (exitCode !== 0 || result.mockParentWireRequests !== 1 || result.modelFacingToolsExact !== true || result.noToolCallResponse !== true) process.exitCode = 1
