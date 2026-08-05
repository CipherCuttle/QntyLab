"""EXP_V2 R1 producer adapter with explicit external source binding."""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.verify_clean_tsmom_exp_v2r1_source_binding import verify_source_binding

ARTIFACTS = ("panel", "signals", "v1_weights", "v2_weights", "funding_assignments", "funding_returns", "turnover", "costs", "equity", "controls", "diagnostics", "metrics", "classifications", "final_liquidation")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-dir", type=Path, required=True)
    parser.add_argument("--binding-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise ValueError("output directory must be empty")
    binding_result = verify_source_binding(args.contract_dir, args.binding_dir, args.source_root)
    from qntylab.clean_tsmom_exp_v2 import canonical_bytes, produce, sha256_bytes

    with tempfile.TemporaryDirectory(prefix="clean-tsmom-exp-v2r1-") as temp:
        experiment_root = Path(temp)
        (experiment_root / "data").mkdir()
        (experiment_root / "data" / "raw").symlink_to((args.source_root / "data" / "raw").resolve(), target_is_directory=True)
        result = produce(experiment_root)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    entries = {}
    for name in ARTIFACTS:
        payload = canonical_bytes(result[name])
        path = args.output_dir / f"{name}.json"
        path.write_bytes(payload)
        entries[path.name] = {"sha256": sha256_bytes(payload), "bytes": len(payload)}
    (args.output_dir / "artifact_manifest.json").write_bytes(canonical_bytes({"schema": "clean-tsmom-exp-v2-artifacts-v1", "files": entries}))
    print("CLEAN_TSMOM_EXP_V2_R1_PRODUCER_ADAPTER_PASS")
    print(f"source_files_verified={binding_result['source_files_present']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(1)
