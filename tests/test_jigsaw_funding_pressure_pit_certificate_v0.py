import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).parents[1]
CERTIFICATE_PATH = ROOT / "experiments/research/jigsaw_funding_pressure_volatility_v0/pit_coverage_certificate.json"
CONTRACT_PATH = ROOT / "experiments/research/jigsaw_funding_pressure_volatility_v0/preregistration.json"

PANEL = [
    "BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT", "LINKUSDT",
    "XLMUSDT", "CHZUSDT", "SANDUSDT", "REEFUSDT", "CHRUSDT", "ALICEUSDT",
    "ONEUSDT", "API3USDT", "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT",
    "LDOUSDT", "APTUSDT",
]

EXPECTED_CONTRACT_DIGEST = "sha256:749641cbee99bc769a6095e2a5877e4ccf1c46db0a82860885eedc06734cd2d6"


def canonical_digest(payload):
    return "sha256:" + hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()


def load_certificate():
    return json.loads(CERTIFICATE_PATH.read_text(encoding="utf-8"))


def test_certificate_digest_and_pit_bindings_are_reproducible():
    certificate = load_certificate()
    digest_input = dict(certificate)
    stored_digest = digest_input.pop("pit_coverage_certificate_digest")
    assert stored_digest == canonical_digest(digest_input)

    contract = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    assert certificate["contract_digest"] == EXPECTED_CONTRACT_DIGEST
    assert contract["contract_digest"] == EXPECTED_CONTRACT_DIGEST
    assert certificate["contract_digest"] == canonical_digest({k: v for k, v in contract.items() if k != "contract_digest"})

    assert [row["symbol"] for row in certificate["ohlcv_census"]] == PANEL
    assert len(certificate["ohlcv_census"]) == 20
    assert certificate["funding_binding"]["exact_panel_count"] == 20
    assert certificate["pit_eligibility"]["funding_eligible_decisions_total"] == 610
    assert certificate["pit_eligibility"]["ohlcv_complete_decisions_total"] == 610
    assert certificate["pit_eligibility"]["combined_pit_eligible_decisions_total"] == 610
    assert certificate["pit_eligibility"]["excluded_by_reason"] == {}
    assert certificate["pit_eligibility"]["first_combined_eligible_decision"] == "2023-10-19T00:00:00Z"
    assert certificate["pit_eligibility"]["last_combined_eligible_decision"] == "2025-06-19T00:00:00Z"
    assert certificate["funding_binding"]["materialization_index_digest"] == "sha256:ceb12a1686f96f328ef54d5bafc184b848fa40ff7a2c71e28dc434a4854486c1"
    assert certificate["funding_binding"]["evidence_set_digest"] == "sha256:3677e5aeafd17c47e4951b2095d6247c8fb7cd3fb603cc70d5ea5658fd768faa"
    assert certificate["ohlcv_evidence_set_digest"] == "sha256:249fcc9e0018770cb0bde80ff3d2a492fc4bf6edc0bb2c9abad2c3d44fe03d82"
    assert certificate["authority"] == {"execution_authority": "NONE", "outcome_access_authority": "NONE"}
    assert all(value == "NO" for value in certificate["no_outcome_attestation"].values())


def test_material_certificate_mutation_changes_digest():
    certificate = load_certificate()
    digest_input = {k: v for k, v in certificate.items() if k != "pit_coverage_certificate_digest"}
    mutated = json.loads(json.dumps(digest_input))
    mutated["pit_eligibility"]["combined_pit_eligible_decisions_total"] = 609
    assert canonical_digest(mutated) != canonical_digest(digest_input)
