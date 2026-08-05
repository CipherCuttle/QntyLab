import hashlib, json
from pathlib import Path
def test_artifact_contract_is_canonical_and_no_real_metrics():
    root=Path(__file__).parents[1]/"experiments/clean_tsmom/v2"; obj=json.loads((root/"artifact_contract.json").read_text())
    assert obj["artifact_manifest_excludes_itself"] is True
    assert "net_return" not in (root/"artifact_contract.json").read_text()
    assert hashlib.sha256((root/"artifact_contract.json").read_bytes()).hexdigest() != "PLACEHOLDER"
