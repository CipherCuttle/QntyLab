// Boot-only/session-observation variant: preflight + spawn dsh in
// --dump-config mode (no LLM request, no parent mock touched) from a given
// caller cwd, proving workspace binding survives caller-cwd variance without
// consuming an extra parent mock wire request.
import { preflightLaunch, parseLauncherArgv } from '/home/swirky/DevHub/repos/QntyLab/experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r1_real_runtime_qualification_v0/launcher/qntylab-launch-dsh.mjs'
import { spawn } from 'node:child_process'

const WORKSPACE = process.argv[2]
const DSH_HOME = '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1/dsh-home'

const args = parseLauncherArgv([
  '--runtime-manifest', '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1/runtime/runtime_manifest.json',
  '--workspace', WORKSPACE,
  '--dsh-home', DSH_HOME,
  '--profile', 'headless',
  '--controller-state', '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1/state/controller.json',
  '--node-executable', process.execPath,
  '--python-executable', '/usr/bin/python3',
  '--codex-executable', '/home/swirky/.local/bin/codex',
  '--claude-executable', '/usr/bin/claude',
])
const preflightResult = preflightLaunch(args, { forbiddenRoots: [] })
console.log('caller cwd was:', process.cwd())
console.log('workspaceReal (bound, independent of caller cwd):', preflightResult.workspaceReal)

const resolved = preflightResult.fingerprints
const child = spawn(resolved.nodeExecutable.resolvedPath, [
  preflightResult.cliPath, '--profile', args.profile, '--dump-default-config',
], {
  cwd: preflightResult.workspaceReal,
  env: { PATH: process.env.PATH, HOME: process.env.HOME, DSH_HOME, QNTYLAB_PYTHON: '/usr/bin/python3' },
  stdio: ['ignore', 'pipe', 'pipe'],
})
let out = ''
child.stdout.on('data', d => { out += d.toString() })
const code = await new Promise(r => child.on('exit', r))
console.log('dsh --dump-default-config exit code:', code, '(0 = profile/workspace bound OK, no LLM call)')
process.exit(code)
