#!/usr/bin/env node

// Phase-D acquisition/materialization seam.
//
// The V1R3 materializer contains the verified patch/install/build/manifest
// primitives. This phase adds the missing repository-native acquisition step:
// clone the exact public source, detach at the pinned commit, verify the
// remote/tree/tag, and only then hand the pristine checkout to those existing
// primitives. No provider or model endpoint is contacted here.

import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import {
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  realpathSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from 'node:fs'
import { delimiter, dirname, isAbsolute, join, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  MaterializationError,
  verifySourceIdentity,
  applyCanonicalPatches,
  fingerprintExecutable,
  installedPackageIdentity,
  buildManifest,
  writeManifest,
} from '../../dsh_stage_a_v1r3r2_claude_hard_read_only_repair_and_requalification_v0/materializer/qntylab-materialize-dsh-runtime.mjs'

export const PHASE_ID = 'DSH_RUNTIME_MATERIALIZATION_AND_LAUNCH_V0'
export const SOURCE_REMOTE = 'https://github.com/deepseek-ai/deepseek-harness.git'
export const SOURCE_REPOSITORY = 'deepseek-ai/deepseek-harness'
export const SOURCE_COMMIT = '99f6f02fecdb7dff40c3fbc9470f5907c29f74ca'
export const SOURCE_TREE = '3bc8f89fe494a4755c188be354add4e8b1e7b188'
export const SOURCE_TAG = 'dsh-v0.1.0-rc.7'
export const PINNED_PNPM = '11.7.0'
export const MATERIALIZER_VERSION = 'qntylab-dsh-materializer-v0'

function sha256File(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

function run(command, args, options = {}) {
  const result = spawnSync(command, args, { encoding: 'utf8', ...options })
  if (result.error) throw result.error
  return result
}

function resolveExecutable(name) {
  if (isAbsolute(name)) {
    if (!existsSync(name) || lstatSync(name).isDirectory()) {
      throw new MaterializationError('BLOCK_TOOLCHAIN', `executable does not exist: ${name}`)
    }
    return realpathSync(name)
  }
  for (const entry of (process.env.PATH || '').split(delimiter)) {
    if (!entry) continue
    const candidate = join(entry, name)
    if (existsSync(candidate) && !lstatSync(candidate).isDirectory()) return realpathSync(candidate)
  }
  throw new MaterializationError('BLOCK_TOOLCHAIN', `executable not found on PATH: ${name}`)
}

function git(sourceRoot, args, code = 'BLOCK_SOURCE') {
  const result = run('git', ['-C', sourceRoot, ...args])
  if (result.status !== 0) {
    throw new MaterializationError(code, `git ${args.join(' ')} failed:\n${result.stderr || result.stdout}`)
  }
  return result.stdout.trim()
}

function assertEmptyOrMissing(path) {
  if (!existsSync(path)) return
  if (!lstatSync(path).isDirectory() || readdirSync(path).length > 0) {
    throw new MaterializationError('BLOCK_SOURCE', `materialization target must be absent or empty: ${path}`)
  }
}

function assertClean(sourceRoot) {
  if (git(sourceRoot, ['status', '--porcelain']) !== '') {
    throw new MaterializationError('BLOCK_SOURCE', `materialized source is dirty: ${sourceRoot}`)
  }
}

function safeRelativePath(path) {
  if (!path || path.startsWith('/') || path.includes('\\') || path.split('/').includes('..') || /[\u0000-\u001f]/.test(path)) {
    throw new MaterializationError('BLOCK_SOURCE', `unsafe source path in pinned tree: ${JSON.stringify(path)}`)
  }
}

function assertSafeTree(sourceRoot, commit) {
  const output = run('git', ['-C', sourceRoot, 'ls-tree', '-r', '-z', '--full-tree', commit])
  if (output.status !== 0) throw new MaterializationError('BLOCK_SOURCE', output.stderr)
  for (const entry of output.stdout.split('\0').filter(Boolean)) {
    const tab = entry.indexOf('\t')
    const header = tab === -1 ? entry : entry.slice(0, tab)
    const path = tab === -1 ? '' : entry.slice(tab + 1)
    safeRelativePath(path)
    const mode = header.split(/\s+/)[0]
    if (mode !== '120000') continue
    const target = git(sourceRoot, ['show', `${commit}:${path}`])
    const resolvedTarget = resolve(sourceRoot, dirname(path), target)
    const root = realpathSync(sourceRoot)
    if (isAbsolute(target) || (resolvedTarget !== root && !resolvedTarget.startsWith(`${root}${sep}`))) {
      throw new MaterializationError('BLOCK_SOURCE', `symlink target is outside source tree: ${path} -> ${target}`)
    }
  }
}

function expectedPackageManager(sourceRoot) {
  const pkg = JSON.parse(readFileSync(join(sourceRoot, 'package.json'), 'utf8'))
  if (pkg.packageManager !== `pnpm@${PINNED_PNPM}`) {
    throw new MaterializationError('BLOCK_TOOLCHAIN', `packageManager must be pnpm@${PINNED_PNPM}, got ${pkg.packageManager}`)
  }
  return pkg.packageManager
}

function pinnedPnpmInvocation(sourceRoot, corepackExecutable, args) {
  const packageManager = expectedPackageManager(sourceRoot)
  const result = run(corepackExecutable, [packageManager, ...args], {
    cwd: sourceRoot,
    env: { ...process.env, COREPACK_ENABLE_DOWNLOAD_PROMPT: '0' },
  })
  if (result.status !== 0) return { result, packageManager }
  return { result, packageManager }
}

export function materializePinnedSource({ runtimeRoot, sourceRemote = SOURCE_REMOTE, sourceCommit = SOURCE_COMMIT } = {}) {
  if (!runtimeRoot || !isAbsolute(runtimeRoot)) throw new MaterializationError('BLOCK_SOURCE', 'runtimeRoot must be absolute')
  assertEmptyOrMissing(runtimeRoot)
  mkdirSync(runtimeRoot, { recursive: true })
  const sourceRoot = join(runtimeRoot, 'source')
  const clone = run('git', ['clone', '--no-checkout', '--no-tags', sourceRemote, sourceRoot], { stdio: ['ignore', 'pipe', 'pipe'] })
  if (clone.status !== 0) throw new MaterializationError('BLOCK_SOURCE', `git clone failed:\n${clone.stderr || clone.stdout}`)
  git(sourceRoot, ['fetch', '--tags', 'origin', sourceCommit])
  git(sourceRoot, ['checkout', '--detach', sourceCommit])
  const identity = verifySourceIdentity(sourceRoot, {
    expectedRepository: SOURCE_REPOSITORY,
    expectedCommit: sourceCommit,
    expectedTree: SOURCE_TREE,
    expectedTag: SOURCE_TAG,
  })
  assertSafeTree(sourceRoot, sourceCommit)
  assertClean(sourceRoot)
  return {
    sourceRoot: realpathSync(sourceRoot),
    sourceRemote,
    sourceCommit: identity.commit,
    sourceTree: identity.tree,
    sourceTag: identity.tag,
    checkoutClean: true,
    materializerVersion: MATERIALIZER_VERSION,
  }
}

export function installPinnedOffline(sourceRoot, { corepackExecutable = 'corepack' } = {}) {
  const corepack = resolveExecutable(corepackExecutable)
  const version = pinnedPnpmInvocation(sourceRoot, corepack, ['--version'])
  if (version.result.status !== 0 || version.result.stdout.trim() !== PINNED_PNPM) {
    throw new MaterializationError('BLOCK_TOOLCHAIN', `pinned pnpm version check failed: ${version.result.stderr || version.result.stdout}`)
  }
  const install = pinnedPnpmInvocation(sourceRoot, corepack, ['install', '--offline', '--frozen-lockfile'])
  if (install.result.status !== 0) {
    throw new MaterializationError('BLOCK_DEPENDENCY_INSTALL', `offline frozen install failed:\n${install.result.stderr || install.result.stdout}`)
  }
  return {
    declaredPackageManager: install.packageManager,
    actualVersion: version.result.stdout.trim(),
    executablePath: corepack,
    executableDigest: sha256File(corepack),
    invocation: ['corepack', `pnpm@${PINNED_PNPM}`],
    installCommand: `corepack pnpm@${PINNED_PNPM} install --offline --frozen-lockfile`,
  }
}

export function buildPinnedRuntime(sourceRoot, { corepackExecutable = 'corepack', buildScript = 'build:lib' } = {}) {
  const corepack = resolveExecutable(corepackExecutable)
  const built = pinnedPnpmInvocation(sourceRoot, corepack, ['run', buildScript])
  if (built.result.status !== 0) {
    throw new MaterializationError('BLOCK_BUILD', `build ${buildScript} failed:\n${built.result.stderr || built.result.stdout}`)
  }
  return { buildScript, command: `corepack pnpm@${PINNED_PNPM} run ${buildScript}` }
}

export function buildPhaseManifest({ sourceRoot, sourceReceipt, patchDigests, packageManagerFingerprint, buildIdentity, lockfileDigest, launcherPath, overlayPath, executablePaths, manifestPath }) {
  const cliRelativePath = 'apps/cli/lib/bin.js'
  const chunkRelativePaths = readdirSync(join(sourceRoot, 'apps/cli/lib'))
    .filter(name => /^(profile-boot|plugin)-.*\.js$/.test(name))
    .map(name => `apps/cli/lib/${name}`)
  const base = buildManifest({
    sourceRoot,
    repository: SOURCE_REPOSITORY,
    commit: SOURCE_COMMIT,
    tree: SOURCE_TREE,
    expectedTag: SOURCE_TAG,
    packageManagerFingerprint,
    lockfileDigest,
    claudeSdkIdentity: installedPackageIdentity(sourceRoot, '@anthropic-ai/claude-agent-sdk'),
    patchDigests,
    profileDigests: { qualificationOverlay: sha256File(overlayPath) },
    launcherDigest: sha256File(launcherPath),
    builtCliRelativePath: cliRelativePath,
    workspaceBundledChunkRelativePaths: chunkRelativePaths,
    executableFingerprints: Object.fromEntries(Object.entries(executablePaths).map(([key, path]) => [key, fingerprintExecutable(path).digest])),
  })
  const manifest = {
    ...base,
    phaseId: PHASE_ID,
    schemaVersion: 'qntylab-dsh-runtime-manifest-v0',
    sourceReceipt,
    sourceRemote: SOURCE_REMOTE,
    governedPatchIdentity: patchDigests.map(({ path, digest }) => ({ path, digest })),
    lockfileDigest,
    buildIdentity: {
      ...buildIdentity,
      entrypointRelativePath: cliRelativePath,
      entrypointDigest: base.builtCliDigest,
      chunkRelativePaths,
    },
    launcherIdentity: { path: realpathSync(launcherPath), digest: sha256File(launcherPath) },
    materializerIdentity: { version: MATERIALIZER_VERSION, path: realpathSync(fileURLToPath(import.meta.url)), digest: sha256File(fileURLToPath(import.meta.url)) },
    manifestPath: resolve(manifestPath),
  }
  return manifest
}

export function writeReceipt(path, receipt) {
  mkdirSync(resolve(path, '..'), { recursive: true })
  writeFileSync(path, `${JSON.stringify(receipt, null, 2)}\n`, 'utf8')
}

export { MaterializationError, verifySourceIdentity, applyCanonicalPatches, fingerprintExecutable, installedPackageIdentity, writeManifest }
