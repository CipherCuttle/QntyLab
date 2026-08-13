"""F-01 (PR #60 post-review closure repair): fresh canonical research memory
must know about the JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_V0R1 Jigsaw
evidence incorporation.

Before this repair, `python -m qntylab.research_ledger context` reported
only the graveyarded CANDIDATE_JIGSAW_HARVEST_V0 family and gave no
indication that JH01_RV_PERSISTENCE now has later temporal replication
evidence -- a fresh research session reading only the ledger (per AGENTS.md)
could not have known this state existed. These tests pin the append-only
recording of that state transition against the real repository ledger and
prove the pre-existing Jigsaw Harvest V0 history is untouched.
"""

import hashlib
import json
from pathlib import Path

from qntylab.research_ledger import (
    RESEARCH_ROOT,
    context_text,
    doctor,
    load_canonical_history,
    rebuild,
    verify_indexes_current,
)

ROOT = Path(__file__).parents[1]
CANDIDATES_PATH = ROOT / "experiments/research/candidates.jsonl"
DECISIONS_PATH = ROOT / "experiments/research/decisions.jsonl"

CANDIDATE_ID = "CANDIDATE_JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_V0R1"
FAMILY_ID = "FAMILY_JH01_RV_PERSISTENCE_TEMPORAL_REPLICATION_V0"
VARIANT_ID = "variant_5b36ae24bb97fc69fcf4a460"

EVIDENCE_SHA256 = {
    "experiments/research/jh01_rv_persistence_temporal_replication_v0/result.json": "e2be973dc5741cfb05768753a664a44194650f0758984cc7ca0caecf9532f7f8",
    "experiments/research/jh01_rv_persistence_temporal_replication_v0/v0r1/execution_result.json": "00c18ed0097587ef8db0e9b5e4003546c862f6001986fe9d54952734aa6f5872",
    "experiments/research/jh01_rv_persistence_temporal_replication_v0/v0r1/provenance_correction.json": "9c98ab16b52aef31f4cd3c939eb24c7d4ed211d954db6936e64fc97b45fb3ac1",
}


def _candidates():
    return [json.loads(line) for line in CANDIDATES_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def _decisions():
    return [json.loads(line) for line in DECISIONS_PATH.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_doctor_passes_against_real_repo():
    assert doctor(RESEARCH_ROOT) == []


def test_rebuild_is_deterministic_and_matches_on_disk_caches():
    state1, trial_index1 = rebuild(RESEARCH_ROOT)
    state2, trial_index2 = rebuild(RESEARCH_ROOT)
    assert state1 == state2
    assert trial_index1 == trial_index2
    on_disk_state = json.loads((ROOT / "experiments/research/state.json").read_text(encoding="utf-8"))
    on_disk_trial_index = json.loads((ROOT / "experiments/research/trial_index.json").read_text(encoding="utf-8"))
    assert state1 == on_disk_state
    assert trial_index1 == on_disk_trial_index


def test_candidate_proposal_is_appended_not_reopening_jigsaw_harvest():
    candidates = _candidates()
    matches = [event for event in candidates if event["candidate_id"] == CANDIDATE_ID]
    assert len(matches) == 1
    event = matches[0]
    assert event["event_type"] == "CANDIDATE_PROPOSED"
    assert event["variant_id"] == VARIANT_ID
    # Deliberately its own family, not FAMILY_JIGSAW_HARVEST_V0 -- that
    # family's own DECISION_RECORDED is scope=FAMILY and explicitly
    # forbidden from being reopened, extended, or rescued.
    assert event["family_id"] == FAMILY_ID
    assert event["family_id"] != "FAMILY_JIGSAW_HARVEST_V0"
    assert event["mode"] == "measurement_only"
    assert event["parameters"]["mode"] == "measurement_only"
    assert event["parameters"]["replication_of_piece_identity"] == "JH01_RV_PERSISTENCE"
    # No CANDIDATE_REOPENED event references this candidate or its family:
    # this repair never reopens anything (existing reopens elsewhere in the
    # stream, for unrelated candidates, are untouched history).
    assert not any(
        e["event_type"] == "CANDIDATE_REOPENED" and e["candidate_id"] in (CANDIDATE_ID, "CANDIDATE_JIGSAW_HARVEST_V0")
        for e in candidates
    )


def test_decision_is_graveyarded_exact_variant_not_survivor():
    decisions = _decisions()
    matches = [event for event in decisions if event["candidate_id"] == CANDIDATE_ID]
    assert len(matches) == 1
    event = matches[0]
    assert event["event_type"] == "DECISION_RECORDED"
    assert event["variant_id"] == VARIANT_ID
    assert event["family_id"] == FAMILY_ID
    # GRAVEYARDED/EXACT_VARIANT, exactly the precedent CANDIDATE_JIGSAW_HARVEST_V0
    # itself used for "measurement-complete, frozen, no further action
    # authorized" -- never SURVIVOR merely because the replication was
    # positive.
    assert event["status"] == "GRAVEYARDED"
    assert event["scope"] == "EXACT_VARIANT"
    assert event["status"] != "SURVIVOR"


def test_decision_evidence_binds_exact_on_disk_digests_no_recomputation():
    decisions = _decisions()
    event = next(item for item in decisions if item["candidate_id"] == CANDIDATE_ID)
    assert set(event["evidence_paths"]) == set(EVIDENCE_SHA256)
    for path, expected_digest in EVIDENCE_SHA256.items():
        assert event["evidence_sha256"][path] == expected_digest
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == expected_digest


def test_decision_note_describes_temporal_replication_narrowly():
    decisions = _decisions()
    event = next(item for item in decisions if item["candidate_id"] == CANDIDATE_ID)
    note = event["decision_note"].lower()
    assert "temporal_replication_explicitly_established" in note
    assert "independence_not_established" in note
    assert "temporal replication is not independent replication" in note
    for banned in ("survivor", "confirmed alpha", "validated strategy"):
        assert banned not in note
    # "economic significance"/"trading edge" appear only inside the
    # disclaiming clause below, never asserted as established.
    assert "value, economic significance, or strategy edge is established or claimed" in note
    assert "no state snapshot, router, qnty, trading, or promotion authority" in note
    assert "post_start_repair=true" in note
    assert "pristine_first_execution=false" in note
    # No scientific recomputation: exact frozen values copied verbatim.
    assert "0.4006840403348443" in event["decision_note"]  # beta
    assert "2.4703453016587016e-19" in event["decision_note"]  # raw p-value


def test_revisit_condition_grants_no_downstream_authority():
    decisions = _decisions()
    event = next(item for item in decisions if item["candidate_id"] == CANDIDATE_ID)
    revisit = event["revisit_condition"].lower()
    assert "new preregist" in revisit
    assert "may not be reopened, extended, or rescued" in revisit
    # "state snapshot"/"router"/"qnty"/"trading"/"promotion" appear only
    # inside the explicit negation "no result here authorizes ... implementation".
    assert "no result here authorizes state snapshot, router, qnty, trading, or promotion implementation" in revisit
    assert "authorizes router" not in revisit
    assert "authorizes qnty" not in revisit
    assert "authorizes trading" not in revisit
    assert "authorizes promotion" not in revisit


def test_jigsaw_harvest_v0_history_is_byte_unchanged():
    candidates = _candidates()
    decisions = _decisions()
    harvest_candidate = next(item for item in candidates if item["candidate_id"] == "CANDIDATE_JIGSAW_HARVEST_V0")
    harvest_decision = next(item for item in decisions if item["event_id"] == "event_decision_jigsaw_harvest_v0_recorded_complete")
    assert harvest_candidate["family_id"] == "FAMILY_JIGSAW_HARVEST_V0"
    assert harvest_decision["status"] == "GRAVEYARDED"
    assert harvest_decision["scope"] == "FAMILY"
    assert "may not be reopened, extended, or rescued" in harvest_decision["revisit_condition"]


def test_fresh_context_surfaces_the_jh01_temporal_replication_lineage():
    text = context_text(RESEARCH_ROOT)
    assert CANDIDATE_ID in text
    assert VARIANT_ID in text
    assert "TEMPORAL_REPLICATION_WITHIN_FROZEN_SCOPE_ESTABLISHED" in text
    assert "INDEPENDENT_REPLICATION_NOT_ESTABLISHED" in text
    assert "MEASUREMENT_ONLY_NO_PROMOTION_AUTHORITY" in text
    # Original Jigsaw Harvest V0 closure remains visible in the same fresh
    # context read.
    assert "CANDIDATE_JIGSAW_HARVEST_V0" in text
    assert "FAMILY_JIGSAW_HARVEST_V0" in text
    # Not listed as an active survivor or follow-up candidate.
    survivors_section = text.split("active survivors:")[1].split("follow-up candidates:")[0]
    assert CANDIDATE_ID not in survivors_section
    followups_section = text.split("follow-up candidates:")[1].split("blocked variants:")[0]
    assert CANDIDATE_ID not in followups_section


def test_global_independence_and_authority_flags_unaffected_by_ledger_entry():
    # verify_indexes_current raises LedgerError on any staleness/mismatch;
    # succeeding at all proves the on-disk generated caches are current.
    state, _, _ledger_sha = verify_indexes_current(RESEARCH_ROOT)
    variant = state["variants"][VARIANT_ID]
    assert variant["status"] == "GRAVEYARDED"
    assert variant["candidate_id"] == CANDIDATE_ID


def test_no_historical_event_id_was_modified_only_appended():
    # A cheap append-only sanity check: every pre-repair Jigsaw Harvest V0
    # event_id still resolves to byte-identical content it always had.
    history = load_canonical_history(RESEARCH_ROOT)
    harvest_candidate = next(e for e in history.candidates if e["candidate_id"] == "CANDIDATE_JIGSAW_HARVEST_V0")
    assert harvest_candidate["event_id"] == "event_ca6637c535576aa54b09651d"
    harvest_decision = next(e for e in history.decisions if e["event_id"] == "event_decision_jigsaw_harvest_v0_recorded_complete")
    assert harvest_decision["candidate_id"] == "CANDIDATE_JIGSAW_HARVEST_V0"
