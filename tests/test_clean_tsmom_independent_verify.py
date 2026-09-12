import json
from pathlib import Path

import pytest

from tools.verify_clean_tsmom_v2_contract import verify


ROOT = Path(__file__).parents[1] / "experiments" / "clean_tsmom" / "v2"


def test_exp_v2_static_contract_verifies_without_evaluator():
    verify(ROOT)


def test_result_material_and_tampering_are_rejected(tmp_path):
    target = tmp_path / "v2"
    target.mkdir()
    for path in ROOT.iterdir():
        target.joinpath(path.name).write_bytes(path.read_bytes())
    target.joinpath("evaluation_v2.json").write_text(
        json.dumps({"result_status": "NOT_YET_RUN", "net_return": 0.0}), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        verify(target)
