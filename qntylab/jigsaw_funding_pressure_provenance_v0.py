"""Bounded provenance and structural-coverage verifier for Jigsaw V0."""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiments/research/jigsaw_funding_pressure_volatility_v0"
PANEL = [
    "BCHUSDT", "XRPUSDT", "LTCUSDT", "TRXUSDT", "ETCUSDT", "LINKUSDT",
    "XLMUSDT", "CHZUSDT", "SANDUSDT", "REEFUSDT", "CHRUSDT", "ALICEUSDT",
    "ONEUSDT", "API3USDT", "GMTUSDT", "APEUSDT", "OPUSDT", "INJUSDT",
    "LDOUSDT", "APTUSDT",
]
CONTRACT_DIGEST = "sha256:749641cbee99bc769a6095e2a5877e4ccf1c46db0a82860885eedc06734cd2d6"
FUNDING_DIGEST = "sha256:3677e5aeafd17c47e4951b2095d6247c8fb7cd3fb603cc70d5ea5658fd768faa"
OHLCV_DIGEST = "sha256:97760d127e33c51f2ac687f5f8edb92ffa3ac01b1c7c963951872a87ab3b5ae9"
PIT_V1_DIGEST = "sha256:eee5ce2769e49970a7a4e8d4851d7da569abc156d4f183959b416bfb8dbf188b"
PIT_V1_SHA = "3e54cb86cdc43c76c1cbf72acc4dfebecb6b10fa"
PREREG_SHA = "98e9dbcbec5dab18f7498cf4c5df77e14a8d5569"
_FULL_SHA1 = re.compile(r"[0-9a-f]{40}")
_SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def canonical_digest(payload: object) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    return "sha256:" + hashlib.sha256(raw).hexdigest()


def file_digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load(name: str) -> dict:
    return json.loads((EXPERIMENT / name).read_text(encoding="utf-8"))


def _without(payload: dict, key: str) -> dict:
    result = dict(payload)
    result.pop(key, None)
    return result


def required_pressure_days() -> list[date]:
    eligibility = _load("pit_coverage_certificate_v1.json")["pit_eligibility"]
    first = datetime.fromisoformat(eligibility["first_decision"].replace("Z", "+00:00")).date()
    last = datetime.fromisoformat(eligibility["last_decision"].replace("Z", "+00:00")).date()
    warmup_days = 365
    return [first - timedelta(days=warmup_days) + timedelta(days=i) for i in range((last - first).days + warmup_days + 1)]


def _event_times(symbol: str) -> list[datetime]:
    path = ROOT / f"data/raw/{symbol}-perp-funding-events.jsonl"
    values = []
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        # Deliberately inspect only identity and timestamp; never parse funding_rate.
        if row.get("symbol") != symbol:
            raise AssertionError(f"wrong symbol in {path}")
        values.append(datetime.fromisoformat(row["funding_time_utc"].replace("Z", "+00:00")))
    return values


def compute_funding_coverage() -> dict:
    days = required_pressure_days()
    missing = []
    event_times = {symbol: _event_times(symbol) for symbol in PANEL}
    for day in days:
        decision = datetime.combine(day, datetime.min.time(), UTC)
        lower = decision - timedelta(hours=24)
        for symbol in PANEL:
            if not any(lower < timestamp <= decision for timestamp in event_times[symbol]):
                missing.append({"symbol": symbol, "pressure_day": day.isoformat()})
    return {
        "schema_version": "jigsaw-funding-pressure-history-coverage-v0",
        "phase": "JIGSAW_FUNDING_PRESSURE_VOLATILITY_PROVENANCE_BASELINE_V0",
        "exact_panel": PANEL,
        "first_required_pressure_day": days[0].isoformat(),
        "last_required_pressure_day": days[-1].isoformat(),
        "pressure_day_count": len(days),
        "symbol_day_requirement_count": len(days) * len(PANEL),
        "symbol_day_complete_count": len(days) * len(PANEL) - len(missing),
        "missing_count": len(missing),
        "missing": missing,
        "funding_evidence_set_digest": FUNDING_DIGEST,
        "materialization_index_digest": canonical_digest(_without(_load("materialization_index.json"), "evidence_set_digest")),
        "eligibility_rule_identity": "decision_time_minus_24h_strictly_less_than_funding_time_less_than_or_equal_to_decision_time",
        "no_feature_values_computed": True,
        "no_outcomes_accessed": True,
    }


def verify_self_digest(payload: dict, field: str) -> None:
    expected = payload[field]
    actual = canonical_digest(_without(payload, field))
    if expected != actual:
        raise AssertionError(f"{field}: expected {expected}, got {actual}")


def verify_git_ancestry(
    commit: str,
    root: Path = ROOT,
    ancestors: tuple[str, ...] = (PREREG_SHA, PIT_V1_SHA),
    git_runner=subprocess.run,
) -> None:
    """Fail closed: Git ancestry MUST be authenticated, never silently skipped.

    A worktree checkout has ``.git`` as a *file* pointing at the real gitdir,
    a regular checkout has it as a directory; ``Path.exists()`` covers both.
    Anything else (bare tarball, no metadata at all) is not a usable runtime
    checkout and must not be treated as equivalent to one.
    """
    if not (root / ".git").exists():
        raise AssertionError(f"no usable Git metadata at {root}: refusing to skip ancestry verification")
    for ancestor in ancestors:
        try:
            result = git_runner(["git", "merge-base", "--is-ancestor", ancestor, commit], cwd=root)
        except OSError as exc:
            raise AssertionError(f"git command unavailable while verifying ancestor {ancestor}: {exc}") from exc
        if result.returncode:
            raise AssertionError(f"{ancestor} is not an ancestor of {commit}")


def _git_text(args: list[str], root: Path = ROOT) -> str:
    """Run a read-only Git plumbing command, failing closed on every error."""
    try:
        result = subprocess.run(args, cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    except OSError as exc:
        raise AssertionError(f"git command unavailable while running {args!r}: {exc}") from exc
    if result.returncode:
        raise AssertionError(f"git command failed: {args!r}")
    return result.stdout.strip()


def historical_materializer_digest(
    commit: str, relative_path: str, root: Path = ROOT
) -> str:
    """SHA-256 of ``relative_path`` **as recorded in the immutable commit**.

    Reads the historical Git blob, never the working tree.  ``commit`` must be
    a full 40-hex object id that Git resolves to a commit, so an abbreviated,
    ambiguous or ref-shaped identifier cannot select a different object than
    the one the frozen baseline names.
    """
    if not _FULL_SHA1.fullmatch(commit):
        raise AssertionError(f"historical anchor is not a full 40-hex object id: {commit!r}")
    if _git_text(["git", "cat-file", "-t", commit], root) != "commit":
        raise AssertionError(f"historical anchor is not a commit object: {commit}")
    blob = _git_text(["git", "rev-parse", "--verify", "--quiet", f"{commit}:{relative_path}"], root)
    if not _FULL_SHA1.fullmatch(blob):
        raise AssertionError(f"{relative_path} does not resolve to an object at {commit}")
    if _git_text(["git", "cat-file", "-t", blob], root) != "blob":
        raise AssertionError(f"{relative_path} at {commit} is not a blob")
    try:
        content = subprocess.run(
            ["git", "cat-file", "blob", blob], cwd=root, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL
        )
    except OSError as exc:
        raise AssertionError(f"git command unavailable while reading blob {blob}: {exc}") from exc
    if content.returncode:
        raise AssertionError(f"could not read blob {blob} for {relative_path} at {commit}")
    return hashlib.sha256(content.stdout).hexdigest()


def verify_historical_materializer_identity(
    baseline: dict, root: Path = ROOT, require_tracked: bool = True
) -> list[dict]:
    """Authenticate the **historical producer** of the frozen funding evidence.

    The frozen ``materializer_files`` hashes identify the exact materializer
    source that produced the frozen evidence bytes.  That is a statement about
    history, so it is authenticated against the immutable Git blobs at the
    baseline's own ``required_git_ancestors`` -- commits that
    :func:`verify_git_ancestry` has already proven are ancestors of the
    candidate commit, and that ``verify_self_digest`` has already proven are
    the ones the frozen baseline actually names.

    It is deliberately NOT authenticated against the working tree.  Checking
    live bytes would assert "the materializer at HEAD is whatever produced the
    frozen evidence", which is false as soon as the shared materializer is
    developed further for unrelated work, and which would tempt a future
    maintainer to launder the current hash into the frozen record.  Every
    anchor must agree; a single disagreeing anchor fails closed.

    ``require_tracked`` additionally asserts the materializer path is still
    tracked at HEAD.  That is repository continuity only -- it constrains no
    bytes and forms no part of the historical identity proof.
    """
    anchors = baseline["required_git_ancestors"]
    if not isinstance(anchors, list) or not anchors:
        raise AssertionError("baseline declares no historical Git anchors")
    if tuple(anchors) != (PREREG_SHA, PIT_V1_SHA):
        raise AssertionError(f"baseline Git anchors do not match the verified ancestry set: {anchors}")
    entries = baseline["materializer_files"]
    if not isinstance(entries, list) or not entries:
        raise AssertionError("baseline declares no materializer files")
    authenticated = []
    for item in entries:
        relative_path, expected = item["relative_path"], item["file_sha256"]
        if not _SHA256_HEX.fullmatch(expected):
            raise AssertionError(f"frozen materializer digest is malformed: {relative_path}")
        for anchor in anchors:
            actual = historical_materializer_digest(anchor, relative_path, root)
            if actual != expected:
                raise AssertionError(
                    f"historical materializer identity mismatch: {relative_path} at {anchor} "
                    f"is {actual}, frozen baseline requires {expected}"
                )
        if require_tracked:
            tracked = subprocess.run(["git", "ls-files", "--error-unmatch", relative_path], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if tracked.returncode:
                raise AssertionError(f"materializer is not Git-tracked: {relative_path}")
        authenticated.append({"relative_path": relative_path, "file_sha256": expected, "anchors": list(anchors)})
    return authenticated


def verify_evidence_entry(item: dict, root: Path = ROOT, require_tracked: bool = True) -> None:
    path = root / item["relative_path"]
    if not path.is_file() or file_digest(path) != item["sha256"] or path.stat().st_size != item["size_bytes"]:
        raise AssertionError(f"evidence byte mismatch: {item['relative_path']}")
    if require_tracked:
        tracked = subprocess.run(["git", "ls-files", "--error-unmatch", item["relative_path"]], cwd=root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if tracked.returncode:
            raise AssertionError(f"evidence is not Git-tracked: {item['relative_path']}")


def verify_baseline() -> dict:
    baseline = _load("provenance_baseline_v0.json")
    verify_self_digest(baseline, "provenance_baseline_digest")
    contract = _load("execution_git_provenance_contract_v0.json")
    coverage = _load("funding_history_coverage_v0.json")
    verify_self_digest(contract, "execution_git_provenance_contract_digest")
    verify_self_digest(coverage, "funding_history_coverage_digest")
    if baseline["funding_history_coverage_digest"] != coverage["funding_history_coverage_digest"]:
        raise AssertionError("funding coverage binding mismatch")
    if baseline["execution_git_provenance_contract_digest"] != contract["execution_git_provenance_contract_digest"]:
        raise AssertionError("Git contract binding mismatch")
    if baseline["exact_ordered_panel"] != PANEL or baseline["outcome_accessed"] is not False:
        raise AssertionError("baseline scientific binding mismatch")
    prereg = _load("../jigsaw_funding_pressure_volatility_v0/preregistration.json")
    if prereg["contract_digest"] != CONTRACT_DIGEST or canonical_digest(_without(prereg, "contract_digest")) != CONTRACT_DIGEST:
        raise AssertionError("contract identity mismatch")
    certificate = _load("pit_coverage_certificate_v1.json")
    if certificate["pit_coverage_certificate_v1_digest"] != PIT_V1_DIGEST or canonical_digest(_without(certificate, "pit_coverage_certificate_v1_digest")) != PIT_V1_DIGEST:
        raise AssertionError("PIT V1 certificate identity mismatch")
    if certificate["ohlcv_evidence_set_digest_v1"] != OHLCV_DIGEST:
        raise AssertionError("OHLCV evidence identity mismatch")
    extension = _load("pit_coverage_evidence_v1/extension_manifest.json")
    if certificate["extension_manifest_digest"] != canonical_digest(extension):
        raise AssertionError("PIT V1 extension manifest identity mismatch")
    if certificate["extension_row_artifact_sha256"] != "sha256:" + file_digest(EXPERIMENT / "pit_coverage_evidence_v1/source_bar_extension.csv"):
        raise AssertionError("PIT V1 extension row identity mismatch")
    if _load("materialization_index.json")["evidence_set_digest"] != FUNDING_DIGEST:
        raise AssertionError("funding evidence identity mismatch")
    candidate_commit = baseline["candidate_commit"] or subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    verify_git_ancestry(candidate_commit)
    for item in baseline["evidence_files"]:
        verify_evidence_entry(item)
    materializers = verify_historical_materializer_identity(baseline)
    actual_coverage = compute_funding_coverage()
    if actual_coverage != _without(coverage, "funding_history_coverage_digest"):
        raise AssertionError("funding history coverage does not match recomputation")
    return {"evidence_files": len(baseline["evidence_files"]), "pressure_days": coverage["pressure_day_count"], "symbol_days_missing": coverage["missing_count"], "historical_materializers": len(materializers)}


if __name__ == "__main__":
    print(json.dumps(verify_baseline(), sort_keys=True))
