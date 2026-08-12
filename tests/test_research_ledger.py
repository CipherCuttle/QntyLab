import json
from pathlib import Path

import pytest

from qntylab.research_ledger import (
    LedgerError,
    append_canonical_event,
    build_trial_completed_event,
    canonical_bytes,
    compute_trial_id,
    compute_variant_id,
    context_text,
    doctor,
    event_id,
    load_canonical_history,
    preflight,
    rebuild,
    replay,
    trial_stream_path,
)


def cfg(**overrides):
    value = {
        "schema_version": 1,
        "strategy_id": "H003_moving_average",
        "strategy_version": "existing-qntylab-strategies-v1",
        "input_path": "fixture.csv",
        "evaluation_start": "2021-01-01T00:00:00Z",
        "evaluation_end": "2021-01-02T00:00:00Z",
        "initial_capital": 10000,
        "fee_bps": 10,
        "slippage_bps": 0,
        "funding_boundary_mode": "NOT_APPLICABLE",
        "gap_policy": "REJECT",
        "expected_interval": "1h",
        "candidate_id": "TEST_H003",
        "research_intent": "SCREEN",
        "parameters": {"fast": 2, "slow": 4, "mode": "long_flat"},
    }
    value.update(overrides)
    return value


def proposal(config=None, **overrides):
    config = config or cfg()
    event = {
        "event_id": "",
        "event_type": "CANDIDATE_PROPOSED",
        "candidate_id": config["candidate_id"],
        "family_id": overrides.pop("family_id", "TEST_FAMILY"),
        "variant_id": compute_variant_id(config),
        "strategy_id": config["strategy_id"],
        "strategy_version": config["strategy_version"],
        "objective": "unit objective",
        "origin": "unit origin",
        "mechanism": "unit mechanism",
        "prediction": "unit prediction",
        "required_data": "unit data",
        "decision_time": "unit decision",
        "execution_time": "unit execution",
        "benchmark": "unit benchmark",
        "parameters": config["parameters"],
        "mode": config["parameters"]["mode"],
        "bar_interval": config["expected_interval"],
        "required_input_kind": "OHLCV_1H_CSV",
        "funding_boundary_mode": config["funding_boundary_mode"],
        "failure_condition": "unit failure",
        "recorded_at_utc": "2026-08-02T00:00:00Z",
    }
    event.update(overrides)
    event["event_id"] = event.get("event_id") or event_id("event_proposal", event)
    return event


def decision(prop, status="SURVIVOR", **overrides):
    event = {
        "event_id": "",
        "event_type": "DECISION_RECORDED",
        "candidate_id": prop["candidate_id"],
        "family_id": prop["family_id"],
        "variant_id": prop["variant_id"],
        "status": status,
        "scope": "EXACT_VARIANT",
        "reason_codes": [f"UNIT_{status}"],
        "decision_note": f"unit {status}",
        "evidence_paths": [],
        "evidence_sha256": {},
        "revisit_condition": "unit revisit",
        "recorded_at_utc": "2026-08-02T00:00:00Z",
    }
    event.update(overrides)
    event["event_id"] = event.get("event_id") or event_id("event_decision", event)
    return event


def reopen_event(prop, previous_decision_event_id, **overrides):
    event = {
        "event_id": "",
        "event_type": "CANDIDATE_REOPENED",
        "candidate_id": prop["candidate_id"],
        "variant_id": prop["variant_id"],
        "previous_decision_event_id": previous_decision_event_id,
        "reason": "Concrete material change justifying this reopen.",
        "material_change": "New evidence changed the frozen contract inputs.",
        "recorded_at_utc": "2026-08-02T03:00:00Z",
    }
    event.update(overrides)
    event["event_id"] = event.get("event_id") or event_id("event_reopen", event)
    return event


def trial(config, *, recorded_at_utc="2026-08-02T01:00:00Z", intent=None, symbol="BTCUSDT"):
    variant_id = compute_variant_id(config)
    trial_id = compute_trial_id(
        variant_id=variant_id,
        symbol=symbol,
        input_sha256="input",
        evaluation_start=config["evaluation_start"],
        evaluation_end=config["evaluation_end"],
        fee_bps=float(config["fee_bps"]),
        slippage_bps=float(config["slippage_bps"]),
        gap_policy=config["gap_policy"],
        expected_interval=config["expected_interval"],
    )
    event = {
        "event_id": "",
        "event_type": "TRIAL_COMPLETED",
        "recorded_at_utc": recorded_at_utc,
        "candidate_id": config["candidate_id"],
        "family_id": "TEST_FAMILY",
        "variant_id": variant_id,
        "trial_id": trial_id,
        "research_intent": intent or config["research_intent"],
        "symbol": symbol,
        "evaluation_start": config["evaluation_start"],
        "evaluation_end": config["evaluation_end"],
        "input_sha256": "input",
        "repository_commit": "commit",
        "relevant_source_sha256": "source",
        "fee_bps": float(config["fee_bps"]),
        "slippage_bps": float(config["slippage_bps"]),
        "gap_policy": config["gap_policy"],
        "expected_interval": config["expected_interval"],
        "receipt_path": f"runs/{trial_id}/run_receipt.json",
        "receipt_sha256": "receipt",
        "compact_metrics": {"net_return": 0.1, "trade_count": 2},
    }
    event["event_id"] = event_id("event_trial", event)
    return event


def write_root(root, candidates, decisions=(), trials=()):
    (root / "trials").mkdir(parents=True)
    (root / "candidates.jsonl").write_bytes(b"".join(canonical_bytes(event) + b"\n" for event in candidates))
    (root / "decisions.jsonl").write_bytes(b"".join(canonical_bytes(event) + b"\n" for event in decisions))
    by_file = {}
    for event in trials:
        by_file.setdefault(trial_stream_path(event["recorded_at_utc"], root), []).append(event)
    if not by_file:
        (root / "trials" / "2026.jsonl").write_text("", encoding="utf-8")
    for path, events in by_file.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"".join(canonical_bytes(event) + b"\n" for event in events))
    rebuild(root)
    return root


def write_canonical_only(root, candidates, decisions=(), trials=()):
    (root / "trials").mkdir(parents=True)
    (root / "candidates.jsonl").write_bytes(b"".join(canonical_bytes(event) + b"\n" for event in candidates))
    (root / "decisions.jsonl").write_bytes(b"".join(canonical_bytes(event) + b"\n" for event in decisions))
    by_file = {}
    for event in trials:
        by_file.setdefault(trial_stream_path(event["recorded_at_utc"], root), []).append(event)
    if not by_file:
        (root / "trials" / "2026.jsonl").write_text("", encoding="utf-8")
    for path, events in by_file.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"".join(canonical_bytes(event) + b"\n" for event in events))
    return root


def test_root_agents_bootstrap_points_to_context():
    text = Path("AGENTS.md").read_text(encoding="utf-8")
    assert "python -m qntylab.research_ledger context" in text
    assert "preflight automatically" in text


def test_streams_are_separate_and_rebuild_is_byte_identical(tmp_path):
    root = write_root(tmp_path, [proposal()])
    assert (root / "candidates.jsonl").exists()
    assert (root / "decisions.jsonl").exists()
    assert (root / "trials" / "2026.jsonl").exists()
    first = ((root / "state.json").read_bytes(), (root / "trial_index.json").read_bytes())
    rebuild(root)
    assert first == ((root / "state.json").read_bytes(), (root / "trial_index.json").read_bytes())


def test_doctor_detects_stale_state_and_trial_index(tmp_path):
    root = write_root(tmp_path, [proposal()])
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    state["variants"].clear()
    (root / "state.json").write_text(json.dumps(state, sort_keys=True) + "\n", encoding="utf-8")
    assert "stale or divergent state.json" in doctor(root)
    rebuild(root)
    index = json.loads((root / "trial_index.json").read_text(encoding="utf-8"))
    index["trials"]["missing"] = {}
    (root / "trial_index.json").write_text(json.dumps(index, sort_keys=True) + "\n", encoding="utf-8")
    assert "stale or divergent trial_index.json" in doctor(root)


def test_unknown_keys_and_identity_mismatch_fail_doctor(tmp_path):
    bad = proposal(extra=True)
    (tmp_path / "trials").mkdir()
    (tmp_path / "candidates.jsonl").write_bytes(canonical_bytes(bad) + b"\n")
    (tmp_path / "decisions.jsonl").write_text("", encoding="utf-8")
    (tmp_path / "trials" / "2026.jsonl").write_text("", encoding="utf-8")
    assert "unknown event keys" in doctor(tmp_path)[0]
    bad2 = proposal(variant_id="variant_wrong")
    (tmp_path / "candidates.jsonl").write_bytes(canonical_bytes(bad2) + b"\n")
    assert "variant_id mismatch" in doctor(tmp_path)[0]


def test_variant_identity_is_stable_and_material(tmp_path):
    base = cfg()
    renamed = dict(base, input_path="renamed.json")
    changed = dict(base, parameters={"fast": 3, "slow": 4, "mode": "long_flat"})
    assert compute_variant_id(base) == compute_variant_id(renamed)
    assert compute_variant_id(base) != compute_variant_id(changed)


def test_trial_identity_distinguishes_asset_window_and_costs():
    base = {
        "variant_id": "variant_x",
        "symbol": "BTCUSDT",
        "input_sha256": "input",
        "evaluation_start": "2021-01-01T00:00:00Z",
        "evaluation_end": "2021-01-02T00:00:00Z",
        "fee_bps": 10,
        "slippage_bps": 0,
        "gap_policy": "REJECT",
        "expected_interval": "1h",
    }
    first = compute_trial_id(**base)
    assert first == compute_trial_id(**base)
    assert first != compute_trial_id(**dict(base, symbol="ETHUSDT"))
    assert first != compute_trial_id(**dict(base, evaluation_end="2021-01-03T00:00:00Z"))
    assert first != compute_trial_id(**dict(base, slippage_bps=1))


def test_preflight_blocks_missing_stale_unregistered_blocked_and_graveyarded(tmp_path):
    config = cfg()
    with pytest.raises(LedgerError):
        preflight(config=config, symbol="BTCUSDT", input_sha256="input", root=tmp_path)
    prop = proposal(config)
    root = write_root(tmp_path, [prop])
    (root / "state.json").unlink()
    with pytest.raises(LedgerError):
        preflight(config=config, symbol="BTCUSDT", input_sha256="input", root=root)
    rebuild(root)
    (root / "candidates.jsonl").write_bytes((root / "candidates.jsonl").read_bytes() + canonical_bytes(proposal(cfg(candidate_id="OTHER"))) + b"\n")
    with pytest.raises(LedgerError, match="indexes stale"):
        preflight(config=config, symbol="BTCUSDT", input_sha256="input", root=root)

    unknown = cfg(parameters={"fast": 3, "slow": 5, "mode": "long_flat"})
    root = write_root(tmp_path / "unknown", [prop])
    with pytest.raises(LedgerError, match="variant unregistered"):
        preflight(config=unknown, symbol="BTCUSDT", input_sha256="input", root=root)
    for status in ("BLOCKED", "GRAVEYARDED"):
        root = write_root(tmp_path / status, [prop], [decision(prop, status)])
        with pytest.raises(LedgerError, match=status):
            preflight(config=config, symbol="BTCUSDT", input_sha256="input", root=root)


def test_proposed_followup_and_survivor_can_preflight(tmp_path):
    config = cfg()
    prop = proposal(config)
    for status, root in [
        ("PROPOSED", write_root(tmp_path / "p", [prop])),
        ("FOLLOW_UP", write_root(tmp_path / "f", [prop], [decision(prop, "FOLLOW_UP")])),
        ("SURVIVOR", write_root(tmp_path / "s", [prop], [decision(prop, "SURVIVOR")])),
    ]:
        assert preflight(config=config, symbol="BTCUSDT", input_sha256="input", root=root)["status"] == status


def test_reopen_recovers_graveyarded_exact_variant(tmp_path):
    config = cfg()
    prop = proposal(config)
    dec = decision(prop, "GRAVEYARDED")
    reopen = {
        "event_id": "event_reopen_1",
        "event_type": "CANDIDATE_REOPENED",
        "candidate_id": prop["candidate_id"],
        "variant_id": prop["variant_id"],
        "previous_decision_event_id": dec["event_id"],
        "reason": "Concrete material data coverage change.",
        "material_change": "New input coverage.",
        "recorded_at_utc": "2026-08-02T02:00:00Z",
    }
    root = write_root(tmp_path, [prop, reopen], [dec])
    assert preflight(config=config, symbol="BTCUSDT", input_sha256="input", root=root)["status"] == "PROPOSED"


def test_duplicate_trials_require_replication(tmp_path):
    config = cfg()
    prop = proposal(config)
    root = write_root(tmp_path, [prop], trials=[trial(config)])
    with pytest.raises(LedgerError, match="exact trial already completed"):
        preflight(config=config, symbol="BTCUSDT", input_sha256="input", root=root)
    replica = dict(config, research_intent="REPLICATION")
    assert preflight(config=replica, symbol="BTCUSDT", input_sha256="input", root=root)["trial_id"]


def test_trial_file_selection_and_receipt_event_are_compact():
    receipt = {
        "candidate_id": "C",
        "family_id": "F",
        "variant_id": "V",
        "trial_id": "T",
        "research_intent": "SCREEN",
        "symbol": "BTCUSDT",
        "evaluation_range": {"start": "2021-01-01T00:00:00Z", "end": "2021-01-02T00:00:00Z"},
        "input_sha256": "input",
        "repository_commit": "commit",
        "relevant_source_sha256": "source",
        "fee_assumption": {"fee_bps": 10.0},
        "slippage_assumption": {"slippage_bps": 0.0},
        "gap_policy": "REJECT",
        "expected_interval": "1h",
    }
    event = build_trial_completed_event(
        receipt=receipt,
        receipt_path=Path("runs/r/run_receipt.json"),
        receipt_sha256="receipt",
        metrics={"net_return": 1.0, "trade_count": 1, "raw_trades": [1, 2, 3]},
        recorded_at_utc="2025-01-01T00:00:00Z",
    )
    assert trial_stream_path(event["recorded_at_utc"], Path("root")) == Path("root/trials/2025.jsonl")
    assert "raw_trades" not in event["compact_metrics"]


def test_doctor_detects_duplicate_ids_invalid_transitions_and_family_scope(tmp_path):
    prop = proposal()
    dup = dict(prop, candidate_id="OTHER")
    root = write_canonical_only(tmp_path / "dup", [prop, dup])
    assert any("duplicate event_id" in issue for issue in doctor(root))
    bad_decision = decision(prop, "FOLLOW_UP")
    bad_reopen = {
        "event_id": "event_reopen_bad",
        "event_type": "CANDIDATE_REOPENED",
        "candidate_id": prop["candidate_id"],
        "variant_id": prop["variant_id"],
        "previous_decision_event_id": bad_decision["event_id"],
        "reason": "Concrete but invalid reopen.",
        "material_change": "None.",
        "recorded_at_utc": "2026-08-02T03:00:00Z",
    }
    root = write_canonical_only(tmp_path / "bad_reopen", [prop, bad_reopen], [bad_decision])
    assert any("reopen targets non-terminal" in issue for issue in doctor(root))

    sibling_cfg = cfg(candidate_id="SIBLING", parameters={"fast": 3, "slow": 6, "mode": "long_flat"})
    sibling = proposal(sibling_cfg)
    root = write_root(tmp_path / "family", [prop, sibling], [decision(prop, "GRAVEYARDED")])
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    assert state["variants"][prop["variant_id"]]["status"] == "GRAVEYARDED"
    assert state["variants"][sibling["variant_id"]]["status"] == "PROPOSED"
    fam = decision(prop, "GRAVEYARDED", scope="FAMILY")
    root = write_root(tmp_path / "family2", [prop, sibling], [fam])
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    assert {row["status"] for row in state["variants"].values()} == {"GRAVEYARDED"}


def test_append_duplicate_id_fails_and_append_keeps_canonical_if_rebuild_fails(tmp_path, monkeypatch):
    root = write_root(tmp_path, [proposal()])
    with pytest.raises(LedgerError, match="duplicate event_id"):
        append_canonical_event(proposal(), root)
    new = proposal(cfg(candidate_id="NEW", parameters={"fast": 5, "slow": 9, "mode": "long_flat"}))

    def boom(_root):
        raise LedgerError("boom")

    monkeypatch.setattr("qntylab.research_ledger.rebuild", boom)
    with pytest.raises(LedgerError, match="boom"):
        append_canonical_event(new, root)
    assert new["event_id"] in (root / "candidates.jsonl").read_text(encoding="utf-8")
    with pytest.raises(LedgerError, match="indexes stale"):
        preflight(config=cfg(candidate_id="NEW", parameters={"fast": 5, "slow": 9, "mode": "long_flat"}), symbol="BTCUSDT", input_sha256="input", root=root)


def test_append_exact_decision_preserves_candidate_and_trial_streams(tmp_path):
    prop = proposal()
    root = write_root(tmp_path, [prop], trials=[trial(cfg())])
    candidate_before = (root / "candidates.jsonl").read_bytes()
    trial_before = (root / "trials" / "2026.jsonl").read_bytes()
    event = decision(prop, "BLOCKED", reason_codes=["UNIT_NON_COMPARABLE_EVIDENCE"])

    append_canonical_event(event, root)

    assert (root / "candidates.jsonl").read_bytes() == candidate_before
    assert (root / "trials" / "2026.jsonl").read_bytes() == trial_before
    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    assert state["variants"][prop["variant_id"]]["status"] == "BLOCKED"
    first = ((root / "state.json").read_bytes(), (root / "trial_index.json").read_bytes())
    rebuild(root)
    assert first == ((root / "state.json").read_bytes(), (root / "trial_index.json").read_bytes())


def test_exact_decision_does_not_accidentally_become_family_decision(tmp_path):
    prop = proposal()
    sibling_config = cfg(candidate_id="SIBLING", parameters={"fast": 3, "slow": 6, "mode": "long_flat"})
    sibling = proposal(sibling_config)
    root = write_root(tmp_path, [prop, sibling])

    append_canonical_event(decision(prop, "FOLLOW_UP"), root)

    state = json.loads((root / "state.json").read_text(encoding="utf-8"))
    assert state["variants"][prop["variant_id"]]["status"] == "FOLLOW_UP"
    assert state["variants"][sibling["variant_id"]]["status"] == "PROPOSED"
    stored = json.loads((root / "decisions.jsonl").read_text(encoding="utf-8"))
    assert stored["scope"] == "EXACT_VARIANT"


def test_rebuild_recovers_removed_index(tmp_path):
    root = write_root(tmp_path, [proposal()])
    (root / "state.json").unlink()
    assert any("state.json" in issue for issue in doctor(root))
    rebuild(root)
    assert doctor(root) == []


def test_large_history_keeps_context_compact_and_duplicate_lookup_indexed(tmp_path, monkeypatch):
    config = cfg()
    prop = proposal(config)
    trials = [
        trial(
            dict(config, evaluation_end=f"2021-01-{(i % 27) + 2:02d}T00:00:00Z", slippage_bps=i % 5),
            recorded_at_utc=f"2026-01-{(i % 27) + 1:02d}T00:00:00Z",
            symbol=f"S{i % 25}USDT",
        )
        for i in range(300)
    ]
    root = write_root(tmp_path, [prop], trials=trials)
    text = context_text(root)
    assert len(text.splitlines()) < 80
    assert "total completed trials: 300" in text
    assert text.count("event_trial") == 0
    first_state = (root / "state.json").read_bytes()
    rebuild(root)
    assert first_state == (root / "state.json").read_bytes()

    def no_scan(_root):
        raise AssertionError("preflight scanned canonical history")

    monkeypatch.setattr("qntylab.research_ledger.load_canonical_history", no_scan)
    with pytest.raises(LedgerError, match="exact trial already completed"):
        preflight(config=config, symbol=trials[0]["symbol"], input_sha256="input", root=root)


# --- F-01: a terminal decision may not be replaced without an explicit,
# exact CANDIDATE_REOPENED (QNTYLAB_TERMINAL_DECISION_INTEGRITY_V0). ---------


def test_first_decision_on_fresh_variant_is_accepted(tmp_path):
    prop = proposal()
    d1 = decision(prop, "GRAVEYARDED", recorded_at_utc="2026-08-02T00:00:00Z")
    root = write_canonical_only(tmp_path, [prop], [d1])

    state, _, issues = replay(load_canonical_history(root), root=root)

    assert issues == []
    assert state["variants"][prop["variant_id"]]["status"] == "GRAVEYARDED"
    assert state["variants"][prop["variant_id"]]["latest_decision_event_id"] == d1["event_id"]


def test_second_terminal_decision_without_reopen_is_rejected(tmp_path):
    prop = proposal()
    d1 = decision(prop, "GRAVEYARDED", recorded_at_utc="2026-08-02T00:00:00Z", decision_note="first terminal")
    d2 = decision(prop, "SURVIVOR", recorded_at_utc="2026-08-02T01:00:00Z", decision_note="silent replacement attempt")
    root = write_canonical_only(tmp_path, [prop], [d1, d2])

    history = load_canonical_history(root)
    state, _, issues = replay(history, root=root)

    assert any("terminal decision replaced without explicit CANDIDATE_REOPENED" in issue for issue in issues)
    # Derived state reflects only the latest *legitimately* closed generation;
    # the silent second decision never takes effect.
    assert state["variants"][prop["variant_id"]]["status"] == "GRAVEYARDED"
    assert state["variants"][prop["variant_id"]]["latest_decision_event_id"] == d1["event_id"]
    # Nothing is dropped from canonical history itself -- both decisions are
    # still present, byte-for-byte, in the immutable stream.
    assert d1 in history.decisions
    assert d2 in history.decisions
    with pytest.raises(LedgerError, match="terminal decision replaced"):
        rebuild(root)


def test_reopen_with_unrelated_candidate_does_not_authorize_replacement(tmp_path):
    prop = proposal()
    d1 = decision(prop, "GRAVEYARDED", recorded_at_utc="2026-08-02T00:00:00Z")
    d2 = decision(prop, "SURVIVOR", recorded_at_utc="2026-08-02T02:00:00Z")
    unrelated_candidate_reopen = reopen_event(
        prop,
        d1["event_id"],
        candidate_id="CANDIDATE_UNRELATED",
        recorded_at_utc="2026-08-02T01:00:00Z",
    )
    root = write_canonical_only(tmp_path, [prop, unrelated_candidate_reopen], [d1, d2])

    state, _, issues = replay(load_canonical_history(root), root=root)

    assert any("terminal decision replaced without explicit CANDIDATE_REOPENED" in issue for issue in issues)
    # d2 (SURVIVOR) never takes effect -- the mismatched-candidate reopen does
    # not authorize it.
    assert state["variants"][prop["variant_id"]]["status"] != "SURVIVOR"
    assert state["variants"][prop["variant_id"]]["latest_decision_event_id"] != d2["event_id"]


def test_reopen_declared_under_wrong_variant_does_not_authorize_replacement(tmp_path):
    prop = proposal()
    sibling = proposal(cfg(candidate_id="SIBLING", parameters={"fast": 3, "slow": 6, "mode": "long_flat"}))
    d1 = decision(prop, "GRAVEYARDED", recorded_at_utc="2026-08-02T00:00:00Z")
    d2 = decision(prop, "SURVIVOR", recorded_at_utc="2026-08-02T02:00:00Z")
    # Well-formed reopen (names a real candidate/variant pair) but declared
    # for the sibling variant, while naming prop's terminal decision.
    misdirected_reopen = reopen_event(sibling, d1["event_id"], recorded_at_utc="2026-08-02T01:00:00Z")
    root = write_canonical_only(tmp_path, [prop, sibling, misdirected_reopen], [d1, d2])

    state, _, issues = replay(load_canonical_history(root), root=root)

    assert any("terminal decision replaced without explicit CANDIDATE_REOPENED" in issue for issue in issues)
    assert state["variants"][prop["variant_id"]]["status"] == "GRAVEYARDED"


def test_reopen_with_wrong_previous_decision_event_id_does_not_authorize_replacement(tmp_path):
    prop = proposal()
    d1 = decision(prop, "GRAVEYARDED", recorded_at_utc="2026-08-02T00:00:00Z")
    d2 = decision(prop, "SURVIVOR", recorded_at_utc="2026-08-02T02:00:00Z")
    stale_reopen = reopen_event(prop, "event_decision_does_not_exist", recorded_at_utc="2026-08-02T01:00:00Z")
    root = write_canonical_only(tmp_path, [prop, stale_reopen], [d1, d2])

    state, _, issues = replay(load_canonical_history(root), root=root)

    assert any("terminal decision replaced without explicit CANDIDATE_REOPENED" in issue for issue in issues)
    assert state["variants"][prop["variant_id"]]["status"] == "GRAVEYARDED"


def test_reopen_recorded_before_the_terminal_decision_does_not_authorize_replacement(tmp_path):
    prop = proposal()
    d1 = decision(prop, "GRAVEYARDED", recorded_at_utc="2026-08-02T02:00:00Z")
    d2 = decision(prop, "SURVIVOR", recorded_at_utc="2026-08-02T03:00:00Z")
    # Recorded before d1 -- a reopen cannot retroactively license a decision
    # it precedes.
    early_reopen = reopen_event(prop, d1["event_id"], recorded_at_utc="2026-08-02T01:00:00Z")
    root = write_canonical_only(tmp_path, [prop, early_reopen], [d1, d2])

    state, _, issues = replay(load_canonical_history(root), root=root)

    assert any("terminal decision replaced without explicit CANDIDATE_REOPENED" in issue for issue in issues)
    # d2 (SURVIVOR) never takes effect -- a reopen recorded before the
    # decision it names cannot retroactively license replacing it.
    assert state["variants"][prop["variant_id"]]["status"] != "SURVIVOR"
    assert state["variants"][prop["variant_id"]]["latest_decision_event_id"] != d2["event_id"]


def test_correct_reopen_then_decision_is_accepted_and_a_third_decision_needs_a_new_reopen(tmp_path):
    prop = proposal()
    d1 = decision(prop, "GRAVEYARDED", recorded_at_utc="2026-08-02T00:00:00Z", decision_note="first terminal")
    r1 = reopen_event(prop, d1["event_id"], recorded_at_utc="2026-08-02T01:00:00Z")
    d2 = decision(prop, "BLOCKED", recorded_at_utc="2026-08-02T02:00:00Z", decision_note="second terminal, legitimately reopened")

    # Exact terminal decision -> exact CANDIDATE_REOPENED -> new decision:
    # accepted (no rejection issue for d2).  The reopen also lets the
    # variant's later, pre-existing reopen-replay pass settle back to
    # PROPOSED -- confirmed against the one real reopen lineage in the
    # canonical ledger (CANDIDATE_JIGSAW_CROSS_SECTIONAL_DISPERSION_V0), which
    # ends the same way. That downstream behavior predates and is unrelated
    # to this guard; it is asserted here only so a regression there is caught.
    root = write_canonical_only(tmp_path / "second", [prop, r1], [d1, d2])
    history = load_canonical_history(root)
    state, _, issues = replay(history, root=root)
    assert issues == []
    assert state["variants"][prop["variant_id"]]["status"] == "PROPOSED"
    assert state["variants"][prop["variant_id"]]["latest_decision_event_id"] is None
    rebuild(root)
    assert doctor(root) == []

    # The same reopen does not carry forward: it named d1, not d2, so a third
    # decision without a *new* reopen is again rejected -- d3 never takes
    # effect.
    d3 = decision(prop, "SURVIVOR", recorded_at_utc="2026-08-02T04:00:00Z", decision_note="unauthorized third decision")
    root3 = write_canonical_only(tmp_path / "third", [prop, r1], [d1, d2, d3])
    state3, _, issues3 = replay(load_canonical_history(root3), root=root3)
    assert any("terminal decision replaced without explicit CANDIDATE_REOPENED" in issue for issue in issues3)
    assert state3["variants"][prop["variant_id"]]["status"] != "SURVIVOR"
    assert state3["variants"][prop["variant_id"]]["latest_decision_event_id"] != d3["event_id"]


def test_append_canonical_event_rejects_silent_terminal_decision_overwrite(tmp_path):
    prop = proposal()
    d1 = decision(prop, "GRAVEYARDED", recorded_at_utc="2026-08-02T00:00:00Z")
    root = write_root(tmp_path, [prop], [d1])
    state_before = (root / "state.json").read_bytes()

    d2 = decision(prop, "SURVIVOR", recorded_at_utc="2026-08-02T01:00:00Z", decision_note="silent replacement via CLI append")
    with pytest.raises(LedgerError, match="terminal decision replaced"):
        append_canonical_event(d2, root)

    # The event lands in the immutable stream, but the illegitimate decision
    # never takes effect: state.json is left exactly as it was rather than
    # silently reflecting the unauthorized decision.
    assert d2["event_id"] in (root / "decisions.jsonl").read_text(encoding="utf-8")
    assert (root / "state.json").read_bytes() == state_before
