import { createHash } from 'node:crypto'
export function canonicalize(value) {
  if (Array.isArray(value)) return value.map(canonicalize)
  if (value !== null && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonicalize(value[key])]))
  return value
}
export function canonicalJson(value) { return JSON.stringify(canonicalize(value)) }
export function sha256Canonical(value) { return createHash('sha256').update(canonicalJson(value), 'utf8').digest('hex') }
