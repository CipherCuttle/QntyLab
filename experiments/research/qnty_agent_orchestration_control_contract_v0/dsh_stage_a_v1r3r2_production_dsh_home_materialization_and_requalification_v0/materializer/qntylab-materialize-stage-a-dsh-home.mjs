#!/usr/bin/env node

// The production Stage-A DSH_HOME materializer.
//
// This is the ONLY production authority for constructing a Stage-A DSH_HOME.
// It replaces the qualification-only `prepareDisposableDshHome` helper, whose
// bytes came from an ambient scratch directory that is not canonical and whose
// absence produced the V0R4 BLOCK_RUNTIME_IDENTITY terminal outcome.
//
// Every materialized object derives from a canonical source:
//   * profiles/headless/*        — template constants in the pinned DSH source
//                                  (deepseek-ai/deepseek-harness 99f6f02, Git-bound)
//   * profiles/node_modules/*    — the pinned runtime materialization root, via
//                                  DSH's own `healProfilesModuleFallback` closure
//   * profiles/node_modules/@qntylab/* — Git-tracked QntyLab Stage-A packages
//
// No ambient scratch directory, operator HOME path, or previously materialized
// DSH_HOME is read, written, required, or trusted. The materializer succeeds on
// a machine where those directories do not exist.

import { createHash } from 'node:crypto'
import {
  cpSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  realpathSync,
  statSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs'
import { createRequire } from 'node:module'
import { homedir } from 'node:os'
import { basename, dirname, isAbsolute, join, relative, resolve, sep } from 'node:path'
import { fileURLToPath } from 'node:url'

import { canonicalJson, sha256Canonical } from '../../dsh_stage_a_v1r3r2_composite_live_launcher_integration_and_requalification_v0/evidence/canonical-json.mjs'

const PHASE = resolve(fileURLToPath(import.meta.url), '../..')
export const ROOT = resolve(PHASE, '../../../..')
export const STAGE_A_PHASE = resolve(
  ROOT,
  'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_stage_a_v1r3r2_prelive_execution_enforcement_gap_closure_v0',
)
export const DEFAULT_RUNTIME_MANIFEST = resolve(
  ROOT,
  'experiments/research/qnty_agent_orchestration_control_contract_v0/dsh_runtime_materialization_and_launch_v0/evidence/runtime_manifest.json',
)

export const DSH_HOME_MANIFEST_FILENAME = 'dsh-home-manifest.json'
export const DSH_HOME_MANIFEST_SCHEMA_VERSION = 'qntylab-stage-a-production-dsh-home-manifest-v0'

/** Ambient roots that may never supply bytes, confer identity, or be required. */
export const NON_AUTHORITATIVE_AMBIENT_ROOTS = Object.freeze([
  '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair/dsh-home',
  '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r2-claude-repair-source',
  '/home/swirky/DevHub/scratch/qntylab-dsh-v1r3r1-repair-source-2',
  '/home/swirky/node_modules',
])

/** The four headless profile files, and the pinned-source constant each derives from. */
const PROFILE_TEMPLATE_SOURCES = Object.freeze({
  'cordis.yml': { relativePath: 'apps/cli/src/profile-boot.ts', constant: 'PROFILE_ROOT_CONFIG' },
  'cordis.patch.yml': { relativePath: 'packages/boot/app-boot/src/profile.ts', constant: 'PROFILE_PATCH_TEMPLATE' },
  'pnpm-workspace.yaml': { relativePath: 'packages/boot/app-boot/src/profile.ts', constant: 'PROFILE_PNPM_WORKSPACE' },
})

/** `SHIPPED_PROFILE_TEMPLATES.headless` in the pinned source; the profile manifest bundle tuple. */
const HEADLESS_BUNDLES = Object.freeze(['@deepseek-ai/dsh-base', '@deepseek-ai/dsh-headless'])

/** The dsh app manifest, relative to the pinned materialization root: `INSTALL_ANCHOR`. */
const INSTALL_ANCHOR_RELATIVE = 'apps/cli/package.json'

/**
 * The Stage-A runtime packages the composite launch policy pins by package-tree
 * digest. Two of them (the subagent providers) are out-of-tree plugins inserted
 * by the Stage-A policy patch, so DSH's own dependency closure does not reach
 * them; all six are pinned to their canonical workspace directories because the
 * qualified contract's tree digests are computed over exactly those directories.
 */
const STAGE_A_RUNTIME_PACKAGES = Object.freeze({
  'dsh-llm': 'packages/llm/llm',
  'dsh-llm-pi-ai': 'packages/llm/llm-pi-ai',
  'dsh-subagent-claude-code': 'packages/subagent/subagent-claude-code',
  'dsh-subagent-codex': 'packages/subagent/subagent-codex',
  'dsh-subprocess': 'packages/subprocess/subprocess',
  'dsh-tool-subagent': 'packages/subagent/tool-subagent',
})

/** Production @qntylab packages, resolved against the Git-tracked Stage-A phase. */
const PRODUCTION_QNTYLAB_PACKAGES = Object.freeze({
  'dsh-stage-a-gated-provider': 'profile/qntylab-stage-a-gated-provider',
  'dsh-stage-a-parent-enforcement': 'profile/qntylab-stage-a-parent-enforcement',
})

/** Never part of a production DSH_HOME identity; qualification overlay only. */
export const QUALIFICATION_ONLY_QNTYLAB_PACKAGES = Object.freeze({
  'dsh-stage-a-stub-provider': 'stub/qntylab-stage-a-stub-provider',
})

export class MaterializationError extends Error {
  constructor(code, message) {
    super(message)
    this.name = 'MaterializationError'
    this.code = code
  }
}

const failWith = (code, message) => { throw new MaterializationError(code, message) }

const digestBytes = bytes => createHash('sha256').update(bytes).digest('hex')
const digestFile = path => digestBytes(readFileSync(path))

function contained(root, candidate) {
  return candidate === root || candidate.startsWith(root.endsWith(sep) ? root : `${root}${sep}`)
}

/**
 * Extract a backtick template-literal constant from a pinned TypeScript source,
 * honouring backslash escapes so an escaped backtick does not truncate the value.
 */
function extractTemplateConstant(sourcePath, constantName) {
  const text = readFileSync(sourcePath, 'utf8')
  const marker = `const ${constantName} = \``
  const start = text.indexOf(marker)
  if (start < 0) failWith('BLOCK_SOURCE_PROVENANCE', `pinned source constant not found: ${constantName} in ${sourcePath}`)
  let index = start + marker.length
  const from = index
  for (;;) {
    if (index >= text.length) failWith('BLOCK_SOURCE_PROVENANCE', `unterminated template constant: ${constantName}`)
    if (text[index] === '\\') { index += 2; continue }
    if (text[index] === '`') break
    index += 1
  }
  const raw = text.slice(from, index)
  if (raw.includes('${')) failWith('BLOCK_SOURCE_PROVENANCE', `template constant is interpolated, not a literal: ${constantName}`)
  return raw.replace(/\\`/g, '`')
}

/**
 * Derive the four headless profile files byte-exactly from the pinned DSH source.
 * The ambient scratch DSH_HOME is never read.
 * @returns `{ files, sources }` — file name to bytes, and the provenance records.
 */
export function deriveHeadlessProfileBytes(runtimeRoot) {
  const files = {}
  const sources = []
  const seen = new Map()
  for (const [name, { relativePath, constant }] of Object.entries(PROFILE_TEMPLATE_SOURCES)) {
    const sourcePath = join(runtimeRoot, relativePath)
    if (!existsSync(sourcePath)) failWith('BLOCK_SOURCE_PROVENANCE', `pinned profile template source missing: ${relativePath}`)
    if (!seen.has(relativePath)) seen.set(relativePath, digestFile(sourcePath))
    files[name] = extractTemplateConstant(sourcePath, constant)
    sources.push({
      profileFile: name,
      pinnedSourcePath: relativePath,
      pinnedSourceDigest: seen.get(relativePath),
      constant,
      kind: 'PINNED_DSH_SOURCE_TEMPLATE_CONSTANT',
    })
  }
  // `initProfile` writes the manifest with JSON.stringify(value, undefined, 2) + '\n'.
  files['package.json'] = `${JSON.stringify({
    name: 'dsh-profile-headless',
    private: true,
    dependencies: {},
    dsh: { profile: { bundles: [...HEADLESS_BUNDLES] } },
  }, undefined, 2)}\n`
  sources.push({
    profileFile: 'package.json',
    pinnedSourcePath: 'packages/boot/app-boot/src/profile.ts',
    pinnedSourceDigest: seen.get('packages/boot/app-boot/src/profile.ts'),
    constant: 'initProfile+SHIPPED_PROFILE_TEMPLATES.headless',
    kind: 'PINNED_DSH_SOURCE_GENERATOR',
  })
  sources.sort((a, b) => a.profileFile.localeCompare(b.profileFile))
  return { files, sources }
}

/**
 * Reproduce DSH's own `healProfilesModuleFallback` closure: a BFS over
 * `dependencies` + `peerDependencies` from the installation anchor, resolving
 * each name from its own real location, first resolution winning. This is the
 * canonical definition of the flat profile module fallback — the same algorithm
 * DSH runs at boot — so the materialized graph is exactly what the pinned
 * runtime would heal, and DSH's boot-time heal is a no-op over it.
 * @returns an insertion-ordered Map of package name to resolved directory.
 */
export function computeInstallationClosure(installAnchor) {
  const appManifest = JSON.parse(readFileSync(installAnchor, 'utf8'))
  const links = new Map()
  if (appManifest.name !== undefined) links.set(appManifest.name, dirname(installAnchor))
  const skipped = new Set()
  const queue = [{ anchor: installAnchor, manifest: appManifest }]
  for (let next = queue.shift(); next !== undefined; next = queue.shift()) {
    for (const dep of [
      ...Object.keys(next.manifest.dependencies ?? {}),
      ...Object.keys(next.manifest.peerDependencies ?? {}),
    ]) {
      if (links.has(dep)) continue
      let dir
      for (const searchPath of createRequire(next.anchor).resolve.paths(dep) ?? []) {
        const candidate = join(searchPath, dep)
        if (existsSync(join(candidate, 'package.json'))) { dir = candidate; break }
      }
      // A declared-but-uninstalled dependency cannot be a loader-visible plugin.
      // DSH's own heal skips it rather than failing the boot, so the production
      // graph must skip it too — but the skipped set is recorded, not silent:
      // these names are unreachable from the flat fallback by construction and
      // resolve, where they exist at all, from their dependent's real directory.
      if (dir === undefined) { skipped.add(dep); continue }
      links.set(dep, dir)
      const manifestPath = join(dir, 'package.json')
      queue.push({ anchor: manifestPath, manifest: JSON.parse(readFileSync(manifestPath, 'utf8')) })
    }
  }
  return { links, skipped: [...skipped].sort() }
}

/**
 * The complete canonical production package graph: DSH's installation closure
 * plus the six Stage-A runtime packages pinned to their workspace directories.
 * Sorted by package name so the result is order-independent.
 */
export function computeCanonicalPackageGraph(runtimeRoot) {
  const installAnchor = join(runtimeRoot, INSTALL_ANCHOR_RELATIVE)
  if (!existsSync(installAnchor)) failWith('BLOCK_SOURCE_PROVENANCE', `pinned installation anchor missing: ${INSTALL_ANCHOR_RELATIVE}`)
  const { links: closure, skipped } = computeInstallationClosure(installAnchor)
  const graph = new Map()
  for (const [name, dir] of closure) graph.set(name, { directory: dir, provenance: 'DSH_INSTALLATION_DEPENDENCY_CLOSURE' })
  for (const [name, relativePath] of Object.entries(STAGE_A_RUNTIME_PACKAGES)) {
    const full = `@deepseek-ai/${name}`
    const directory = join(runtimeRoot, relativePath)
    if (!existsSync(join(directory, 'package.json'))) {
      failWith('BLOCK_SOURCE_PROVENANCE', `Stage-A runtime package missing from the pinned runtime: ${relativePath}`)
    }
    graph.set(full, { directory, provenance: 'STAGE_A_CONTRACT_PINNED_WORKSPACE_PACKAGE' })
  }
  const sorted = new Map([...graph.entries()].sort(([a], [b]) => a.localeCompare(b)))
  return { graph: sorted, skippedDependencyEdges: skipped.filter(name => !sorted.has(name)) }
}

/** Digest a package tree the way the qualified composite launcher does. */
function selectedFiles(root, { all = false } = {}) {
  const output = []
  function visit(path) {
    for (const entry of readdirSync(path, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      if (entry.name === 'node_modules') continue
      const current = join(path, entry.name)
      if (entry.isSymbolicLink()) failWith('BLOCK_PACKAGE_IDENTITY', `package tree contains a symlink: ${current}`)
      if (entry.isDirectory()) visit(current)
      else if (entry.isFile() && (all || entry.name === 'package.json' || current.includes(`${sep}lib${sep}`))) {
        output.push([relative(root, current), digestFile(current)])
      }
    }
  }
  visit(root)
  return output
}

export function packageTreeDigest(root) {
  return sha256Canonical(selectedFiles(realpathSync(root)))
}

function packageIdentity(directory) {
  const manifest = JSON.parse(readFileSync(join(directory, 'package.json'), 'utf8'))
  return { name: manifest.name ?? null, version: manifest.version ?? null }
}

/**
 * Resolve a destination path and enforce the fresh-disposable destination policy
 * with realpath/symlink-aware containment. The nearest existing ancestor is
 * realpathed so a symlinked parent cannot smuggle the destination into a
 * forbidden root.
 */
export function resolveDestination(destination, { runtimeRoot, qntyLabRoot = ROOT, operatorHome = homedir() } = {}) {
  if (typeof destination !== 'string' || destination.length === 0) failWith('BLOCK_DESTINATION', 'destination is required')
  if (!isAbsolute(destination)) failWith('BLOCK_DESTINATION', `destination must be absolute: ${destination}`)
  const normalized = resolve(destination)

  let ancestor = normalized
  const trailing = []
  while (!existsSync(ancestor)) {
    const parent = dirname(ancestor)
    if (parent === ancestor) failWith('BLOCK_DESTINATION', `destination has no existing ancestor: ${destination}`)
    trailing.unshift(basename(ancestor))
    ancestor = parent
  }
  const realAncestor = realpathSync(ancestor)
  const realDestination = trailing.length === 0 ? realAncestor : join(realAncestor, ...trailing)

  if (existsSync(normalized)) {
    const stat = lstatSync(normalized)
    if (stat.isSymbolicLink()) failWith('BLOCK_DESTINATION', `destination is a symlink: ${destination}`)
    if (!stat.isDirectory()) failWith('BLOCK_DESTINATION', `destination exists and is not a directory: ${destination}`)
    const entries = readdirSync(normalized)
    if (entries.length > 0) {
      failWith('BLOCK_DESTINATION', `destination is not empty (fresh destination required, reuse is forbidden): ${destination}`)
    }
  }

  const forbidden = [
    ['QNTYLAB_ROOT', realpathSync(qntyLabRoot)],
    ['DSH_RUNTIME_ROOT', realpathSync(runtimeRoot)],
    ['OPERATOR_HOME', realpathSync(operatorHome)],
  ]
  for (const [label, root] of forbidden) {
    if (contained(root, realDestination)) failWith('BLOCK_DESTINATION', `destination is inside ${label}: ${destination}`)
  }
  for (const ambient of NON_AUTHORITATIVE_AMBIENT_ROOTS) {
    let realAmbient
    try { realAmbient = realpathSync(ambient) } catch { continue }
    if (contained(realAmbient, realDestination)) failWith('BLOCK_DESTINATION', `destination is inside a non-authoritative ambient root: ${destination}`)
  }
  return { path: normalized, realPath: realDestination }
}

/** Read and verify the pinned runtime identity. Never mutates the runtime. */
export function readRuntimeIdentity(runtimeManifestPath = DEFAULT_RUNTIME_MANIFEST) {
  if (!existsSync(runtimeManifestPath)) failWith('BLOCK_RUNTIME_IDENTITY', `runtime manifest missing: ${runtimeManifestPath}`)
  const manifest = JSON.parse(readFileSync(runtimeManifestPath, 'utf8'))
  let runtimeRoot
  try { runtimeRoot = realpathSync(manifest.materializationRoot) } catch {
    failWith('BLOCK_RUNTIME_IDENTITY', `pinned runtime materialization root is unavailable: ${manifest.materializationRoot}`)
  }
  const builtCli = join(runtimeRoot, relative(manifest.materializationRoot, manifest.builtCliAbsolutePath))
  if (!existsSync(builtCli)) failWith('BLOCK_RUNTIME_IDENTITY', 'pinned built CLI is missing')
  const observed = {
    sourceCommit: manifest.sourceIdentity?.commit ?? null,
    sourceTree: manifest.sourceIdentity?.tree ?? null,
    sourceTag: manifest.sourceIdentity?.tag ?? null,
    lockfileDigest: digestFile(join(runtimeRoot, 'pnpm-lock.yaml')),
    builtCliDigest: digestFile(builtCli),
  }
  if (observed.lockfileDigest !== manifest.lockfileDigest) failWith('BLOCK_RUNTIME_IDENTITY', 'pinned lockfile bytes changed')
  if (observed.builtCliDigest !== manifest.builtCliDigest) failWith('BLOCK_RUNTIME_IDENTITY', 'pinned built CLI bytes changed')
  return { manifest, runtimeRoot, observed, manifestArtifactDigest: digestFile(runtimeManifestPath) }
}

/**
 * Materialize a complete production Stage-A DSH_HOME into a fresh destination.
 *
 * @param destination            absolute path to an empty or nonexistent directory.
 * @param runtimeManifestPath    the pinned runtime manifest artifact.
 * @param classification         'PRODUCTION' (default). Any other value is rejected;
 *                               the qualification overlay is a separate, explicit step.
 * @returns the DSH_HOME manifest and its canonical digest.
 */
export function materializeStageADshHome({
  destination,
  runtimeManifestPath = DEFAULT_RUNTIME_MANIFEST,
  stageAPhaseRoot = STAGE_A_PHASE,
  classification = 'PRODUCTION',
  qntyLabRoot = ROOT,
  operatorHome = homedir(),
} = {}) {
  if (classification !== 'PRODUCTION') {
    failWith('BLOCK_CLASSIFICATION', `the production materializer only produces PRODUCTION homes; got ${classification}`)
  }
  const runtime = readRuntimeIdentity(runtimeManifestPath)
  const { runtimeRoot } = runtime
  const target = resolveDestination(destination, { runtimeRoot, qntyLabRoot, operatorHome })

  const beforeIdentity = { ...runtime.observed }
  const { files: profileFiles, sources: profileSources } = deriveHeadlessProfileBytes(runtimeRoot)
  const { graph, skippedDependencyEdges } = computeCanonicalPackageGraph(runtimeRoot)

  // ---- write the fresh home -------------------------------------------------
  const profilesDir = join(target.path, 'profiles')
  const headlessDir = join(profilesDir, 'headless')
  const modulesDir = join(profilesDir, 'node_modules')
  mkdirSync(headlessDir, { recursive: true })
  mkdirSync(modulesDir, { recursive: true })

  const objects = []
  for (const name of Object.keys(profileFiles).sort()) {
    const bytes = Buffer.from(profileFiles[name], 'utf8')
    writeFileSync(join(headlessDir, name), bytes)
    objects.push({
      path: `profiles/headless/${name}`,
      type: 'file',
      digest: digestBytes(bytes),
      byteLength: bytes.length,
      canonicalSource: 'PINNED_DSH_SOURCE',
      classification: 'PRODUCTION',
    })
  }

  const packageInventory = []
  for (const [name, { directory, provenance }] of graph) {
    const linkPath = join(modulesDir, name)
    mkdirSync(dirname(linkPath), { recursive: true })
    let realTarget
    try { realTarget = realpathSync(directory) } catch {
      failWith('BLOCK_PACKAGE_PROVENANCE', `canonical package target is unresolvable: ${name}`)
    }
    if (!contained(runtimeRoot, realTarget)) {
      failWith('BLOCK_SYMLINK_CONTAINMENT', `package target escapes the pinned runtime root: ${name} -> ${realTarget}`)
    }
    symlinkSync(directory, linkPath, 'junction')
    const identity = packageIdentity(directory)
    const record = {
      path: `profiles/node_modules/${name}`,
      type: 'symlink',
      packageName: name,
      declaredName: identity.name,
      version: identity.version,
      targetRelativeToRuntimeRoot: relative(runtimeRoot, directory),
      targetRealpathRelativeToRuntimeRoot: relative(runtimeRoot, realTarget),
      containment: 'PINNED_DSH_RUNTIME_ROOT',
      packageJsonDigest: digestFile(join(directory, 'package.json')),
      canonicalSource: provenance,
      classification: 'PRODUCTION',
    }
    if (Object.prototype.hasOwnProperty.call(STAGE_A_RUNTIME_PACKAGES, name.replace('@deepseek-ai/', ''))
      && name.startsWith('@deepseek-ai/')) {
      record.packageTreeDigest = packageTreeDigest(directory)
      record.stageAContractPinned = true
    }
    objects.push(record)
    packageInventory.push({ packageName: name, version: identity.version, canonicalSource: provenance })
  }

  const qntyScope = join(modulesDir, '@qntylab')
  mkdirSync(qntyScope, { recursive: true })
  for (const name of Object.keys(PRODUCTION_QNTYLAB_PACKAGES).sort()) {
    const sourceDir = join(stageAPhaseRoot, PRODUCTION_QNTYLAB_PACKAGES[name])
    if (!existsSync(join(sourceDir, 'package.json'))) {
      failWith('BLOCK_PACKAGE_PROVENANCE', `canonical @qntylab package missing: ${name}`)
    }
    const destinationDir = join(qntyScope, name)
    cpSync(sourceDir, destinationDir, { recursive: true, dereference: false })
    const identity = packageIdentity(destinationDir)
    const files = selectedFiles(realpathSync(destinationDir), { all: true })
    objects.push({
      path: `profiles/node_modules/@qntylab/${name}`,
      type: 'package-tree',
      packageName: `@qntylab/${name}`,
      declaredName: identity.name,
      version: identity.version,
      packageTreeDigest: sha256Canonical(selectedFiles(realpathSync(destinationDir))),
      wholeTreeDigest: sha256Canonical(files),
      fileCount: files.length,
      canonicalSource: 'GIT_TRACKED_QNTYLAB_STAGE_A_PACKAGE',
      canonicalSourcePath: relative(qntyLabRoot, sourceDir),
      classification: 'PRODUCTION',
    })
    packageInventory.push({ packageName: `@qntylab/${name}`, version: identity.version, canonicalSource: 'GIT_TRACKED_QNTYLAB_STAGE_A_PACKAGE' })
  }

  // ---- fail closed on anything unexpected -----------------------------------
  verifyMaterializedHome(target.path, { runtimeRoot })

  const afterIdentity = { ...readRuntimeIdentity(runtimeManifestPath).observed }
  if (canonicalJson(beforeIdentity) !== canonicalJson(afterIdentity)) {
    failWith('SCOPE_EXPANSION_REQUIRED', 'pinned runtime identity changed during materialization')
  }

  objects.sort((a, b) => a.path.localeCompare(b.path))
  packageInventory.sort((a, b) => a.packageName.localeCompare(b.packageName))

  const identityBody = {
    artifactType: 'QNTYLAB_STAGE_A_PRODUCTION_DSH_HOME_MANIFEST',
    schemaVersion: DSH_HOME_MANIFEST_SCHEMA_VERSION,
    classification: 'PRODUCTION',
    provenance: {
      pinnedRuntime: {
        repository: runtime.manifest.sourceIdentity?.repository ?? null,
        commit: runtime.manifest.sourceIdentity?.commit ?? null,
        tree: runtime.manifest.sourceIdentity?.tree ?? null,
        tag: runtime.manifest.sourceIdentity?.tag ?? null,
        lockfileDigest: runtime.observed.lockfileDigest,
        builtCliDigest: runtime.observed.builtCliDigest,
        runtimeManifestArtifactDigest: runtime.manifestArtifactDigest,
      },
      installAnchorRelativePath: INSTALL_ANCHOR_RELATIVE,
      headlessBundles: [...HEADLESS_BUNDLES],
      profileTemplateSources: profileSources,
      stageAPackageSourceRelativeRoot: relative(qntyLabRoot, stageAPhaseRoot),
      ambientRootsUsed: [],
      ambientAuthorityUsed: false,
      skippedDependencyEdges: {
        count: skippedDependencyEdges.length,
        names: skippedDependencyEdges,
        basis: 'Declared dependencies with no installed directory under the pinned runtime. DSH\'s own healProfilesModuleFallback skips these identically, so none is loader-visible through the flat profile fallback; where such a package exists it resolves from its dependent\'s real directory by ordinary Node symlink-following.',
        loaderVisibleUnresolvedPackages: 0,
      },
    },
    packageInventory,
    objects,
    productionStubProviderPresent: false,
    nondeterministicResidue: [
      {
        field: 'materializedAtUtc',
        reason: 'wall-clock stamp; observational only',
        excludedFromIdentity: true,
      },
      {
        field: 'destinationAbsolutePath',
        reason: 'the destination is a fresh disposable directory whose absolute path is chosen per run; identity is path-independent by construction',
        excludedFromIdentity: true,
      },
      {
        field: 'materializationRootAbsolutePath',
        reason: 'the pinned runtime root is an absolute machine path; every symlink target is recorded relative to it so home identity does not encode it. Because this field is outside the identity digest it is never trusted as containment authority: verifyHomeManifest derives the root from the pinned runtime manifest and requires this recorded value to equal it',
        excludedFromIdentity: true,
      },
    ],
  }

  const homeManifestDigest = sha256Canonical(identityBody)
  const manifest = {
    ...identityBody,
    homeManifestDigest,
    materializedAtUtc: new Date().toISOString(),
    destinationAbsolutePath: target.path,
    materializationRootAbsolutePath: runtimeRoot,
  }
  writeFileSync(join(target.path, DSH_HOME_MANIFEST_FILENAME), `${JSON.stringify(manifest, undefined, 2)}\n`)
  return { destination: target.path, runtimeRoot, manifest, homeManifestDigest, identityBody }
}

/**
 * Verify a materialized DSH_HOME fails closed on every rejected condition:
 * a stub provider in production, unexpected @qntylab packages, missing required
 * packages, and any symlink escaping the pinned runtime root.
 */
export function verifyMaterializedHome(home, { runtimeRoot, allowQualificationStub = false } = {}) {
  const modulesDir = join(home, 'profiles/node_modules')
  const headlessDir = join(home, 'profiles/headless')
  for (const name of ['cordis.yml', 'cordis.patch.yml', 'package.json', 'pnpm-workspace.yaml']) {
    if (!existsSync(join(headlessDir, name))) failWith('BLOCK_PROFILE_IDENTITY', `materialized home is missing profiles/headless/${name}`)
  }
  const qntyScope = join(modulesDir, '@qntylab')
  if (!existsSync(qntyScope)) failWith('BLOCK_RUNTIME_IDENTITY', 'materialized home is missing the Stage-A package scope')
  const present = readdirSync(qntyScope).sort()
  const allowed = new Set([
    ...Object.keys(PRODUCTION_QNTYLAB_PACKAGES),
    ...(allowQualificationStub ? Object.keys(QUALIFICATION_ONLY_QNTYLAB_PACKAGES) : []),
  ])
  for (const name of present) {
    if (Object.prototype.hasOwnProperty.call(QUALIFICATION_ONLY_QNTYLAB_PACKAGES, name) && !allowQualificationStub) {
      failWith('BLOCK_PRODUCTION_STUB_PROVIDER', `qualification-only stub provider present in a production DSH_HOME: @qntylab/${name}`)
    }
    if (!allowed.has(name)) failWith('BLOCK_PACKAGE_IDENTITY', `unexpected @qntylab package: ${name}`)
  }
  for (const name of Object.keys(PRODUCTION_QNTYLAB_PACKAGES)) {
    if (!present.includes(name)) failWith('BLOCK_PACKAGE_IDENTITY', `required @qntylab package missing: ${name}`)
  }
  for (const name of Object.keys(STAGE_A_RUNTIME_PACKAGES)) {
    const path = join(modulesDir, '@deepseek-ai', name)
    if (!existsSync(path)) failWith('BLOCK_RUNTIME_IDENTITY', `required runtime package missing: ${name}`)
    if (!contained(runtimeRoot, realpathSync(path))) failWith('BLOCK_SYMLINK_CONTAINMENT', `runtime package escapes the pinned root: ${name}`)
  }
  // Every symlink anywhere in the home must resolve inside the pinned runtime root.
  const walk = directory => {
    for (const entry of readdirSync(directory, { withFileTypes: true })) {
      const current = join(directory, entry.name)
      if (entry.isSymbolicLink()) {
        let real
        try { real = realpathSync(current) } catch {
          failWith('BLOCK_SYMLINK_CONTAINMENT', `dangling symlink in materialized home: ${relative(home, current)}`)
        }
        if (!contained(runtimeRoot, real)) {
          failWith('BLOCK_SYMLINK_CONTAINMENT', `symlink escapes the pinned runtime root: ${relative(home, current)} -> ${real}`)
        }
        continue
      }
      if (entry.isDirectory()) walk(current)
    }
  }
  walk(join(home, 'profiles'))
  return true
}

/**
 * Apply the bounded offline qualification overlay to an already materialized
 * home: add the qualification-only stub provider and reclassify the manifest.
 * This is never reachable from the production materialization path.
 */
export function applyQualificationOverlay(home, { stageAPhaseRoot = STAGE_A_PHASE } = {}) {
  const manifestPath = join(home, DSH_HOME_MANIFEST_FILENAME)
  if (!existsSync(manifestPath)) failWith('BLOCK_HOME_MANIFEST', 'cannot overlay a home without a DSH_HOME manifest')
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  const qntyScope = join(home, 'profiles/node_modules/@qntylab')
  const overlayed = []
  for (const [name, relativePath] of Object.entries(QUALIFICATION_ONLY_QNTYLAB_PACKAGES)) {
    cpSync(join(stageAPhaseRoot, relativePath), join(qntyScope, name), { recursive: true, dereference: false })
    overlayed.push(`@qntylab/${name}`)
  }
  manifest.classification = 'QUALIFICATION_OVERLAY'
  manifest.productionStubProviderPresent = true
  manifest.qualificationOverlayPackages = overlayed
  manifest.productionHomeManifestDigest = manifest.homeManifestDigest
  manifest.homeManifestDigest = null
  manifest.overlayNote = 'Qualification overlay only. This home is NOT a production DSH_HOME identity and carries no production home-manifest digest.'
  writeFileSync(manifestPath, `${JSON.stringify(manifest, undefined, 2)}\n`)
  return { home, overlayed, productionHomeManifestDigest: manifest.productionHomeManifestDigest }
}

/**
 * Enumerate everything physically present under `profiles/` and return whatever
 * the manifest does not record. Drift and deletion are caught by digesting the
 * recorded objects; this catches the remaining direction, addition, so that a
 * package or file nobody vouched for cannot ride along inside a home that
 * otherwise verifies.
 */
function unrecordedObjects(home, recordedPaths) {
  const containers = new Set()
  for (const recorded of recordedPaths) {
    const parts = recorded.split('/')
    for (let index = 1; index < parts.length; index += 1) containers.add(parts.slice(0, index).join('/'))
  }
  const additions = []
  const walk = directory => {
    for (const entry of readdirSync(directory, { withFileTypes: true }).sort((a, b) => a.name.localeCompare(b.name))) {
      const current = join(directory, entry.name)
      const relativePath = relative(home, current)
      // A recorded object is covered by its own digest; never descend into it.
      if (recordedPaths.has(relativePath)) continue
      if (entry.isDirectory() && !entry.isSymbolicLink() && containers.has(relativePath)) { walk(current); continue }
      additions.push(relativePath)
    }
  }
  walk(join(home, 'profiles'))
  return additions
}

/**
 * Recompute a materialized home's identity from disk and compare to its manifest.
 *
 * The pinned runtime root is taken from the runtime manifest, never from the
 * DSH_HOME manifest. The home manifest deliberately excludes that absolute path
 * from its identity digest, so a forged manifest could otherwise nominate its
 * own containment root — widening it to `/` would let every symlink "resolve
 * inside the runtime root" and pass. The recorded value is still checked, but
 * as a claim to be confirmed rather than as the authority.
 */
export function verifyHomeManifest(home, { runtimeManifestPath = DEFAULT_RUNTIME_MANIFEST } = {}) {
  const manifestPath = join(home, DSH_HOME_MANIFEST_FILENAME)
  if (!existsSync(manifestPath)) failWith('BLOCK_HOME_MANIFEST', `DSH_HOME manifest missing: ${manifestPath}`)
  const manifest = JSON.parse(readFileSync(manifestPath, 'utf8'))
  if (manifest.classification !== 'PRODUCTION') {
    failWith('BLOCK_HOME_MANIFEST', `not a production DSH_HOME manifest: ${manifest.classification}`)
  }
  const { homeManifestDigest, materializedAtUtc, destinationAbsolutePath, materializationRootAbsolutePath, ...identityBody } = manifest
  const recomputed = sha256Canonical(identityBody)
  if (recomputed !== homeManifestDigest) failWith('BLOCK_HOME_MANIFEST', 'DSH_HOME manifest digest does not match its own identity body')

  // Containment authority comes from the pinned runtime manifest, not the home.
  const runtimeRoot = readRuntimeIdentity(runtimeManifestPath).runtimeRoot
  if (materializationRootAbsolutePath !== runtimeRoot) {
    failWith('BLOCK_HOME_MANIFEST', `DSH_HOME manifest names a foreign materialization root: ${materializationRootAbsolutePath}`)
  }

  // Nothing may be present that the manifest does not record.
  const additions = unrecordedObjects(home, new Set(manifest.objects.map(object => object.path)))
  if (additions.length > 0) {
    failWith('BLOCK_HOME_MANIFEST', `materialized home contains unrecorded objects: ${additions.slice(0, 5).join(', ')}`)
  }

  // Re-verify every recorded object against the bytes actually on disk.
  for (const object of manifest.objects) {
    const path = join(home, object.path)
    if (object.type === 'file') {
      if (!existsSync(path) || digestFile(path) !== object.digest) failWith('BLOCK_HOME_MANIFEST', `manifest object drifted: ${object.path}`)
    } else if (object.type === 'symlink') {
      if (!lstatSync(path).isSymbolicLink()) failWith('BLOCK_HOME_MANIFEST', `manifest object is no longer a symlink: ${object.path}`)
      const real = realpathSync(path)
      if (relative(runtimeRoot, real) !== object.targetRealpathRelativeToRuntimeRoot) {
        failWith('BLOCK_HOME_MANIFEST', `symlink target drifted: ${object.path}`)
      }
    } else if (object.type === 'package-tree') {
      if (sha256Canonical(selectedFiles(realpathSync(path), { all: true })) !== object.wholeTreeDigest) {
        failWith('BLOCK_HOME_MANIFEST', `package tree drifted: ${object.path}`)
      }
    }
  }
  verifyMaterializedHome(home, { runtimeRoot })
  return { manifest, homeManifestDigest }
}

export const MATERIALIZER_PATH = relative(ROOT, fileURLToPath(import.meta.url))
