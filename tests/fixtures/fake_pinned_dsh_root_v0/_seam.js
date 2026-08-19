// Shared recorder for the no-live DSH seam.  Never contacts a product.
import { appendFileSync } from 'node:fs'

export function record(event) {
  const target = process.env.QNTYLAB_FAKE_DSH_TRACE
  if (target) appendFileSync(target, JSON.stringify(event) + '\n')
}
