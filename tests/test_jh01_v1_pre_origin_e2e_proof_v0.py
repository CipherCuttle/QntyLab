"""JH01 V1 pre-origin end-to-end proof suite (temp state only).

Proves the COMPLETE composition -- synthetic Binance archive fixtures +
synthetic REST-tail fixtures + temp operation state dirs + fake qualified
release transport + FROZEN recorder + FROZEN wrapper + production caller +
target_commit preflight seam -- without any network, GitHub, Binance REST,
or contact with the real campaign state directory.

Proof numbering (18 proofs + firewall guard) is embedded in test names and
docstrings.  Every campaign state directory is a pytest ``tmp_path``.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from hashlib import sha256
import json
from pathlib import Path

import pytest

from qntylab import jh01_v1_prospective_operation_v0 as operation
from qntylab import jh01_v1_prospective_production_caller_v0 as caller
from qntylab import jh01_v1_prospective_recorder_implementation_v0 as recorder
from qntylab import jh01_v1_prospective_source_adapter_v0 as adapter

from tests._jh01_v1_prospective_fixtures import (
    FIRST_REQUIRED,
    ORIGIN,
    PANEL,
    REQUIRED_CLOSE_COUNT,
    kline_row,
    synthetic_archive_provider,
    synthetic_fetch_klines,
)


ROOT = Path(__file__).resolve().parents[1]
PINNED = "c" * 40
OTHER_COMMIT = "d" * 40
FROZEN_RECORDER_SHA256 = "4f5e1791be9f17c1871f9b510329a1632412e028d2a84223fa59e83bbe95ec1a"
FROZEN_WRAPPER_SHA256 = "1176037ff0d3102afc67670202154970e4af1491cff1cd19bc9526c9c9d67c41"
LEDGER_NAME = "jh01_v1_operation_events.jsonl"


# --------------------------------------------------------------------------
# seam fakes (no network anywhere)
# --------------------------------------------------------------------------

def fake_run_git(*, head: str = PINNED, remote: str = PINNED, porcelain: str = ""):
    """Injected run_git seam standing in for a real temp git repo."""
    def run_git(args):
        command = [str(part) for part in args]
        if command[0] == "fetch":
            return ""
        if command[:2] == ["rev-parse", "origin/master"]:
            return remote + "\n"
        if command[:2] == ["rev-parse", "HEAD"]:
            return head + "\n"
        if command[0] == "status":
            return porcelain
        raise AssertionError(f"unexpected git invocation: {command}")
    return run_git


class FakeTransport:
    """Fake transport implementing the frozen ReleaseTransport interface."""

    def __init__(self, origin: datetime = ORIGIN):
        self.origin = origin
        self.release: recorder.RemoteRelease | None = None
        self.create_calls = 0
        self.upload_calls = 0
        self.publish_calls = 0

    def find(self, origin_id: str):
        return () if self.release is None else (self.release,)

    def create(self, release: recorder.RemoteRelease):
        self.create_calls += 1
        self.release = recorder.RemoteRelease(
            release.origin_id, release.tag, release.artifact_digest,
            release.asset_name, None, None, target_commit=release.target_commit,
        )
        return self.release

    def upload(self, tag: str, asset_name: str, content: bytes):
        self.upload_calls += 1
        assert self.release is not None
        self.release = recorder.RemoteRelease(
            self.release.origin_id, tag, self.release.artifact_digest, asset_name,
            sha256(content).hexdigest(), None, target_commit=self.release.target_commit,
        )
        return self.release

    def publish(self, release: recorder.RemoteRelease):
        self.publish_calls += 1
        self.release = recorder.RemoteRelease(
            release.origin_id, release.tag, release.artifact_digest, release.asset_name,
            release.asset_sha256, self.origin + timedelta(minutes=10),
            target_commit=release.target_commit, immutable=True,
            repository_id="repo", owner_id="owner", release_id=7,
            purl=f"pkg:github/CipherCuttle/QntyLab@{release.tag}", package_id="repo",
        )
        return self.release

    def acquire_attestation(self, release: recorder.RemoteRelease):
        return b"synthetic-bundle", b"synthetic-root\n"


class AmbiguousTransport(FakeTransport):
    """Unknown remote-write outcome: two matching releases exist."""

    def find(self, origin_id: str):
        assert self.release is not None
        return (self.release, self.release)


class FakeVerifier:
    def verify(self, *, asset: bytes, bundle: bytes, trusted_root: bytes,
               expectation: recorder.AttestationExpectation):
        assert bundle == b"synthetic-bundle"
        assert trusted_root == b"synthetic-root\n"
        return recorder.VerifiedAttestation(expectation, ORIGIN + timedelta(minutes=20), bundle, trusted_root)


def activate(tmp_path: Path) -> Path:
    """Activate REAL_PROSPECTIVE in a temporary state directory."""
    state_dir = tmp_path / "state"
    operation.Operation(ROOT, state_dir).activate_real(activation_time=ORIGIN - timedelta(days=1))
    return state_dir


def ledger_text(state_dir: Path) -> str:
    return (state_dir / LEDGER_NAME).read_text()


def origin_event_count(state_dir: Path, event_type: str) -> int:
    return sum(
        1 for line in ledger_text(state_dir).splitlines() if line.strip()
        and json.loads(line)["event_type"] == event_type
    )


def call_record_due(
    tmp_path: Path,
    *,
    now: datetime,
    transport=None,
    run_git=None,
    archive_provider=None,
    fetch_klines=None,
    state_dir: Path | None = None,
):
    return caller.record_due(
        ROOT,
        state_dir or tmp_path / "state",
        now=now,
        run_git=run_git or fake_run_git(),
        archive_provider=archive_provider or synthetic_archive_provider(),
        fetch_klines=fetch_klines or synthetic_fetch_klines(),
        transport_factory=(lambda: transport) if transport is not None else None,
        verifier=FakeVerifier(),
        offline_reverify=lambda package: recorder.verify_retention_package(package),
    )


def materialize(*, archive_provider=None, fetch_klines=None):
    return adapter.materialize_origin_bars(
        origin=ORIGIN,
        first_required_close=FIRST_REQUIRED,
        archive_provider=archive_provider or synthetic_archive_provider(),
        fetch_klines=fetch_klines or synthetic_fetch_klines(),
    )


# --------------------------------------------------------------------------
# composition proofs (archive + REST boundary through frozen validate_bars)
# --------------------------------------------------------------------------

def test_proof_01_archive_rest_boundary_composition_gap_and_duplicate_free():
    """Proof 1: archive bulk + REST tail compose with no gap and no duplicate;
    the composed set is accepted by the frozen validate_bars."""
    bars = materialize()
    assert len(bars) == len(PANEL) * REQUIRED_CLOSE_COUNT
    keys = {(bar.symbol, bar.logical_close) for bar in bars}
    assert len(keys) == len(bars), "duplicate logical closes in composition"
    expected_closes = {FIRST_REQUIRED + timedelta(hours=i) for i in range(REQUIRED_CLOSE_COUNT)}
    for symbol in PANEL:
        assert {bar.logical_close for bar in bars if bar.symbol == symbol} == expected_closes
    ordered = recorder.validate_bars(bars, panel=PANEL, origin=ORIGIN, first_required_close=FIRST_REQUIRED)
    assert ordered == bars


def test_proof_02_rest_open_bar_rejected():
    """Proof 2: the currently open REST bar (close beyond origin boundary) is rejected."""
    open_bar = kline_row(ORIGIN + timedelta(hours=1), 0)
    with pytest.raises(adapter.SourceAdapterBlocked, match="open or future"):
        adapter.rest_bar_from_row(PANEL[0], open_bar, first_required_close=FIRST_REQUIRED, origin=ORIGIN)


def test_proof_03_rest_future_close_rejected():
    """Proof 3: a REST row closing after the origin boundary is rejected."""
    future = kline_row(ORIGIN + timedelta(hours=25), 0)
    with pytest.raises(adapter.SourceAdapterBlocked, match="open or future"):
        adapter.rest_bar_from_row(PANEL[0], future, first_required_close=FIRST_REQUIRED, origin=ORIGIN)


def test_proof_04_wrong_symbol_rejected():
    """Proof 4: a non-panel symbol is rejected end to end."""
    row = kline_row(ORIGIN, 0)
    with pytest.raises(adapter.SourceAdapterBlocked, match="non-panel symbol"):
        adapter.rest_bar_from_row("BTCUSDT", row, first_required_close=FIRST_REQUIRED, origin=ORIGIN)
    victim = PANEL[7]

    def provider_without_victim(*, symbol: str, year: int, month: int):
        if symbol == victim:
            return None
        return synthetic_archive_provider()(symbol=symbol, year=year, month=month)

    with pytest.raises(recorder.RecorderBlocked):
        materialize(
            archive_provider=provider_without_victim,
            fetch_klines=synthetic_fetch_klines(omit_symbols=frozenset({victim})),
        )


def test_proof_05_wrong_interval_rejected():
    """Proof 5: a REST row that is not an exact 1h interval is rejected."""
    bad = kline_row(ORIGIN, 0, close_override_ms=int((ORIGIN - timedelta(hours=1)).timestamp() * 1000) + 3_600_000)
    with pytest.raises(adapter.SourceAdapterBlocked, match="exact 1h interval"):
        adapter.rest_bar_from_row(PANEL[0], bad, first_required_close=FIRST_REQUIRED, origin=ORIGIN)


def test_proof_06_wrong_timestamp_mapping_rejected():
    """Proof 6: a REST row whose open/close times do not map onto the frozen
    logical-close mapping is rejected."""
    shifted = kline_row(ORIGIN, 0, open_shift_ms=1000)
    with pytest.raises(adapter.SourceAdapterBlocked, match="hour alignment|logical close"):
        adapter.rest_bar_from_row(PANEL[0], shifted, first_required_close=FIRST_REQUIRED, origin=ORIGIN)


def test_proof_07_missing_panel_symbol_rejected_by_frozen_validator():
    """Proof 7: a composition missing one panel symbol fails closed."""
    victim = PANEL[11]
    base_provider = synthetic_archive_provider()

    def provider_without_victim(*, symbol: str, year: int, month: int):
        if symbol == victim:
            return None
        return base_provider(symbol=symbol, year=year, month=month)

    with pytest.raises(recorder.RecorderBlocked, match="missing source symbol"):
        materialize(
            archive_provider=provider_without_victim,
            fetch_klines=synthetic_fetch_klines(omit_symbols=frozenset({victim})),
        )


def test_proof_08_missing_hour_rejected_as_source_gap():
    """Proof 8: one missing hourly close fails closed as a source gap."""
    victim = PANEL[3]
    dropped_close = datetime(2026, 9, 8, tzinfo=UTC)
    drop_open = int((dropped_close - timedelta(hours=1)).timestamp() * 1000)
    with pytest.raises(recorder.RecorderBlocked, match="source gap"):
        materialize(fetch_klines=synthetic_fetch_klines(drop_opens={victim: {drop_open}}))


def test_proof_09_manifest_deterministic_and_byte_sensitive():
    """Proof 9: same inputs regenerate an identical source_data_manifest_sha256
    and per-row raw_row_sha256; different bytes produce a different digest."""
    first = materialize()
    second = materialize()
    manifest_one = recorder.source_manifest(first, panel=PANEL, origin=ORIGIN, first_required_close=FIRST_REQUIRED)
    manifest_two = recorder.source_manifest(second, panel=PANEL, origin=ORIGIN, first_required_close=FIRST_REQUIRED)
    assert manifest_one["source_data_manifest_sha256"] == manifest_two["source_data_manifest_sha256"]
    sample = first[0]
    expected_row_digest = sha256(recorder.canonical_bytes(sample.raw_row)).hexdigest()
    assert manifest_one["rows"][0]["raw_row_sha256"] == expected_row_digest

    mutated_rows = []
    for index, bar in enumerate(first):
        if index == 0:
            row = list(bar.raw_row)
            row[4] = f"{float(row[4]) + 1.0:.4f}"
            mutated_rows.append(recorder.Bar(bar.symbol, bar.logical_close, float(row[4]), tuple(row)))
        else:
            mutated_rows.append(bar)
    manifest_three = recorder.source_manifest(mutated_rows, panel=PANEL, origin=ORIGIN, first_required_close=FIRST_REQUIRED)
    assert manifest_three["source_data_manifest_sha256"] != manifest_one["source_data_manifest_sha256"]
    assert manifest_three["rows"][0]["raw_row_sha256"] != manifest_one["rows"][0]["raw_row_sha256"]


# --------------------------------------------------------------------------
# preflight / publication fail-closed proofs
# --------------------------------------------------------------------------

def test_proof_10_target_commit_mismatch_between_preflight_and_publication_rejected(tmp_path):
    """Proof 10: when the preflight-derived target commit differs from the
    publication expectation found on the remote, the path fails closed."""
    # Phase 1: a successful run captures the true remote identity.
    capture_state = activate(tmp_path / "capture")
    capturing = FakeTransport()
    receipt = call_record_due(tmp_path / "capture", now=ORIGIN + timedelta(minutes=1), transport=capturing, state_dir=capture_state)
    assert receipt["origin_state"] == "RECORDED"
    published = capturing.release
    assert published is not None and published.target_commit == PINNED

    # Phase 2: fresh temp state; remote already holds a release pinned to a
    # different commit while the preflight derives PINNED -> must block.
    conflict_state = activate(tmp_path / "conflict")
    conflicting = FakeTransport()
    conflicting.release = recorder.RemoteRelease(
        published.origin_id, published.tag, published.artifact_digest,
        published.asset_name, None, None, target_commit=OTHER_COMMIT,
    )
    before = ledger_text(conflict_state)
    with pytest.raises(recorder.RecorderBlocked, match="same origin different target commit"):
        call_record_due(tmp_path / "conflict", now=ORIGIN + timedelta(minutes=1), transport=conflicting, state_dir=conflict_state)
    assert ledger_text(conflict_state) == before
    assert conflicting.publish_calls == 0


def test_proof_11_dirty_or_stale_worktree_rejected_by_preflight(tmp_path):
    """Proof 11: dirty tracked worktree and HEAD != origin/master both fail
    closed before any collection or publication."""
    with pytest.raises(caller.CallerBlocked, match="dirty"):
        caller.canonical_target_commit(fake_run_git(porcelain=" M qntylab/x.py\n"))
    with pytest.raises(caller.CallerBlocked, match="not origin/master"):
        caller.canonical_target_commit(fake_run_git(head=OTHER_COMMIT))
    state_dir = activate(tmp_path)
    captured: list[dict] = []
    with pytest.raises(caller.CallerBlocked, match="dirty|not origin/master"):
        call_record_due(
            tmp_path,
            now=ORIGIN + timedelta(minutes=1),
            run_git=fake_run_git(porcelain=" M qntylab/x.py\n"),
            fetch_klines=synthetic_fetch_klines(capture=captured),
            state_dir=state_dir,
        )
    assert captured == [], "collection started despite failed preflight"
    assert origin_event_count(state_dir, "ORIGIN_RECORDED") == 0


# --------------------------------------------------------------------------
# scheduler lifecycle proofs (temp state, fake transport)
# --------------------------------------------------------------------------

def test_proof_12_not_due_before_origin_fails_closed_with_zero_writes(tmp_path, capsys):
    """Proof 12: synthetic now before 2026-09-15T00:00:00Z -> --record-due
    exits nonzero with an explicit NOT_DUE verdict and performs zero writes."""
    state_dir = activate(tmp_path)
    captured: list[dict] = []
    before = ledger_text(state_dir)
    rc = caller.main(
        ["--record-due", "--root", str(ROOT), "--state-dir", str(state_dir),
         "--now", "2026-09-14T23:00:00Z"],
        run_git=fake_run_git(),
        archive_provider=synthetic_archive_provider(),
        fetch_klines=synthetic_fetch_klines(capture=captured),
        verifier=FakeVerifier(),
        offline_reverify=lambda package: None,
    )
    assert rc == 3
    verdict = json.loads(capsys.readouterr().out)
    assert verdict["origin_state"] == "NOT_DUE"
    assert verdict["origin_utc"] == "2026-09-15T00:00:00Z"
    assert captured == [], "REST seam consulted before the origin was due"
    assert ledger_text(state_dir) == before, "ledger written while NOT_DUE"
    assert not (state_dir / "retention").exists()


def test_proof_13_due_synthetic_origin_completes_exactly_once(tmp_path):
    """Proof 13: synthetic now inside the due window completes the full
    production path exactly once (ORIGIN_RECORDED, retention package)."""
    state_dir = activate(tmp_path)
    transport = FakeTransport()
    receipt = call_record_due(tmp_path, now=ORIGIN + timedelta(minutes=1), transport=transport, state_dir=state_dir)
    assert receipt["origin_state"] == "RECORDED"
    assert receipt["publication_state"] == "ORIGIN_COMPLETE"
    assert receipt["target_commit"] == PINNED
    assert origin_event_count(state_dir, "ORIGIN_RECORDED") == 1
    retention_dirs = list((state_dir / "retention").iterdir())
    assert len(retention_dirs) == 1
    assert (retention_dirs[0] / "forecast.json").is_file()
    assert transport.create_calls == 1 and transport.upload_calls == 1 and transport.publish_calls == 1


def test_proof_14_duplicate_scheduler_invocation_creates_no_second_origin(tmp_path):
    """Proof 14: invoking the record path twice with the same synthetic now
    leaves exactly one ORIGIN_RECORDED; the second call is a harmless no-op."""
    state_dir = activate(tmp_path)
    transport = FakeTransport()
    now = ORIGIN + timedelta(minutes=1)
    first = call_record_due(tmp_path, now=now, transport=transport, state_dir=state_dir)
    second = call_record_due(tmp_path, now=now, transport=transport, state_dir=state_dir)
    third = call_record_due(tmp_path, now=now, transport=transport, state_dir=state_dir)
    assert first["origin_state"] == "RECORDED"
    assert second == {"origin_state": "NOT_DUE", "origin_utc": "2026-09-16T00:00:00Z"}
    assert third == {"origin_state": "NOT_DUE", "origin_utc": "2026-09-16T00:00:00Z"}
    assert origin_event_count(state_dir, "ORIGIN_RECORDED") == 1
    assert transport.create_calls == 1 and transport.publish_calls == 1


def test_proof_15_unknown_remote_write_remains_fail_closed(tmp_path):
    """Proof 15: an unknown remote write outcome (ambiguous releases, or an
    existing release with a different artifact digest) blocks publication and
    the caller surfaces the failure closed with no ledger write."""
    # Variant A: two matching remote releases -> BLOCK_AMBIGUOUS_REMOTE.
    state_a = activate(tmp_path / "ambiguous")
    ambiguous = AmbiguousTransport()
    ambiguous.release = recorder.RemoteRelease("origin", "tag", "", "forecast.json", None, None)
    before_a = ledger_text(state_a)
    with pytest.raises(recorder.RecorderBlocked, match="BLOCK_AMBIGUOUS_REMOTE"):
        call_record_due(tmp_path / "ambiguous", now=ORIGIN + timedelta(minutes=1), transport=ambiguous, state_dir=state_a)
    assert ledger_text(state_a) == before_a

    # Variant B: single existing release with a different artifact digest.
    capture_state = activate(tmp_path / "capture")
    capturing = FakeTransport()
    assert call_record_due(tmp_path / "capture", now=ORIGIN + timedelta(minutes=1), transport=capturing, state_dir=capture_state)["origin_state"] == "RECORDED"
    published = capturing.release
    state_b = activate(tmp_path / "digest-conflict")
    conflicting = FakeTransport()
    conflicting.release = recorder.RemoteRelease(
        published.origin_id, published.tag, "f" * 64,
        published.asset_name, None, None, target_commit=PINNED,
    )
    before_b = ledger_text(state_b)
    with pytest.raises(recorder.RecorderBlocked, match="same origin different digest"):
        call_record_due(tmp_path / "digest-conflict", now=ORIGIN + timedelta(minutes=1), transport=conflicting, state_dir=state_b)
    assert ledger_text(state_b) == before_b
    assert conflicting.publish_calls == 0


def test_proof_16_missed_window_is_terminal_and_cannot_resurrect(tmp_path):
    """Proof 16: now beyond t+1h appends ORIGIN_BLOCKED exactly once; the
    campaign is terminal and later attempts do not resurrect it."""
    state_dir = activate(tmp_path)
    bars = materialize()
    operation_obj = operation.Operation(ROOT, state_dir)
    runtime = recorder.PublicationRuntime(FakeTransport(), FakeVerifier())

    # Beyond the persistence window through the frozen wrapper directly:
    # ORIGIN_BLOCKED is appended once.
    first = operation_obj.record_due(
        now=ORIGIN + timedelta(hours=2), bars=bars, runtime=runtime,
        target_commit=PINNED, offline_reverify=lambda package: recorder.verify_retention_package(package),
    )
    assert first["origin_state"] == "BLOCKED_MISSED_WINDOW"
    assert origin_event_count(state_dir, "ORIGIN_BLOCKED") == 1
    assert origin_event_count(state_dir, "ORIGIN_RECORDED") == 0

    # Repeat attempts append nothing further (terminal, no resurrection).
    second = operation_obj.record_due(
        now=ORIGIN + timedelta(hours=3), bars=bars, runtime=runtime,
        target_commit=PINNED, offline_reverify=lambda package: recorder.verify_retention_package(package),
    )
    assert second["origin_state"] == "BLOCKED_MISSED_WINDOW"
    assert origin_event_count(state_dir, "ORIGIN_BLOCKED") == 1

    # The production caller also refuses fail closed afterwards.
    with pytest.raises(caller.CallerBlocked, match="BLOCKED_MISSED_WINDOW"):
        call_record_due(tmp_path, now=ORIGIN + timedelta(hours=4), transport=FakeTransport(), state_dir=state_dir)
    status = operation_obj.status(now=ORIGIN + timedelta(hours=4))
    assert status["campaign_state"] == "BLOCKED"
    assert status["completed_origin_count"] == 0


# --------------------------------------------------------------------------
# freeze-integrity proofs
# --------------------------------------------------------------------------

def test_proof_17_frozen_recorder_module_digest_unchanged():
    """Proof 17: the frozen recorder implementation still hashes to the
    published frozen digest, computed at test runtime from the repo root."""
    path = ROOT / "qntylab" / "jh01_v1_prospective_recorder_implementation_v0.py"
    assert sha256(path.read_bytes()).hexdigest() == FROZEN_RECORDER_SHA256


def test_proof_18_frozen_wrapper_module_digest_unchanged():
    """Proof 18: the frozen prospective operation wrapper still hashes to the
    published frozen digest, computed at test runtime from the repo root."""
    path = ROOT / "qntylab" / "jh01_v1_prospective_operation_v0.py"
    assert sha256(path.read_bytes()).hexdigest() == FROZEN_WRAPPER_SHA256


# --------------------------------------------------------------------------
# firewall guard
# --------------------------------------------------------------------------

def test_firewall_suite_never_references_real_state_directory():
    """Firewall: no test module in this pre-origin proof suite references the
    real campaign state directory name; all state paths are tmp_path-bound."""
    forbidden = caller.REAL_STATE_DIRNAME
    scanned = [
        Path(__file__).resolve(),
        ROOT / "tests" / "test_jh01_v1_prospective_source_adapter_v0.py",
        ROOT / "tests" / "test_jh01_v1_prospective_production_caller_v0.py",
        ROOT / "tests" / "_jh01_v1_prospective_fixtures.py",
    ]
    for path in scanned:
        assert forbidden not in path.read_text(), f"firewall violation in {path.name}"
    # The real-state binding exists only in the caller module; this suite never
    # relies on it -- every helper above takes an explicit tmp_path state dir.
    assert caller.default_state_dir().name == forbidden
