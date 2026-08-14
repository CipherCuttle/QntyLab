"""Fixture-only implementation qualification for the frozen JH01 V1 recorder.

This module has no HTTP client, scheduler, evaluator, or Qnty dependency.  A
future activation artifact is deliberately required before a real V1 origin
can enter the source or forecast path.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from enum import Enum
from hashlib import sha256
import inspect
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any, Mapping, Protocol, Sequence
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from .binance_um_kline_1h import MaterializationError, receipt_from_bytes

from . import jh01_rv_persistence_incremental_forecast_value_prereg_v1 as prereg
from .jh01_v1_bootstrap_source_range_contract_repair_v0 import derive_bootstrap_source_range


PROJECT_ID = "JH01_RV_PERSISTENCE_INCREMENTAL_FORECAST_VALUE_V1_PROSPECTIVE_RECORDER_AND_INPUT_MATERIALIZATION_IMPLEMENTATION_V0"
EXPERIMENT_ID = prereg.EXPERIMENT_ID
CANDIDATE_ID = prereg.CANDIDATE_ID
INTERVAL = "1h"
HORIZON_HOURS = 24
FIRST_LIVE_ORIGIN = datetime(2026, 9, 15, tzinfo=UTC)
LAST_LIVE_ORIGIN = datetime(2027, 9, 14, tzinfo=UTC)


class RecorderBlocked(ValueError):
    """The frozen recorder contract rejects a requested operation."""


class OriginState(str, Enum):
    ORIGIN_PRECHECK = "ORIGIN_PRECHECK"
    SOURCE_MATERIALIZED = "SOURCE_MATERIALIZED"
    FORECAST_COMPUTED = "FORECAST_COMPUTED"
    ARTIFACT_FROZEN = "ARTIFACT_FROZEN"
    PUBLICATION_IN_PROGRESS = "PUBLICATION_IN_PROGRESS"
    PUBLICATION_AUTHORITATIVE = "PUBLICATION_AUTHORITATIVE"
    ATTESTATION_ACQUIRED = "ATTESTATION_ACQUIRED"
    RETENTION_PACKAGE_FROZEN = "RETENTION_PACKAGE_FROZEN"
    OFFLINE_REVERIFIED = "OFFLINE_REVERIFIED"
    ORIGIN_COMPLETE = "ORIGIN_COMPLETE"
    BLOCKED = "BLOCKED"


class UnknownWrite(RuntimeError):
    """The request may have committed remotely; interrogate before retrying."""


@dataclass(frozen=True)
class RemoteRelease:
    origin_id: str
    tag: str
    artifact_digest: str
    asset_name: str
    asset_sha256: str | None
    published_at: datetime | None
    release_id: int | None = None
    repository: str = "CipherCuttle/QntyLab"
    target_commit: str | None = None
    immutable: bool | None = None
    repository_id: str | None = None
    owner_id: str | None = None
    purl: str | None = None
    package_id: str | None = None


@dataclass(frozen=True)
class AttestationExpectation:
    repository: str
    tag: str
    target_commit: str
    asset_name: str
    asset_sha256: str
    predicate_type: str = "https://in-toto.io/attestation/release/v0.2"
    signer_uri: str = "https://dotcom.releases.github.com"
    repository_id: str | None = None
    owner_id: str | None = None
    release_id: str | None = None
    purl: str | None = None
    package_id: str | None = None


@dataclass(frozen=True)
class VerifiedAttestation:
    expectation: AttestationExpectation
    tsa_timestamp: datetime
    bundle: bytes
    trusted_root: bytes


class ReleaseTransport(Protocol):
    def find(self, origin_id: str) -> Sequence[RemoteRelease]: ...
    def create(self, release: RemoteRelease) -> RemoteRelease: ...
    def upload(self, tag: str, asset_name: str, content: bytes) -> RemoteRelease: ...
    def publish(self, release: RemoteRelease) -> RemoteRelease: ...
    def acquire_attestation(self, release: RemoteRelease) -> tuple[bytes, bytes]: ...


class AttestationVerifier(Protocol):
    def verify(self, *, asset: bytes, bundle: bytes, trusted_root: bytes, expectation: AttestationExpectation) -> VerifiedAttestation: ...


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False).encode("utf-8")


def digest(value: Any) -> str:
    return sha256(canonical_bytes(value)).hexdigest()


def _stamp(value: datetime) -> str:
    if value.tzinfo is None:
        raise RecorderBlocked("UTC-aware timestamp required")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _utc(value: str | datetime) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00")) if isinstance(value, str) else value
    if parsed.tzinfo is None:
        raise RecorderBlocked("UTC-aware timestamp required")
    parsed = parsed.astimezone(UTC)
    if parsed.minute or parsed.second or parsed.microsecond:
        raise RecorderBlocked("hour-aligned timestamp required")
    return parsed


def frozen_contract(root: Path) -> dict[str, Any]:
    artifact = prereg.load_preregistration(root)
    prereg.validate(artifact)
    repair = json.loads((root / "experiments/research/jh01_rv_persistence_incremental_forecast_value_v1/bootstrap_source_range_contract_repair_v0.json").read_text())
    if repair["state"] != "CLOSED_PASS" or repair["repair"]["repaired_first_required_source_close"] != "2025-08-15T00:00:00Z":
        raise RecorderBlocked("corrected bootstrap repair unavailable")
    if repair["historical_predecessor"]["historical_first_required_bar_close"] == repair["repair"]["repaired_first_required_source_close"]:
        raise RecorderBlocked("obsolete boundary was not superseded")
    return {"preregistration": artifact, "repair": repair}


def implementation_identity() -> str:
    """Bind artifacts to the actual module source, never a caller-provided SHA."""
    return sha256(Path(inspect.getsourcefile(implementation_identity) or __file__).read_bytes()).hexdigest()


def required_origins() -> tuple[datetime, ...]:
    values = tuple(FIRST_LIVE_ORIGIN + timedelta(days=index) for index in range(365))
    if values[-1] != LAST_LIVE_ORIGIN:
        raise RecorderBlocked("frozen schedule drift")
    return values


def origin_identity(origin: datetime) -> str:
    return digest({"project_id": PROJECT_ID, "candidate_id": CANDIDATE_ID, "v1_preregistration_digest": "bdb85130cae75e9f156db9aa1fd955d7f565a3714ae091871d5ac4447c1ec27b", "forecast_origin_utc": _stamp(origin)})


@dataclass(frozen=True)
class Bar:
    symbol: str
    logical_close: datetime
    close: float
    raw_row: tuple[Any, ...]
    completed: bool = True


def validate_bars(bars: Sequence[Bar], *, panel: Sequence[str], origin: datetime, first_required_close: datetime) -> tuple[Bar, ...]:
    if tuple(panel) != tuple(_frozen_panel()) or len(panel) != 20 or len(set(panel)) != 20:
        raise RecorderBlocked("wrong ordered panel")
    seen: set[tuple[str, datetime]] = set()
    by_symbol: dict[str, list[Bar]] = {symbol: [] for symbol in panel}
    for bar in bars:
        if bar.symbol not in by_symbol or len(bar.raw_row) != 12 or not bar.completed:
            raise RecorderBlocked("malformed, open, or wrong-symbol bar")
        close = _utc(bar.logical_close)
        try:
            open_ms, raw_close, close_ms = int(bar.raw_row[0]), float(bar.raw_row[4]), int(bar.raw_row[6])
        except (TypeError, ValueError) as exc:
            raise RecorderBlocked("malformed Binance 12-field kline") from exc
        if open_ms != int((close - timedelta(hours=1)).timestamp() * 1000) or close_ms != int((close - timedelta(milliseconds=1)).timestamp() * 1000) or not math.isfinite(raw_close) or raw_close != bar.close:
            raise RecorderBlocked("provider timestamp or close does not map to logical close")
        if close > origin:
            raise RecorderBlocked("future source bar")
        if close < first_required_close or not math.isfinite(bar.close) or bar.close <= 0:
            raise RecorderBlocked("invalid source close")
        key = (bar.symbol, close)
        if key in seen:
            raise RecorderBlocked("duplicate logical close")
        seen.add(key); by_symbol[bar.symbol].append(bar)
    for symbol, rows in by_symbol.items():
        if not rows:
            raise RecorderBlocked(f"missing source symbol: {symbol}")
        rows.sort(key=lambda item: item.logical_close)
        if rows[0].logical_close != first_required_close or rows[-1].logical_close != origin:
            raise RecorderBlocked(f"source coverage boundary mismatch: {symbol}")
        if any(right.logical_close - left.logical_close != timedelta(hours=1) for left, right in zip(rows, rows[1:])):
            raise RecorderBlocked(f"source gap: {symbol}")
    return tuple(sorted(bars, key=lambda item: (item.logical_close, panel.index(item.symbol))))


def source_manifest(bars: Sequence[Bar], *, panel: Sequence[str], origin: datetime, first_required_close: datetime) -> dict[str, Any]:
    ordered = validate_bars(bars, panel=panel, origin=origin, first_required_close=first_required_close)
    rows = [{"symbol": bar.symbol, "interval": INTERVAL, "logical_close_utc": _stamp(bar.logical_close), "provider": "Binance USD-M", "raw_row_sha256": sha256(canonical_bytes(bar.raw_row)).hexdigest()} for bar in ordered]
    value = {"ordered_20_symbol_panel": list(panel), "ordered_20_symbol_panel_digest": digest(list(panel)), "interval": INTERVAL, "first_required_source_close": _stamp(first_required_close), "maximum_source_bar_close_utc": _stamp(max(bar.logical_close for bar in ordered)), "origin_utc": _stamp(origin), "rows": rows}
    return {**value, "source_data_manifest_sha256": digest(value)}


def _frozen_panel() -> tuple[str, ...]:
    return ("ALICEUSDT", "APEUSDT", "API3USDT", "APTUSDT", "BCHUSDT", "CHRUSDT", "CHZUSDT", "ETCUSDT", "GMTUSDT", "INJUSDT", "LDOUSDT", "LINKUSDT", "LTCUSDT", "ONEUSDT", "OPUSDT", "REEFUSDT", "SANDUSDT", "TRXUSDT", "XLMUSDT", "XRPUSDT")


def bars_from_authenticated_archive(*, symbol: str, year: int, month: int, zip_bytes: bytes, checksum_text: str) -> tuple[Bar, ...]:
    """REUSE_AS_IS: admit only rows accepted by the canonical USD-M parser."""
    try:
        _, rows = receipt_from_bytes(symbol, year, month, zip_bytes, checksum_text)
    except MaterializationError as exc:
        raise RecorderBlocked(f"canonical Binance source rejection: {exc.status}") from exc
    values: list[Bar] = []
    for row in rows:
        opened = _utc(row["timestamp"])
        close = opened + timedelta(hours=1)
        raw = (int(opened.timestamp() * 1000), row["open"], row["high"], row["low"], row["close"], row["volume"], int((close - timedelta(milliseconds=1)).timestamp() * 1000), "0", 0, "0", "0", "0")
        values.append(Bar(symbol, close, float(row["close"]), raw))
    return tuple(values)


def _prices(bars: Sequence[Bar], panel: Sequence[str]) -> dict[str, dict[datetime, float]]:
    result = {symbol: {} for symbol in panel}
    for bar in bars:
        result[bar.symbol][bar.logical_close] = bar.close
    return result


def market_return(prices: Mapping[str, Mapping[datetime, float]], panel: Sequence[str], close: datetime) -> float:
    prior = close - timedelta(hours=1)
    try:
        returns = [math.log(prices[symbol][close] / prices[symbol][prior]) for symbol in panel]
    except KeyError as exc:
        raise RecorderBlocked("required return close missing") from exc
    return sum(returns) / len(returns)


def rv24_prior(prices: Mapping[str, Mapping[datetime, float]], panel: Sequence[str], origin: datetime) -> float:
    return math.sqrt(sum(market_return(prices, panel, origin - timedelta(hours=index)) ** 2 for index in range(24)))


def rv24_future(prices: Mapping[str, Mapping[datetime, float]], panel: Sequence[str], origin: datetime) -> float:
    return math.sqrt(sum(market_return(prices, panel, origin + timedelta(hours=index)) ** 2 for index in range(1, 25)))


def eligible_training_origins(origin: datetime) -> tuple[datetime, ...]:
    latest = origin - timedelta(days=2)  # o + 24h < t; equality at t is excluded.
    values = tuple(FIRST_LIVE_ORIGIN - timedelta(days=366) + timedelta(days=index) for index in range((latest - (FIRST_LIVE_ORIGIN - timedelta(days=366))).days + 1))
    if any(item + timedelta(hours=24) >= origin for item in values):
        raise RecorderBlocked("strict training cutoff violated")
    return values


def _ols(rows: Sequence[tuple[Sequence[float], float]]) -> tuple[float, tuple[float, ...]]:
    # Small deterministic normal-equation solver with an intercept; fixture scope only.
    width = len(rows[0][0]) + 1
    matrix = [[0.0] * (width + 1) for _ in range(width)]
    for features, target in rows:
        x = [1.0, *features]
        for i in range(width):
            for j in range(width): matrix[i][j] += x[i] * x[j]
            matrix[i][-1] += x[i] * target
    for column in range(width):
        pivot = max(range(column, width), key=lambda row: abs(matrix[row][column]))
        if abs(matrix[pivot][column]) < 1e-14: raise RecorderBlocked("singular frozen OLS fixture")
        matrix[column], matrix[pivot] = matrix[pivot], matrix[column]
        scale = matrix[column][column]; matrix[column] = [cell / scale for cell in matrix[column]]
        for row in range(width):
            if row != column:
                scale = matrix[row][column]; matrix[row] = [left - scale * right for left, right in zip(matrix[row], matrix[column])]
    solved = tuple(matrix[index][-1] for index in range(width))
    return solved[0], solved[1:]


def compute_models(bars: Sequence[Bar], *, panel: Sequence[str], origin: datetime) -> dict[str, Any]:
    prices = _prices(bars, panel); training = eligible_training_origins(origin)
    if origin == FIRST_LIVE_ORIGIN and len(training) != 365:
        raise RecorderBlocked("initial training count must equal 365")
    prior = {item: rv24_prior(prices, panel, item) for item in (*training, origin)}
    target = {item: rv24_future(prices, panel, item) for item in training}
    candidate_rows = [((prior[item],), target[item]) for item in training]
    c_alpha, (c_beta,) = _ols(candidate_rows)
    b3_rows = []
    for item in training:
        window = [prior.get(item - timedelta(days=lag)) or rv24_prior(prices, panel, item - timedelta(days=lag)) for lag in range(30)]
        b3_rows.append(((window[0], sum(window[:7]) / 7, sum(window) / 30), target[item]))
    b3_alpha, b3_coefficients = _ols(b3_rows)
    current_window = [prior.get(origin - timedelta(days=lag)) or rv24_prior(prices, panel, origin - timedelta(days=lag)) for lag in range(30)]
    c_raw = c_alpha + c_beta * prior[origin]
    b3_raw = b3_alpha + sum(coef * value for coef, value in zip(b3_coefficients, (current_window[0], sum(current_window[:7]) / 7, sum(current_window) / 30)))
    return {"C_JH01": {"alpha": c_alpha, "beta": c_beta, "raw_forecast": c_raw, "floored_forecast": max(0.0, c_raw)}, "B0": {"forecast": max(0.0, sum(target.values()) / len(target))}, "B1": {"forecast": prior[origin]}, "B3": {"alpha": b3_alpha, "daily_coefficient": b3_coefficients[0], "weekly_coefficient": b3_coefficients[1], "monthly_coefficient": b3_coefficients[2], "raw_forecast": b3_raw, "floored_forecast": max(0.0, b3_raw)}, "training_origin_count": len(training), "training_first_origin": _stamp(training[0]), "training_last_origin": _stamp(training[-1])}


def build_forecast_artifact(root: Path, bars: Sequence[Bar], *, origin: datetime, qualification_mode: bool) -> dict[str, Any]:
    if origin in required_origins():
        raise RecorderBlocked("REAL_V1_ACTIVATION_REQUIRED")
    if not qualification_mode:
        raise RecorderBlocked("QUALIFICATION_FIXTURE_MODE_REQUIRED")
    contract = frozen_contract(root); preregistration = contract["preregistration"]; repair = contract["repair"]
    panel = preregistration["frozen_target"]["ordered_20_symbol_panel"]
    first_required = _utc(repair["repair"]["repaired_first_required_source_close"])
    manifest = source_manifest(bars, panel=panel, origin=origin, first_required_close=first_required)
    models = compute_models(bars, panel=panel, origin=origin)
    artifact = {"project_id": PROJECT_ID, "experiment_id": EXPERIMENT_ID, "candidate_id": CANDIDATE_ID, "v1_preregistration_digest": preregistration["preregistration_digest"], "forecast_origin_utc": _stamp(origin), "ordered_20_symbol_panel": panel, "ordered_20_symbol_panel_digest": digest(panel), "target_horizon_identity": "RV24_FUTURE_24H", "source_provider_contract_identity": "BINANCE_USD_M_PERPETUAL_1H_LOGICAL_CLOSE", "first_required_source_close": _stamp(first_required), "maximum_source_bar_close_utc": manifest["maximum_source_bar_close_utc"], "training_target_cutoff_exclusive_utc": _stamp(origin), "source_data_manifest_identity": manifest["source_data_manifest_sha256"], "source_data_manifest_sha256": manifest["source_data_manifest_sha256"], "model_implementation_identity_digest": implementation_identity(), "nonnegative_floor_application": "AFTER_FORECAST_MAX_0", "persistence_mechanism": "GITHUB_IMMUTABLE_RELEASE_V0R3_QUALIFIED", "qualification_mode": qualification_mode, **models}
    return {**artifact, "forecast_artifact_canonical_digest": digest(artifact)}


def recover_publication(existing: Mapping[str, str] | None, artifact: Mapping[str, Any]) -> str:
    expected = artifact["forecast_artifact_canonical_digest"]
    if existing is None: return "PUBLICATION_MAY_PROCEED"
    if existing.get("state") == "AMBIGUOUS": raise RecorderBlocked("ambiguous remote release")
    if existing.get("origin_identity") != origin_identity(_utc(artifact["forecast_origin_utc"])): raise RecorderBlocked("wrong existing origin")
    if existing.get("artifact_digest") == expected: return "IDEMPOTENT_AUTHORITATIVE_RECOVERY"
    raise RecorderBlocked("same origin different digest")


def release_identity(artifact: Mapping[str, Any]) -> RemoteRelease:
    """One deterministic tag/asset identity per project/candidate/prereg/origin."""
    origin_id = origin_identity(_utc(artifact["forecast_origin_utc"]))
    tag = f"jh01-v1-recorder-{origin_id[:24]}"
    return RemoteRelease(origin_id, tag, artifact["forecast_artifact_canonical_digest"], "forecast.json", None, None)


class GitHubReleaseTransport:
    """Concrete GitHub immutable-release transport behind ``ReleaseTransport``.

    The HTTP lifecycle is deliberately small and deterministic.  Authentication
    comes from ``QNTYLAB_GITHUB_TOKEN`` or the authenticated GitHub CLI; all
    authoritative state is read back from GitHub after each mutating request.
    Attestation acquisition uses the official ``gh release verify`` and
    ``gh attestation trusted-root`` commands because GitHub's release
    attestation endpoint is intentionally exposed through that client.
    """

    API = "https://api.github.com"
    UPLOADS = "https://uploads.github.com"

    def __init__(self, *, repository: str = "CipherCuttle/QntyLab", token: str | None = None, gh_binary: str = "gh", timeout: float = 30.0, opener=urlopen):
        if "/" not in repository or repository.count("/") != 1:
            raise RecorderBlocked("repository must be owner/name")
        self.repository = repository
        self.token = token or os.environ.get("QNTYLAB_GITHUB_TOKEN")
        self.gh_binary = gh_binary
        self.timeout = timeout
        self._opener = opener
        self._repository_metadata: dict[str, Any] | None = None

    def _auth_token(self) -> str:
        if self.token and self.token.strip():
            return self.token.strip()
        try:
            result = subprocess.run([self.gh_binary, "auth", "token"], capture_output=True, text=True, check=False)
        except OSError as exc:
            raise RecorderBlocked("GitHub authentication unavailable") from exc
        if result.returncode or not result.stdout.strip():
            raise RecorderBlocked("GitHub authentication unavailable")
        return result.stdout.strip()

    def _request(self, method: str, url: str, *, payload: bytes | None = None, content_type: str = "application/json") -> tuple[int, bytes, Mapping[str, str]]:
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self._auth_token()}",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "QntyLab-JH01-Recorder/1",
        }
        if payload is not None:
            headers["Content-Type"] = content_type
        request = Request(url, data=payload, headers=headers, method=method)
        try:
            with self._opener(request, timeout=self.timeout) as response:
                return response.status, response.read(), dict(response.headers.items())
        except HTTPError as exc:
            if exc.code == 404:
                return 404, exc.read(), dict(exc.headers.items())
            if exc.code in {408, 429, 500, 502, 503, 504}:
                raise UnknownWrite(f"GitHub {method} uncertain: HTTP {exc.code}") from exc
            detail = exc.read().decode(errors="replace")[:500]
            raise RecorderBlocked(f"GitHub {method} rejected: HTTP {exc.code}: {detail}") from exc
        except (URLError, TimeoutError) as exc:
            raise UnknownWrite(f"GitHub {method} outcome unknown") from exc

    def _json(self, method: str, path: str, *, payload: Mapping[str, Any] | None = None, upload: bytes | None = None) -> dict[str, Any] | None:
        base = self.UPLOADS if upload is not None else self.API
        encoded = upload if upload is not None else (canonical_bytes(payload) if payload is not None else None)
        content_type = "application/octet-stream" if upload is not None else "application/json"
        status, body, _ = self._request(method, base + path, payload=encoded, content_type=content_type)
        if status == 404:
            return None
        try:
            value = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RecorderBlocked("GitHub returned malformed JSON") from exc
        if not isinstance(value, dict):
            raise RecorderBlocked("GitHub returned non-object JSON")
        return value

    @staticmethod
    def _remote_time(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise RecorderBlocked("GitHub returned a timestamp without timezone")
        return parsed.astimezone(UTC)

    @staticmethod
    def _parse(value: Mapping[str, Any], *, expected: RemoteRelease | None = None) -> RemoteRelease:
        assets = value.get("assets") or []
        asset = next((item for item in assets if item.get("name") == (expected.asset_name if expected else "forecast.json")), None)
        digest_value = (asset or {}).get("digest")
        asset_sha = digest_value.removeprefix("sha256:") if isinstance(digest_value, str) else None
        return RemoteRelease(
            origin_id=expected.origin_id if expected else str(value.get("tag_name", "")),
            tag=str(value.get("tag_name", "")),
            artifact_digest=expected.artifact_digest if expected else (asset_sha or ""),
            asset_name=str((asset or {}).get("name", expected.asset_name if expected else "forecast.json")),
            asset_sha256=asset_sha,
            published_at=GitHubReleaseTransport._remote_time(str(value["published_at"])) if value.get("published_at") else None,
            release_id=int(value["id"]) if value.get("id") is not None else None,
            repository=expected.repository if expected else "CipherCuttle/QntyLab",
            target_commit=str(value.get("target_commitish")) if value.get("target_commitish") else (expected.target_commit if expected else None),
            immutable=value.get("immutable") if isinstance(value.get("immutable"), bool) else None,
        )

    def _get_tag(self, tag: str, *, expected: RemoteRelease | None = None) -> RemoteRelease | None:
        value = self._json("GET", f"/repos/{self.repository}/releases/tags/{quote(tag, safe='')}")
        if value is None:
            return None
        return self._enrich(self._parse(value, expected=expected))

    def _enrich(self, release: RemoteRelease) -> RemoteRelease:
        if self._repository_metadata is None:
            metadata = self._json("GET", f"/repos/{self.repository}")
            if metadata is None:
                raise RecorderBlocked("repository metadata unavailable")
            self._repository_metadata = metadata
        repo_id = str(self._repository_metadata["id"])
        owner_id = str((self._repository_metadata.get("owner") or {})["id"])
        release_id = str(release.release_id) if release.release_id is not None else None
        purl = f"pkg:github/{self.repository}@{release.tag}"
        return replace(release, repository_id=repo_id, owner_id=owner_id, release_id=release.release_id, purl=purl, package_id=repo_id)

    def find(self, origin_id: str) -> Sequence[RemoteRelease]:
        # The deterministic tag is derived from the origin identity; lookup is
        # exact and never searches by a mutable title or release description.
        tag = f"jh01-v1-recorder-{origin_id[:24]}"
        release = self._get_tag(tag)
        return () if release is None else (replace(release, origin_id=origin_id),)

    def create(self, release: RemoteRelease) -> RemoteRelease:
        value = self._json("POST", f"/repos/{self.repository}/releases", payload={"tag_name": release.tag, "target_commitish": release.target_commit, "name": release.tag, "draft": True, "prerelease": True})
        if value is None:
            raise RecorderBlocked("GitHub draft creation returned no release")
        return self._enrich(self._parse(value, expected=release))

    def upload(self, tag: str, asset_name: str, content: bytes) -> RemoteRelease:
        release = self._get_tag(tag)
        if release is None or release.release_id is None:
            raise RecorderBlocked("release disappeared before asset upload")
        value = self._json("POST", f"/repos/{self.repository}/releases/{release.release_id}/assets?name={quote(asset_name, safe='')}", upload=content)
        if value is None:
            raise RecorderBlocked("GitHub asset upload returned no asset")
        updated = self._get_tag(tag, expected=release)
        if updated is None:
            raise RecorderBlocked("release disappeared after asset upload")
        return updated

    def publish(self, release: RemoteRelease) -> RemoteRelease:
        if release.release_id is None:
            raise RecorderBlocked("release ID required before publication")
        value = self._json("PATCH", f"/repos/{self.repository}/releases/{release.release_id}", payload={"draft": False, "prerelease": False})
        if value is None:
            raise RecorderBlocked("GitHub publication returned no release")
        published = self._parse(value, expected=release)
        authoritative = self._get_tag(release.tag, expected=release)
        if authoritative is None or authoritative.published_at is None:
            raise RecorderBlocked("authoritative published release readback unavailable")
        if authoritative.immutable is not True:
            raise RecorderBlocked("GitHub release is not authoritative immutable state")
        if authoritative.target_commit and release.target_commit and authoritative.target_commit != release.target_commit:
            raise RecorderBlocked("authoritative target commit mismatch")
        return authoritative

    def acquire_attestation(self, release: RemoteRelease) -> tuple[bytes, bytes]:
        try:
            verified = subprocess.run([self.gh_binary, "release", "verify", release.tag, "--repo", self.repository, "--format", "json"], capture_output=True, text=True, check=False)
            trusted = subprocess.run([self.gh_binary, "attestation", "trusted-root"], capture_output=True, text=False, check=False)
        except OSError as exc:
            raise RecorderBlocked("GitHub attestation tooling unavailable") from exc
        if verified.returncode or trusted.returncode:
            raise RecorderBlocked("GitHub release attestation acquisition failed")
        try:
            result = json.loads(verified.stdout)
            bundle = result["attestation"]["bundle"]
            bundle_bytes = canonical_bytes(bundle)
        except (json.JSONDecodeError, KeyError, TypeError) as exc:
            raise RecorderBlocked("GitHub release attestation bundle malformed") from exc
        return bundle_bytes, trusted.stdout


def _window(timestamp: datetime | None, origin: datetime, *, label: str) -> datetime:
    if timestamp is None or timestamp.tzinfo is None:
        raise RecorderBlocked(f"missing authoritative {label}")
    value = timestamp.astimezone(UTC)
    if not origin <= value < origin + timedelta(hours=1):
        raise RecorderBlocked(f"{label} outside frozen one-hour window")
    return value


class PublicationRuntime:
    """Small crash-safe release state machine; transport owns all HTTP effects."""

    def __init__(self, transport: ReleaseTransport, verifier: AttestationVerifier):
        self.transport, self.verifier = transport, verifier

    def _existing(self, expected: RemoteRelease) -> RemoteRelease | None:
        candidates = tuple(self.transport.find(expected.origin_id))
        if len(candidates) > 1:
            raise RecorderBlocked("BLOCK_AMBIGUOUS_REMOTE")
        if not candidates:
            return None
        current = candidates[0]
        if current.tag != expected.tag or current.artifact_digest != expected.artifact_digest:
            raise RecorderBlocked("same origin different digest")
        return current

    def publish(self, artifact: Mapping[str, Any], *, origin: datetime, target_commit: str) -> tuple[tuple[OriginState, ...], RemoteRelease, VerifiedAttestation]:
        content = canonical_bytes(artifact); expected = replace(release_identity(artifact), target_commit=target_commit)
        states = [OriginState.ORIGIN_PRECHECK, OriginState.SOURCE_MATERIALIZED, OriginState.FORECAST_COMPUTED, OriginState.ARTIFACT_FROZEN, OriginState.PUBLICATION_IN_PROGRESS]
        release = self._existing(expected)
        if release is None:
            try:
                release = self.transport.create(expected)
            except UnknownWrite:
                release = self._existing(expected)
                if release is None:  # One identical-request transient retry only.
                    release = self.transport.create(expected)
        if release.artifact_digest != expected.artifact_digest:
            raise RecorderBlocked("different-digest release created")
        if release.asset_sha256 is None:
            try:
                release = self.transport.upload(expected.tag, expected.asset_name, content)
            except UnknownWrite:
                release = self._existing(expected)
                if release is None or release.asset_sha256 is None:
                    release = self.transport.upload(expected.tag, expected.asset_name, content)
        if release.asset_sha256 != sha256(content).hexdigest():
            raise RecorderBlocked("authoritative uploaded asset digest mismatch")
        if release.published_at is None:
            publish = getattr(self.transport, "publish", None)
            if publish is None:
                raise RecorderBlocked("transport cannot publish draft release")
            release = publish(release)
        _window(release.published_at, origin, label="published_at")
        states.append(OriginState.PUBLICATION_AUTHORITATIVE)
        try:
            bundle, trusted_root = self.transport.acquire_attestation(release)
        except UnknownWrite:
            bundle, trusted_root = self.transport.acquire_attestation(release)  # bounded one recovery acquisition
        expectation = AttestationExpectation("CipherCuttle/QntyLab", release.tag, target_commit, release.asset_name, release.asset_sha256, repository_id=release.repository_id, owner_id=release.owner_id, release_id=str(release.release_id) if release.release_id is not None else None, purl=release.purl, package_id=release.package_id)
        verified = self.verifier.verify(asset=content, bundle=bundle, trusted_root=trusted_root, expectation=expectation)
        if verified.expectation != expectation:
            raise RecorderBlocked("attestation subject/policy mismatch")
        _window(verified.tsa_timestamp, origin, label="verified TSA timestamp")
        states.extend((OriginState.ATTESTATION_ACQUIRED, OriginState.RETENTION_PACKAGE_FROZEN, OriginState.OFFLINE_REVERIFIED, OriginState.ORIGIN_COMPLETE))
        return tuple(states), release, verified


class ExternalSigstoreVerifier:
    """Adapter for the qualified generic V0R3-policy verifier executable.

    The command must accept ``ASSET ROOT BUNDLE POLICY`` and emit only a
    verified JSON receipt.  This adapter deliberately has no unsafe fallback:
    until a separately qualified generic verifier artifact exists, calling it
    blocks instead of treating a local retention manifest as attestation proof.
    """

    def __init__(self, executable: Path): self.executable = executable

    def verify(self, *, asset: bytes, bundle: bytes, trusted_root: bytes, expectation: AttestationExpectation) -> VerifiedAttestation:
        if not self.executable.is_file():
            raise RecorderBlocked("generic per-origin Sigstore verifier unavailable")
        with tempfile.TemporaryDirectory(prefix="qntylab-jh01-attestation-") as temporary:
            base = Path(temporary); asset_path, root_path, bundle_path, policy_path = base / "forecast.json", base / "trusted_root.jsonl", base / "release_attestation.sigstore.json", base / "expected_policy.json"
            asset_path.write_bytes(asset); root_path.write_bytes(trusted_root); bundle_path.write_bytes(bundle)
            policy_path.write_bytes(canonical_bytes({"repository": expectation.repository, "repository_id": expectation.repository_id, "owner_id": expectation.owner_id, "release_id": expectation.release_id, "tag": expectation.tag, "purl": expectation.purl, "package_id": expectation.package_id, "target_commit": expectation.target_commit, "asset_name": expectation.asset_name, "asset_sha256": expectation.asset_sha256, "predicate_type": expectation.predicate_type, "signer_uri": expectation.signer_uri}))
            run = subprocess.run([str(self.executable), str(asset_path), str(root_path), str(bundle_path), str(policy_path)], capture_output=True, text=True)
            if run.returncode:
                raise RecorderBlocked("per-origin Sigstore verifier rejected attestation")
            try: receipt = json.loads(run.stdout)
            except json.JSONDecodeError as exc: raise RecorderBlocked("per-origin Sigstore verifier receipt malformed") from exc
            if receipt.get("stage_a") != "PASS" or receipt.get("stage_b") != "PASS" or receipt.get("signer") != expectation.signer_uri:
                raise RecorderBlocked("per-origin Sigstore receipt policy mismatch")
            tsa = datetime.fromisoformat(str(receipt.get("tsa", "")).replace("Z", "+00:00"))
            return VerifiedAttestation(expectation, tsa, bundle, trusted_root)


def retention_package(path: Path, *, forecast: Mapping[str, Any], release_metadata: Mapping[str, Any], bundle: bytes, trusted_root: bytes) -> dict[str, Any]:
    """Create a package; this does not itself assert Sigstore verification."""
    path.mkdir(parents=True, exist_ok=True)
    files = {"forecast.json": canonical_bytes(forecast), "release_metadata.json": canonical_bytes(release_metadata), "release_attestation.sigstore.json": bundle, "trusted_root.jsonl": trusted_root}
    for name, content in files.items(): (path / name).write_bytes(content)
    manifest = {"files": {name: sha256(content).hexdigest() for name, content in files.items()}, "timing_authority": "V0R3 verified Sigstore bundle plus signer, signed predicate/subjects, and GitHub TSA; release_metadata is informational only"}
    (path / "retention_manifest.json").write_bytes(canonical_bytes(manifest))
    return manifest


def verify_retention_package(path: Path) -> None:
    """Verify package integrity only; timing/attestation authority is V0R3."""
    manifest = json.loads((path / "retention_manifest.json").read_text())
    expected = {name: sha256((path / name).read_bytes()).hexdigest() for name in manifest["files"]}
    if expected != manifest["files"]: raise RecorderBlocked("retention package digest mismatch")
    forecast = json.loads((path / "forecast.json").read_text())
    if forecast.get("forecast_artifact_canonical_digest") != digest({key: value for key, value in forecast.items() if key != "forecast_artifact_canonical_digest"}): raise RecorderBlocked("forecast artifact digest mismatch")


def offline_reverify_v0r3_qualified_package(root: Path, *, go_binary: Path) -> None:
    """Reuse the qualified V0R3 Sigstore policy under hard network isolation.

    The V0R3 verifier is intentionally frozen to its retained release evidence;
    this integration qualification proves the real verifier path without
    claiming that arbitrary fixture bundles are cryptographically verified.
    """
    qualified = root / "qualifications/jh01_v0r3"
    with tempfile.TemporaryDirectory(prefix="qntylab-jh01-v0r3-") as temporary:
        executable = Path(temporary) / "verify-v0r3"
        build = subprocess.run([str(go_binary), "build", "-o", str(executable), "."], cwd=qualified, capture_output=True, text=True, env={**os.environ, "GOPROXY": "off"})
        if build.returncode:
            raise RecorderBlocked("V0R3 verifier build failed")
        retained = qualified / "retention"
        run = subprocess.run(["bwrap", "--unshare-net", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--", str(executable), str(retained / "forecast.json"), str(retained / "trusted_root.jsonl"), str(retained / "release_attestation.sigstore.json")], capture_output=True, text=True)
        if run.returncode:
            raise RecorderBlocked("V0R3 offline Sigstore policy rejected retained package")


def offline_reverify_current_package(root: Path, *, package: Path, go_binary: Path, expected_policy: Path) -> None:
    """Hard-isolated re-verification of a current recorder retention package."""
    with tempfile.TemporaryDirectory(prefix="qntylab-jh01-current-") as temporary:
        executable = Path(temporary) / "verify-v0r3-generic"
        build = subprocess.run([str(go_binary), "build", "-o", str(executable), "."], cwd=root / "qualifications/jh01_v0r3", capture_output=True, text=True, env={**os.environ, "GOPROXY": "off"})
        if build.returncode:
            raise RecorderBlocked("generic V0R3 verifier build failed")
        command = ["bwrap", "--unshare-net", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc", "--", str(executable), str(package / "forecast.json"), str(package / "trusted_root.jsonl"), str(package / "release_attestation.sigstore.json"), str(expected_policy)]
        run = subprocess.run(command, capture_output=True, text=True)
        if run.returncode:
            raise RecorderBlocked("current package offline Sigstore policy rejected retention package")
