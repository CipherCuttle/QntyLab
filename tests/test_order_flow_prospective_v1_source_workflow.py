from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/order-flow-prospective-v1-source-qualification.yml"
SOURCE = ROOT / "qntylab/order_flow_prospective_v1_source.py"
CONTRACT = ROOT / "experiments/research/qnty_edge_discovery_order_flow_v1/source_qualification.json"
RESULT = ROOT / "experiments/research/qnty_edge_discovery_order_flow_v1/recorder_qualification_result.json"


def test_source_qualification_workflow_is_manual_probe_only() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "pull_request:" in text
    assert "workflow_dispatch:" in text
    assert "schedule:" not in text
    assert "contents: write" not in text
    assert "ref: master" in text
    assert "run_non_scientific_live_probe" in text
    assert "NON_SCIENTIFIC_SOURCE_QUALIFICATION" in text
    assert "scientific_evidence" in text
    assert "symbol_count" in text
    assert "persist-credentials: false" in text


def test_source_module_has_no_import_time_network_or_scheduler_authority() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "urlopen(" not in text.split("def default_fetch_one", 1)[0]
    assert "schedule" not in text.lower().split("class SourceBlocked", 1)[0]
    assert "subprocess.check_output" in text
    assert "scientific recording window missed; provider fetch forbidden" in text
    assert "NON_SCIENTIFIC_SOURCE_QUALIFICATION" in text


def test_contract_and_pass_receipt_keep_authority_separated() -> None:
    import json

    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    result = json.loads(RESULT.read_text(encoding="utf-8"))
    assert result["state"] == "PASS"
    assert result["scientific_evidence"] is False
    assert result["authority"] == "NONE"
    assert result["workflow_run"]["id"] == 34730310188
    assert result["immutable_release"]["immutable"] is True
    assert contract["state"] == "IMPLEMENTED_UNQUALIFIED"
    assert contract["phase_authority"]["non_scientific_provider_probe_authorized"] is True
    assert contract["phase_authority"]["real_prospective_collection_authorized"] is False
    assert contract["phase_authority"]["scheduler_authorized"] is False
    assert contract["phase_authority"]["prospective_activation_authorized"] is False
