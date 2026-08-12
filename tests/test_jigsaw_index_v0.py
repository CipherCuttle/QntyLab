import json
from pathlib import Path

import pytest

from qntylab.jigsaw_index import (
    JigsawIndexError,
    RESEARCH_ROOT,
    build_index,
    doctor,
    get_piece,
    list_pieces,
    load_index,
    main,
    write_index,
)
from qntylab.research_ledger import canonical_bytes, sha256_path

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _single_piece_source(**overrides):
    document = {
        "schema_version": "jigsaw-evidence-piece-v0",
        "experiment_id": "FIXTURE_SINGLE_V0",
        "preregistration_id": "FIXTURE_SINGLE_PREREG_V0",
        "piece_type": "CONDITION_EFFECT",
        "research_status": "FROZEN_HISTORICAL_EVIDENCE",
        "authority": "NON_AUTHORITATIVE",
        "promotion_eligible": False,
        "primary": {
            "proposition": "mean(x | HIGH) - mean(x | LOW) > 0",
            "decision": "NOT_SUPPORTED_UNDER_FROZEN_SPECIFICATION",
            "adjudication": "NO_POSITIVE_CONTRAST",
        },
        "bound": {"panel_symbols": 5, "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z"},
        "evidence_class": "NEGATIVE_OR_NULL_FOR_FROZEN_POSITIVE_DIRECTION",
        "authorities": {"strategy": "NONE", "router": "NONE", "qnty": "NONE"},
    }
    document.update(overrides)
    return document


def _multi_piece_source(proposition_ids, **overrides):
    pieces = []
    for proposition_id in proposition_ids:
        pieces.append(
            {
                "proposition_id": proposition_id,
                "piece_type": "PREDICTIVE_ASSOCIATION",
                "classification": "INCONCLUSIVE",
                "evidence_class": "NO_SUPPORT_ESTABLISHED_FOR_FROZEN_POSITIVE_DIRECTION",
                "snapshot_binding": {
                    "snapshot_id": "fixture-snap",
                    "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z",
                    "panel_symbols": 3,
                },
                "prior_feature_exposure": "NO",
                "promotion_eligible": False,
                "authorities": {
                    "causal": "NONE",
                    "strategy": "NONE",
                    "router": "NONE",
                    "state_snapshot": "NONE",
                    "qnty": "NONE",
                    "trading": "NONE",
                },
            }
        )
    document = {
        "schema_version": "jigsaw-evidence-piece-v0",
        "experiment_id": "FIXTURE_MULTI_V0",
        "project_id": "FIXTURE_PROJECT",
        "research_status": "FROZEN_HISTORICAL_EVIDENCE",
        "authority": "NON_AUTHORITATIVE_EXPLORATORY_ONLY",
        "piece_count": len(pieces),
        "piece_order": list(proposition_ids),
        "pieces": pieces,
    }
    document.update(overrides)
    return document


def _write(root: Path, relative_dir: str, document: dict, filename: str = "result.json") -> Path:
    path = root / relative_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# A. Complete current census
# ---------------------------------------------------------------------------


def test_a_complete_current_census_matches_frozen_known_sources():
    index = build_index(RESEARCH_ROOT)
    relative_paths = {source["relative_path"] for source in index["sources"]}
    assert relative_paths == {
        "experiments/research/jigsaw_harvest_v0/result.json",
        "experiments/research/jigsaw_funding_pressure_volatility_v0/result.json",
        "experiments/research/jh01_rv_persistence_temporal_replication_v0/result.json",
    }
    assert index["summary"]["total_sources"] == 3
    assert index["summary"]["total_pieces"] == 6


# ---------------------------------------------------------------------------
# B2. JH01 V0R1 temporal replication piece (single-result shape)
# ---------------------------------------------------------------------------


def test_b2_jh01_v0r1_replication_piece_discoverable_and_bound():
    index = build_index(RESEARCH_ROOT)
    row = get_piece(index, "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_V0R1")
    assert row is not None
    assert row["provenance"]["source_shape"] == "SINGLE_PIECE_OBJECT"
    fields = row["native_scientific_fields"]
    assert fields["piece_type"] == "PREDICTIVE_ASSOCIATION"
    assert fields["classification"] == "REPLICATED_WITHIN_FROZEN_TEMPORAL_SCOPE"
    payload = row["native_payload"]
    assert payload["source_piece_id"] == "JH01_RV_PERSISTENCE"
    assert payload["replication_of_piece_identity"] == "JH01_RV_PERSISTENCE"
    assert payload["feature"] == "RV24_prior,t"
    assert payload["outcome"] == "RV24_future,t"
    # Result and correction digests bound together, exactly as frozen by V0R1
    # and its mandatory provenance correction -- never recomputed here.
    provenance = payload["provenance"]
    assert provenance["source_execution_result_digest"] == "3dba3a0f0700a768e981dcecfe5793532bcd4bc1db7dc4dbcd9e4806a722c5c1"
    assert provenance["provenance_correction_digest"] == "c396b6cc53d92a87c7dfa45920c05a772bb447c1f98de5bdbbae065e255b7154"
    assert provenance["canonical_corrected_prior_v0_execution_started_digest"] == (
        "9c8b00ad68c1e1ba389512c94a4c145264844a4e24fae75c038fcc9e0144f285"
    )
    assert provenance["malformed_historical_digest_is_authoritative"] is False
    assert provenance["result_and_correction_must_be_consumed_together"] is True
    assert provenance["post_start_repair"] is True
    assert provenance["pristine_first_execution"] is False
    # The original JH01 discovery piece is untouched by this addition.
    original = get_piece(index, "JH01_RV_PERSISTENCE")
    assert original["native_scientific_fields"]["classification"] == "SUPPORTED_WITHIN_FROZEN_SCOPE"
    assert original["native_payload"]["beta"] == 0.5047974226484947


# ---------------------------------------------------------------------------
# B. Harvest multi-piece shape
# ---------------------------------------------------------------------------


def test_b_harvest_pieces_individually_discoverable_with_separate_classifications():
    index = build_index(RESEARCH_ROOT)
    harvest_rows = list_pieces(index, experiment_id="JIGSAW_HARVEST_V0_PREREGISTRATION_V0")
    assert {row["piece_identity"] for row in harvest_rows} == {
        "JH01_RV_PERSISTENCE",
        "JH02_DISPERSION_TO_RV",
        "JH03_BREADTH_TO_RETURN",
        "JH04_DRAWDOWN_TO_RETURN",
    }
    classifications = {row["piece_identity"]: row["native_scientific_fields"]["classification"] for row in harvest_rows}
    assert classifications["JH01_RV_PERSISTENCE"] == "SUPPORTED_WITHIN_FROZEN_SCOPE"
    assert classifications["JH02_DISPERSION_TO_RV"] == "SUPPORTED_WITHIN_FROZEN_SCOPE"
    assert classifications["JH03_BREADTH_TO_RETURN"] == "INCONCLUSIVE"
    assert classifications["JH04_DRAWDOWN_TO_RETURN"] == "INCONCLUSIVE"
    # No row carries the family_summary rollup in place of its own verdict.
    for row in harvest_rows:
        assert "family_summary" not in row["native_payload"]
        assert "propositions_registered" not in row["native_scientific_fields"]


# ---------------------------------------------------------------------------
# C. Single-result shape
# ---------------------------------------------------------------------------


def test_c_funding_pressure_single_result_discoverable_in_native_vocabulary():
    index = build_index(RESEARCH_ROOT)
    row = get_piece(index, "JIGSAW_FUNDING_PRESSURE_VOLATILITY_V0")
    assert row is not None
    assert row["provenance"]["source_shape"] == "SINGLE_PIECE_OBJECT"
    fields = row["native_scientific_fields"]
    assert fields["piece_type"] == "CONDITION_EFFECT"
    assert fields["evidence_class"] == "NEGATIVE_OR_NULL_FOR_FROZEN_POSITIVE_DIRECTION"
    assert fields["primary.decision"] == "NOT_SUPPORTED_UNDER_FROZEN_SPECIFICATION"
    assert fields["primary.adjudication"] == "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST"
    # Harvest vocabulary ("classification") is never invented for this shape.
    assert "classification" not in fields
    assert "decision" not in fields  # top-level "decision" key does not exist on this source


# ---------------------------------------------------------------------------
# D. Exposure preservation
# ---------------------------------------------------------------------------


def test_d_exposure_preserved_on_real_sources():
    index = build_index(RESEARCH_ROOT)
    by_identity = {row["piece_identity"]: row["prior_feature_exposure"] for row in index["pieces"]}
    assert by_identity["JH01_RV_PERSISTENCE"] == "NO"
    assert by_identity["JH02_DISPERSION_TO_RV"] == "YES"
    assert by_identity["JH03_BREADTH_TO_RETURN"] == "NO"
    assert by_identity["JH04_DRAWDOWN_TO_RETURN"] == "NO"
    # funding-pressure's source never mentions prior_feature_exposure at all.
    assert by_identity["JIGSAW_FUNDING_PRESSURE_VOLATILITY_V0"] == "UNKNOWN"


def test_d_exposure_absent_field_becomes_unknown_not_no(tmp_path):
    _write(tmp_path, "fixture_exposure", _single_piece_source())  # no prior_feature_exposure key at all
    index = build_index(tmp_path)
    row = get_piece(index, "FIXTURE_SINGLE_V0")
    assert row["prior_feature_exposure"] == "UNKNOWN"

    tmp_path2 = tmp_path / "yes_case"
    _write(tmp_path2, "fixture_exposure_yes", _single_piece_source(experiment_id="FIXTURE_YES_V0", prior_feature_exposure="YES"))
    index_yes = build_index(tmp_path2)
    assert get_piece(index_yes, "FIXTURE_YES_V0")["prior_feature_exposure"] == "YES"

    tmp_path3 = tmp_path / "no_case"
    _write(tmp_path3, "fixture_exposure_no", _single_piece_source(experiment_id="FIXTURE_NO_V0", prior_feature_exposure="NO"))
    index_no = build_index(tmp_path3)
    assert get_piece(index_no, "FIXTURE_NO_V0")["prior_feature_exposure"] == "NO"


# ---------------------------------------------------------------------------
# E. Deterministic rebuild
# ---------------------------------------------------------------------------


def test_e_two_independent_builds_are_byte_identical():
    first = build_index(RESEARCH_ROOT)
    second = build_index(RESEARCH_ROOT)
    assert canonical_bytes(first) == canonical_bytes(second)


# ---------------------------------------------------------------------------
# F. Stable ordering
# ---------------------------------------------------------------------------


def test_f_ordering_independent_of_filesystem_enumeration_order(tmp_path):
    # Create the alphabetically-later directory first so directory-entry
    # order (creation order) disagrees with the expected sorted output order.
    _write(tmp_path, "zzz_experiment", _single_piece_source(experiment_id="ZZZ_V0"))
    _write(tmp_path, "aaa_experiment", _single_piece_source(experiment_id="AAA_V0"))
    index = build_index(tmp_path)
    identities = [row["piece_identity"] for row in index["pieces"]]
    assert identities == sorted(identities)
    assert identities[0] == "AAA_V0"
    assert identities[-1] == "ZZZ_V0"


# ---------------------------------------------------------------------------
# G. Duplicate identity
# ---------------------------------------------------------------------------


def test_g_duplicate_piece_identity_within_one_source_fails_closed(tmp_path):
    document = _multi_piece_source(["DUP_ID", "DUP_ID"])
    _write(tmp_path, "fixture_dup_within", document)
    with pytest.raises(JigsawIndexError, match="duplicate piece identity"):
        build_index(tmp_path)


def test_g_duplicate_piece_identity_across_sources_fails_closed(tmp_path):
    _write(tmp_path, "fixture_dup_a", _single_piece_source(experiment_id="SAME_ID"))
    _write(tmp_path, "fixture_dup_b", _single_piece_source(experiment_id="SAME_ID"))
    with pytest.raises(JigsawIndexError, match="duplicate piece identity"):
        build_index(tmp_path)


# ---------------------------------------------------------------------------
# H. Unsupported eligible shape
# ---------------------------------------------------------------------------


def test_h_unsupported_schema_version_within_recognized_family_fails_closed(tmp_path):
    _write(tmp_path, "fixture_future_version", _single_piece_source(schema_version="jigsaw-evidence-piece-v1"))
    with pytest.raises(JigsawIndexError, match="unsupported eligible Jigsaw evidence schema"):
        build_index(tmp_path)


def test_h_malformed_payload_shape_under_supported_version_fails_closed(tmp_path):
    document = _single_piece_source()
    document["pieces"] = {"not": "a list"}  # supported schema_version, unrecognized payload shape
    _write(tmp_path, "fixture_malformed_pieces", document)
    with pytest.raises(JigsawIndexError, match="unsupported eligible Jigsaw evidence payload shape"):
        build_index(tmp_path)


def test_h_missing_required_identity_fails_closed(tmp_path):
    document = _single_piece_source()
    del document["experiment_id"]
    _write(tmp_path, "fixture_no_experiment_id", document)
    with pytest.raises(JigsawIndexError, match="malformed required source identity"):
        build_index(tmp_path)


# ---------------------------------------------------------------------------
# I. Source digest / staleness
# ---------------------------------------------------------------------------


def test_i_doctor_detects_stale_index_after_source_bytes_change(tmp_path):
    _write(tmp_path, "fixture_stale", _single_piece_source())
    write_index(tmp_path)
    assert doctor(tmp_path) == []

    # Mutate the source after the index was written.
    _write(tmp_path, "fixture_stale", _single_piece_source(interpretation="mutated after freeze"))
    issues = doctor(tmp_path)
    assert issues == ["stale or divergent jigsaw_index.json"]


def test_i_doctor_detects_added_and_removed_sources(tmp_path):
    _write(tmp_path, "fixture_one", _single_piece_source(experiment_id="ONE_V0"))
    write_index(tmp_path)
    assert doctor(tmp_path) == []

    _write(tmp_path, "fixture_two", _single_piece_source(experiment_id="TWO_V0"))
    assert doctor(tmp_path) == ["stale or divergent jigsaw_index.json"]

    write_index(tmp_path)
    assert doctor(tmp_path) == []

    (tmp_path / "fixture_one" / "result.json").unlink()
    assert doctor(tmp_path) == ["stale or divergent jigsaw_index.json"]


# ---------------------------------------------------------------------------
# J. Authority non-escalation
# ---------------------------------------------------------------------------


def test_j_no_real_source_is_escalated_into_new_authority():
    index = build_index(RESEARCH_ROOT)
    for row in index["pieces"]:
        assert row["authority"]["promotion_eligible"] is False
        authorities = row["authority"]["authorities"] or {}
        assert all(value == "NONE" for value in authorities.values())


def test_j_missing_authority_fields_stay_absent_not_fabricated(tmp_path):
    document = _single_piece_source()
    del document["promotion_eligible"]
    del document["authorities"]
    _write(tmp_path, "fixture_no_authority", document)
    index = build_index(tmp_path)
    row = get_piece(index, "FIXTURE_SINGLE_V0")
    assert row["authority"]["promotion_eligible"] is None
    assert row["authority"]["authorities"] is None


# ---------------------------------------------------------------------------
# K. Query exactness
# ---------------------------------------------------------------------------


def test_k_exact_identity_query_no_fuzzy_matching():
    index = build_index(RESEARCH_ROOT)
    assert get_piece(index, "JH01_RV_PERSISTENCE") is not None
    assert get_piece(index, "jh01_rv_persistence") is None  # case mismatch: no fuzzy match
    assert get_piece(index, "JH01") is None  # prefix: no fuzzy match
    assert get_piece(index, "DOES_NOT_EXIST") is None


# ---------------------------------------------------------------------------
# L. Protected-history integrity
# ---------------------------------------------------------------------------


def test_l_source_artifacts_are_byte_unchanged_by_index_generation():
    protected = [
        RESEARCH_ROOT / "jigsaw_harvest_v0" / "result.json",
        RESEARCH_ROOT / "jigsaw_harvest_v0" / "execution_result.json",
        RESEARCH_ROOT / "jigsaw_harvest_v0" / "preregistration.json",
        RESEARCH_ROOT / "jigsaw_funding_pressure_volatility_v0" / "result.json",
        RESEARCH_ROOT / "jigsaw_funding_pressure_volatility_v0" / "execution_result.json",
        RESEARCH_ROOT / "jigsaw_funding_pressure_volatility_v0" / "preregistration.json",
        RESEARCH_ROOT / "jh01_rv_persistence_temporal_replication_v0" / "result.json",
        RESEARCH_ROOT / "jh01_rv_persistence_temporal_replication_v0" / "v0r1" / "execution_result.json",
        RESEARCH_ROOT / "jh01_rv_persistence_temporal_replication_v0" / "v0r1" / "provenance_correction.json",
        RESEARCH_ROOT / "jh01_rv_persistence_temporal_replication_v0" / "preregistration.json",
        RESEARCH_ROOT / "corpus_index.json",
        RESEARCH_ROOT / "candidates.jsonl",
        RESEARCH_ROOT / "decisions.jsonl",
    ]
    before = {path: sha256_path(path) for path in protected}
    build_index(RESEARCH_ROOT)
    write_index(RESEARCH_ROOT)
    load_index(RESEARCH_ROOT)
    after = {path: sha256_path(path) for path in protected}
    assert before == after


# ---------------------------------------------------------------------------
# CLI / query-surface smoke coverage
# ---------------------------------------------------------------------------


def test_cli_doctor_and_list_and_get_against_real_repo(capsys):
    main(["doctor"])
    out = capsys.readouterr().out
    assert "OK" in out

    main(["list", "--experiment-id", "JIGSAW_HARVEST_V0_PREREGISTRATION_V0"])
    listed = json.loads(capsys.readouterr().out)
    assert set(listed) == {
        "JH01_RV_PERSISTENCE",
        "JH02_DISPERSION_TO_RV",
        "JH03_BREADTH_TO_RETURN",
        "JH04_DRAWDOWN_TO_RETURN",
    }

    main(["get", "JH01_RV_PERSISTENCE"])
    piece = json.loads(capsys.readouterr().out)
    assert piece["piece_identity"] == "JH01_RV_PERSISTENCE"


def test_cli_get_unknown_identity_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["get", "NOT_A_REAL_PIECE"])
    assert exc_info.value.code == 1
