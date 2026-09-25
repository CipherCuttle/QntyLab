"""Independent EXP_V2 R1 result adapter; it never imports the producer."""
from __future__ import annotations

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.verify_clean_tsmom_exp_v2r1_source_binding import verify_source_binding


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--contract-dir", type=Path, required=True)
    parser.add_argument("--binding-dir", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--producer-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise ValueError("output directory must be empty")
    verify_source_binding(args.contract_dir, args.binding_dir, args.source_root)
    with tempfile.TemporaryDirectory(prefix="clean-tsmom-exp-v2r1-verify-") as temp:
        experiment_root = Path(temp)
        (experiment_root / "data").mkdir()
        (experiment_root / "data" / "raw").symlink_to((args.source_root / "data" / "raw").resolve(), target_is_directory=True)
        contract_link = experiment_root / "experiments" / "clean_tsmom"
        contract_link.mkdir(parents=True)
        (contract_link / "v2").symlink_to(args.contract_dir.resolve(), target_is_directory=True)
        command = [sys.executable, str(Path(__file__).with_name("verify_clean_tsmom_exp_v2_results.py")), "--experiment-dir", str(experiment_root), "--producer-root", str(args.producer_root), "--output-dir", str(args.output_dir)]
        return subprocess.run(command, check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
