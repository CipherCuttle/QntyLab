#!/usr/bin/env node
// QntyLab canonical DSH launcher (DSH_STAGE_A_V1R3_LAUNCH_PLANE_QUALIFICATION_V0).
//
// This launcher is the sole sanctioned way to start the built DSH CLI. It is
// deliberately indifferent to its own caller's cwd: every path it needs is
// taken as an absolute flag, verified, and then passed explicitly into the
// child spawn's `cwd` option. That is the direct fix for the V1R2 near-miss
// (a pre-live boot dry run that crashed from the orchestrating agent's own
// QntyLab worktree, saved only by that worktree happening to lack `tsx`).
//
// Every fail-closed error this module raises uses one of the terminal codes
// named in the V1R3 plan (`BLOCK_RUNTIME_IDENTITY`, `BLOCK_EXECUTABLE_IDENTITY`,
// `FAIL_WORKSPACE_ISOLATION`, `BLOCK_MATERIALIZATION`). Nothing here reads a
// secret or performs a paid model call; the parent endpoint is expected to be
// a loopback qualification mock or, at real live time, a value supplied by a
// separately authorized live launch.

import { createHash } from 'node:crypto'
import { spawn } from 'node:child_process'
import { readFileSync, realpathSync, existsSync, statSync, writeFileSync } from 'node:fs'
import { basename, isAbsolute, join, resolve, sep } from 'node:path'

export class LaunchPlaneError extends Error {
  constructor(code, message) {
    super(message)
    this.name = 'LaunchPlaneError'
    this.code = code
  }
}

const REQUIRED_ABSOLUTE_ARGS = [
  'runtimeManifest',
  'workspace',
  'dshHome',
  'profile',
  'controllerState',
  'nodeExecutable',
  'pythonExecutable',
  'codexExecutable',
  'claudeExecutable',
]

const ARG_FLAG_BY_KEY = {
  runtimeManifest: '--runtime-manifest',
  workspace: '--workspace',
  dshHome: '--dsh-home',
  profile: '--profile',
  controllerState: '--controller-state',
  nodeExecutable: '--node-executable',
  pythonExecutable: '--python-executable',
  codexExecutable: '--codex-executable',
  claudeExecutable: '--claude-executable',
  parentEndpoint: '--parent-endpoint',
}

export function parseLauncherArgv(argv) {
  const out = {}
  const flagToKey = Object.fromEntries(Object.entries(ARG_FLAG_BY_KEY).map(([k, v]) => [v, k]))
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i]
    const key = flagToKey[flag]
    if (!key) throw new LaunchPlaneError('BLOCK_LAUNCH_ARGV', `unrecognized launcher flag: ${flag}`)
    const value = argv[i + 1]
    if (value === undefined) throw new LaunchPlaneError('BLOCK_LAUNCH_ARGV', `${flag} requires a value`)
    out[key] = value
    i += 1
  }
  return out
}

function fingerprintFile(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

function requireAbsoluteResolvable(key, value) {
  if (!value) throw new LaunchPlaneError('BLOCK_EXECUTABLE_IDENTITY', `${ARG_FLAG_BY_KEY[key]} is required`)
  if (!isAbsolute(value)) {
    throw new LaunchPlaneError('BLOCK_EXECUTABLE_IDENTITY', `${ARG_FLAG_BY_KEY[key]} must be absolute, got: ${value}`)
  }
  if (!existsSync(value)) {
    throw new LaunchPlaneError('BLOCK_EXECUTABLE_IDENTITY', `${ARG_FLAG_BY_KEY[key]} does not resolve to a real file: ${value}`)
  }
  return realpathSync(value)
}

// A path `p` "contains" `root` if `p === root` or `p` starts with `root +
// sep`. Both sides are realpath-resolved by the caller first, which is what
// makes this also a symlink-containment check and not just a string prefix
// check on the literal argv value.
function isContainedIn(root, candidate) {
  if (candidate === root) return true
  return candidate.startsWith(root.endsWith(sep) ? root : root + sep)
}

// Resolve `target` to a realpath even when it (or trailing components of it)
// does not exist yet. Plain `resolve()` on a not-yet-existing path performs
// only lexical normalization and never dereferences symlinks in any
// ancestor directory — if an ancestor is a symlink into a forbidden root
// (e.g. a disposable-fixture *parent* directory symlinked at test-fixture
// setup time, with the actual workspace leaf created only at spawn time),
// a lexical-only resolve would miss it, and the OS would still dereference
// that symlink for real when the child later chdir's into it. This walks up
// to the nearest existing ancestor, realpath-resolves *that*, then
// re-appends the literal (not-yet-existing) remainder.
function realpathAllowingMissing(target) {
  const absolute = resolve(target)
  if (existsSync(absolute)) return realpathSync(absolute)
  const parent = resolve(absolute, '..')
  if (parent === absolute) return absolute // reached filesystem root without finding an existing ancestor
  const resolvedParent = realpathAllowingMissing(parent)
  return join(resolvedParent, basename(absolute))
}

/**
 * Validate the full launcher argv against the runtime manifest and the
 * workspace-containment policy. Throws LaunchPlaneError (never returns a
 * false/ok value) on any violation — this function is the single fail-closed
 * preflight gate the plan requires to run before any DSH process is spawned.
 *
 * @param {object} args - parsed launcher argv (see parseLauncherArgv)
 * @param {object} opts
 * @param {string[]} [opts.forbiddenRoots] - realpaths that --workspace must
 *   not be inside, equal to, or symlink-equivalent to (QntyLab root, Qnty
 *   root, DSH runtime/materialization root).
 */
export function preflightLaunch(args, { forbiddenRoots = [] } = {}) {
  for (const key of REQUIRED_ABSOLUTE_ARGS) {
    if (!args[key]) throw new LaunchPlaneError('BLOCK_LAUNCH_ARGV', `${ARG_FLAG_BY_KEY[key]} is required`)
  }

  const manifestPath = requireAbsoluteResolvable('runtimeManifest', args.runtimeManifest)
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  const manifestRoot = realpathSync(manifest.materializationRoot)

  // --workspace itself is a disposable fixture directory that need not exist
  // yet as a *file*, but its parent must, and its realpath must not fall
  // inside any forbidden root once resolved.
  if (!isAbsolute(args.workspace)) {
    throw new LaunchPlaneError('FAIL_WORKSPACE_ISOLATION', `--workspace must be absolute, got: ${args.workspace}`)
  }
  const workspaceReal = realpathAllowingMissing(args.workspace)
  for (const forbidden of [...forbiddenRoots, manifestRoot]) {
    const forbiddenReal = realpathSync(forbidden)
    if (isContainedIn(forbiddenReal, workspaceReal)) {
      throw new LaunchPlaneError(
        'FAIL_WORKSPACE_ISOLATION',
        `--workspace (${workspaceReal}) is inside a forbidden root (${forbiddenReal})`,
      )
    }
  }

  if (!isAbsolute(args.dshHome)) {
    throw new LaunchPlaneError('BLOCK_LAUNCH_ARGV', `--dsh-home must be absolute, got: ${args.dshHome}`)
  }
  if (!isAbsolute(args.controllerState)) {
    throw new LaunchPlaneError('BLOCK_LAUNCH_ARGV', `--controller-state must be absolute, got: ${args.controllerState}`)
  }
  if (!isAbsolute(args.profile) || !existsSync(args.profile)) {
    throw new LaunchPlaneError('BLOCK_LAUNCH_ARGV', `--profile must be an absolute, existing path: ${args.profile}`)
  }

  const executableKeys = ['nodeExecutable', 'pythonExecutable', 'codexExecutable', 'claudeExecutable']
  const manifestFingerprints = manifest.executableFingerprints || {}
  const fingerprints = {}
  for (const key of executableKeys) {
    const real = requireAbsoluteResolvable(key, args[key])
    if (statSync(real).isDirectory()) {
      throw new LaunchPlaneError('BLOCK_EXECUTABLE_IDENTITY', `${ARG_FLAG_BY_KEY[key]} must be a file, not a directory: ${real}`)
    }
    const digest = fingerprintFile(real)
    const expected = manifestFingerprints[key]
    if (!expected) {
      throw new LaunchPlaneError(
        'BLOCK_RUNTIME_IDENTITY',
        `runtime manifest has no recorded fingerprint for ${key}`,
      )
    }
    if (digest !== expected) {
      throw new LaunchPlaneError(
        'BLOCK_EXECUTABLE_IDENTITY',
        `${ARG_FLAG_BY_KEY[key]} fingerprint mismatch: expected ${expected}, got ${digest} (${real})`,
      )
    }
    // Record the realpath-resolved path, not the original (possibly
    // symlinked) argv value. `spawnDsh` executes these resolved paths, not
    // the raw argv, so the process the OS actually execve's is the same one
    // that was just fingerprinted — closing the same "resolve, then let the
    // OS re-resolve at execve" TOCTOU gap this phase's Codex repair patch
    // closes in DSH's own source.
    fingerprints[key] = { digest, resolvedPath: real }
  }

  // Built CLI identity: the manifest must point at a real, in-root built
  // entrypoint, never a source .ts file behind a tsx/esm loader.
  const cliPath = manifest.builtCliAbsolutePath
  if (!cliPath || !isAbsolute(cliPath)) {
    throw new LaunchPlaneError('BLOCK_RUNTIME_IDENTITY', 'runtime manifest is missing an absolute builtCliAbsolutePath')
  }
  if (/\.ts$/.test(cliPath) || cliPath.includes(`${sep}src${sep}`)) {
    throw new LaunchPlaneError(
      'BLOCK_RUNTIME_IDENTITY',
      `runtime manifest built CLI path looks like source, not a build artifact: ${cliPath}`,
    )
  }
  if (!existsSync(cliPath)) {
    throw new LaunchPlaneError('BLOCK_MATERIALIZATION', `built CLI does not exist at manifest path: ${cliPath}`)
  }
  const cliReal = realpathSync(cliPath)
  if (!isContainedIn(manifestRoot, cliReal)) {
    throw new LaunchPlaneError('BLOCK_RUNTIME_IDENTITY', `built CLI (${cliReal}) is not inside materialization root (${manifestRoot})`)
  }
  const cliDigest = fingerprintFile(cliReal)
  // Unconditionally required, unlike a merely-optional field: every other
  // identity check in this function fails closed when its expected value is
  // absent, and the built CLI is the single most consequential file about
  // to be spawned. A manifest missing this field must not silently skip
  // content-tamper detection on the entrypoint.
  if (!manifest.builtCliDigest) {
    throw new LaunchPlaneError('BLOCK_RUNTIME_IDENTITY', 'runtime manifest is missing builtCliDigest')
  }
  if (manifest.builtCliDigest !== cliDigest) {
    throw new LaunchPlaneError('BLOCK_EXECUTABLE_IDENTITY', 'built CLI digest drift from runtime manifest')
  }
  // Every other manifest-declared path must genuinely resolve inside the
  // manifest's own declared root — this is the structural fix for V1R2's
  // evidence-quality debt (hashes recorded for files that did not exist
  // where claimed).
  for (const [label, declaredPath] of Object.entries(manifest.workspaceBundledChunks || {})) {
    if (!existsSync(declaredPath)) {
      throw new LaunchPlaneError('BLOCK_RUNTIME_IDENTITY', `manifest chunk "${label}" does not exist: ${declaredPath}`)
    }
    if (!isContainedIn(manifestRoot, realpathSync(declaredPath))) {
      throw new LaunchPlaneError('BLOCK_RUNTIME_IDENTITY', `manifest chunk "${label}" resolves outside materialization root`)
    }
  }

  return { manifest, manifestRoot, cliPath: cliReal, cliDigest, fingerprints, workspaceReal }
}

/**
 * Spawn the built DSH CLI with an explicit cwd, regardless of this process's
 * own cwd. Returns the child process handle; callers await its exit and
 * write their own receipt.
 */
export function spawnDsh(args, preflightResult, { extraEnv = {}, stdio = 'inherit' } = {}) {
  // Use the realpath-resolved paths recorded at preflight time, not the raw
  // argv values. If nodeExecutable/pythonExecutable/etc. were symlinks, this
  // is what makes the process actually execve'd the same one that was just
  // fingerprinted, instead of leaving a window for the OS to re-resolve a
  // possibly-swapped symlink target at spawn time.
  const resolved = preflightResult.fingerprints
  const env = {
    PATH: process.env.PATH ?? '',
    HOME: process.env.HOME ?? '',
    DSH_HOME: args.dshHome,
    QNTYLAB_PYTHON: resolved.pythonExecutable.resolvedPath,
    // Fingerprint-verified codex/claude paths, so a DSH build that has
    // landed the codex-executable-binding repair (or an equivalent Claude
    // seam) can consume them instead of re-resolving a bare name from PATH.
    // Until that repair lands and is verified to actually consume these,
    // this is necessary-but-not-sufficient binding — see PHASE.md.
    QNTYLAB_CODEX_EXECUTABLE: resolved.codexExecutable.resolvedPath,
    QNTYLAB_CLAUDE_EXECUTABLE: resolved.claudeExecutable.resolvedPath,
    ...extraEnv,
  }
  if (args.parentEndpoint) env.QNTYLAB_DSH_PARENT_ENDPOINT = args.parentEndpoint
  const child = spawn(resolved.nodeExecutable.resolvedPath, [preflightResult.cliPath, '--profile', args.profile], {
    cwd: preflightResult.workspaceReal,
    env,
    stdio,
  })
  return child
}

export function writeLaunchReceipt(path, receipt) {
  writeFileSync(path, `${JSON.stringify(receipt, null, 2)}\n`, 'utf8')
}

async function main() {
  const args = parseLauncherArgv(process.argv.slice(2))
  const forbiddenRootsEnv = process.env.QNTYLAB_LAUNCH_FORBIDDEN_ROOTS
  const forbiddenRoots = forbiddenRootsEnv ? forbiddenRootsEnv.split(':').filter(Boolean) : []
  let preflightResult
  try {
    preflightResult = preflightLaunch(args, { forbiddenRoots })
  } catch (err) {
    if (err instanceof LaunchPlaneError) {
      process.stderr.write(`${err.code}: ${err.message}\n`)
      process.exitCode = 1
      return
    }
    throw err
  }
  const child = spawnDsh(args, preflightResult)
  child.on('exit', code => {
    process.exitCode = code ?? 1
  })
}

const isMain = process.argv[1] && import.meta.url === `file://${process.argv[1]}`
if (isMain) {
  main().catch(err => {
    process.stderr.write(`${err.stack || err}\n`)
    process.exitCode = 1
  })
}
