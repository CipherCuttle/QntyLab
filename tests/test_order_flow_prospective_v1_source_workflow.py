from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/order-flow-prospective-v1-source-qualification.yml"
LIVE_WORKFLOW = ROOT / ".github/workflows/order-flow-prospective-v1-source-live-probe.yml"
SOURCE = ROOT / "qntylab/order_flow_prospective_v1_source.py"
CONTRACT = ROOT / "experiments/research/qnty_edge_discovery_order_flow_v1/source_qualification.json"
RESULT = ROOT / "experiments/research/qnty_edge_discovery_order_flow_v1/recorder_qualification_result.json"


def test_source_qualification_workflows_isolate_pr_ci_from_self_hosted_probe() -> None:
    verify_text = WORKFLOW.read_text(encoding="utf-8")
    live_text = LIVE_WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in verify_text
    assert "workflow_dispatch:" not in verify_text
    assert "self-hosted" not in verify_text
    assert "schedule:" not in verify_text
    assert "contents: write" not in verify_text
    assert "persist-credentials: false" in verify_text

    assert "workflow_dispatch:" in live_text
    assert "pull_request:" not in live_text
    assert "schedule:" not in live_text
    assert "contents: write" not in live_text
    assert "ref: master" in live_text
    assert "run_non_scientific_live_probe" in live_text
    assert "NON_SCIENTIFIC_SOURCE_QUALIFICATION" in live_text
    assert "scientific_evidence" in live_text
    assert "symbol_count" in live_text
    assert "persist-credentials: false" in live_text
    assert "runs-on: [self-hosted, linux, x64, qntylab-eu-source]" in live_text


def test_source_module_has_no_import_time_network_or_scheduler_authority() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert "urlopen(" not in text.split("def default_fetch_one", 1)[0]
    assert "schedule" not in text.lower().split("class SourceBlocked", 1)[0]
    assert "subprocess.check_output" in text
    assert "scientific recording window missed; provider fetch forbidden" in text
    assert "scientific recording window elapsed during provider acquisition" in text
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
    assert contract["live_probe_workflow_path"] == ".github/workflows/order-flow-prospective-v1-source-live-probe.yml"
    assert contract["phase_authority"]["non_scientific_provider_probe_authorized"] is True
    assert contract["phase_authority"]["real_prospective_collection_authorized"] is False
    assert contract["phase_authority"]["scheduler_authorized"] is False
    assert contract["phase_authority"]["prospective_activation_authorized"] is False
    assert contract["qualification_deviation"]["source_contract_changed"] is False
    assert contract["qualification_deviation"]["provider_payload_observed"] is False
    assert contract["qualification_deviation"]["repair_runner_labels"] == [
        "self-hosted",
        "linux",
        "x64",
        "qntylab-eu-source",
    ]
