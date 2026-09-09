"""Focused contract tests for the frozen H003 research handoff."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "experiments" / "h003_bridge_v0" / "compute_signal_intent.py"


def _run(out_dir: Path) -> None:
    subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--out-dir",
            str(out_dir),
            "--source-commit",
            "a" * 40,
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )


def test_h003_handoff_is_deterministic_and_explicitly_non_authoritative(tmp_path: Path) -> None:
    first = tmp_path / "first"
    second = tmp_path / "second"
    _run(first)
    _run(second)

    artifact_name = "H003_SIGNAL_INTENT_V0.json"
    assert (first / artifact_name).read_bytes() == (second / artifact_name).read_bytes()
    assert (first / "H003_SIGNAL_INTENT_V0.sha256").read_bytes() == (
        second / "H003_SIGNAL_INTENT_V0.sha256"
    ).read_bytes()

    artifact = json.loads((first / artifact_name).read_text(encoding="utf-8"))
    assert artifact["authority"] == {
        "capital": "NONE",
        "execution": "FORBIDDEN",
        "signing": "NONE",
        "submission": "NONE",
    }
    assert artifact["upstream"]["source_repository"] == "CipherCuttle/QntyLab"
    assert artifact["upstream"]["source_commit"] == "a" * 40
    assert artifact["upstream"]["candidate_id"] == "CANDIDATE_H003_MA_48_192_LONG_FLAT"
    assert artifact["upstream"]["strategy_id"] == "H003_moving_average"
    assert artifact["upstream"]["variant_id"] == "variant_00eb140f03a5f6ab40600160"
    assert artifact["upstream"]["parameters"] == {"fast": 48, "slow": 192, "mode": "long_flat"}
    assert artifact["upstream"]["source_semantic"] == "BINANCE_SPOT_SOLUSDT_1H"
    assert artifact["signal"]["source_bar_timestamp"] == artifact["signal"]["decision_bar_t_open"]
    assert artifact["transition"] == {
        "action": "NO_ACTION",
        "current_target": "LONG",
        "previous_target": "LONG",
    }
