import hashlib
import json
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).parents[1]
CONTRACT_PATH = ROOT / "experiments/research/jigsaw_funding_pressure_volatility_v0/preregistration.json"
INDEX_PATH = ROOT / "experiments/research/jigsaw_funding_pressure_volatility_v0/materialization_index.json"
PANEL = [
    "BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT", "LINKUSDT",
    "XLMUSDT", "CHZUSDT", "SANDUSDT", "REEFUSDT", "CHRUSDT", "ALICEUSDT",
    "ONEUSDT", "API3USDT", "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT",
    "LDOUSDT", "APTUSDT",
]


def canonical_digest(payload):
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    ).hexdigest()


def load_contract():
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


def load_index():
    return json.loads(INDEX_PATH.read_text(encoding="utf-8"))


def ecdf_fraction(history, current):
    values = [*history, current]
    return Fraction(sum(value <= current for value in values), len(values))


def state_for(percentile):
    if percentile <= Fraction(1, 3):
        return "LOW"
    if percentile < Fraction(2, 3):
        return "MID"
    return "HIGH"


def test_ecdf_fraction_reaches_all_bins_and_freezes_tertile_boundaries():
    history = [1, 2, 3, 4, 5]
    assert [state_for(ecdf_fraction(history, value)) for value in (0, 2.5, 5)] == ["LOW", "MID", "HIGH"]
    assert state_for(Fraction(1, 3)) == "LOW"
    assert state_for(Fraction(2, 3)) == "HIGH"
    assert state_for(Fraction(1, 2)) == "MID"


def test_contract_digest_and_fraction_scale_binding():
    contract = load_contract()
    digest_input = dict(contract)
    expected = digest_input.pop("contract_digest")
    assert expected == f"sha256:{canonical_digest(digest_input)}"
    feature = contract["feature"]
    assert feature["panel"] == PANEL
    assert feature["normalization"]["scale"] == {"name": "fraction", "minimum": 0, "maximum": 1}
    assert feature["normalization"]["history_observations"] == 365
    assert feature["normalization"]["includes_current_observation"] is True
    assert feature["normalization"]["tie_semantics"].startswith("inclusive <=")
    assert feature["state_bins"]["LOW"]["threshold"] == {"numerator": 1, "denominator": 3}
    assert feature["state_bins"]["HIGH"]["threshold"] == {"numerator": 2, "denominator": 3}
    assert contract["primary_hypotheses"] == ["HIGH_MINUS_LOW_MEAN_RV24 > 0"]


def test_materialization_index_binds_exact_panel_content_identities():
    contract = load_contract()
    index = load_index()
    assert index["panel"] == PANEL
    assert index["symbols_total"] == index["symbols_materialized_verified"] == 20
    assert index["source_contents_are_not_committed"] is True
    assert index["common_authenticated_coverage_start"] == "2022-10-18T16:00:00Z"
    assert index["common_authenticated_coverage_end"] == "2025-06-19T00:00:00.005Z"
    assert len(index["members"]) == 20
    for member in index["members"]:
        assert set(member) >= {
            "symbol", "manifest_relative_path", "manifest_sha256",
            "normalized_data_relative_path", "normalized_sha256",
            "authenticated_coverage_start", "authenticated_coverage_end",
            "materializer_implementation_identity", "materializer_contract_version",
            "aggregate_source_receipt_digest",
        }
        assert len(member["manifest_sha256"]) == 64
        assert len(member["normalized_sha256"]) == 64
        assert len(member["aggregate_source_receipt_digest"]) == 64
    assert contract["materialization_binding"]["materialization_index_digest"] == (
        f"sha256:{canonical_digest(index)}"
    )
    assert contract["materialization_binding"]["evidence_set_digest"] == index["evidence_set_digest"]


def test_materialization_index_semantic_mutation_changes_binding():
    index = load_index()
    mutated = json.loads(json.dumps(index))
    mutated["members"][0]["normalized_sha256"] = "0" * 64
    assert canonical_digest(mutated) != canonical_digest(index)


def test_contract_has_no_execution_or_outcome_authority():
    contract = load_contract()
    assert contract["execution_authority"] == "NONE"
    assert contract["outcome_access_authority"] == "NONE"
    assert contract["router_authority"] == "NONE"
    assert "THIS COMMIT FREEZES THE CONTRACT ONLY" in contract["execution_gate"]
    assert "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST" in contract["kill_conditions"]
