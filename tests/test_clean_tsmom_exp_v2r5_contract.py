import json
from pathlib import Path
ROOT = Path(__file__).parents[1]
def test_r5_contract_identity_and_required_fields():
    semantics = json.loads((ROOT / "experiments/clean_tsmom/v2r5/accounting_semantics_r5.json").read_bytes()); artifact = json.loads((ROOT / "experiments/clean_tsmom/v2r5/artifact_contract_r5.json").read_bytes())
    assert semantics["contract_revision"] == "ACCOUNTING_SEMANTICS_R5"; assert semantics["real_results_exposed_before_r5"] == 0; assert artifact["identity_tolerance"] == 1e-12; assert "liquidation_turnover" in artifact["required_ledger_fields"]
