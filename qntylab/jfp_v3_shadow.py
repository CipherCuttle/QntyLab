"""Armed-but-inactive collector for the frozen JFPV3_01 experiment.

This module records source observations and per-origin scientific inputs only.
It has deliberately no terminal inference, result aggregation, or activation
side effect. Network clients are injectable; tests use local fixtures.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import subprocess
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any, Iterable, Mapping, Protocol

ROOT = Path(__file__).resolve().parents[1]
V3_DIR = ROOT / "experiments" / "research" / "jigsaw_fast_prospective_signal_discovery_v3"
PR_A_COMMIT = "d11f3d1b1e47439533e62efc2926b0da5b0efcba"
PR_A_CANONICAL_MERGE = "20e707adf51cc1ab620dc8d4ca6b07b6c4a7964d"
PR_B_V0_CLOSURE = "5fde5d670a84ea7a60a4d0109c7da7db0f858d07"
PR_B_V0_CANONICAL_MERGE = "0dd0eacaea5abbedf086a1fb95de5134f7789e1d"
R1_IMPLEMENTATION_MANIFEST = "experiments/research/jigsaw_fast_prospective_signal_discovery_v3/collector_v0r1/implementation_manifest.json"
R2_IMPLEMENTATION_MANIFEST = "experiments/research/jigsaw_fast_prospective_signal_discovery_v3/collector_v0r2/implementation_manifest.json"
GENERATION_ID = "JFPV3_01"
CANDIDATE_ID = "JFPV3_01"
N_MIN = 15
LISTING_AGE = timedelta(days=30)
EXPECTED_ARTIFACTS = (
    "lineage.json", "preregistration.json", "universe_contract.json",
    "source_contract.json", "scientific_contract.json", "schedule_contract.json",
    "result_schema.json", "artifact_manifest.json",
)
HEX64 = set("0123456789abcdef")
HEX40 = set("0123456789abcdef")


class ContractError(ValueError):
    """A fail-closed contract or evidence error."""


class SourceTransport(Protocol):
    def metadata(self) -> tuple[bytes, str, str]: ...
    def bars(self, symbol: str, start: datetime, end: datetime) -> tuple[bytes, str, list[dict[str, Any]]]: ...


class BinanceUmTransport:
    """Injectable Binance transport; production callers must provide the client.

    No client is constructed or called by this module's CLI or tests.
    """

    METADATA_ENDPOINT = "https://fapi.binance.com/fapi/v1/exchangeInfo"
    OHLCV_ENDPOINT = "https://fapi.binance.com/fapi/v1/klines"

    def __init__(self, requester):
        self.requester = requester

    def metadata(self) -> tuple[bytes, str, str]:
        raw = self.requester("GET", self.METADATA_ENDPOINT, {})
        payload = json.loads(raw)
        return raw, "binance-futures-exchangeInfo", "binance-rest-v0"

    def bars(self, symbol: str, start: datetime, end: datetime) -> tuple[bytes, str, list[dict[str, Any]]]:
        symbol = _validate_symbol(symbol); start, end = ensure_utc(start), ensure_utc(end)
        raw = self.requester("GET", self.OHLCV_ENDPOINT, {"symbol": symbol, "interval": "1h", "startTime": int(start.timestamp() * 1000), "endTime": int(end.timestamp() * 1000)})
        rows = json.loads(raw)
        bars = [{"symbol": symbol, "close_time": stamp(datetime.fromtimestamp((int(row[0]) + 3_600_000) / 1000, UTC)), "close": row[4], "interval": "1h", "source_id": "binance-futures-klines", "raw_digest": bytes_digest(raw)} for row in rows]
        return raw, "binance-futures-klines", bars


class UrllibRequester:
    """Minimal official-source requester, constructed only by the CLI runner."""

    def __call__(self, method: str, endpoint: str, params: Mapping[str, Any]) -> bytes:
        query = urllib.parse.urlencode(params)
        url = f"{endpoint}?{query}" if query else endpoint
        request = urllib.request.Request(url, method=method)
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.read()


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode()


def digest(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def bytes_digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def stamp(value: datetime) -> str:
    value = ensure_utc(value)
    return value.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_stamp(value: str) -> datetime:
    try:
        return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except (TypeError, ValueError) as exc:
        raise ContractError(f"invalid UTC timestamp: {value!r}") from exc


def ensure_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ContractError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


def load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"cannot load contract artifact: {path}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"contract artifact must be an object: {path}")
    return value


def git_sha(repo_root: Path) -> str:
    try:
        return subprocess.check_output(("git", "rev-parse", "HEAD"), cwd=repo_root, text=True).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ContractError("cannot establish repository commit") from exc


def _git(repo_root: Path, *args: str, check: bool = True) -> str:
    try:
        return subprocess.check_output(("git", *args), cwd=repo_root, text=True, stderr=subprocess.PIPE).strip()
    except (OSError, subprocess.CalledProcessError) as exc:
        if check:
            raise ContractError(f"git operation failed: {' '.join(args)}") from exc
        return ""


def is_ancestor(repo_root: Path, ancestor: str, descendant: str) -> bool:
    try:
        subprocess.check_call(("git", "merge-base", "--is-ancestor", ancestor, descendant), cwd=repo_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def resolve_runtime_canonical_state(repo_root: Path = ROOT, *, refresh: bool = True) -> dict[str, Any]:
    """Resolve current canonicality from a fresh remote reconciliation."""
    if refresh:
        try:
            subprocess.check_call(("git", "fetch", "origin", "--prune"), cwd=repo_root, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise ContractError("fresh origin/master reconciliation failed") from exc
    head_sha = _git(repo_root, "rev-parse", "HEAD")
    origin_master_sha = _git(repo_root, "rev-parse", "origin/master")
    dirty = bool(_git(repo_root, "status", "--porcelain"))
    anchors = {"pr_a_commit": PR_A_COMMIT, "pr_a_canonical_merge": PR_A_CANONICAL_MERGE, "pr_b_v0_closure": PR_B_V0_CLOSURE, "pr_b_v0_canonical_merge": PR_B_V0_CANONICAL_MERGE}
    lineage = {name: is_ancestor(repo_root, anchor, head_sha) for name, anchor in anchors.items()}
    return {"head_sha": head_sha, "origin_master_sha": origin_master_sha, "worktree_clean": not dirty, "lineage": lineage, "fresh_remote_reconciliation": refresh, "canonical": head_sha == origin_master_sha and not dirty and all(lineage.values())}


def bind_pr_a(repo_root: Path = ROOT, *, current_sha: str | None = None) -> dict[str, Any]:
    """Verify the merged PR-A artifacts against its immutable manifest."""
    current_sha = current_sha or git_sha(repo_root)
    if not is_ancestor(repo_root, PR_A_COMMIT, current_sha) or not is_ancestor(repo_root, PR_A_CANONICAL_MERGE, current_sha):
        raise ContractError("PR-A immutable lineage is not ancestral to current canonical HEAD")
    try:
        subprocess.check_call(("git", "cat-file", "-e", f"{PR_A_COMMIT}^{{commit}}"), cwd=repo_root, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise ContractError("PR-A commit is not present in repository history") from exc
    values = {name: load_json(repo_root / "experiments/research/jigsaw_fast_prospective_signal_discovery_v3" / name) for name in EXPECTED_ARTIFACTS}
    manifest = values["artifact_manifest.json"]
    for name, expected in manifest.get("artifacts", {}).items():
        path = repo_root / "experiments/research/jigsaw_fast_prospective_signal_discovery_v3" / name
        if not path.is_file() or bytes_digest(path.read_bytes()) != expected:
            raise ContractError(f"PR-A artifact manifest mismatch: {name}")
    prereg = values["preregistration.json"]
    if prereg.get("generation_id") != GENERATION_ID or prereg.get("candidate_id") != CANDIDATE_ID:
        raise ContractError("PR-A generation binding mismatch")
    return {"current_head": current_sha, "pr_a_commit": PR_A_COMMIT, "pr_a_canonical_merge": PR_A_CANONICAL_MERGE, "generation_id": GENERATION_ID, "candidate_id": CANDIDATE_ID, "artifact_digests": dict(manifest["artifacts"]), "source_contract_id": "JFPV3_SOURCE_CONTRACT", "universe_contract_id": "JFPV3_PIT_ELIGIBILITY_V0", "scientific_contract_id": "JFPV3_SCIENTIFIC_CONTRACT", "schedule_contract_id": "JFPV3_SCHEDULE_CONTRACT", "result_schema_digest": manifest["artifacts"]["result_schema.json"]}


def implementation_identity(repo_root: Path = ROOT, manifest_path: str = R2_IMPLEMENTATION_MANIFEST) -> dict[str, Any]:
    """Verify the active implementation bytes against the frozen content manifest."""
    path = repo_root / manifest_path
    manifest = load_json(path)
    for relative, expected in manifest.get("files", {}).items():
        actual_path = repo_root / relative if not relative.startswith("collector_v0") else repo_root / "experiments/research/jigsaw_fast_prospective_signal_discovery_v3" / relative
        if not actual_path.is_file() or bytes_digest(actual_path.read_bytes()) != expected:
            raise ContractError(f"repaired implementation content mismatch: {relative}")
    return {"implementation_digest": manifest.get("implementation_digest"), "candidate_commit_sha": manifest.get("candidate_commit_sha"), "manifest_digest": bytes_digest(path.read_bytes()), "manifest_path": manifest_path}


def _validate_symbol(symbol: str) -> str:
    if not isinstance(symbol, str) or not symbol or symbol != symbol.upper() or not symbol.isalnum():
        raise ContractError(f"ambiguous symbol: {symbol!r}")
    return symbol


def normalize_metadata(raw: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Normalize only structural exchangeInfo fields; never reads returns."""
    rows = raw.get("symbols")
    if not isinstance(rows, list):
        raise ContractError("metadata symbols must be a list")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in rows:
        if not isinstance(row, Mapping):
            raise ContractError("metadata symbol record must be an object")
        symbol = _validate_symbol(row.get("symbol"))
        if symbol in seen:
            raise ContractError("duplicate symbol in metadata")
        seen.add(symbol)
        try:
            onboard = int(row["onboardDate"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ContractError(f"invalid onboardDate for {symbol}") from exc
        normalized.append({"symbol": symbol, "venue": row.get("venue", "Binance"), "market_type": row.get("market_type", "USD-M perpetual"), "contract_type": row.get("contractType"), "quote_asset": row.get("quoteAsset"), "status": row.get("status"), "onboardDate": onboard})
    return sorted(normalized, key=lambda row: row["symbol"])


def resolve_universe(metadata: Mapping[str, Any], *, origin: datetime, observed_at: datetime, source_id: str, transport_id: str, raw_metadata_digest: str | None = None) -> dict[str, Any]:
    origin, observed_at = ensure_utc(origin), ensure_utc(observed_at)
    if observed_at > origin:
        raise ContractError("PIT_VIOLATION: metadata observed after origin")
    normalized = normalize_metadata(metadata)
    cutoff_ms = int((origin - LISTING_AGE).timestamp() * 1000)
    eligible: list[str] = []
    excluded: list[dict[str, str]] = []
    for row in normalized:
        reason = None
        if row["venue"] != "Binance" or row["market_type"] != "USD-M perpetual" or row["contract_type"] != "PERPETUAL" or row["quote_asset"] != "USDT": reason = "CONTRACT_IDENTITY_AMBIGUOUS"
        elif row["status"] != "TRADING": reason = "STATUS_NOT_TRADING"
        elif row["onboardDate"] > cutoff_ms: reason = "LISTING_AGE_BELOW_30_DAYS"
        if reason: excluded.append({"symbol": row["symbol"], "reason": reason})
        else: eligible.append(row["symbol"])
    ordered = tuple(sorted(eligible))
    return {"origin_timestamp": stamp(origin), "metadata_source_id": source_id, "metadata_transport_id": transport_id, "metadata_observed_at": stamp(observed_at), "raw_metadata_digest": raw_metadata_digest or bytes_digest(canonical_bytes(metadata)), "normalized_metadata_digest": digest(normalized), "normalizer_version": "JFPV3_METADATA_NORMALIZER_V0", "eligible_symbol_records": [row for row in normalized if row["symbol"] in ordered], "excluded_symbol_records": excluded, "ordered_U_t": list(ordered), "N_t": len(ordered), "universe_digest": digest(list(ordered)), "sealed_at": None}


def schedule(activation_timestamp: datetime, count: int = 365) -> list[datetime]:
    activation_timestamp = ensure_utc(activation_timestamp)
    if count != 365:
        raise ContractError("schedule count is frozen at 365")
    first_allowed = activation_timestamp + timedelta(hours=24)
    first_date = first_allowed.date() if first_allowed.time() == time(0) else first_allowed.date() + timedelta(days=1)
    first = datetime.combine(first_date, time(0), tzinfo=UTC)
    return [first + timedelta(days=index) for index in range(count)]


def validate_activation(record: Mapping[str, Any], *, current_sha: str, origin_master_sha: str | None = None, dirty: bool = False, binding: Mapping[str, Any] | None = None, expected_implementation_sha: str | None = None, lineage: Mapping[str, bool] | None = None) -> None:
    required = ("activation_master_sha", "collector_implementation_sha", "preregistration_digest", "universe_contract_digest", "source_contract_digest", "scientific_contract_digest", "schedule_contract_digest", "activation_timestamp", "shadow_run_id")
    if any(key not in record for key in required): raise ContractError("activation record incomplete")
    if not origin_master_sha or dirty or current_sha != origin_master_sha or record["activation_master_sha"] != current_sha: raise ContractError("activation requires clean current canonical master")
    if lineage is not None and not all(lineage.values()): raise ContractError("activation immutable lineage is not ancestral")
    if len(current_sha) != 40 or any(character not in HEX40 for character in current_sha.lower()): raise ContractError("invalid activation master SHA")
    for field in ("collector_implementation_sha", "preregistration_digest", "universe_contract_digest", "source_contract_digest", "scientific_contract_digest", "schedule_contract_digest"):
        value = record[field]
        if not isinstance(value, str) or len(value) != 64 or any(character not in HEX64 for character in value.lower()):
            raise ContractError(f"invalid activation identity: {field}")
    if expected_implementation_sha is not None and record["collector_implementation_sha"] != expected_implementation_sha: raise ContractError("activation implementation identity mismatch")
    if binding is not None:
        for field, key in (("preregistration_digest", "preregistration.json"), ("universe_contract_digest", "universe_contract.json"), ("source_contract_digest", "source_contract.json"), ("scientific_contract_digest", "scientific_contract.json"), ("schedule_contract_digest", "schedule_contract.json")):
            if record[field] != binding["artifact_digests"][key]: raise ContractError(f"activation contract mismatch: {field}")
    if not isinstance(record["shadow_run_id"], str) or not record["shadow_run_id"]: raise ContractError("shadow_run_id required")
    parse_stamp(record["activation_timestamp"])


class ReceiptLedger:
    """Append-only JSONL event chain with deterministic replay and mutation detection."""
    def __init__(self, path: Path):
        self.path = path

    def _events(self, event_type: str | None = None) -> list[dict[str, Any]]:
        if not self.path.exists(): return []
        events = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line: continue
            try: events.append(json.loads(line))
            except json.JSONDecodeError as exc: raise ContractError("receipt log is not valid JSONL") from exc
        return [event for event in events if event_type is None or event.get("event_type") == event_type]

    def verify(self) -> dict[str, Any]:
        previous = "GENESIS"
        events = self._events()
        by_id: set[str] = set()
        for index, event in enumerate(events):
            if event.get("sequence") != index or event.get("previous_event_digest") != previous: raise ContractError("receipt chain mismatch")
            event_id = event.get("event_id")
            if not isinstance(event_id, str) or event_id in by_id: raise ContractError("duplicate receipt event")
            body = {key: value for key, value in event.items() if key != "event_digest"}
            if event.get("event_digest") != digest(body): raise ContractError("receipt mutation detected")
            by_id.add(event_id); previous = event["event_digest"]
        return {"event_count": len(events), "head_digest": previous, "integrity": "PASS"}

    def append(self, event_id: str, event_type: str, payload: Mapping[str, Any]) -> dict[str, Any]:
        events = self._events(); self.verify()
        for event in events:
            if event["event_id"] == event_id:
                if event["event_type"] == event_type and event["payload"] == payload: return event
                raise ContractError("duplicate event id with different payload")
        body = {"sequence": len(events), "event_id": event_id, "event_type": event_type, "previous_event_digest": events[-1]["event_digest"] if events else "GENESIS", "payload": dict(payload)}
        event = {**body, "event_digest": digest(body)}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(canonical_bytes(event).decode() + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        return event


def schedule_digest(origins: Iterable[datetime], *, activation_timestamp: datetime | None = None) -> str:
    """Digest the exact frozen 365-midnight UTC schedule."""
    values = [ensure_utc(origin) for origin in origins]
    if len(values) != 365 or values != sorted(values):
        raise ContractError("schedule must contain exactly 365 ordered origins")
    if any(value.time() != time(0) for value in values):
        raise ContractError("schedule origins must be at 00:00:00Z")
    if any(current - previous != timedelta(days=1) for previous, current in zip(values, values[1:])):
        raise ContractError("schedule spacing is not 24h")
    if activation_timestamp is not None and values[0] < ensure_utc(activation_timestamp) + timedelta(hours=24):
        raise ContractError("schedule starts before the 24-hour activation boundary")
    return digest([stamp(value) for value in values])


ACTIVATION_PAYLOAD_FIELDS = {
    "schedule_digest", "first_origin", "last_origin", "scheduled_origin_count", "activation_record_digest",
}


class ActivationManager:
    """Durable preparation, exact schedule persistence, and one commit point."""

    def __init__(self, ledger: ReceiptLedger):
        self.ledger = ledger

    def _events(self, event_type: str | None = None) -> list[dict[str, Any]]:
        events = self.ledger._events()
        return [event for event in events if event_type is None or event.get("event_type") == event_type]

    def _prepared(self) -> dict[str, Any] | None:
        events = self._events("ACTIVATION_PREPARED")
        if len(events) > 1:
            raise ContractError("duplicate activation preparation")
        return events[0] if events else None

    def _committed(self) -> dict[str, Any] | None:
        events = self._events("SHADOW_ACTIVATED")
        if len(events) > 1:
            raise ContractError("second activation commit")
        return events[0] if events else None

    @staticmethod
    def _record_from_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
        return {key: value for key, value in payload.items() if key not in ACTIVATION_PAYLOAD_FIELDS}

    @staticmethod
    def _expected_schedule_payload(prepared: Mapping[str, Any], index: int) -> dict[str, Any]:
        payload = prepared["payload"]
        return {
            "origin_index": index,
            "origin_id": f"origin-{index:03d}",
            "origin_timestamp": stamp(parse_stamp(payload["first_origin"]) + timedelta(days=index)),
            "shadow_run_id": payload["shadow_run_id"],
            "activation_record_digest": payload["activation_record_digest"],
            "schedule_digest": payload["schedule_digest"],
        }

    def _validate_prepared_payload(self, prepared: Mapping[str, Any]) -> None:
        payload = prepared["payload"]
        record = self._record_from_payload(payload)
        if payload.get("activation_record_digest") != digest(record):
            raise ContractError("activation identity mutation")
        origins = schedule(parse_stamp(payload["activation_timestamp"]))
        expected_digest = schedule_digest(origins, activation_timestamp=parse_stamp(payload["activation_timestamp"]))
        if payload.get("schedule_digest") != expected_digest:
            raise ContractError("schedule digest mutation")
        if payload.get("first_origin") != stamp(origins[0]) or payload.get("last_origin") != stamp(origins[-1]) or payload.get("scheduled_origin_count") != 365:
            raise ContractError("activation schedule metadata mutation")

    def prepare(self, activation_record: Mapping[str, Any], origins: Iterable[datetime]) -> dict[str, Any]:
        record = dict(activation_record)
        validate_activation(record, current_sha=record.get("activation_master_sha", ""), origin_master_sha=record.get("activation_master_sha"))
        values = [ensure_utc(origin) for origin in origins]
        schedule_hash = schedule_digest(values, activation_timestamp=parse_stamp(record["activation_timestamp"]))
        ordered = [stamp(value) for value in values]
        payload = {
            **record,
            "schedule_digest": schedule_hash,
            "first_origin": ordered[0],
            "last_origin": ordered[-1],
            "scheduled_origin_count": len(ordered),
            "activation_record_digest": digest(record),
        }
        prepared = self._prepared()
        committed = self._committed()
        if prepared:
            self._validate_prepared_payload(prepared)
        if committed:
            self.summary()
            if not prepared or committed["payload"].get("activation_record_digest") != payload["activation_record_digest"] or committed["payload"].get("schedule_digest") != payload["schedule_digest"]:
                raise ContractError("conflicting activation after commit")
            return committed
        if prepared:
            if prepared["payload"] != payload:
                raise ContractError("conflicting activation preparation")
            return prepared
        if self._events("ORIGIN_SCHEDULED"):
            raise ContractError("orphan scheduled origin")
        return self.ledger.append(f"activation-prepared-{record['shadow_run_id']}", "ACTIVATION_PREPARED", payload)

    def persist_schedule(self, *, limit: int | None = None) -> int:
        prepared = self._prepared()
        if not prepared:
            raise ContractError("schedule requires activation preparation")
        self._validate_prepared_payload(prepared)
        if limit is not None and (not isinstance(limit, int) or isinstance(limit, bool) or not 0 <= limit <= 365):
            raise ContractError("invalid schedule persistence limit")
        scheduled = self._events("ORIGIN_SCHEDULED")
        existing: dict[int, dict[str, Any]] = {}
        for event in scheduled:
            payload = event["payload"]
            index = payload.get("origin_index")
            if not isinstance(index, int) or isinstance(index, bool) or index in existing or not 0 <= index < 365:
                raise ContractError("duplicate or orphan scheduled origin")
            expected = self._expected_schedule_payload(prepared, index)
            if event["event_id"] != f"{prepared['payload']['shadow_run_id']}-origin-{index:03d}" or payload != expected:
                raise ContractError("schedule mutation or conflicting replay")
            existing[index] = event
        target = 365 if limit is None else limit
        for index in range(target):
            if index not in existing:
                expected = self._expected_schedule_payload(prepared, index)
                self.ledger.append(f"{prepared['payload']['shadow_run_id']}-origin-{index:03d}", "ORIGIN_SCHEDULED", expected)
        return len(self._events("ORIGIN_SCHEDULED"))

    def commit(self) -> dict[str, Any]:
        prepared = self._prepared()
        if not prepared:
            raise ContractError("cannot commit without preparation")
        self._validate_prepared_payload(prepared)
        committed = self._committed()
        if committed:
            self.summary()
            if committed["payload"].get("activation_record_digest") != prepared["payload"].get("activation_record_digest"):
                raise ContractError("conflicting activation commit")
            return committed
        if self.persist_schedule() != 365:
            raise ContractError("partial activation cannot commit")
        rows = self._events("ORIGIN_SCHEDULED")
        if len(rows) != 365:
            raise ContractError("activation schedule is incomplete")
        expected = {index: self._expected_schedule_payload(prepared, index) for index in range(365)}
        actual = {event["payload"]["origin_index"]: event["payload"] for event in rows}
        if actual != expected:
            raise ContractError("activation schedule integrity failure")
        payload = {**prepared["payload"], "activation_state": "ACTIVATED_READY_FOR_FIRST_ORIGIN"}
        return self.ledger.append(f"activation-committed-{prepared['payload']['shadow_run_id']}", "SHADOW_ACTIVATED", payload)

    def summary(self) -> dict[str, Any]:
        self.ledger.verify()
        prepared = self._prepared()
        committed = self._committed()
        rows = self._events("ORIGIN_SCHEDULED")
        if not prepared and rows:
            raise ContractError("orphan scheduled origin")
        if prepared:
            self._validate_prepared_payload(prepared)
            self.persist_schedule(limit=0)
            expected = {index: self._expected_schedule_payload(prepared, index) for index in range(365)}
            actual = {event["payload"].get("origin_index"): event["payload"] for event in rows}
            if len(actual) != len(rows) or any(index not in expected for index in actual) or any(actual[index] != expected[index] for index in actual):
                raise ContractError("schedule payload integrity failure")
        if committed:
            if not prepared or len(rows) != 365 or committed["payload"] != {**prepared["payload"], "activation_state": "ACTIVATED_READY_FOR_FIRST_ORIGIN"}:
                raise ContractError("committed activation has incomplete or mutated evidence")
            state = "ACTIVATED_READY_FOR_FIRST_ORIGIN"
        elif prepared:
            state = "ACTIVATION_INCOMPLETE"
        else:
            state = "ARMED_BUT_INACTIVE"
        return {
            "activation_state": state,
            "activation_count": len(self._events("SHADOW_ACTIVATED")),
            "prepared": prepared["payload"] if prepared else None,
            "committed": committed["payload"] if committed else None,
            "scheduled_count": len(rows),
        }


def activate_shadow(
    ledger: ReceiptLedger,
    activation_record: Mapping[str, Any],
    origins: Iterable[datetime],
    *,
    canonical_state: Mapping[str, Any] | None = None,
    binding: Mapping[str, Any] | None = None,
    expected_implementation_sha: str | None = None,
) -> dict[str, Any]:
    if canonical_state is not None:
        validate_activation(
            activation_record,
            current_sha=canonical_state.get("head_sha", ""),
            origin_master_sha=canonical_state.get("origin_master_sha"),
            dirty=not canonical_state.get("worktree_clean", False),
            binding=binding,
            expected_implementation_sha=expected_implementation_sha,
            lineage=canonical_state.get("lineage"),
        )
    manager = ActivationManager(ledger)
    manager.prepare(activation_record, origins)
    manager.commit()
    return status(ledger)


def activate_shadow_runtime(ledger: ReceiptLedger, *, repo_root: Path = ROOT, now: datetime | None = None) -> dict[str, Any]:
    """Guarded future activation operation; never called by tests or import."""
    state = resolve_runtime_canonical_state(repo_root, refresh=True)
    if not state["canonical"]:
        raise ContractError("activation requires fresh clean canonical master")
    binding = bind_pr_a(repo_root, current_sha=state["head_sha"])
    identity = implementation_identity(repo_root)
    activation_time = ensure_utc(now or datetime.now(UTC))
    record = {
        "activation_master_sha": state["head_sha"],
        "collector_implementation_sha": identity["implementation_digest"],
        "preregistration_digest": binding["artifact_digests"]["preregistration.json"],
        "universe_contract_digest": binding["artifact_digests"]["universe_contract.json"],
        "source_contract_digest": binding["artifact_digests"]["source_contract.json"],
        "scientific_contract_digest": binding["artifact_digests"]["scientific_contract.json"],
        "schedule_contract_digest": binding["artifact_digests"]["schedule_contract.json"],
        "activation_timestamp": stamp(activation_time),
        "shadow_run_id": f"{GENERATION_ID}-{activation_time.strftime('%Y%m%dT%H%M%SZ')}-{state['head_sha'][:12]}",
    }
    return activate_shadow(ledger, record, schedule(activation_time), canonical_state=state, binding=binding, expected_implementation_sha=identity["implementation_digest"])


def due_origin_ids(ledger: ReceiptLedger, *, now: datetime) -> list[str]:
    """Return due members of the one committed schedule, never early."""
    now = ensure_utc(now)
    authority = ActivationManager(ledger).summary()
    if authority["activation_state"] != "ACTIVATED_READY_FOR_FIRST_ORIGIN":
        raise ContractError("due-origin execution requires committed activation")
    terminal = {
        event["payload"].get("origin_id")
        for event in ledger._events()
        if event["event_type"] in {"ORIGIN_BLOCKED", "ORIGIN_ELIGIBLE"}
    }
    result = []
    for event in ledger._events("ORIGIN_SCHEDULED"):
        payload = event["payload"]
        origin = parse_stamp(payload["origin_timestamp"])
        feature_sealed = any(item["event_type"] == "FEATURE_SEALED" and item["payload"].get("origin_id") == payload["origin_id"] for item in ledger._events())
        if payload["origin_id"] not in terminal and origin <= now and not (feature_sealed and now < origin + timedelta(hours=24)):
            result.append(payload["origin_id"])
    return result


def collect_due(collector: "Collector", transport: SourceTransport, *, now: datetime) -> list[str]:
    """Collect only due origins through the injected official-source capability."""
    now = ensure_utc(now)
    completed: list[str] = []
    for origin_id in due_origin_ids(collector.ledger, now=now):
        scheduled = next(event["payload"] for event in collector.ledger._events("ORIGIN_SCHEDULED") if event["payload"]["origin_id"] == origin_id)
        origin = parse_stamp(scheduled["origin_timestamp"])
        metadata_event = next((event for event in collector.ledger._events() if event["event_type"] == "METADATA_SEALED" and event["payload"].get("origin_id") == origin_id), None)
        if metadata_event is None:
            raw_metadata, source_id, transport_id = transport.metadata()
            metadata = json.loads(raw_metadata)
            event = collector.seal_metadata(origin_id, origin, metadata, raw_metadata=raw_metadata, observed_at=origin, source_id=source_id, transport_id=transport_id, now=now)
            if event["event_type"] != "METADATA_SEALED":
                continue
            metadata_event = event
        symbols = tuple(metadata_event["payload"]["ordered_U_t"])
        feature_event = next((event for event in collector.ledger._events() if event["event_type"] == "FEATURE_SEALED" and event["payload"].get("origin_id") == origin_id), None)
        if feature_event is None:
            bars: list[dict[str, Any]] = []
            for symbol in symbols:
                _raw, _source_id, symbol_bars = transport.bars(symbol, origin - timedelta(hours=24), origin)
                bars.extend(symbol_bars)
            inputs = collector._latest(origin_id)
            if inputs is None or inputs["event_type"] != "FEATURE_INPUTS_SEALED":
                inputs = collector.seal_feature_inputs(origin_id, bars, source_capability_id="BINANCE_USDM_1H_KLINES", source_id="binance-futures-klines", acquired_at=now, now=now)
                if inputs["event_type"] != "FEATURE_INPUTS_SEALED":
                    continue
            feature_event = collector.seal_feature(origin_id, bars, now=now)
        if now >= origin + timedelta(hours=24) and feature_event["event_type"] == "FEATURE_SEALED":
            outcome_bars: list[dict[str, Any]] = []
            for symbol in symbols:
                _raw, _source_id, symbol_bars = transport.bars(symbol, origin, origin + timedelta(hours=24))
                outcome_bars.extend(symbol_bars)
            collector.mature_outcome(origin_id, outcome_bars, source_capability_id="BINANCE_USDM_1H_KLINES", source_id="binance-futures-klines", now=now)
        completed.append(origin_id)
    return completed


def _bar_map(bars: Iterable[Mapping[str, Any]], symbols: Iterable[str]) -> dict[tuple[str, str], Mapping[str, Any]]:
    result: dict[tuple[str, str], Mapping[str, Any]] = {}
    allowed = set(symbols)
    for bar in bars:
        symbol = _validate_symbol(bar.get("symbol")); when = parse_stamp(bar.get("close_time"))
        if symbol not in allowed or (symbol, stamp(when)) in result: raise ContractError("FEATURE_BAR_INTEGRITY_FAILURE")
        if bar.get("interval") != "1h" or bar.get("source_id") is None: raise ContractError("SOURCE_IDENTITY_MISMATCH")
        result[(symbol, stamp(when))] = bar
    return result


def _prices(bar_map: Mapping[tuple[str, str], Mapping[str, Any]], symbols: tuple[str, ...], closes: list[datetime]) -> dict[str, list[float]]:
    values: dict[str, list[float]] = {}
    for symbol in symbols:
        try: values[symbol] = [float(bar_map[(symbol, stamp(when))]["close"]) for when in closes]
        except (KeyError, TypeError, ValueError) as exc: raise ContractError("FEATURE_WINDOW_INCOMPLETE") from exc
        if any(value <= 0 for value in values[symbol]): raise ContractError("FEATURE_BAR_INTEGRITY_FAILURE")
    return values


def feature_values(prior_bars: Iterable[Mapping[str, Any]], symbols: Iterable[str], origin: datetime) -> tuple[float, float, int]:
    """Compute only the frozen origin-level feature/baseline from supplied bars."""
    origin = ensure_utc(origin); ordered = tuple(symbols)
    if tuple(sorted(ordered)) != ordered or len(ordered) < N_MIN: raise ContractError("BLOCKED_UNIVERSE_TOO_SMALL")
    closes = [origin - timedelta(hours=24 - index) for index in range(25)]
    prices = _prices(_bar_map(prior_bars, ordered), ordered, closes)
    squares: list[float] = []; downside = 0.0
    for values in prices.values():
        for prior, current in zip(values, values[1:]):
            ret = math.log(current / prior); square = ret * ret; squares.append(square)
            if ret < 0: downside += square
    denominator = sum(squares)
    if denominator <= 0: raise ContractError("BLOCKED_INVALID_FEATURE_DOMAIN")
    return downside / denominator, denominator ** 0.5, len(ordered)


def future_value(future_bars: Iterable[Mapping[str, Any]], symbols: Iterable[str], origin: datetime, sealed_n: int) -> float:
    ordered = tuple(symbols)
    if sealed_n != len(ordered): raise ContractError("PIT_VIOLATION")
    closes = [ensure_utc(origin) + timedelta(hours=index) for index in range(1, 25)]
    prior_closes = [ensure_utc(origin)]
    bar_map = _bar_map(future_bars, ordered)
    squares: list[float] = []
    for symbol in ordered:
        try: values = [float(bar_map[(symbol, stamp(when))]["close"]) for when in closes]
        except (KeyError, TypeError, ValueError) as exc: raise ContractError("OUTCOME_WINDOW_INCOMPLETE") from exc
        try: previous = float(bar_map[(symbol, stamp(prior_closes[0]))]["close"])
        except (KeyError, TypeError, ValueError) as exc: raise ContractError("OUTCOME_WINDOW_INCOMPLETE") from exc
        for value in values:
            if value <= 0: raise ContractError("OUTCOME_BAR_INTEGRITY_FAILURE")
            ret = math.log(value / previous); squares.append(ret * ret); previous = value
    return sum(squares) ** 0.5


class Collector:
    """Per-origin recorder. It is inert until a caller explicitly supplies data."""

    def __init__(self, ledger: ReceiptLedger, *, binding: Mapping[str, Any] | None = None):
        self.ledger = ledger
        self.binding = dict(binding or {})

    def _events_for(self, origin_id: str) -> list[dict[str, Any]]:
        return [event for event in self.ledger._events() if event["payload"].get("origin_id") == origin_id]

    def _latest(self, origin_id: str) -> dict[str, Any] | None:
        events = self._events_for(origin_id)
        return events[-1] if events else None

    def _require(self, origin_id: str, event_type: str) -> dict[str, Any]:
        authority = ActivationManager(self.ledger).summary()
        if authority["activation_state"] != "ACTIVATED_READY_FOR_FIRST_ORIGIN":
            raise ContractError("collection requires committed activation")
        event = self._latest(origin_id)
        if event is None or event["event_type"] != event_type:
            raise ContractError(f"invalid state transition: expected {event_type}")
        committed = authority["committed"]
        scheduled = next((row["payload"] for row in self.ledger._events("ORIGIN_SCHEDULED") if row["payload"].get("origin_id") == origin_id), None)
        if scheduled is None or scheduled.get("shadow_run_id") != committed.get("shadow_run_id") or scheduled.get("schedule_digest") != committed.get("schedule_digest") or scheduled.get("activation_record_digest") != committed.get("activation_record_digest"):
            raise ContractError("origin is not a member of committed activation")
        return event

    def record_schedule(self, origins: Iterable[datetime], *, activation_record: Mapping[str, Any] | None = None, canonical_state: Mapping[str, Any] | None = None) -> None:
        if activation_record is None or canonical_state is None:
            raise ContractError("schedule recording requires explicit fresh activation state")
        validate_activation(activation_record, current_sha=canonical_state.get("head_sha", ""), origin_master_sha=canonical_state.get("origin_master_sha"), dirty=not canonical_state.get("worktree_clean", False), binding=self.binding or None, expected_implementation_sha=self.binding.get("implementation_digest") if self.binding else None, lineage=canonical_state.get("lineage"))
        origins = list(origins)
        if len(origins) != 365 or origins != sorted(origins): raise ContractError("schedule must contain exactly 365 ordered origins")
        manager = ActivationManager(self.ledger)
        manager.prepare(activation_record, origins)
        manager.commit()

    def seal_metadata(self, origin_id: str, origin: datetime, metadata: Mapping[str, Any], *, raw_metadata: bytes, observed_at: datetime, source_id: str, transport_id: str, now: datetime | None = None) -> dict[str, Any]:
        self._require(origin_id, "ORIGIN_SCHEDULED")
        origin, observed_at = ensure_utc(origin), ensure_utc(observed_at)
        now = ensure_utc(now or datetime.now(UTC))
        if now < origin:
            raise ContractError("origin is not due")
        if observed_at > now:
            raise ContractError("metadata observed after collection time")
        snapshot = resolve_universe(metadata, origin=origin, observed_at=observed_at, source_id=source_id, transport_id=transport_id, raw_metadata_digest=bytes_digest(raw_metadata))
        snapshot["origin_id"] = origin_id; snapshot["sealed_at"] = stamp(now); snapshot["raw_metadata_b64"] = base64.b64encode(raw_metadata).decode("ascii")
        if snapshot["N_t"] < N_MIN:
            return self.ledger.append(f"{origin_id}-blocked-metadata", "ORIGIN_BLOCKED", {"origin_id": origin_id, "origin_timestamp": stamp(origin), "block_reason": "UNIVERSE_TOO_SMALL", "metadata_snapshot": snapshot})
        return self.ledger.append(f"{origin_id}-metadata-sealed", "METADATA_SEALED", snapshot)

    def seal_feature_inputs(self, origin_id: str, bars: Iterable[Mapping[str, Any]], *, source_capability_id: str, source_id: str, acquired_at: datetime, now: datetime | None = None) -> dict[str, Any]:
        metadata_event = self._require(origin_id, "METADATA_SEALED")
        payload = metadata_event["payload"]; symbols = tuple(payload["ordered_U_t"]); origin = parse_stamp(payload["origin_timestamp"])
        now = ensure_utc(now or datetime.now(UTC)); acquired_at = ensure_utc(acquired_at)
        if now < origin: raise ContractError("feature inputs are not yet available")
        if acquired_at > now: raise ContractError("feature inputs acquired after collection time")
        bars = list(bars); bar_map = _bar_map(bars, symbols)
        if any(parse_stamp(bar.get("close_time")) > origin for bar in bars): raise ContractError("PIT_VIOLATION: feature input is after origin")
        required = [(symbol, stamp(when)) for symbol in symbols for when in [origin - timedelta(hours=24 - index) for index in range(25)]]
        if any(key not in bar_map for key in required):
            return self.ledger.append(f"{origin_id}-blocked-feature-inputs", "ORIGIN_BLOCKED", {"origin_id": origin_id, "block_reason": "FEATURE_WINDOW_INCOMPLETE"})
        payload = {"origin_id": origin_id, "origin_timestamp": stamp(origin), "ordered_U_t": list(symbols), "N_t": payload["N_t"], "universe_digest": payload["universe_digest"], "required_prior_bar_identities": [{"symbol": symbol, "close_time": when} for symbol, when in required], "raw_source_digests": sorted({bar["raw_digest"] for bar in bars}), "normalized_bar_digests": sorted(digest(dict(bar)) for bar in bars), "source_capability_id": source_capability_id, "source_id": source_id, "feature_input_sealed_at": stamp(datetime.now(UTC)), "acquired_at": stamp(acquired_at)}
        payload["feature_input_receipt_digest"] = digest(payload)
        return self.ledger.append(f"{origin_id}-feature-inputs-sealed", "FEATURE_INPUTS_SEALED", payload)

    def seal_feature(self, origin_id: str, bars: Iterable[Mapping[str, Any]], *, now: datetime | None = None) -> dict[str, Any]:
        inputs = self._require(origin_id, "FEATURE_INPUTS_SEALED")["payload"]; origin = parse_stamp(inputs["origin_timestamp"])
        if ensure_utc(now or datetime.now(UTC)) < origin: raise ContractError("feature is not yet available")
        feature, baseline, n = feature_values(bars, inputs["ordered_U_t"], origin)
        if n != inputs["N_t"]: raise ContractError("sealed N_t changed")
        payload = {"origin_id": origin_id, "origin_timestamp": stamp(origin), "ordered_U_t": inputs["ordered_U_t"], "universe_digest": inputs["universe_digest"], "N_t": n, "downside_share": feature, "panel_rv24": baseline, "implementation_identity": "qntylab.jfp_v3_shadow:feature_values", "feature_sealed_at": stamp(datetime.now(UTC))}
        payload["feature_receipt_digest"] = digest(payload)
        return self.ledger.append(f"{origin_id}-feature-sealed", "FEATURE_SEALED", payload)

    def mature_outcome(self, origin_id: str, bars: Iterable[Mapping[str, Any]], *, source_capability_id: str, source_id: str, now: datetime | None = None) -> dict[str, Any]:
        feature = self._require(origin_id, "FEATURE_SEALED")["payload"]; origin = parse_stamp(feature["origin_timestamp"]); bars = list(bars)
        now = ensure_utc(now or datetime.now(UTC))
        if now < origin + timedelta(hours=24): raise ContractError("outcome is not mature")
        if any(parse_stamp(bar.get("close_time")) > origin + timedelta(hours=24) for bar in bars): raise ContractError("outcome input exceeds frozen maturity boundary")
        try: value = future_value(bars, feature["ordered_U_t"], origin, feature["N_t"])
        except ContractError as exc:
            if str(exc) == "OUTCOME_WINDOW_INCOMPLETE": return self.ledger.append(f"{origin_id}-blocked-outcome", "ORIGIN_BLOCKED", {"origin_id": origin_id, "block_reason": "OUTCOME_WINDOW_INCOMPLETE"})
            raise
        payload = {"origin_id": origin_id, "origin_timestamp": stamp(origin), "sealed_universe_digest": feature["universe_digest"], "ordered_U_t": feature["ordered_U_t"], "N_t": feature["N_t"], "outcome_bar_source_identities": sorted({bar["source_id"] for bar in bars}), "outcome_input_digest": digest([dict(bar) for bar in bars]), "panel_rv24_future": value, "outcome_matured_at": stamp(datetime.now(UTC)), "source_capability_id": source_capability_id, "source_id": source_id}
        payload["outcome_receipt_digest"] = digest(payload)
        event = self.ledger.append(f"{origin_id}-outcome-matured", "OUTCOME_MATURED", payload)
        return self.ledger.append(f"{origin_id}-eligible", "ORIGIN_ELIGIBLE", {"origin_id": origin_id, "universe_digest": feature["universe_digest"], "feature_receipt_digest": feature["feature_receipt_digest"], "outcome_receipt_digest": payload["outcome_receipt_digest"]}) if event else event


def status(ledger: ReceiptLedger) -> dict[str, Any]:
    events = ledger._events(); counts: dict[str, int] = {}
    blocks: dict[str, int] = {}
    for event in events:
        kind = event["event_type"]; counts[kind] = counts.get(kind, 0) + 1
        reason = event["payload"].get("block_reason")
        if reason: blocks[reason] = blocks.get(reason, 0) + 1
    activation = ActivationManager(ledger).summary()
    identity = activation["committed"] or activation["prepared"] or {}
    scheduled = [event["payload"] for event in events if event["event_type"] == "ORIGIN_SCHEDULED"]
    completed = {event["payload"].get("origin_id") for event in events if event["event_type"] in {"ORIGIN_BLOCKED", "ORIGIN_ELIGIBLE"}}
    next_origin = next((row["origin_timestamp"] for row in scheduled if row.get("origin_id") not in completed), None)
    return {
        "activation_state": activation["activation_state"],
        "activation_count": activation["activation_count"],
        "shadow_run_id": identity.get("shadow_run_id"),
        "activation_timestamp": identity.get("activation_timestamp"),
        "activation_master_sha": identity.get("activation_master_sha"),
        "first_origin": identity.get("first_origin"),
        "last_origin": identity.get("last_origin"),
        "next_origin": next_origin,
        "scheduled_count": counts.get("ORIGIN_SCHEDULED", 0),
        "metadata_sealed_count": counts.get("METADATA_SEALED", 0),
        "feature_sealed_count": counts.get("FEATURE_SEALED", 0),
        "outcome_matured_count": counts.get("OUTCOME_MATURED", 0),
        "eligible_count": counts.get("ORIGIN_ELIGIBLE", 0),
        "blocked_count": sum(blocks.values()),
        "block_reason_counts": blocks,
        "receipt_integrity": ledger.verify()["integrity"],
        "runner_health": "READY" if activation["activation_state"] == "ACTIVATED_READY_FOR_FIRST_ORIGIN" else "INACTIVE",
        "scientific_statistics": "NOT_EXPOSED",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m qntylab.jfp_v3_shadow")
    parser.add_argument("command", choices=("verify-config", "create-schedule", "activate-shadow", "collect-due", "status", "verify-receipts"))
    parser.add_argument("--ledger", type=Path, default=Path("data/jfp_v3_shadow/events.jsonl"))
    args = parser.parse_args(argv)
    if args.command == "verify-config": print(json.dumps(bind_pr_a(), sort_keys=True)); return 0
    ledger = ReceiptLedger(args.ledger)
    if args.command == "status": print(json.dumps(status(ledger), sort_keys=True)); return 0
    if args.command == "verify-receipts": print(json.dumps(ledger.verify(), sort_keys=True)); return 0
    if args.command == "activate-shadow": print(json.dumps(activate_shadow_runtime(ledger), sort_keys=True)); return 0
    if args.command == "collect-due": print(json.dumps(collect_due(Collector(ledger), BinanceUmTransport(UrllibRequester()), now=datetime.now(UTC)), sort_keys=True)); return 0
    raise ContractError("schedule creation is committed as part of activate-shadow")


if __name__ == "__main__":  # pragma: no cover
    main()
