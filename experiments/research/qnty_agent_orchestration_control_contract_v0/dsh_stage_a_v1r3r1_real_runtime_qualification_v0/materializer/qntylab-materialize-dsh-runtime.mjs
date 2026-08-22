#!/usr/bin/env node
// QntyLab DSH runtime materializer (DSH_STAGE_A_V1R3R1_REAL_RUNTIME_QUALIFICATION_V0).
//
// Materialization is treated as part of the qualified graph, not an external
// precondition (V1R2's failure: a bare pinned clone with no install was
// launched while a *separate* clone had the actual `node_modules`/build).
// This script takes a pre-cloned pinned source tree (`--source-root`) — this
// offline qualification phase does not perform network `git clone`/`pnpm
// install` fetches itself, since V1R3 is explicitly bounded to local,
// frozen, offline materialization only — verifies its commit identity,
// applies the canonical QntyLab-owned repair patches, installs dependencies
// offline/frozen, builds, and emits a `runtime_manifest.json` describing
// exactly what was materialized.
//
// Every declared manifest path is a realpath descendant of the
// materialization root; the launcher (`qntylab-launch-dsh.mjs`) re-verifies
// that at preflight time and fails closed on any drift.

import { createHash } from 'node:crypto'
import { spawnSync } from 'node:child_process'
import { existsSync, mkdirSync, readFileSync, realpathSync, writeFileSync, statSync, readdirSync } from 'node:fs'
import { isAbsolute, join, resolve } from 'node:path'

export class MaterializationError extends Error {
  constructor(code, message) {
    super(message)
    this.name = 'MaterializationError'
    this.code = code
  }
}

function fingerprintFile(path) {
  return createHash('sha256').update(readFileSync(path)).digest('hex')
}

function fingerprintText(text) {
  return createHash('sha256').update(text, 'utf8').digest('hex')
}

function run(cmd, cmdArgs, opts) {
  const result = spawnSync(cmd, cmdArgs, { encoding: 'utf8', ...opts })
  if (result.error) throw result.error
  return result
}

function resolveExecutable(executable) {
  if (isAbsolute(executable)) {
    if (!existsSync(executable) || statSync(executable).isDirectory()) {
      throw new MaterializationError('DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY', `executable does not exist: ${executable}`)
    }
    return realpathSync(executable)
  }
  for (const entry of (process.env.PATH || '').split(':')) {
    if (!entry) continue
    const candidate = join(entry, executable)
    if (existsSync(candidate) && !statSync(candidate).isDirectory()) return realpathSync(candidate)
  }
  throw new MaterializationError('DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY', `executable not found on PATH: ${executable}`)
}

function gitOutput(sourceRoot, args, code) {
  const result = run('git', ['-C', sourceRoot, ...args])
  if (result.status !== 0) {
    throw new MaterializationError(code, `git ${args.join(' ')} failed for ${sourceRoot}: ${result.stderr}`)
  }
  return result.stdout.trim()
}

function packageJsonPath(sourceRoot, packageName) {
  const candidate = join(sourceRoot, 'node_modules', ...packageName.split('/'), 'package.json')
  if (existsSync(candidate)) return realpathSync(candidate)

  const virtualStore = join(sourceRoot, 'node_modules', '.pnpm')
  if (existsSync(virtualStore)) {
    for (const entry of readdirSync(virtualStore)) {
      const virtualCandidate = join(virtualStore, entry, 'node_modules', ...packageName.split('/'), 'package.json')
      if (existsSync(virtualCandidate)) return realpathSync(virtualCandidate)
    }
  }
  throw new MaterializationError(
    'DSH_STAGE_A_V1R3_BLOCK_MATERIALIZATION',
    `installed package identity missing: ${packageName}`,
  )
}

export function installedPackageIdentity(sourceRoot, packageName) {
  const packagePath = packageJsonPath(sourceRoot, packageName)
  const packageJson = JSON.parse(readFileSync(packagePath, 'utf8'))
  return {
    package: packageName,
    version: packageJson.version ?? null,
    packageJsonDigest: fingerprintFile(packagePath),
  }
}

/**
 * Verify the pinned source tree's identity by comparing the checked-out
 * commit/tag against the declared expectation, via git itself (not a trust
 * label carried over from a prior phase).
 */
export function verifySourceIdentity(sourceRoot, { expectedRepository, expectedCommit, expectedTree, expectedTag } = {}) {
  const actualCommit = gitOutput(sourceRoot, ['rev-parse', 'HEAD'], 'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY')
  const actualTree = gitOutput(sourceRoot, ['rev-parse', 'HEAD^{tree}'], 'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY')
  let actualRepository = null
  if (expectedRepository) {
    const remote = gitOutput(sourceRoot, ['config', '--get', 'remote.origin.url'], 'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY')
    actualRepository = remote
      .replace(/\.git$/, '')
      .replace(/^git@github\.com:/, '')
      .replace(/^https?:\/\/github\.com\//, '')
  }
  if (expectedCommit && actualCommit !== expectedCommit) {
    throw new MaterializationError(
      'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY',
      `pinned source commit mismatch: expected ${expectedCommit}, got ${actualCommit}`,
    )
  }
  if (expectedTree && actualTree !== expectedTree) {
    throw new MaterializationError(
      'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY',
      `pinned source tree mismatch: expected ${expectedTree}, got ${actualTree}`,
    )
  }
  if (expectedRepository && actualRepository !== expectedRepository) {
    throw new MaterializationError(
      'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY',
      `pinned source repository mismatch: expected ${expectedRepository}, got ${actualRepository}`,
    )
  }
  const treeResult = run('git', ['-C', sourceRoot, 'cat-file', '-t', actualCommit])
  if (treeResult.status !== 0 || treeResult.stdout.trim() !== 'commit') {
    throw new MaterializationError(
      'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY',
      `git cat-file did not confirm a real commit object for ${actualCommit}`,
    )
  }
  if (expectedTag) {
    const tagResult = run('git', ['-C', sourceRoot, 'tag', '--points-at', actualCommit])
    const tags = tagResult.stdout.split('\n').map(s => s.trim()).filter(Boolean)
    if (!tags.includes(expectedTag)) {
      throw new MaterializationError(
        'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY',
        `expected tag ${expectedTag} does not point at ${actualCommit} (found: ${tags.join(', ') || 'none'})`,
      )
    }
  }
  return { repository: actualRepository, commit: actualCommit, tree: actualTree, tag: expectedTag ?? null }
}

/**
 * Apply canonical QntyLab-owned repair patches, in declared order, using
 * `git apply` against the source root. Any patch that fails to apply cleanly
 * is a hard block — this phase never falls back to hand-editing.
 */
export function applyCanonicalPatches(sourceRoot, patchPaths) {
  const digests = []
  for (const patchPath of patchPaths) {
    if (!existsSync(patchPath)) {
      throw new MaterializationError('DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY', `repair patch not found: ${patchPath}`)
    }
    const checkResult = run('git', ['-C', sourceRoot, 'apply', '--check', patchPath])
    if (checkResult.status !== 0) {
      throw new MaterializationError(
        'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY',
        `repair patch does not apply cleanly: ${patchPath}\n${checkResult.stderr}`,
      )
    }
    const applyResult = run('git', ['-C', sourceRoot, 'apply', patchPath])
    if (applyResult.status !== 0) {
      throw new MaterializationError(
        'DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY',
        `repair patch failed to apply: ${patchPath}\n${applyResult.stderr}`,
      )
    }
    digests.push({ path: patchPath, digest: fingerprintFile(patchPath) })
  }
  return digests
}

/**
 * Install dependencies offline/frozen. If the local pnpm store lacks a
 * required package, this fails closed with BLOCK_MISSING_OFFLINE_DEPENDENCY
 * rather than silently falling back to a network fetch or an old sibling
 * worktree's node_modules.
 */
export function installOffline(sourceRoot, { pnpmExecutable = 'pnpm', installArgs } = {}) {
  const pkg = JSON.parse(readFileSync(join(sourceRoot, 'package.json'), 'utf8'))
  const packageManager = pkg.packageManager || ''
  // Confirm the exact pinned contract rather than assuming a literal flag
  // name; the repo's own `packageManager` field and pnpm-workspace presence
  // are load-bearing here, per the plan's PLAN RISKS note.
  if (!packageManager.startsWith('pnpm@') && !existsSync(join(sourceRoot, 'pnpm-workspace.yaml'))) {
    throw new MaterializationError(
      'DSH_STAGE_A_V1R3_BLOCK_MISSING_OFFLINE_DEPENDENCY',
      'source root does not declare a pnpm-managed workspace; cannot confirm the offline/frozen install contract',
    )
  }
  const args = installArgs || ['install', '--offline', '--frozen-lockfile']
  const actualExecutable = resolveExecutable(pnpmExecutable)
  const versionResult = run(actualExecutable, ['--version'])
  if (versionResult.status !== 0) {
    throw new MaterializationError('DSH_STAGE_A_V1R3_BLOCK_MATERIALIZATION', `could not read pnpm version: ${versionResult.stderr}`)
  }
  const result = run(actualExecutable, args, { cwd: sourceRoot })
  if (result.status !== 0) {
    throw new MaterializationError(
      'DSH_STAGE_A_V1R3_BLOCK_MISSING_OFFLINE_DEPENDENCY',
      `offline frozen install failed (no network fallback attempted):\n${result.stderr || result.stdout}`,
    )
  }
  return {
    declaredPackageManager: packageManager,
    actualVersion: versionResult.stdout.trim(),
    executablePath: actualExecutable,
    executableDigest: fingerprintFile(actualExecutable),
  }
}

export function buildRuntime(sourceRoot, { buildScript = 'build:lib', pnpmExecutable = 'pnpm' } = {}) {
  const result = run(resolveExecutable(pnpmExecutable), ['run', buildScript], { cwd: sourceRoot })
  if (result.status !== 0) {
    throw new MaterializationError(
      'DSH_STAGE_A_V1R3_BLOCK_MATERIALIZATION',
      `build step "${buildScript}" failed:\n${result.stderr || result.stdout}`,
    )
  }
  return { buildScript }
}

/**
 * Resolve an executable's absolute path + sha256 fingerprint. Never trusts a
 * bare PATH-relative name at record time.
 */
export function fingerprintExecutable(executablePath) {
  if (!isAbsolute(executablePath) || !existsSync(executablePath)) {
    throw new MaterializationError('DSH_STAGE_A_V1R3_BLOCK_RUNTIME_IDENTITY', `executable does not exist: ${executablePath}`)
  }
  const real = realpathSync(executablePath)
  return { path: real, digest: fingerprintFile(real) }
}

/**
 * Emit runtime_manifest.json. Every path recorded here must be a genuine
 * realpath descendant of `materializationRoot` (except the pinned executable
 * fingerprints, which are host tools deliberately outside the materialized
 * tree and are recorded by fingerprint, not by containment).
 */
export function buildManifest({
  sourceRoot,
  repository,
  commit,
  tree,
  expectedTag,
  packageManagerFingerprint,
  lockfileDigest,
  claudeSdkIdentity,
  patchDigests,
  profileDigests,
  launcherDigest,
  builtCliRelativePath,
  workspaceBundledChunkRelativePaths = [],
  executableFingerprints,
}) {
  const materializationRoot = realpathSync(sourceRoot)
  const builtCliAbsolutePath = resolve(materializationRoot, builtCliRelativePath)
  if (!existsSync(builtCliAbsolutePath)) {
    throw new MaterializationError(
      'DSH_STAGE_A_V1R3_BLOCK_MATERIALIZATION',
      `expected built CLI output missing after build: ${builtCliAbsolutePath}`,
    )
  }
  const builtCliDigest = fingerprintFile(builtCliAbsolutePath)
  const workspaceBundledChunks = {}
  for (const rel of workspaceBundledChunkRelativePaths) {
    const abs = resolve(materializationRoot, rel)
    if (!existsSync(abs)) {
      throw new MaterializationError('DSH_STAGE_A_V1R3_BLOCK_MATERIALIZATION', `expected build chunk missing: ${abs}`)
    }
    workspaceBundledChunks[rel] = abs
  }
  return {
    phaseId: 'DSH_STAGE_A_V1R3R1_REAL_RUNTIME_QUALIFICATION_V0',
    materializationRoot,
    sourceIdentity: { repository: repository ?? 'deepseek-ai/deepseek-harness', commit, tree, tag: expectedTag ?? null },
    packageManagerFingerprint,
    lockfileDigest,
    claudeSdkIdentity,
    patchDigests,
    profileDigests,
    launcherDigest,
    builtCliAbsolutePath,
    builtCliDigest,
    workspaceBundledChunks,
    executableFingerprints,
    materializedAtUtc: new Date().toISOString(),
  }
}

export function writeManifest(destPath, manifest) {
  mkdirSync(resolve(destPath, '..'), { recursive: true })
  const text = `${JSON.stringify(manifest, null, 2)}\n`
  writeFileSync(destPath, text, 'utf8')
  return fingerprintText(text)
}
