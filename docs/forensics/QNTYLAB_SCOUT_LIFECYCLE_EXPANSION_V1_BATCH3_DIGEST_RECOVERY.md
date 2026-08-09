# RECOVERED_BY_DIGEST_VERIFICATION

QNTYLAB_SCOUT_LIFECYCLE_EXPANSION_V1 — ordered target list, positions 41–60
(historically referred to as "Batch 3")

## Status of the original artifact

The original Batch-3 JSON file (the standalone per-batch closure artifact analogous
to `BINANCE_USDM_LIFECYCLE_EXPANSION_V1_BATCH1.json` / `..._BATCH2.json`) was never
produced and is **not recovered**. It remains lost.

What **is** recovered is the ordered target list itself, including positions 41–60,
because the full list was written verbatim — not just its Batch-1/Batch-2 prefixes —
into `experiments/data/step1_4_result.json`, committed at
`07f793ac81483ce9cec5cbd80b1a637e7125990b` ("research: close lifecycle expansion V1
batch 1"). That committed array is independently re-hashed below and its digest
exactly equals the previously known `ordered_target_list_sha256`. No reconstruction
by inference, re-derivation, or re-sourcing was performed — positions 41–60 are
read directly out of the already-committed historical output.

## Algorithm identity

- **Commit:** `07f793ac81483ce9cec5cbd80b1a637e7125990b`
- **Path:** `scripts/step1_4.py`
- **Function:** `main()`, era-stratified round-robin over `candidate_pool`
  (candidate pool = local launch-manifest snapshot minus the 18 V0-audited symbols),
  bucketed by first-archive-year ("era"), each era bucket sorted by `(start, symbol)`,
  then drained round-robin across eras in ascending era order to build
  `ordered_target_list`.

## Input snapshot identity

- `experiments/data/manifests_index.json` (committed at `07f793a`) — per-symbol
  `file`, `file_sha256`, `start`, `end`, `complete_archive_months_only`, `gaps`,
  `content_sha256`, derived from `experiments/data/launch_manifest_snapshot/*.json`
  (168 files, also committed at `07f793a`).
- The V0-audited-18 exclusion set, sourced at execution time from the V0 lifecycle
  manifest (`audited18` field, recorded inline in `step1_4_result.json`).
- These are the frozen, already-committed materialization of the algorithm's inputs;
  the ephemeral `/tmp/...` paths referenced inside `scripts/step1_4.py` are the
  original execution-time source locations and no longer exist, but the committed
  output artifact is the authoritative frozen record of what those inputs produced.

## Preimage format (HASH_PREIMAGE_FORMAT)

```python
def canonical_bytes(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()

def sha256_hex(b):
    return hashlib.sha256(b).hexdigest()

ordered_target_list_sha256 = sha256_hex(canonical_bytes(ordered_target_list))
```
(`scripts/step1_4.py`, commit `07f793a`)

## Expected vs. recomputed digest

```
EXPECTED_SHA256: 6a10d2d39c9f28dc267811092e6f5ab71abc093156cb7eec6f105c5a24c2c1e2
REPLAY_SHA256:   6a10d2d39c9f28dc267811092e6f5ab71abc093156cb7eec6f105c5a24c2c1e2
MATCH:           YES
```

Recomputed by independently applying `canonical_bytes` + `sha256_hex` (as defined
above) to the `ordered_target_list` array stored in
`experiments/data/step1_4_result.json` at commit `07f793a`. `ordered_target_count`
in that file is 162 (the full candidate-pool ordering, of which positions 1–60 are
the ones referred to as Batch 1/2/3).

## Prefix verification

- Positions 1–20 (`ordered_target_list[0:20]`) exactly equal `batch_1` in the same
  file, and exactly equal the `batch2_target_list`'s predecessor batch as closed in
  `BINANCE_USDM_LIFECYCLE_EXPANSION_V1_BATCH1.json` (commit `07f793a`). **MATCH.**
- Positions 21–40 (`ordered_target_list[20:40]`) exactly equal `batch2_target_list`
  in `experiments/data/expansion_v1_batch2_evidence.json`, commit `17a41f3f8d1f975d35019a60ed9e1f352a9757ef`
  ("research: close lifecycle expansion V1 batch 2"). **MATCH.**

## Recovered positions 41–60

```
41. ETCUSDT
42. MANAUSDT
43. INJUSDT
44. ARBUSDT
45. ETHFIUSDT
46. SIRENUSDT
47. LINKUSDT
48. ALICEUSDT
49. LDOUSDT
50. LEVERUSDT
51. ENAUSDT
52. PAXGUSDT
53. XLMUSDT
54. HBARUSDT
55. APTUSDT
56. BLURUSDT
57. SAGAUSDT
58. FUNUSDT
59. XMRUSDT
60. ONEUSDT
```

## Verdict

`FROZEN_60_TARGET_SET_DIGEST_VERIFIED_RECOVERED`
