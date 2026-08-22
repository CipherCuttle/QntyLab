#!/usr/bin/env node

import { mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { spawn } from 'node:child_process'
import { fileURLToPath } from 'node:url'
import { dirname, join, resolve } from 'node:path'
import { parseLauncherArgv, preflightLaunch } from '../launcher/qntylab-launch-dsh.mjs'

const PHASE_DIR = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const manifestPath = process.env.QNTYLAB_DSH_MANIFEST || join(PHASE_DIR, 'evidence/runtime_manifest.json')
const receiptPath = process.env.QNTYLAB_DSH_BOOT_RECEIPT || join(PHASE_DIR, 'evidence/boot_receipt.json')
const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
const dshHome = process.env.QNTYLAB_DSH_BOOT_HOME || '/var/tmp/qntylab-dsh-boot-home-v0'
const workspace = process.env.QNTYLAB_DSH_BOOT_WORKSPACE || '/var/tmp/qntylab-dsh-boot-workspace-v0'
mkdirSync(dshHome, { recursive: true })
mkdirSync(workspace, { recursive: true })
const args = parseLauncherArgv([
  '--runtime-manifest', manifestPath,
  '--workspace', workspace,
  '--dsh-home', dshHome,
  '--profile', 'headless',
  '--controller-state', join(dshHome, 'state/controller.json'),
  '--node-executable', process.execPath,
  '--python-executable', process.env.QNTYLAB_PYTHON || '/usr/bin/python3',
  '--codex-executable', process.env.QNTYLAB_CODEX_EXECUTABLE || '/home/swirky/.local/bin/codex',
  '--claude-executable', process.env.QNTYLAB_CLAUDE_EXECUTABLE || '/usr/bin/claude',
])
const preflight = preflightLaunch(args, { forbiddenRoots: [resolve(PHASE_DIR, '../../../..')] })
const child = spawn(preflight.fingerprints.nodeExecutable.resolvedPath, [preflight.cliPath, '--profile', args.profile, '--help'], {
  cwd: preflight.workspaceReal,
  env: {
    PATH: process.env.PATH || '',
    HOME: join(dshHome, 'home'),
    DSH_HOME: dshHome,
    QNTYLAB_PYTHON: preflight.fingerprints.pythonExecutable.resolvedPath,
    QNTYLAB_CODEX_EXECUTABLE: preflight.fingerprints.codexExecutable.resolvedPath,
    QNTYLAB_CLAUDE_EXECUTABLE: preflight.fingerprints.claudeExecutable.resolvedPath,
  },
  stdio: ['ignore', 'pipe', 'pipe'],
})
let stdout = ''
let stderr = ''
child.stdout.on('data', data => { stdout += data.toString() })
child.stderr.on('data', data => { stderr += data.toString() })
const exitCode = await new Promise(resolveExit => child.on('exit', code => resolveExit(code)))
const receipt = {
  boot: exitCode === 0 ? 'PASS' : 'FAIL',
  actualDshProcessConfirmed: exitCode === 0,
  exitCode,
  entrypoint: preflight.cliPath,
  entrypointDigest: preflight.cliDigest,
  workspace: preflight.workspaceReal,
  stdoutHead: stdout.slice(0, 2000),
  stderrTail: stderr.split('\n').slice(-20).join('\n'),
  providerRequests: 0,
  secretReads: 0,
}
writeFileSync(receiptPath, `${JSON.stringify(receipt, null, 2)}\n`)
console.log(JSON.stringify(receipt, null, 2))
process.exitCode = exitCode === 0 ? 0 : 1
