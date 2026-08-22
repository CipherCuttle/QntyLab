import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'
import { existsSync, lstatSync, mkdirSync, readFileSync, symlinkSync, unlinkSync } from 'node:fs'
import { preflightLaunch, spawnDsh, parseLauncherArgv } from '/home/swirky/DevHub/repos/QntyLab/experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r1_real_runtime_qualification_v0/launcher/qntylab-launch-dsh.mjs'
import { createQualificationMock } from '/home/swirky/DevHub/repos/QntyLab/experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r1_real_runtime_qualification_v0/mock/qualification-openai-mock.mjs'

const PDIR = dirname(fileURLToPath(import.meta.url))
const MANIFEST_PATH = process.env.QNTYLAB_DSH_MANIFEST || join(PDIR, '../evidence/runtime_manifest.json')
const DSH_HOME = process.env.QNTYLAB_DSH_HOME || '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/dsh-home'
const WORKSPACE = process.argv[2] || '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/workspace/run1'
mkdirSync(WORKSPACE, { recursive: true })
const SOURCE_ROOT = JSON.parse(readFileSync(MANIFEST_PATH, 'utf8')).materializationRoot

function settleQualificationPluginTree() {
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
  console.log('plugin tree settled:', Object.keys(packages).join(', '))
}

settleQualificationPluginTree()

const mock = createQualificationMock({ model: 'gpt-5-mini' })
const baseUrl = await mock.listen(0)
console.log('mock listening at', baseUrl)

const args = parseLauncherArgv([
  '--runtime-manifest', MANIFEST_PATH,
  '--workspace', WORKSPACE,
  '--dsh-home', DSH_HOME,
  '--profile', 'headless',
  '--controller-state', `${DSH_HOME}/../state/controller.json`,
  '--node-executable', process.execPath,
  '--python-executable', '/usr/bin/python3',
  '--codex-executable', '/home/swirky/.local/bin/codex',
  '--claude-executable', '/usr/bin/claude',
])

const preflightResult = preflightLaunch(args, { forbiddenRoots: [] })
console.log('preflight OK. workspaceReal =', preflightResult.workspaceReal)
console.log('cliPath =', preflightResult.cliPath)

// spawnDsh doesn't accept the app's own positional task arg or --patch; use
// its documented spawn but append our overlay + task by re-invoking spawn
// logic inline (spawnDsh's argv is fixed to [cliPath, '--profile', profile]).
// For this proof run we extend via extraEnv only (spawnDsh signature already
// supports it) and pass the task/patch through a thin wrapper since the
// canonical launcher's own argv passthrough for app-level args is declared
// as launcher-owned in PHASE.md ("App flags are not the launcher's business").
const { spawn } = await import('node:child_process')
const resolved = preflightResult.fingerprints
const env = {
  PATH: process.env.PATH ?? '',
  HOME: process.env.HOME ?? '',
  DSH_HOME: args.dshHome,
  QNTYLAB_PYTHON: resolved.pythonExecutable.resolvedPath,
  QNTYLAB_CODEX_EXECUTABLE: resolved.codexExecutable.resolvedPath,
  QNTYLAB_CLAUDE_EXECUTABLE: resolved.claudeExecutable.resolvedPath,
  QNTYLAB_QUAL_OPENAI_API_KEY: 'sk-qualification-only-fake-not-real',
  QNTYLAB_QUAL_OPENAI_BASE_URL: baseUrl,
}
const child = spawn(resolved.nodeExecutable.resolvedPath, [
  preflightResult.cliPath, '--profile', args.profile,
  '--patch', join(PDIR, 'qualification.patch.yml'),
  'Reply with a short greeting. Do not call any tool.',
], { cwd: preflightResult.workspaceReal, env, stdio: ['ignore', 'pipe', 'pipe'] })

let stdout = ''
let stderr = ''
child.stdout.on('data', d => { stdout += d.toString() })
child.stderr.on('data', d => { stderr += d.toString() })
const exitCode = await new Promise(resolve => child.on('exit', code => resolve(code)))
console.log('exit code:', exitCode)
console.log('stdout:', stdout)
if (exitCode !== 0) console.log('stderr tail:', stderr.split('\n').slice(-30).join('\n'))
console.log('mock requests:', mock.requests.length)
for (const r of mock.requests) {
  console.log(JSON.stringify({ model: r.body.model, tools: (r.body.tools || []).map(t => t.function?.name) }))
}
await mock.close()
process.exit(exitCode === 0 && mock.requests.length === 1 ? 0 : 1)
