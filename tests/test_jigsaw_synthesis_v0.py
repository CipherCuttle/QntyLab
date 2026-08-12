import json
from pathlib import Path

import pytest

from qntylab.jigsaw_index import RESEARCH_ROOT, write_index
from qntylab.jigsaw_synthesis import (
    JigsawSynthesisError,
    SYNTHESIS_DIRECTORY_NAME,
    SYNTHESIS_FILENAME,
    build_synthesis,
    doctor,
    get_pair,
    load_synthesis,
    main,
    synthesis_digest,
    write_synthesis,
)
from qntylab.research_ledger import canonical_bytes

HARVEST_PIECE_IDS = {
    "JH01_RV_PERSISTENCE",
    "JH02_DISPERSION_TO_RV",
    "JH03_BREADTH_TO_RETURN",
    "JH04_DRAWDOWN_TO_RETURN",
}
FUNDING_PRESSURE_ID = "JIGSAW_FUNDING_PRESSURE_VOLATILITY_V0"
ALL_PIECE_IDS = HARVEST_PIECE_IDS | {FUNDING_PRESSURE_ID}


# ---------------------------------------------------------------------------
# Fixture helpers -- mirror tests/test_jigsaw_index_v0.py's fixture style so a
# custom jigsaw-evidence-piece source tree can be built under tmp_path.
# ---------------------------------------------------------------------------


def _multi_piece_source(pieces_overrides, **overrides):
    pieces = []
    for proposition_id, extra in pieces_overrides:
        piece = {
            "proposition_id": proposition_id,
            "piece_type": "PREDICTIVE_ASSOCIATION",
            "classification": "INCONCLUSIVE",
            "evidence_class": "NO_SUPPORT_ESTABLISHED_FOR_FROZEN_POSITIVE_DIRECTION",
            "snapshot_binding": {
                "snapshot_id": "fixture-snap-a",
                "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z",
                "panel_symbols": 3,
            },
            "feature": "FEATURE_X",
            "outcome": "OUTCOME_Y",
            "prior_feature_exposure": "NO",
            "promotion_eligible": False,
            "limitations": ["fixture limitation"],
            "authorities": {"strategy": "NONE", "router": "NONE", "qnty": "NONE"},
        }
        piece.update(extra)
        pieces.append(piece)
    document = {
        "schema_version": "jigsaw-evidence-piece-v0",
        "experiment_id": "FIXTURE_MULTI_V0",
        "project_id": "FIXTURE_PROJECT",
        "research_status": "FROZEN_HISTORICAL_EVIDENCE",
        "authority": "NON_AUTHORITATIVE_EXPLORATORY_ONLY",
        "piece_count": len(pieces),
        "piece_order": [p[0] for p in pieces_overrides],
        "pieces": pieces,
    }
    document.update(overrides)
    return document


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
        "bound": {"panel_symbols": 5, "decision_window": "2024-01-15T00:00:00Z..2024-03-01T00:00:00Z"},
        "evidence_class": "NEGATIVE_OR_NULL_FOR_FROZEN_POSITIVE_DIRECTION",
        "authorities": {"strategy": "NONE", "router": "NONE", "qnty": "NONE"},
    }
    document.update(overrides)
    return document


def _write(root: Path, relative_dir: str, document: dict, filename: str = "result.json") -> Path:
    path = root / relative_dir / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# A. Complete piece coverage
# ---------------------------------------------------------------------------


def test_a_every_canonical_piece_appears_exactly_once_in_inventory():
    synthesis = build_synthesis(RESEARCH_ROOT)
    identities = [row["piece_identity"] for row in synthesis["piece_inventory"]]
    assert set(identities) == ALL_PIECE_IDS
    assert len(identities) == len(set(identities)) == 5


# ---------------------------------------------------------------------------
# B. Complete pair coverage
# ---------------------------------------------------------------------------


def test_b_every_unordered_pair_appears_exactly_once():
    synthesis = build_synthesis(RESEARCH_ROOT)
    pairs = synthesis["pair_relationships"]
    assert len(pairs) == 10  # 5 choose 2
    seen = set()
    for pair in pairs:
        key = frozenset((pair["piece_a"], pair["piece_b"]))
        assert key not in seen, f"duplicate/reversed pair: {pair['pair_id']}"
        seen.add(key)
    assert len(seen) == 10


# ---------------------------------------------------------------------------
# C. Harvest shared history cannot become independent replication
# ---------------------------------------------------------------------------


def test_c_harvest_shared_snapshot_pairs_never_independent_replication():
    synthesis = build_synthesis(RESEARCH_ROOT)
    for pair in synthesis["pair_relationships"]:
        if pair["piece_a"] in HARVEST_PIECE_IDS and pair["piece_b"] in HARVEST_PIECE_IDS:
            assert pair["same_snapshot_identity"] == "YES"
            assert pair["independence_status"] == "SHARED_FROZEN_HISTORY"
            assert pair["independence_status"] != "INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED"
            assert pair["allowed_synthesis"] != "INDEPENDENT_CONFIRMATION_ELIGIBLE"


# ---------------------------------------------------------------------------
# D. Different source files do not automatically become independent
# ---------------------------------------------------------------------------


def test_d_different_files_do_not_auto_grant_independence():
    synthesis = build_synthesis(RESEARCH_ROOT)
    for pair in synthesis["pair_relationships"]:
        if FUNDING_PRESSURE_ID in (pair["piece_a"], pair["piece_b"]):
            assert pair["same_source_artifact"] == "NO"
            # Different files alone must not read as established independence.
            assert pair["independence_status"] != "INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED"
            assert pair["independence_status"] in (
                "OVERLAPPING_HISTORY_INDEPENDENCE_NOT_ESTABLISHED",
                "INDEPENDENCE_NOT_ESTABLISHED",
            )


# ---------------------------------------------------------------------------
# E. Window overlap alone cannot produce same_data_history = YES
# ---------------------------------------------------------------------------


def test_e_window_overlap_without_snapshot_identity_stays_not_established(tmp_path):
    _write(
        tmp_path,
        "fixture_a",
        _multi_piece_source(
            [("FX_A", {"snapshot_binding": {"decision_window": "2024-01-01T00:00:00Z..2024-06-01T00:00:00Z", "panel_symbols": 3}})]
        ),
    )
    _write(
        tmp_path,
        "fixture_b",
        _single_piece_source(
            experiment_id="FIXTURE_OTHER_V0",
            bound={"panel_symbols": 3, "decision_window": "2024-03-01T00:00:00Z..2024-09-01T00:00:00Z"},
        ),
    )
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "FX_A", "FIXTURE_OTHER_V0")
    assert pair["decision_window_relation"] == "PARTIAL_OVERLAP"
    assert pair["same_snapshot_identity"] == "UNKNOWN"
    assert pair["same_data_history"] == "NOT_ESTABLISHED"
    assert pair["independence_status"] == "OVERLAPPING_HISTORY_INDEPENDENCE_NOT_ESTABLISHED"


# ---------------------------------------------------------------------------
# F. Same cardinality does not imply same universe/panel
# ---------------------------------------------------------------------------


def test_f_matching_panel_cardinality_never_drives_a_derived_field(tmp_path):
    # Two pieces with identical panel_symbols=20 but everything else
    # different must not have that cardinality match leak into any
    # pairwise fact -- this module never reads panel_symbols at all when
    # deriving same_data_history/same_snapshot_identity/claim_relation.
    _write(
        tmp_path,
        "fixture_a",
        _multi_piece_source(
            [("FX_20_A", {"snapshot_binding": {"decision_window": "2024-01-01T00:00:00Z..2024-06-01T00:00:00Z", "panel_symbols": 20}})]
        ),
    )
    _write(
        tmp_path,
        "fixture_b",
        _multi_piece_source(
            [("FX_20_B", {"snapshot_binding": {"decision_window": "2025-01-01T00:00:00Z..2025-06-01T00:00:00Z", "panel_symbols": 20}})]
        ),
        filename="result.json",
    )
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "FX_20_A", "FX_20_B")
    assert pair["decision_window_relation"] == "DISJOINT"
    assert pair["same_snapshot_identity"] == "UNKNOWN"
    assert pair["same_data_history"] == "NOT_ESTABLISHED"
    assert pair["independence_status"] == "INDEPENDENCE_NOT_ESTABLISHED"


# ---------------------------------------------------------------------------
# G. Missing identity/exposure data stays UNKNOWN / NOT_ESTABLISHED
# ---------------------------------------------------------------------------


def test_g_missing_snapshot_id_is_unknown_not_a_guess():
    synthesis = build_synthesis(RESEARCH_ROOT)
    pair = get_pair(synthesis, "JH01_RV_PERSISTENCE", FUNDING_PRESSURE_ID)
    assert pair["same_snapshot_identity"] == "UNKNOWN"
    assert pair["same_feature"] == "NOT_ESTABLISHED"
    assert pair["same_outcome"] == "NOT_ESTABLISHED"
    assert pair["same_data_history"] == "NOT_ESTABLISHED"
    assert pair["claim_relation"] == "CLAIM_RELATION_NOT_ESTABLISHED"


# ---------------------------------------------------------------------------
# H. Prior exposure preserved, does not rewrite native classification
# ---------------------------------------------------------------------------


def test_h_prior_exposure_preserved_and_native_classification_untouched():
    synthesis = build_synthesis(RESEARCH_ROOT)
    inventory = {row["piece_identity"]: row for row in synthesis["piece_inventory"]}
    assert inventory["JH02_DISPERSION_TO_RV"]["prior_feature_exposure"] == "YES"
    assert inventory["JH02_DISPERSION_TO_RV"]["native_scientific_fields"]["classification"] == "SUPPORTED_WITHIN_FROZEN_SCOPE"
    assert inventory[FUNDING_PRESSURE_ID]["prior_feature_exposure"] == "UNKNOWN"

    pair = get_pair(synthesis, "JH01_RV_PERSISTENCE", "JH02_DISPERSION_TO_RV")
    assert pair["prior_exposure_relation"] == {
        "piece_a_prior_feature_exposure": "NO",
        "piece_b_prior_feature_exposure": "YES",
    }
    statement = next(s for s in synthesis["synthesis_statements"] if s["synthesis_id"] == "SYN__JH01_RV_PERSISTENCE__JH02_DISPERSION_TO_RV")
    for banned in ("independent discovery", "pristine", "novel confirmation", "first exposure"):
        assert banned not in statement["statement"].lower()


# ---------------------------------------------------------------------------
# I. INCONCLUSIVE preservation
# ---------------------------------------------------------------------------


def test_i_inconclusive_pieces_remain_inconclusive_everywhere():
    synthesis = build_synthesis(RESEARCH_ROOT)
    inventory = {row["piece_identity"]: row for row in synthesis["piece_inventory"]}
    assert inventory["JH03_BREADTH_TO_RETURN"]["native_scientific_fields"]["classification"] == "INCONCLUSIVE"
    assert inventory["JH04_DRAWDOWN_TO_RETURN"]["native_scientific_fields"]["classification"] == "INCONCLUSIVE"

    statement = next(
        s for s in synthesis["synthesis_statements"] if s["synthesis_id"] == "SYN__JH03_BREADTH_TO_RETURN__JH04_DRAWDOWN_TO_RETURN"
    )
    for verdict in statement["native_source_verdicts"].values():
        assert verdict["native_scientific_fields"]["classification"] == "INCONCLUSIVE"
    lowered = statement["statement"].lower()
    for banned in ("failed", "disproved", "no return predictability", "negative", "zero effect"):
        assert banned not in lowered


# ---------------------------------------------------------------------------
# J. Negative-direction falsification preservation
# ---------------------------------------------------------------------------


def test_j_funding_pressure_negative_result_not_escalated():
    synthesis = build_synthesis(RESEARCH_ROOT)
    row = next(r for r in synthesis["piece_inventory"] if r["piece_identity"] == FUNDING_PRESSURE_ID)
    fields = row["native_scientific_fields"]
    assert fields["primary.decision"] == "NOT_SUPPORTED_UNDER_FROZEN_SPECIFICATION"
    assert fields["primary.adjudication"] == "NO_POSITIVE_HIGH_MINUS_LOW_DIRECTIONAL_CONTRAST"
    # No statement anywhere claims an inverse effect or a null theorem.
    for statement in synthesis["synthesis_statements"]:
        assert FUNDING_PRESSURE_ID not in statement["supporting_piece_ids"]
    for pair in synthesis["pair_relationships"]:
        if FUNDING_PRESSURE_ID in (pair["piece_a"], pair["piece_b"]):
            assert pair["allowed_synthesis"] == "SEPARATE_ONLY"


# ---------------------------------------------------------------------------
# K. No vote counting
# ---------------------------------------------------------------------------


def test_k_no_scoring_or_vote_counting_fields_anywhere():
    synthesis = build_synthesis(RESEARCH_ROOT)
    blob = json.dumps(synthesis)
    for banned_field in (
        '"evidence_score"',
        '"confidence_weight"',
        '"confidence"',
        '"independent_confirmation_count"',
        '"jigsaw_verdict"',
        '"market_state_evidence"',
    ):
        assert banned_field not in blob
    # Adding two related SUPPORTED_WITHIN_FROZEN_SCOPE fixtures must not
    # produce any field that looks like an aggregate strength score.
    for pair in synthesis["pair_relationships"]:
        assert set(pair.keys()) == {
            "pair_id",
            "piece_a",
            "piece_b",
            "same_source_artifact",
            "same_experiment",
            "same_snapshot_identity",
            "decision_window_relation",
            "same_data_history",
            "same_feature",
            "same_outcome",
            "prior_exposure_relation",
            "claim_relation",
            "independence_status",
            "allowed_synthesis",
        }


# ---------------------------------------------------------------------------
# L. No State Snapshot authority
# ---------------------------------------------------------------------------


def test_l_no_state_snapshot_or_downstream_authority_anywhere():
    synthesis = build_synthesis(RESEARCH_ROOT)
    gc = synthesis["global_constraints"]
    assert gc["state_snapshot_authority"] == "NONE"
    assert gc["router_authority"] == "NONE"
    assert gc["qnty_authority"] == "NONE"
    assert gc["trading_authority"] == "NONE"
    assert gc["promotion_authority"] == "NONE"
    blob = json.dumps(synthesis).lower()
    assert "state_snapshot_authorized" not in blob
    assert "feature_eligible_for_state_snapshot" not in blob


# ---------------------------------------------------------------------------
# M / N. Source and index immutability
# ---------------------------------------------------------------------------


def test_m_n_source_and_index_artifacts_byte_unchanged():
    from qntylab.research_ledger import sha256_path

    protected = [
        RESEARCH_ROOT / "jigsaw_harvest_v0" / "result.json",
        RESEARCH_ROOT / "jigsaw_harvest_v0" / "execution_result.json",
        RESEARCH_ROOT / "jigsaw_harvest_v0" / "preregistration.json",
        RESEARCH_ROOT / "jigsaw_funding_pressure_volatility_v0" / "result.json",
        RESEARCH_ROOT / "jigsaw_funding_pressure_volatility_v0" / "execution_result.json",
        RESEARCH_ROOT / "jigsaw_funding_pressure_volatility_v0" / "preregistration.json",
        RESEARCH_ROOT / "jigsaw_index.json",
    ]
    before = {path: sha256_path(path) for path in protected}
    build_synthesis(RESEARCH_ROOT)
    write_synthesis(RESEARCH_ROOT)
    load_synthesis(RESEARCH_ROOT)
    after = {path: sha256_path(path) for path in protected}
    assert before == after


# ---------------------------------------------------------------------------
# O. Deterministic build
# ---------------------------------------------------------------------------


def test_o_two_independent_builds_are_byte_identical():
    first = build_synthesis(RESEARCH_ROOT)
    second = build_synthesis(RESEARCH_ROOT)
    assert canonical_bytes(first) == canonical_bytes(second)
    assert synthesis_digest(first) == synthesis_digest(second)


def test_o_pair_and_statement_ordering_is_stable(tmp_path):
    _write(tmp_path, "zzz_experiment", _single_piece_source(experiment_id="ZZZ_V0"))
    _write(tmp_path, "aaa_experiment", _single_piece_source(experiment_id="AAA_V0"))
    synthesis = build_synthesis(tmp_path)
    identities = [row["piece_identity"] for row in synthesis["piece_inventory"]]
    assert identities == sorted(identities)
    pair_ids = [pair["pair_id"] for pair in synthesis["pair_relationships"]]
    assert pair_ids == sorted(pair_ids)


# ---------------------------------------------------------------------------
# P. Stale input detection
# ---------------------------------------------------------------------------


def test_p_doctor_detects_stale_synthesis_after_index_source_changes(tmp_path):
    _write(tmp_path, "fixture_stale", _single_piece_source())
    write_index(tmp_path)
    write_synthesis(tmp_path)
    assert doctor(tmp_path) == []

    _write(tmp_path, "fixture_stale", _single_piece_source(interpretation="mutated after freeze"))
    # jigsaw_index.json itself is now stale relative to its source bytes.
    issues = doctor(tmp_path)
    assert issues != []
    assert any("jigsaw_index is not current" in issue for issue in issues)


def test_p_doctor_detects_stale_synthesis_after_index_rebuild(tmp_path):
    _write(tmp_path, "fixture_stale2", _single_piece_source(experiment_id="STALE2_V0"))
    write_index(tmp_path)
    write_synthesis(tmp_path)
    assert doctor(tmp_path) == []

    # A new eligible source changes the index census; rebuild the index but
    # not the synthesis artifact -- synthesis must now report stale.
    _write(tmp_path, "fixture_stale2_new", _single_piece_source(experiment_id="STALE2_NEW_V0"))
    write_index(tmp_path)
    issues = doctor(tmp_path)
    assert issues == ["stale or divergent jigsaw_synthesis_eligibility.json"]

    write_synthesis(tmp_path)
    assert doctor(tmp_path) == []


# ---------------------------------------------------------------------------
# Q. No self-ingestion into the F-02 discovery index
# ---------------------------------------------------------------------------


def test_q_synthesis_artifact_is_not_ingested_as_a_sixth_jigsaw_piece(tmp_path):
    from qntylab.jigsaw_index import build_index as jigsaw_build_index

    _write(tmp_path, "fixture_one", _single_piece_source())
    write_index(tmp_path)
    before = jigsaw_build_index(tmp_path)
    assert before["summary"]["total_pieces"] == 1

    write_synthesis(tmp_path)
    after = jigsaw_build_index(tmp_path)
    assert after["summary"]["total_pieces"] == 1
    assert after["summary"]["total_sources"] == before["summary"]["total_sources"]
    relative_paths = {source["relative_path"] for source in after["sources"]}
    assert not any(SYNTHESIS_DIRECTORY_NAME in path for path in relative_paths)


def test_q_synthesis_schema_version_is_outside_the_recognized_jigsaw_family():
    from qntylab.jigsaw_index import RECOGNIZED_SCHEMA_FAMILY_PREFIX
    from qntylab.jigsaw_synthesis import SYNTHESIS_SCHEMA_VERSION

    assert not SYNTHESIS_SCHEMA_VERSION.startswith(RECOGNIZED_SCHEMA_FAMILY_PREFIX)


# ---------------------------------------------------------------------------
# R. Exact traceability
# ---------------------------------------------------------------------------


def test_r_every_statement_traces_to_its_exact_source_pieces():
    synthesis = build_synthesis(RESEARCH_ROOT)
    inventory_ids = {row["piece_identity"]: row for row in synthesis["piece_inventory"]}
    for statement in synthesis["synthesis_statements"]:
        assert len(statement["supporting_piece_ids"]) == 2
        for piece_id in statement["supporting_piece_ids"]:
            assert piece_id in inventory_ids
            assert piece_id in statement["native_source_verdicts"]
            verdict = statement["native_source_verdicts"][piece_id]
            source_row = inventory_ids[piece_id]
            assert verdict["native_scientific_fields"] == source_row["native_scientific_fields"]
            assert verdict["prior_feature_exposure"] == source_row["prior_feature_exposure"]
            # source content digest is independently recoverable via the
            # piece_inventory row keyed by the same piece_identity.
            assert source_row["source_content_digest"]


# ---------------------------------------------------------------------------
# Additional: synthesis is bound to jigsaw_index digest and source digests
# ---------------------------------------------------------------------------


def test_source_binding_matches_current_index():
    from qntylab.jigsaw_index import build_index as jigsaw_build_index, index_digest

    synthesis = build_synthesis(RESEARCH_ROOT)
    index = jigsaw_build_index(RESEARCH_ROOT)
    assert synthesis["generated_from"]["jigsaw_index_digest"] == index_digest(index)
    assert synthesis["generated_from"]["source_files_sha256"] == index["generated_from"]["source_files_sha256"]
    assert synthesis["generated_from"]["jigsaw_index_schema"] == index["schema_version"]


def test_committed_artifact_matches_fresh_rebuild():
    committed = load_synthesis(RESEARCH_ROOT)
    fresh = build_synthesis(RESEARCH_ROOT)
    assert committed == fresh


# ---------------------------------------------------------------------------
# JOINT_CONTEXT_ONLY path (not reached by real current data; exercised via
# a synthetic fixture so the code path is proven, not merely dead).
# ---------------------------------------------------------------------------


def test_joint_context_only_reachable_for_overlapping_related_distinct_claim(tmp_path):
    _write(
        tmp_path,
        "fixture_a",
        _multi_piece_source(
            [
                (
                    "JOINT_A",
                    {
                        "feature": "SHARED_FEATURE",
                        "outcome": "OUTCOME_ONE",
                        "snapshot_binding": {"decision_window": "2024-01-01T00:00:00Z..2024-06-01T00:00:00Z", "panel_symbols": 3},
                    },
                )
            ],
            experiment_id="FIXTURE_JOINT_A_V0",
        ),
    )
    _write(
        tmp_path,
        "fixture_b",
        _single_piece_source(
            experiment_id="FIXTURE_JOINT_B_V0",
            primary={"proposition": "x", "decision": "y", "adjudication": "z", "feature": "SHARED_FEATURE"},
        ),
    )
    # _single_piece_source's whole document IS the piece; add a top-level
    # "feature" field (not nested in primary) so it is directly comparable.
    doc_path = tmp_path / "fixture_b" / "result.json"
    document = json.loads(doc_path.read_text())
    document["feature"] = "SHARED_FEATURE"
    document["outcome"] = "OUTCOME_TWO"
    document["bound"]["decision_window"] = "2024-03-01T00:00:00Z..2024-09-01T00:00:00Z"
    doc_path.write_text(json.dumps(document), encoding="utf-8")

    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "JOINT_A", "FIXTURE_JOINT_B_V0")
    assert pair["same_feature"] == "YES"
    assert pair["same_snapshot_identity"] == "UNKNOWN"
    assert pair["decision_window_relation"] == "PARTIAL_OVERLAP"
    assert pair["independence_status"] == "OVERLAPPING_HISTORY_INDEPENDENCE_NOT_ESTABLISHED"
    assert pair["claim_relation"] == "RELATED_DISTINCT_CLAIM"
    assert pair["allowed_synthesis"] == "JOINT_CONTEXT_ONLY"
    statement = next(
        s for s in synthesis["synthesis_statements"] if set(s["supporting_piece_ids"]) == {"JOINT_A", "FIXTURE_JOINT_B_V0"}
    )
    assert "mutual confirmation" in statement["statement"]


# ---------------------------------------------------------------------------
# CLI smoke coverage
# ---------------------------------------------------------------------------


def test_cli_doctor_and_summary_and_pair_against_real_repo(capsys):
    main(["doctor"])
    out = capsys.readouterr().out
    assert "OK" in out

    main(["summary"])
    summary = json.loads(capsys.readouterr().out)
    assert summary["total_pairs"] == 10

    main(["pair", "JH01_RV_PERSISTENCE", "JH02_DISPERSION_TO_RV"])
    pair = json.loads(capsys.readouterr().out)
    assert pair["pair_id"] == "JH01_RV_PERSISTENCE::JH02_DISPERSION_TO_RV"


def test_cli_pair_unknown_identity_exits_nonzero(capsys):
    with pytest.raises(SystemExit) as exc_info:
        main(["pair", "NOT_A_REAL_PIECE", "ALSO_NOT_REAL"])
    assert exc_info.value.code == 1


def test_load_synthesis_missing_file_fails_closed(tmp_path):
    with pytest.raises(JigsawSynthesisError):
        load_synthesis(tmp_path)
