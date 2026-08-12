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
JH01_V0R1_REPLICATION_ID = "JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_V0R1"
ALL_PIECE_IDS = HARVEST_PIECE_IDS | {FUNDING_PRESSURE_ID, JH01_V0R1_REPLICATION_ID}


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
    assert len(identities) == len(set(identities)) == 6


# ---------------------------------------------------------------------------
# B. Complete pair coverage
# ---------------------------------------------------------------------------


def test_b_every_unordered_pair_appears_exactly_once():
    synthesis = build_synthesis(RESEARCH_ROOT)
    pairs = synthesis["pair_relationships"]
    assert len(pairs) == 15  # 6 choose 2
    seen = set()
    for pair in pairs:
        key = frozenset((pair["piece_a"], pair["piece_b"]))
        assert key not in seen, f"duplicate/reversed pair: {pair['pair_id']}"
        seen.add(key)
    assert len(seen) == 15


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
            "decision_window_direction",
            "same_data_history",
            "same_feature",
            "same_outcome",
            "prior_exposure_relation",
            "claim_relation",
            "independence_status",
            "replication_target_relation",
            "replication_relation",
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
# Statement-text consistency with claim_relation (hostile-review repair).
#
# A hostile review of the frozen candidate found that _statement_text's
# SAME_HISTORY_MULTI_PROPOSITION_CONTEXT branch re-derived its wording from
# raw same_feature/same_outcome instead of the already-correct claim_relation
# field, producing two bugs: (1) an IDENTICAL_CLAIM pair could be described
# as testing "different features", and (2) a CLAIM_RELATION_NOT_ESTABLISHED
# pair could be described with confident "different" language, laundering
# NOT_ESTABLISHED into a negative in reader-facing prose. Both are fixed by
# branching on claim_relation directly; these tests reproduce the exact
# scenarios and pin the fix.
# ---------------------------------------------------------------------------


def test_identical_claim_statement_never_claims_different_features(tmp_path):
    document = {
        "schema_version": "jigsaw-evidence-piece-v0",
        "experiment_id": "FIXTURE_IDENTICAL_V0",
        "research_status": "FROZEN_HISTORICAL_EVIDENCE",
        "authority": "NON_AUTHORITATIVE_EXPLORATORY_ONLY",
        "piece_count": 2,
        "piece_order": ["ID_A", "ID_B"],
        "pieces": [
            {
                "proposition_id": "ID_A",
                "piece_type": "PREDICTIVE_ASSOCIATION",
                "classification": "SUPPORTED_WITHIN_FROZEN_SCOPE",
                "feature": "SAME_FEATURE",
                "outcome": "SAME_OUTCOME",
                "snapshot_binding": {
                    "snapshot_id": "fixture-snap-identical",
                    "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z",
                    "panel_symbols": 3,
                },
                "prior_feature_exposure": "NO",
                "promotion_eligible": False,
            },
            {
                "proposition_id": "ID_B",
                "piece_type": "PREDICTIVE_ASSOCIATION",
                "classification": "SUPPORTED_WITHIN_FROZEN_SCOPE",
                "feature": "SAME_FEATURE",
                "outcome": "SAME_OUTCOME",
                "snapshot_binding": {
                    "snapshot_id": "fixture-snap-identical",
                    "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z",
                    "panel_symbols": 3,
                },
                "prior_feature_exposure": "NO",
                "promotion_eligible": False,
            },
        ],
    }
    _write(tmp_path, "fixture_identical", document)
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "ID_A", "ID_B")
    assert pair["same_feature"] == "YES"
    assert pair["same_outcome"] == "YES"
    assert pair["claim_relation"] == "IDENTICAL_CLAIM"
    assert pair["allowed_synthesis"] == "SAME_HISTORY_MULTI_PROPOSITION_CONTEXT"
    statement = next(s for s in synthesis["synthesis_statements"] if set(s["supporting_piece_ids"]) == {"ID_A", "ID_B"})
    assert "different features" not in statement["statement"]
    assert "same explicit feature against the same explicit outcome" in statement["statement"]


def test_claim_relation_not_established_statement_never_asserts_confident_difference(tmp_path):
    document = {
        "schema_version": "jigsaw-evidence-piece-v0",
        "experiment_id": "FIXTURE_UNESTABLISHED_V0",
        "research_status": "FROZEN_HISTORICAL_EVIDENCE",
        "authority": "NON_AUTHORITATIVE_EXPLORATORY_ONLY",
        "piece_count": 2,
        "piece_order": ["NE_A", "NE_B"],
        "pieces": [
            {
                "proposition_id": "NE_A",
                "piece_type": "PREDICTIVE_ASSOCIATION",
                "classification": "SUPPORTED_WITHIN_FROZEN_SCOPE",
                "feature": "SOME_FEATURE",
                "outcome": "SOME_OUTCOME",
                "snapshot_binding": {
                    "snapshot_id": "fixture-snap-unestablished",
                    "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z",
                    "panel_symbols": 3,
                },
                "prior_feature_exposure": "NO",
                "promotion_eligible": False,
            },
            {
                # Deliberately no "feature"/"outcome" fields -- mirrors the
                # real funding-pressure piece's CONDITION_EFFECT shape.
                "proposition_id": "NE_B",
                "piece_type": "CONDITION_EFFECT",
                "primary": {"decision": "NOT_SUPPORTED_UNDER_FROZEN_SPECIFICATION"},
                "snapshot_binding": {
                    "snapshot_id": "fixture-snap-unestablished",
                    "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z",
                    "panel_symbols": 3,
                },
                "prior_feature_exposure": "UNKNOWN",
                "promotion_eligible": False,
            },
        ],
    }
    _write(tmp_path, "fixture_unestablished", document)
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "NE_A", "NE_B")
    assert pair["same_feature"] == "NOT_ESTABLISHED"
    assert pair["same_outcome"] == "NOT_ESTABLISHED"
    assert pair["claim_relation"] == "CLAIM_RELATION_NOT_ESTABLISHED"
    # Same source artifact (and same explicit snapshot_id) still makes this
    # SHARED_FROZEN_HISTORY -- independence_status is about the data/history
    # binding, not about whether claim_relation is comparable.
    assert pair["independence_status"] == "SHARED_FROZEN_HISTORY"
    assert pair["allowed_synthesis"] == "SAME_HISTORY_MULTI_PROPOSITION_CONTEXT"
    statement = next(s for s in synthesis["synthesis_statements"] if set(s["supporting_piece_ids"]) == {"NE_A", "NE_B"})
    lowered = statement["statement"].lower()
    assert "different features and different outcome" not in lowered
    assert "not established" in lowered


# ---------------------------------------------------------------------------
# Post-review closure repair: shared history must dominate any self-declared
# replication relationship; a bare declaration must never establish
# empirical independence. A closure-gate hostile finding showed that an
# earlier revision checked explicit_independent_replication_of *before* the
# shared-history test, so a piece could declare replication of another piece
# while still demonstrably sharing that piece's exact frozen snapshot or
# source artifact, and the declaration would win. See design_note.md and
# hostile_review.md for the full finding and repair rationale.
# ---------------------------------------------------------------------------


def _declared_replication_piece(proposition_id, target_id, snapshot_binding, **extra):
    piece = {
        "proposition_id": proposition_id,
        "piece_type": "PREDICTIVE_ASSOCIATION",
        "classification": "SUPPORTED_WITHIN_FROZEN_SCOPE",
        "feature": f"FEATURE_{proposition_id}",
        "outcome": f"OUTCOME_{proposition_id}",
        "snapshot_binding": snapshot_binding,
        "prior_feature_exposure": "NO",
        "promotion_eligible": False,
        "explicit_independent_replication_of": target_id,
    }
    piece.update(extra)
    return piece


def test_closure_a_declared_replication_with_exact_snapshot_match_stays_shared_history(tmp_path):
    snapshot = {
        "snapshot_id": "fixture-snap-closure-a",
        "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z",
        "panel_symbols": 3,
    }
    document = {
        "schema_version": "jigsaw-evidence-piece-v0",
        "experiment_id": "FIXTURE_CLOSURE_A_V0",
        "research_status": "FROZEN_HISTORICAL_EVIDENCE",
        "authority": "NON_AUTHORITATIVE_EXPLORATORY_ONLY",
        "piece_count": 2,
        "piece_order": ["CLOSURE_A", "CLOSURE_B"],
        "pieces": [
            _declared_replication_piece("CLOSURE_A", "CLOSURE_B", snapshot),
            _declared_replication_piece("CLOSURE_B", "CLOSURE_A", snapshot),
        ],
    }
    _write(tmp_path, "fixture_closure_a", document)
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "CLOSURE_A", "CLOSURE_B")
    assert pair["same_snapshot_identity"] == "YES"
    assert pair["independence_status"] == "SHARED_FROZEN_HISTORY"
    assert pair["independence_status"] != "INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED"
    assert pair["allowed_synthesis"] != "INDEPENDENT_CONFIRMATION_ELIGIBLE"
    assert pair["allowed_synthesis"] == "SAME_HISTORY_MULTI_PROPOSITION_CONTEXT"


def test_closure_b_declared_replication_with_same_source_artifact_stays_shared_history(tmp_path):
    # Distinct snapshot_ids (so same_snapshot_identity == NO) but the same
    # source artifact -- same_source_artifact == YES must still dominate.
    document = {
        "schema_version": "jigsaw-evidence-piece-v0",
        "experiment_id": "FIXTURE_CLOSURE_B_V0",
        "research_status": "FROZEN_HISTORICAL_EVIDENCE",
        "authority": "NON_AUTHORITATIVE_EXPLORATORY_ONLY",
        "piece_count": 2,
        "piece_order": ["CLOSURE_C", "CLOSURE_D"],
        "pieces": [
            _declared_replication_piece(
                "CLOSURE_C",
                "CLOSURE_D",
                {"snapshot_id": "fixture-snap-closure-b1", "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z", "panel_symbols": 3},
            ),
            _declared_replication_piece(
                "CLOSURE_D",
                "CLOSURE_C",
                {"snapshot_id": "fixture-snap-closure-b2", "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z", "panel_symbols": 3},
            ),
        ],
    }
    _write(tmp_path, "fixture_closure_b", document)
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "CLOSURE_C", "CLOSURE_D")
    assert pair["same_source_artifact"] == "YES"
    assert pair["same_snapshot_identity"] == "NO"
    assert pair["independence_status"] == "SHARED_FROZEN_HISTORY"
    assert pair["allowed_synthesis"] == "SAME_HISTORY_MULTI_PROPOSITION_CONTEXT"


def test_closure_c_declared_replication_without_shared_history_never_grants_independent_confirmation(tmp_path):
    # Two different source artifacts, two different explicit snapshot IDs,
    # disjoint decision windows -- no shared-history evidence at all. A bare
    # declaration alone must not manufacture empirical independence.
    _write(
        tmp_path,
        "fixture_closure_c1",
        {
            "schema_version": "jigsaw-evidence-piece-v0",
            "experiment_id": "FIXTURE_CLOSURE_C1_V0",
            "piece_type": "PREDICTIVE_ASSOCIATION",
            "research_status": "FROZEN_HISTORICAL_EVIDENCE",
            "authority": "NON_AUTHORITATIVE",
            "promotion_eligible": False,
            "feature": "FEATURE_CLOSURE_E",
            "outcome": "OUTCOME_CLOSURE_E",
            "snapshot_binding": {
                "snapshot_id": "fixture-snap-closure-c1",
                "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z",
                "panel_symbols": 3,
            },
            "prior_feature_exposure": "NO",
            "explicit_independent_replication_of": "CLOSURE_F",
        },
        filename="result.json",
    )
    _write(
        tmp_path,
        "fixture_closure_c2",
        {
            "schema_version": "jigsaw-evidence-piece-v0",
            "experiment_id": "FIXTURE_CLOSURE_C2_V0",
            "piece_type": "PREDICTIVE_ASSOCIATION",
            "research_status": "FROZEN_HISTORICAL_EVIDENCE",
            "authority": "NON_AUTHORITATIVE",
            "promotion_eligible": False,
            "feature": "FEATURE_CLOSURE_E",
            "outcome": "OUTCOME_CLOSURE_E",
            "snapshot_binding": {
                "snapshot_id": "fixture-snap-closure-c2",
                "decision_window": "2025-06-01T00:00:00Z..2025-07-01T00:00:00Z",
                "panel_symbols": 3,
            },
            "prior_feature_exposure": "NO",
            "explicit_independent_replication_of": "CLOSURE_E",
        },
        filename="result.json",
    )
    # These are SINGLE_PIECE_OBJECT sources; piece_identity == experiment_id.
    document_e = json.loads((tmp_path / "fixture_closure_c1" / "result.json").read_text())
    document_e["experiment_id"] = "CLOSURE_E"
    (tmp_path / "fixture_closure_c1" / "result.json").write_text(json.dumps(document_e), encoding="utf-8")
    document_f = json.loads((tmp_path / "fixture_closure_c2" / "result.json").read_text())
    document_f["experiment_id"] = "CLOSURE_F"
    (tmp_path / "fixture_closure_c2" / "result.json").write_text(json.dumps(document_f), encoding="utf-8")

    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "CLOSURE_E", "CLOSURE_F")
    assert pair["same_source_artifact"] == "NO"
    assert pair["same_snapshot_identity"] == "NO"
    assert pair["decision_window_relation"] == "DISJOINT"
    assert pair["independence_status"] == "INDEPENDENCE_NOT_ESTABLISHED"
    assert pair["independence_status"] != "INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED"
    assert pair["allowed_synthesis"] == "SEPARATE_ONLY"
    assert pair["allowed_synthesis"] != "INDEPENDENT_CONFIRMATION_ELIGIBLE"


def test_closure_d_current_real_artifact_semantics_unchanged():
    synthesis = build_synthesis(RESEARCH_ROOT)
    assert synthesis["global_constraints"]["independent_replication_established"] == "NO"
    harvest_pairs = [
        p for p in synthesis["pair_relationships"] if p["piece_a"] in HARVEST_PIECE_IDS and p["piece_b"] in HARVEST_PIECE_IDS
    ]
    assert len(harvest_pairs) == 6
    assert all(p["independence_status"] == "SHARED_FROZEN_HISTORY" for p in harvest_pairs)
    funding_pairs = [p for p in synthesis["pair_relationships"] if FUNDING_PRESSURE_ID in (p["piece_a"], p["piece_b"])]
    assert len(funding_pairs) == 5
    assert all(p["allowed_synthesis"] == "SEPARATE_ONLY" for p in funding_pairs)
    assert not any(p["independence_status"] == "INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED" for p in synthesis["pair_relationships"])


def test_closure_e_existing_gates_still_pass():
    # Non-escalation, determinism, source immutability, and staleness gates
    # (tests J, K, L, M/N, O, P above) are exercised by their own dedicated
    # tests already run in this same module; this is a lightweight
    # cross-check that the closure repair did not disturb them.
    assert doctor(RESEARCH_ROOT) == []
    first = build_synthesis(RESEARCH_ROOT)
    second = build_synthesis(RESEARCH_ROOT)
    assert canonical_bytes(first) == canonical_bytes(second)
    committed = load_synthesis(RESEARCH_ROOT)
    assert committed == first


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
# JH01 V0R1 temporal replication (JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_JIGSAW_EVIDENCE_IMPLEMENTATION_V0).
#
# TEMPORALLY DISJOINT REPLICATION != INDEPENDENT REPLICATION. These tests pin
# the real-data pair's exact mechanical resolution and then hostile-review
# the generic replication_relation machinery against synthetic fixtures, the
# same way test_closure_a/b/c above hostile-reviewed independence_status.
# ---------------------------------------------------------------------------


def test_jh01_v0r1_real_pair_is_temporal_replication_not_independence(tmp_path=None):
    synthesis = build_synthesis(RESEARCH_ROOT)
    pair = get_pair(synthesis, "JH01_RV_PERSISTENCE", JH01_V0R1_REPLICATION_ID)
    assert pair is not None
    assert pair["claim_relation"] == "IDENTICAL_CLAIM"
    assert pair["decision_window_relation"] == "DISJOINT"
    # F-02 (PR #60 post-review closure repair): JH01_RV_PERSISTENCE's window
    # (...2025-06-19) ends before JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_
    # V0R1's window begins (2025-07-20...), so direction must mechanically
    # resolve to A_BEFORE_B -- the replication really is later, not merely
    # asserted to be.
    assert pair["decision_window_direction"] == "A_BEFORE_B"
    assert pair["same_snapshot_identity"] == "NO"
    assert pair["same_source_artifact"] == "NO"
    # The two axes disagree on purpose: temporally disjoint replication is
    # explicitly established while independence stays not established.
    assert pair["replication_relation"] == "TEMPORAL_REPLICATION_EXPLICITLY_ESTABLISHED"
    assert pair["independence_status"] == "INDEPENDENCE_NOT_ESTABLISHED"
    assert pair["independence_status"] != "INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED"
    assert pair["allowed_synthesis"] == "TEMPORAL_REPLICATION_CONTEXT_ONLY"
    assert pair["allowed_synthesis"] != "INDEPENDENT_CONFIRMATION_ELIGIBLE"


def test_jh01_v0r1_real_pair_statement_says_later_because_direction_is_mechanically_later():
    # F-02: the statement must say "later" only because decision_window_direction
    # mechanically establishes it, never merely because the replicating piece
    # declared itself a replication of the target.
    synthesis = build_synthesis(RESEARCH_ROOT)
    statement = next(
        s for s in synthesis["synthesis_statements"] if set(s["supporting_piece_ids"]) == {"JH01_RV_PERSISTENCE", JH01_V0R1_REPLICATION_ID}
    )
    assert "a later temporally separate frozen evaluation" in statement["statement"]
    assert "an earlier" not in statement["statement"]


def test_jh01_v0r1_does_not_flip_global_independent_replication_flag():
    synthesis = build_synthesis(RESEARCH_ROOT)
    assert synthesis["global_constraints"]["independent_replication_established"] == "NO"
    assert not any(
        p["independence_status"] == "INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED" for p in synthesis["pair_relationships"]
    )
    assert synthesis["summary"]["pairs_by_replication_relation"]["TEMPORAL_REPLICATION_EXPLICITLY_ESTABLISHED"] == 1


def test_jh01_v0r1_statement_disclaims_independence_and_forecast_value():
    synthesis = build_synthesis(RESEARCH_ROOT)
    statement = next(
        s for s in synthesis["synthesis_statements"] if set(s["supporting_piece_ids"]) == {"JH01_RV_PERSISTENCE", JH01_V0R1_REPLICATION_ID}
    )
    lowered = statement["statement"].lower()
    for banned in ("independent confirmation", "novel alpha", "trading edge", "economic significance"):
        assert banned not in lowered
    # The statement only ever mentions "independent replication" to disclaim
    # it, never to assert it.
    assert "does not establish independent replication" in lowered
    assert "provider" in lowered
    blob = " ".join(statement["prohibited_inferences"]).lower()
    assert "provider" in blob and "causal" in blob
    assert "incremental" in blob or "out-of-time forecast value" in blob


def test_jh01_v0r1_original_discovery_piece_untouched_by_addition():
    synthesis = build_synthesis(RESEARCH_ROOT)
    row = next(r for r in synthesis["piece_inventory"] if r["piece_identity"] == "JH01_RV_PERSISTENCE")
    assert row["native_scientific_fields"]["classification"] == "SUPPORTED_WITHIN_FROZEN_SCOPE"
    assert row["frozen_binding"]["decision_window"] == "2023-11-18T00:00:00Z..2025-06-19T00:00:00Z"


# --- Hostile-review-style fixtures for the new replication_relation axis --


def _replication_piece(experiment_id, snapshot_binding, replication_of=None, **extra):
    document = {
        "schema_version": "jigsaw-evidence-piece-v0",
        "experiment_id": experiment_id,
        "research_status": "FROZEN_HISTORICAL_EVIDENCE",
        "authority": "NON_AUTHORITATIVE_EXPLORATORY_ONLY",
        "piece_type": "PREDICTIVE_ASSOCIATION",
        "promotion_eligible": False,
        "feature": "RV24_prior,t",
        "outcome": "RV24_future,t",
        "snapshot_binding": snapshot_binding,
        "prior_feature_exposure": "NO",
    }
    if replication_of is not None:
        document["replication_of_piece_identity"] = replication_of
    document.update(extra)
    return document


def test_replication_a_shared_history_dominates_a_declared_replication_target(tmp_path):
    # Both pieces share the exact same explicit snapshot_id: a declared
    # replication target must not escape SHARED_FROZEN_HISTORY into a
    # "temporal replication" reading -- shared history is checked first,
    # unconditionally, exactly as it is for independence_status.
    snapshot = {"snapshot_id": "fixture-snap-repl-a", "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z", "panel_symbols": 3}
    _write(tmp_path, "fixture_repl_a1", _replication_piece("REPL_A_TARGET", snapshot), filename="result.json")
    _write(tmp_path, "fixture_repl_a2", _replication_piece("REPL_A_SOURCE", snapshot, replication_of="REPL_A_TARGET"), filename="result.json")
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "REPL_A_TARGET", "REPL_A_SOURCE")
    assert pair["independence_status"] == "SHARED_FROZEN_HISTORY"
    assert pair["replication_target_relation"] in ("A_DECLARES_REPLICATION_OF_B", "B_DECLARES_REPLICATION_OF_A")
    assert pair["replication_relation"] == "REPLICATION_TARGET_DECLARED_RELATION_NOT_ESTABLISHED"
    assert pair["allowed_synthesis"] == "SAME_HISTORY_MULTI_PROPOSITION_CONTEXT"
    assert pair["allowed_synthesis"] != "TEMPORAL_REPLICATION_CONTEXT_ONLY"


def test_replication_b_disjoint_declared_target_reaches_temporal_replication_but_not_independence(tmp_path):
    _write(
        tmp_path,
        "fixture_repl_b1",
        _replication_piece("REPL_B_TARGET", {"snapshot_id": "fixture-snap-repl-b1", "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z", "panel_symbols": 3}),
        filename="result.json",
    )
    _write(
        tmp_path,
        "fixture_repl_b2",
        _replication_piece(
            "REPL_B_SOURCE",
            {"snapshot_id": "fixture-snap-repl-b2", "decision_window": "2025-01-01T00:00:00Z..2025-02-01T00:00:00Z", "panel_symbols": 3},
            replication_of="REPL_B_TARGET",
        ),
        filename="result.json",
    )
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "REPL_B_TARGET", "REPL_B_SOURCE")
    assert pair["decision_window_relation"] == "DISJOINT"
    assert pair["replication_relation"] == "TEMPORAL_REPLICATION_EXPLICITLY_ESTABLISHED"
    assert pair["independence_status"] == "INDEPENDENCE_NOT_ESTABLISHED"
    assert pair["independence_status"] != "INDEPENDENT_REPLICATION_EXPLICITLY_ESTABLISHED"
    assert pair["allowed_synthesis"] == "TEMPORAL_REPLICATION_CONTEXT_ONLY"
    assert synthesis["global_constraints"]["independent_replication_established"] == "NO"


def test_replication_c_no_declaration_stays_no_explicit_target_even_when_disjoint(tmp_path):
    # A random disjoint experiment must not read as a replication of another
    # piece merely because it shares feature/outcome text and a disjoint
    # window -- only an explicit, matching declaration counts.
    _write(
        tmp_path,
        "fixture_repl_c1",
        _replication_piece("REPL_C_TARGET", {"snapshot_id": "fixture-snap-repl-c1", "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z", "panel_symbols": 3}),
        filename="result.json",
    )
    _write(
        tmp_path,
        "fixture_repl_c2",
        _replication_piece("REPL_C_OTHER", {"snapshot_id": "fixture-snap-repl-c2", "decision_window": "2025-01-01T00:00:00Z..2025-02-01T00:00:00Z", "panel_symbols": 3}),
        filename="result.json",
    )
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "REPL_C_TARGET", "REPL_C_OTHER")
    assert pair["claim_relation"] == "IDENTICAL_CLAIM"
    assert pair["decision_window_relation"] == "DISJOINT"
    assert pair["replication_target_relation"] == "NONE"
    assert pair["replication_relation"] == "NO_EXPLICIT_REPLICATION_TARGET"
    assert pair["allowed_synthesis"] == "SEPARATE_ONLY"


def test_replication_d_declared_target_naming_a_nonexistent_piece_never_matches(tmp_path):
    _write(
        tmp_path,
        "fixture_repl_d1",
        _replication_piece(
            "REPL_D_SOURCE",
            {"snapshot_id": "fixture-snap-repl-d1", "decision_window": "2025-01-01T00:00:00Z..2025-02-01T00:00:00Z", "panel_symbols": 3},
            replication_of="NOT_AN_INDEXED_PIECE",
        ),
        filename="result.json",
    )
    _write(
        tmp_path,
        "fixture_repl_d2",
        _replication_piece("REPL_D_OTHER", {"snapshot_id": "fixture-snap-repl-d2", "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z", "panel_symbols": 3}),
        filename="result.json",
    )
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "REPL_D_SOURCE", "REPL_D_OTHER")
    assert pair["replication_target_relation"] == "NONE"
    assert pair["replication_relation"] == "NO_EXPLICIT_REPLICATION_TARGET"


def test_replication_e_mismatched_claim_blocks_the_statement_even_with_declared_target(tmp_path):
    # A declared, temporally disjoint replication target whose feature/outcome
    # do not actually match must not produce a TEMPORAL_REPLICATION_CONTEXT_ONLY
    # statement -- allowed_synthesis still requires claim_relation compatibility.
    _write(
        tmp_path,
        "fixture_repl_e1",
        {
            "schema_version": "jigsaw-evidence-piece-v0",
            "experiment_id": "REPL_E_TARGET",
            "research_status": "FROZEN_HISTORICAL_EVIDENCE",
            "authority": "NON_AUTHORITATIVE_EXPLORATORY_ONLY",
            "piece_type": "PREDICTIVE_ASSOCIATION",
            "promotion_eligible": False,
            "feature": "FEATURE_ONE",
            "outcome": "OUTCOME_ONE",
            "snapshot_binding": {"snapshot_id": "fixture-snap-repl-e1", "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z", "panel_symbols": 3},
            "prior_feature_exposure": "NO",
        },
        filename="result.json",
    )
    _write(
        tmp_path,
        "fixture_repl_e2",
        {
            "schema_version": "jigsaw-evidence-piece-v0",
            "experiment_id": "REPL_E_SOURCE",
            "research_status": "FROZEN_HISTORICAL_EVIDENCE",
            "authority": "NON_AUTHORITATIVE_EXPLORATORY_ONLY",
            "piece_type": "PREDICTIVE_ASSOCIATION",
            "promotion_eligible": False,
            "feature": "FEATURE_TWO_UNRELATED",
            "outcome": "OUTCOME_TWO_UNRELATED",
            "snapshot_binding": {"snapshot_id": "fixture-snap-repl-e2", "decision_window": "2025-01-01T00:00:00Z..2025-02-01T00:00:00Z", "panel_symbols": 3},
            "prior_feature_exposure": "NO",
            "replication_of_piece_identity": "REPL_E_TARGET",
        },
        filename="result.json",
    )
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "REPL_E_TARGET", "REPL_E_SOURCE")
    assert pair["replication_relation"] == "TEMPORAL_REPLICATION_EXPLICITLY_ESTABLISHED"
    assert pair["claim_relation"] == "DIFFERENT_CLAIM"
    assert pair["allowed_synthesis"] == "SEPARATE_ONLY"
    assert not any(
        set(s["supporting_piece_ids"]) == {"REPL_E_TARGET", "REPL_E_SOURCE"} for s in synthesis["synthesis_statements"]
    )


def test_replication_f_legacy_independent_declaration_field_still_never_read_for_replication(tmp_path):
    # The pre-existing explicit_independent_replication_of field (see
    # test_closure_a/b/c above) must not be silently aliased into the new
    # replication_of_piece_identity mechanism either.
    snapshot_a = {"snapshot_id": "fixture-snap-repl-f1", "decision_window": "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z", "panel_symbols": 3}
    snapshot_b = {"snapshot_id": "fixture-snap-repl-f2", "decision_window": "2025-01-01T00:00:00Z..2025-02-01T00:00:00Z", "panel_symbols": 3}
    _write(
        tmp_path,
        "fixture_repl_f1",
        _replication_piece("REPL_F_TARGET", snapshot_a, explicit_independent_replication_of="REPL_F_SOURCE"),
        filename="result.json",
    )
    _write(
        tmp_path,
        "fixture_repl_f2",
        _replication_piece("REPL_F_SOURCE", snapshot_b, explicit_independent_replication_of="REPL_F_TARGET"),
        filename="result.json",
    )
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "REPL_F_TARGET", "REPL_F_SOURCE")
    assert pair["replication_target_relation"] == "NONE"
    assert pair["replication_relation"] == "NO_EXPLICIT_REPLICATION_TARGET"
    assert pair["independence_status"] == "INDEPENDENCE_NOT_ESTABLISHED"


# ---------------------------------------------------------------------------
# F-02 (PR #60 post-review closure repair): decision_window_direction is
# derived mechanically from the parsed windows, never from piece names or
# which side made the explicit replication declaration.
# ---------------------------------------------------------------------------


def test_replication_g_reverse_time_declaration_is_never_worded_as_later(tmp_path):
    # The *declaring* piece's window is the earlier of the disjoint pair.
    # A naive implementation that assumes the declaring piece is always
    # "later" would mis-describe this as a later evaluation; the statement
    # must say "earlier" instead, read off the mechanical direction only.
    _write(
        tmp_path,
        "fixture_repl_g_target",
        _replication_piece("REPL_G_TARGET", {"snapshot_id": "fixture-snap-repl-g-target", "decision_window": "2025-01-01T00:00:00Z..2025-02-01T00:00:00Z", "panel_symbols": 3}),
        filename="result.json",
    )
    _write(
        tmp_path,
        "fixture_repl_g_source",
        _replication_piece(
            "REPL_G_SOURCE",
            {"snapshot_id": "fixture-snap-repl-g-source", "decision_window": "2023-01-01T00:00:00Z..2023-02-01T00:00:00Z", "panel_symbols": 3},
            replication_of="REPL_G_TARGET",
        ),
        filename="result.json",
    )
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "REPL_G_TARGET", "REPL_G_SOURCE")
    assert pair["decision_window_relation"] == "DISJOINT"
    assert pair["replication_relation"] == "TEMPORAL_REPLICATION_EXPLICITLY_ESTABLISHED"
    # REPL_G_SOURCE (the declaring piece) is piece_a or piece_b depending on
    # sort order, but its window is strictly earlier than REPL_G_TARGET's
    # regardless -- assert on the resolved direction relative to piece_a/b,
    # not on which side declared.
    a_id, b_id = pair["piece_a"], pair["piece_b"]
    source_is_a = a_id == "REPL_G_SOURCE"
    expected_direction = "A_BEFORE_B" if source_is_a else "B_BEFORE_A"
    assert pair["decision_window_direction"] == expected_direction
    statement = next(
        s for s in synthesis["synthesis_statements"] if set(s["supporting_piece_ids"]) == {"REPL_G_TARGET", "REPL_G_SOURCE"}
    )
    assert "an earlier temporally separate frozen evaluation" in statement["statement"]
    assert "a later" not in statement["statement"]


def test_replication_h_overlapping_windows_with_declared_target_never_reach_temporal_replication(tmp_path):
    # F-02 forensic check: an explicit replication_of_piece_identity
    # declaration must not, by itself, manufacture
    # TEMPORAL_REPLICATION_EXPLICITLY_ESTABLISHED when the two pieces'
    # decision windows actually overlap -- only a provably DISJOINT relation
    # may reach it.
    _write(
        tmp_path,
        "fixture_repl_h_target",
        _replication_piece("REPL_H_TARGET", {"snapshot_id": "fixture-snap-repl-h-target", "decision_window": "2024-01-01T00:00:00Z..2024-06-01T00:00:00Z", "panel_symbols": 3}),
        filename="result.json",
    )
    _write(
        tmp_path,
        "fixture_repl_h_source",
        _replication_piece(
            "REPL_H_SOURCE",
            {"snapshot_id": "fixture-snap-repl-h-source", "decision_window": "2024-03-01T00:00:00Z..2024-09-01T00:00:00Z", "panel_symbols": 3},
            replication_of="REPL_H_TARGET",
        ),
        filename="result.json",
    )
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "REPL_H_TARGET", "REPL_H_SOURCE")
    assert pair["decision_window_relation"] == "PARTIAL_OVERLAP"
    assert pair["decision_window_direction"] == "NOT_APPLICABLE"
    assert pair["replication_relation"] == "REPLICATION_TARGET_DECLARED_RELATION_NOT_ESTABLISHED"
    assert pair["allowed_synthesis"] != "TEMPORAL_REPLICATION_CONTEXT_ONLY"


@pytest.mark.parametrize(
    ("window_a", "window_b", "expected_relation"),
    [
        ("2024-01-01T00:00:00Z..2024-02-01T00:00:00Z", "2024-01-01T00:00:00Z..2024-02-01T00:00:00Z", "EXACT"),
        ("2024-01-01T00:00:00Z..2024-06-01T00:00:00Z", "2024-02-01T00:00:00Z..2024-03-01T00:00:00Z", "A_CONTAINS_B"),
        ("2024-02-01T00:00:00Z..2024-03-01T00:00:00Z", "2024-01-01T00:00:00Z..2024-06-01T00:00:00Z", "B_CONTAINS_A"),
    ],
)
def test_replication_i_non_disjoint_relations_never_get_a_direction(tmp_path, window_a, window_b, expected_relation):
    # decision_window_direction is only ever meaningful for a provably
    # DISJOINT pair; every other relation must resolve to NOT_APPLICABLE so
    # nothing downstream can accidentally read "before"/"after" out of an
    # EXACT, contained, or overlapping pair.
    _write(
        tmp_path,
        "fixture_repl_i_a",
        _replication_piece("REPL_I_A", {"snapshot_id": "fixture-snap-repl-i-a", "decision_window": window_a, "panel_symbols": 3}),
        filename="result.json",
    )
    _write(
        tmp_path,
        "fixture_repl_i_b",
        _replication_piece("REPL_I_B", {"snapshot_id": "fixture-snap-repl-i-b", "decision_window": window_b, "panel_symbols": 3}),
        filename="result.json",
    )
    synthesis = build_synthesis(tmp_path)
    pair = get_pair(synthesis, "REPL_I_A", "REPL_I_B")
    assert pair["decision_window_relation"] == expected_relation
    assert pair["decision_window_direction"] == "NOT_APPLICABLE"


# ---------------------------------------------------------------------------
# CLI smoke coverage
# ---------------------------------------------------------------------------


def test_cli_doctor_and_summary_and_pair_against_real_repo(capsys):
    main(["doctor"])
    out = capsys.readouterr().out
    assert "OK" in out

    main(["summary"])
    summary = json.loads(capsys.readouterr().out)
    assert summary["total_pairs"] == 15

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
