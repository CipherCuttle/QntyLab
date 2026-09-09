"""H003_SIGNAL_INTENT_V0 — frozen signal reproduction + immutable intent artifact.

Phase: QNTY_H003_SOL_TO_QNTYSPOT_SHADOW_BRIDGE_V0 (Subtask B+C).

Mechanically reproduces the frozen candidate CANDIDATE_H003_MA_48_192_LONG_FLAT
using the EXISTING qntylab callables (no reimplementation, no tuning):

    from qntylab.strategies import positions
    positions("H003_moving_average", close_array, {"fast": 48, "slow": 192, "mode": "long_flat"})

and independently cross-checks the last completed bar's raw signal with exact
rational arithmetic (fractions.Fraction over the decimal close strings).

Determinism / replay contract:
  * Inputs are ONLY the refreshed CSV (data/raw/SOLUSDT-1h.csv) and its
    manifest (data/manifests/SOLUSDT-1h.json). No wall-clock reads.
  * computed_at is taken from the manifest's retrieved_at (the fetch instant),
    so a re-run over the same immutable inputs is byte-identical.
  * Canonical JSON: sorted keys, no whitespace, UTF-8.
  * artifact_digest rule: sha256 over the canonical JSON bytes of the artifact
    with the "artifact_digest" field set to the empty string "". The written
    file carries the digest filled in; the .sha256 sidecar carries the hex.
  * No JSON floats anywhere: every number is an integer or a
    {numerator, denominator} exact-rational pair.

Authority: this artifact carries an ALREADY-COMPUTED decision downstream. It
grants NO execution authority: authority block is capital/signing/submission
= NONE and execution = FORBIDDEN. No signer, key, wallet, or submission code
exists here or is created by this script.

Usage (from the QntyLab repo/worktree root):
    python3 experiments/h003_bridge_v0/compute_signal_intent.py \
        --out-dir /path/to/QntySpot-worktree/qualifications/h003_bridge_v0 \
        --source-commit <canonical-QntyLab-commit>
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from fractions import Fraction
from pathlib import Path

import numpy as np

# The documented invocation runs this file directly from the repository root;
# make the checked-out package importable without requiring installation.
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from qntylab.data import load
from qntylab.strategies import positions

SCHEMA_NAME = "H003_SIGNAL_INTENT_V0"
PHASE = "QNTY_H003_SOL_TO_QNTYSPOT_SHADOW_BRIDGE_V0"
CANDIDATE_ID = "CANDIDATE_H003_MA_48_192_LONG_FLAT"
STRATEGY_ID = "H003_moving_average"
VARIANT_ID = "variant_00eb140f03a5f6ab40600160"
STRATEGY_VERSION = "existing-qntylab-strategies-v1"
PARAMS = {"fast": 48, "slow": 192, "mode": "long_flat"}
SOURCE_SEMANTIC = "BINANCE_SPOT_SOLUSDT_1H"
SOURCE_REPOSITORY = "CipherCuttle/QntyLab"
FULL_GIT_SHA_RE = re.compile(r"\A[0-9a-f]{40}\Z")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj: dict) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def exact_ma(closes: list[str], window: int) -> Fraction:
    """Exact MA over the last `window` decimal close strings."""
    sample = closes[-window:]
    if len(sample) != window:
        raise SystemExit(f"STOP: only {len(sample)} closes available, need {window}")
    total = Fraction(0)
    for c in sample:
        total += Fraction(c)
    return total / window


def sign_exact(x: Fraction) -> int:
    return -1 if x < 0 else (1 if x > 0 else 0)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="data/raw/SOLUSDT-1h.csv")
    parser.add_argument("--manifest", default="data/manifests/SOLUSDT-1h.json")
    parser.add_argument("--out-dir", required=True, help="artifact output directory")
    parser.add_argument(
        "--source-commit",
        required=True,
        help="canonical QntyLab commit to bind into the handoff provenance",
    )
    args = parser.parse_args()

    if not FULL_GIT_SHA_RE.fullmatch(args.source_commit):
        parser.error("--source-commit must be a 40-character lowercase git SHA")

    csv_path = Path(args.csv)
    manifest_path = Path(args.manifest)
    out_dir = Path(args.out_dir)
    expected_csv = REPO_ROOT / "data" / "raw" / "SOLUSDT-1h.csv"
    expected_manifest = REPO_ROOT / "data" / "manifests" / "SOLUSDT-1h.json"
    if csv_path.resolve() != expected_csv.resolve() or manifest_path.resolve() != expected_manifest.resolve():
        parser.error("--csv and --manifest must identify the frozen SOLUSDT-1h inputs")

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    # Close-series identity: sha256 of the CSV file bytes (must equal manifest).
    csv_bytes = csv_path.read_bytes()
    csv_sha = sha256_bytes(csv_bytes)
    if csv_sha != manifest["sha256"]:
        print(f"STOP: CSV sha256 {csv_sha} != manifest sha256 {manifest['sha256']}")
        return 2

    # Load via the existing loader (validates OHLCV + gap report).
    rows = load(csv_path)
    closes_str = [row["close"] for row in rows]
    close_np = np.array([float(c) for c in closes_str], dtype=float)
    n = len(rows)
    t = n - 1  # last completed bar index

    # Frozen callable, exactly as dispatched in qntylab.strategies.positions.
    pos = positions(STRATEGY_ID, close_np, dict(PARAMS))

    # Numpy raw signal at t, mirroring qntylab/strategies.py moving_average()
    # lines 13-15 (np.convolve valid, sign of ma_fast - ma_slow). This is a
    # mechanical mirror for cross-checking, not a reimplementation of the
    # strategy: the causal positions still come from positions() above.
    kernel_fast = np.ones(PARAMS["fast"]) / PARAMS["fast"]
    kernel_slow = np.ones(PARAMS["slow"]) / PARAMS["slow"]
    ma_fast_np = np.convolve(close_np, kernel_fast, "valid")
    ma_slow_np = np.convolve(close_np, kernel_slow, "valid")
    # index algebra: ma_fast has len n-fast+1; raw[t] uses ma_fast[t-fast+1] vs ma_slow[t-slow+1]
    raw_np_t = int(np.sign(ma_fast_np[t - PARAMS["fast"] + 1] - ma_slow_np[t - PARAMS["slow"] + 1]))

    # Internal consistency of the callable's causal shift at t:
    # positions[t] must equal clamp(raw[t-1], 0) for long_flat.
    raw_np_prev = int(np.sign(ma_fast_np[t - PARAMS["fast"]] - ma_slow_np[t - PARAMS["slow"]]))
    if float(pos[t]) != float(max(raw_np_prev, 0)):
        print(f"STOP: positions()[{t}]={pos[t]} != clamp(raw[{t-1}],0)={max(raw_np_prev, 0)}")
        return 2

    # Exact rational cross-check at t.
    ma48 = exact_ma(closes_str, PARAMS["fast"])
    ma192 = exact_ma(closes_str, PARAMS["slow"])
    raw_exact = sign_exact(ma48 - ma192)
    if raw_exact != raw_np_t:
        print(f"STOP: reproduction failure — exact sign {raw_exact} != numpy raw {raw_np_t} at bar {t}")
        return 2

    # Causal target for bar t+1: _causal shifts raw[t] into position[t+1];
    # long_flat clamps via max(raw, 0).
    causal_target_num = max(raw_exact, 0)
    causal_target = "LONG" if causal_target_num == 1 else "FLAT"
    previous_target = "LONG" if float(pos[t]) > 0 else "FLAT"
    transition_action = "NO_ACTION" if previous_target == causal_target else "TARGET_CHANGE"

    first_open = rows[0]["timestamp"]
    last_open = rows[t]["timestamp"]
    close_of_t = last_open.replace("Z", "+00:00")
    from datetime import datetime, timedelta, UTC

    close_of_t = (
        datetime.fromisoformat(last_open.replace("Z", "+00:00")) + timedelta(hours=1)
    ).isoformat().replace("+00:00", "Z")

    artifact = {
        "artifact_digest": "",  # filled after hashing (digest rule: hash with this field empty)
        "authority": {
            "capital": "NONE",
            "execution": "FORBIDDEN",
            "signing": "NONE",
            "submission": "NONE",
        },
        "bar_window": {
            "bar_count": n,
            "close_of_bar_t": close_of_t,
            "first_bar_open": first_open,
            "last_bar_open": last_open,
        },
        "close_series": {
            "digest_rule": "sha256 of data/raw/SOLUSDT-1h.csv file bytes (equals manifest sha256)",
            "path": "data/raw/SOLUSDT-1h.csv",
            "sha256": csv_sha,
        },
        "computed_at": manifest["retrieved_at"],
        "computed_at_rule": "manifest retrieved_at (deterministic replay; no wall clock)",
        "phase": PHASE,
        "schema_name": SCHEMA_NAME,
        "schema_version": "V0",
        "signal": {
            "causal_target_t_plus_1": causal_target,
            "decision_bar_t_open": last_open,
            "decision_rule": "sign(ma48 - ma192) at close of bar t, clamped by long_flat; position applies t->t+1",
            "ma48": {"denominator": ma48.denominator, "numerator": ma48.numerator},
            "ma192": {"denominator": ma192.denominator, "numerator": ma192.numerator},
            "raw_signal_at_t": raw_exact,
            "source_bar_timestamp": last_open,
        },
        "transition": {
            "action": transition_action,
            "current_target": causal_target,
            "previous_target": previous_target,
        },
        "upstream": {
            "candidate_id": CANDIDATE_ID,
            "parameters": dict(PARAMS),
            "qntylab_head": args.source_commit,
            "source_commit": args.source_commit,
            "source_repository": SOURCE_REPOSITORY,
            "source_semantic": SOURCE_SEMANTIC,
            "strategy_id": STRATEGY_ID,
            "strategy_version": STRATEGY_VERSION,
            "variant_id": VARIANT_ID,
        },
    }

    digest = sha256_bytes(canonical_json(artifact))
    artifact["artifact_digest"] = digest

    out_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = out_dir / f"{SCHEMA_NAME}.json"
    artifact_path.write_bytes(canonical_json(artifact) + b"\n")
    (out_dir / f"{SCHEMA_NAME}.sha256").write_text(digest + "\n")

    print(json.dumps({
        "artifact": str(artifact_path),
        "artifact_digest": digest,
        "bar_count": n,
        "causal_target": causal_target,
        "close_of_bar_t": close_of_t,
        "csv_sha256": csv_sha,
        "last_bar_open": last_open,
        "ma48": f"{ma48.numerator}/{ma48.denominator}",
        "ma192": f"{ma192.numerator}/{ma192.denominator}",
        "raw_signal_at_t": raw_exact,
    }, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
