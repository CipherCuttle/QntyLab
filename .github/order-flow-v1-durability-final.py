from __future__ import annotations

import json
from pathlib import Path
import subprocess

OP = Path("qntylab/order_flow_prospective_v1_operation.py")
TEST = Path("tests/test_order_flow_prospective_v1_activation.py")
RUNTIME = Path("experiments/research/qnty_edge_discovery_order_flow_v1/prospective_runtime.json")
DOC = Path("ops/systemd/user/order-flow-v1-prospective.md")

HOST_BINDING_CONTEXT = "QNTYLAB_ORDER_FLOW_V1_HOST_V1"
HOST_BINDING_DIGEST = "0902027d8e7eb13bf130934d46a48b61cd6b126fef13f371844f4d5de9e39f5e"
CANONICAL_STATE_DIR = "/home/swirky/.local/state/qntylab/order_flow_prospective_v1"


def once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


once(
    OP,
    'STATE_DIRNAME = "order_flow_prospective_v1"\nLEDGER_FILENAME = recorder.LEDGER_FILENAME\n',
    'STATE_DIRNAME = "order_flow_prospective_v1"\n'
    'CANONICAL_STATE_DIR = Path("/home/swirky/.local/state/qntylab/order_flow_prospective_v1")\n'
    'MACHINE_ID_PATH = Path("/etc/machine-id")\n'
    'HOST_BINDING_CONTEXT = "QNTYLAB_ORDER_FLOW_V1_HOST_V1"\n'
    'TRUSTED_HOST_BINDING_DIGEST = "0902027d8e7eb13bf130934d46a48b61cd6b126fef13f371844f4d5de9e39f5e"\n'
    'EVIDENCE_RELEASE_SCHEMA = "ORDER_FLOW_V1_EVIDENCE_RELEASE_V1"\n'
    'LEDGER_FILENAME = recorder.LEDGER_FILENAME\n',
    "runtime constants",
)

once(
    OP,
    'def default_state_dir() -> Path:\n'
    '    base = Path(os.environ.get("XDG_STATE_HOME") or (Path.home() / ".local" / "state"))\n'
    '    return base / "qntylab" / STATE_DIRNAME\n',
    'def default_state_dir() -> Path:\n'
    '    return CANONICAL_STATE_DIR\n\n\n'
    'def _validate_recording_state_dir(state_dir: Path) -> Path:\n'
    '    resolved = state_dir.expanduser().resolve()\n'
    '    if resolved != CANONICAL_STATE_DIR.resolve():\n'
    '        raise OperationBlocked("canonical recording state directory mismatch")\n'
    '    return resolved\n',
    "state directory pin",
)

once(
    OP,
    '    if runtime.get("release_asset") != LEDGER_FILENAME:\n'
    '        raise OperationBlocked("runtime release asset changed")\n',
    '    if runtime.get("release_asset") != LEDGER_FILENAME:\n'
    '        raise OperationBlocked("runtime release asset changed")\n'
    '    if runtime.get("state_dir") != str(CANONICAL_STATE_DIR):\n'
    '        raise OperationBlocked("runtime canonical state directory changed")\n'
    '    host_identity = runtime.get("trusted_host_identity")\n'
    '    if not isinstance(host_identity, dict):\n'
    '        raise OperationBlocked("trusted host identity contract is malformed")\n'
    '    if host_identity.get("method") != "SHA256_CONTEXTUALIZED_SHA256_ETC_MACHINE_ID":\n'
    '        raise OperationBlocked("trusted host identity method changed")\n'
    '    if host_identity.get("context") != HOST_BINDING_CONTEXT:\n'
    '        raise OperationBlocked("trusted host identity context changed")\n'
    '    if host_identity.get("digest") != TRUSTED_HOST_BINDING_DIGEST:\n'
    '        raise OperationBlocked("trusted host identity digest changed")\n'
    '    if host_identity.get("probe_host_binding_required") is not True:\n'
    '        raise OperationBlocked("trusted host binding requirement changed")\n',
    "runtime host/state contract",
)

marker = '\ndef _validate_installed_units(root: Path) -> None:\n'
host_block = '''
def _trusted_host_fingerprint(path: Path = MACHINE_ID_PATH) -> str:
    try:
        machine_digest = sha256(path.read_bytes()).hexdigest()
    except OSError as exc:
        raise OperationBlocked("trusted host machine-id is unavailable") from exc
    return sha256(f"{HOST_BINDING_CONTEXT}:{machine_digest}".encode("utf-8")).hexdigest()


def validate_trusted_host(root: Path, machine_id_path: Path = MACHINE_ID_PATH) -> dict[str, str]:
    runtime = _json(root / RUNTIME_PATH)
    host_identity = runtime.get("trusted_host_identity")
    expected = host_identity.get("digest") if isinstance(host_identity, dict) else None
    actual = _trusted_host_fingerprint(machine_id_path)
    if expected != TRUSTED_HOST_BINDING_DIGEST or actual != expected:
        raise OperationBlocked("executing host does not match the qualified trusted host")
    return {
        "method": "SHA256_CONTEXTUALIZED_SHA256_ETC_MACHINE_ID",
        "context": HOST_BINDING_CONTEXT,
        "digest": actual,
    }

'''
once(OP, marker, "\n" + host_block + "def _validate_installed_units(root: Path) -> None:\n", "trusted host enforcement")

once(
    OP,
    '    validate_activation_artifacts(root)\n'
    '    validate_project_authority(root)\n'
    '    _validate_installed_units(root)\n',
    '    validate_activation_artifacts(root)\n'
    '    validate_project_authority(root)\n'
    '    validate_trusted_host(root)\n'
    '    _validate_installed_units(root)\n',
    "canonical host preflight",
)

text = OP.read_text(encoding="utf-8")
start = text.index("\ndef _release_snapshot(tag: str)")
end = text.index("\ndef record_due(", start)
release_block = r'''
def _release_snapshot(tag: str) -> dict[str, Any] | None:
    result = _run(("gh", "api", "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2022-11-28", f"repos/{REPOSITORY}/releases/tags/{tag}"), check=False)
    if result.returncode:
        detail = f"{result.stdout}\n{result.stderr}"
        if "HTTP 404" in detail or "Not Found" in detail:
            return None
        raise OperationBlocked(f"GitHub release lookup failed: {detail.strip()}")
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OperationBlocked("GitHub release lookup returned malformed JSON") from exc
    if not isinstance(value, dict):
        raise OperationBlocked("GitHub release lookup returned non-object JSON")
    return value


def _release_metadata(release: dict[str, Any]) -> dict[str, Any]:
    try:
        metadata = json.loads(release.get("body") or "")
    except json.JSONDecodeError as exc:
        raise OperationBlocked("evidence release metadata is malformed") from exc
    if not isinstance(metadata, dict) or metadata.get("schema") != EVIDENCE_RELEASE_SCHEMA:
        raise OperationBlocked("evidence release metadata schema mismatch")
    count = metadata.get("event_count")
    if not isinstance(count, int) or count < 1:
        raise OperationBlocked("evidence release event count is malformed")
    for key in ("head_event_digest", "ledger_sha256"):
        value = metadata.get(key)
        if not isinstance(value, str) or len(value) != 64 or any(c not in "0123456789abcdef" for c in value):
            raise OperationBlocked(f"evidence release metadata digest is malformed: {key}")
    previous = metadata.get("previous_release_tag")
    if previous is not None and (not isinstance(previous, str) or not previous.startswith(RELEASE_PREFIX)):
        raise OperationBlocked("evidence release previous tag is malformed")
    return metadata


def _release_assets(release: dict[str, Any]) -> list[dict[str, Any]]:
    return [asset for asset in release.get("assets", []) if isinstance(asset, dict) and asset.get("name") == LEDGER_FILENAME]


def _ledger_tag(events: Sequence[dict[str, Any]]) -> str:
    if not events:
        raise OperationBlocked("cannot tag an empty evidence ledger")
    digest = events[-1].get("event_digest")
    if not isinstance(digest, str) or len(digest) != 64:
        raise OperationBlocked("ledger last event digest is malformed")
    return f"{RELEASE_PREFIX}{len(events):06d}-{digest[:24]}"


def _ledger_release_metadata(ledger: recorder.EvidenceLedger, *, previous_release_tag: str | None) -> dict[str, Any]:
    events = ledger.events()
    if not events or not ledger.path.is_file():
        raise OperationBlocked("cannot describe an empty evidence ledger")
    return {"schema": EVIDENCE_RELEASE_SCHEMA, "event_count": len(events), "head_event_digest": events[-1]["event_digest"], "ledger_sha256": sha256(ledger.path.read_bytes()).hexdigest(), "previous_release_tag": previous_release_tag, "scientific_evaluation": "FORBIDDEN"}


def _list_evidence_releases() -> list[dict[str, Any]]:
    result = _run(("gh", "api", "-H", "Accept: application/vnd.github+json", "-H", "X-GitHub-Api-Version: 2022-11-28", f"repos/{REPOSITORY}/releases?per_page=100"))
    try:
        releases = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise OperationBlocked("GitHub release listing returned malformed JSON") from exc
    if not isinstance(releases, list):
        raise OperationBlocked("GitHub release listing returned non-list JSON")
    return [release for release in releases if isinstance(release, dict) and isinstance(release.get("tag_name"), str) and release["tag_name"].startswith(RELEASE_PREFIX)]


def _evidence_release_state() -> dict[str, Any]:
    parsed: list[dict[str, Any]] = []
    for release in _list_evidence_releases():
        metadata = _release_metadata(release)
        expected_tag = f"{RELEASE_PREFIX}{metadata['event_count']:06d}-{metadata['head_event_digest'][:24]}"
        if release.get("tag_name") != expected_tag:
            raise OperationBlocked("evidence release tag/metadata mismatch")
        assets = _release_assets(release)
        if len(assets) > 1:
            raise OperationBlocked("evidence release asset cardinality mismatch")
        if assets and assets[0].get("digest") != f"sha256:{metadata['ledger_sha256']}":
            raise OperationBlocked("evidence release asset/metadata digest mismatch")
        if release.get("draft") is False:
            if release.get("immutable") is not True or len(assets) != 1:
                raise OperationBlocked("published evidence release is not immutable and complete")
        elif release.get("draft") is not True:
            raise OperationBlocked("evidence release draft state is malformed")
        parsed.append({**release, "_evidence_meta": metadata})
    published = [item for item in parsed if item.get("draft") is False]
    drafts = [item for item in parsed if item.get("draft") is True]
    if len(drafts) > 1:
        raise OperationBlocked("more than one evidence release draft exists")
    counts = [item["_evidence_meta"]["event_count"] for item in published]
    if len(set(counts)) != len(counts):
        raise OperationBlocked("competing published evidence releases exist at one event count")
    published_head = max(published, key=lambda item: item["_evidence_meta"]["event_count"], default=None)
    draft_head = drafts[0] if drafts else None
    if published_head is not None:
        meta = published_head["_evidence_meta"]
        if meta["event_count"] == 1:
            if meta["previous_release_tag"] is not None:
                raise OperationBlocked("first evidence release unexpectedly names a predecessor")
        else:
            previous = _release_snapshot(meta["previous_release_tag"])
            if previous is None or previous.get("draft") is not False:
                raise OperationBlocked("evidence release predecessor is unavailable")
            previous_meta = _release_metadata(previous)
            if previous_meta["event_count"] != meta["event_count"] - 1:
                raise OperationBlocked("evidence release predecessor count mismatch")
    if draft_head is not None:
        dmeta = draft_head["_evidence_meta"]
        if published_head is None:
            if dmeta["event_count"] != 1 or dmeta["previous_release_tag"] is not None:
                raise OperationBlocked("first evidence draft has invalid predecessor state")
        else:
            pmeta = published_head["_evidence_meta"]
            if dmeta["event_count"] != pmeta["event_count"] + 1 or dmeta["previous_release_tag"] != published_head["tag_name"]:
                raise OperationBlocked("evidence draft does not extend the published head")
    return {"published_head": published_head, "draft_head": draft_head}


def _download_release_bytes(tag: str) -> bytes:
    with tempfile.TemporaryDirectory(prefix="qntylab-orderflow-download-") as directory:
        _run(("gh", "release", "download", tag, "--repo", REPOSITORY, "--pattern", LEDGER_FILENAME, "--dir", directory))
        restored = Path(directory) / LEDGER_FILENAME
        if not restored.is_file():
            raise OperationBlocked("downloaded evidence release ledger is missing")
        return restored.read_bytes()


def _events_from_ledger_bytes(payload: bytes) -> tuple[dict[str, Any], ...]:
    with tempfile.TemporaryDirectory(prefix="qntylab-orderflow-validate-") as directory:
        path = Path(directory) / LEDGER_FILENAME
        path.write_bytes(payload)
        return recorder.EvidenceLedger(Path(directory)).events()


def _replace_ledger_bytes(ledger: recorder.EvidenceLedger, payload: bytes) -> None:
    with ledger._exclusive_lock():
        temp = ledger.state_dir / f".{LEDGER_FILENAME}.restore"
        try:
            with temp.open("wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, ledger.path)
        finally:
            if temp.exists():
                temp.unlink()
    ledger.events()


def _verify_release(release: dict[str, Any], ledger: recorder.EvidenceLedger) -> dict[str, Any]:
    metadata = _release_metadata(release)
    if release.get("draft") is not False or release.get("immutable") is not True:
        raise OperationBlocked("evidence release is not published immutable")
    events = ledger.events()
    ledger_sha = sha256(ledger.path.read_bytes()).hexdigest()
    if metadata["event_count"] != len(events) or metadata["head_event_digest"] != events[-1]["event_digest"] or metadata["ledger_sha256"] != ledger_sha:
        raise OperationBlocked("immutable evidence release metadata differs from local ledger")
    assets = _release_assets(release)
    if len(assets) != 1 or assets[0].get("digest") != f"sha256:{ledger_sha}":
        raise OperationBlocked("immutable evidence release asset digest mismatch")
    if _download_release_bytes(release["tag_name"]) != ledger.path.read_bytes():
        raise OperationBlocked("independent immutable evidence restore differs from local ledger")
    return {"tag": release["tag_name"], "ledger_sha256": ledger_sha, "immutable": True, "independent_restore": "PASS"}


def reconcile_canonical_ledger(ledger: recorder.EvidenceLedger) -> dict[str, Any]:
    state = _evidence_release_state()
    published = state["published_head"]
    draft = state["draft_head"]
    local = ledger.events()
    if published is None:
        if len(local) > 1:
            raise OperationBlocked("multiple local events exist without a published remote head")
        if draft is not None and (not local or _ledger_tag(local) != draft["tag_name"]):
            raise OperationBlocked("unrecoverable first evidence draft conflicts with local state")
        return {"state": "NO_REMOTE_HEAD" if draft is None else "LOCAL_MATCHES_FIRST_DRAFT"}
    payload = _download_release_bytes(published["tag_name"])
    meta = published["_evidence_meta"]
    remote = _events_from_ledger_bytes(payload)
    if sha256(payload).hexdigest() != meta["ledger_sha256"] or len(remote) != meta["event_count"] or remote[-1]["event_digest"] != meta["head_event_digest"]:
        raise OperationBlocked("remote evidence ledger does not match release metadata")
    if not local:
        if draft is not None:
            raise OperationBlocked("remote draft exists but local recovery state is absent")
        _replace_ledger_bytes(ledger, payload)
        return {"state": "RESTORED_REMOTE_HEAD", "tag": published["tag_name"]}
    if tuple(local) == tuple(remote):
        if draft is not None:
            raise OperationBlocked("remote draft exists beyond the matching local published head")
        return {"state": "LOCAL_MATCHES_REMOTE_HEAD", "tag": published["tag_name"]}
    if len(local) < len(remote):
        if tuple(local) != tuple(remote[:len(local)]) or draft is not None:
            raise OperationBlocked("local evidence ledger diverges from immutable remote history")
        _replace_ledger_bytes(ledger, payload)
        return {"state": "RESTORED_NEWER_REMOTE_HEAD", "tag": published["tag_name"]}
    if len(local) == len(remote) + 1 and tuple(remote) == tuple(local[:-1]) and local[-1]["previous_event_digest"] == remote[-1]["event_digest"]:
        if draft is not None and _ledger_tag(local) != draft["tag_name"]:
            raise OperationBlocked("remote draft conflicts with the local unanchored suffix")
        return {"state": "LOCAL_HAS_ONE_UNANCHORED_EXTENSION"}
    raise OperationBlocked("local evidence ledger is more than one event ahead of or diverges from immutable remote history")


def ensure_immutable_anchor(ledger: recorder.EvidenceLedger, target_commit: str) -> dict[str, Any]:
    events = ledger.events()
    if not events or not ledger.path.is_file():
        return {"state": "NO_LEDGER"}
    tag = _ledger_tag(events)
    state = _evidence_release_state()
    published = state["published_head"]
    draft = state["draft_head"]
    if published is None:
        if len(events) != 1:
            raise OperationBlocked("first evidence release must contain exactly one event")
        previous_tag = None
    else:
        pmeta = published["_evidence_meta"]
        if pmeta["event_count"] == len(events):
            if published["tag_name"] != tag:
                raise OperationBlocked("local ledger conflicts with published evidence at this event count")
            return _verify_release(published, ledger)
        if pmeta["event_count"] != len(events) - 1 or events[-1]["previous_event_digest"] != pmeta["head_event_digest"]:
            raise OperationBlocked("local ledger is not the single next event after published evidence")
        previous_tag = published["tag_name"]
    metadata = _ledger_release_metadata(ledger, previous_release_tag=previous_tag)
    release = _release_snapshot(tag)
    if draft is not None:
        if draft["tag_name"] != tag:
            raise OperationBlocked("a competing evidence draft already exists")
        release = draft
    if release is None:
        _run(("gh", "release", "create", tag, "--repo", REPOSITORY, "--target", target_commit, "--title", tag, "--notes", json.dumps(metadata, sort_keys=True, separators=(",", ":")), "--prerelease", "--draft"))
        release = _release_snapshot(tag)
    if release is None or release.get("draft") is not True or _release_metadata(release) != metadata:
        raise OperationBlocked("draft evidence release is unavailable or mismatched")
    assets = _release_assets(release)
    if len(assets) == 0:
        _run(("gh", "release", "upload", tag, f"{ledger.path}#{LEDGER_FILENAME}", "--repo", REPOSITORY))
        release = _release_snapshot(tag)
        assets = _release_assets(release or {})
    if len(assets) != 1 or assets[0].get("digest") != f"sha256:{metadata['ledger_sha256']}":
        raise OperationBlocked("draft evidence asset digest mismatch")
    _run(("gh", "release", "edit", tag, "--repo", REPOSITORY, "--draft=false", "--prerelease"))
    release = _release_snapshot(tag)
    if release is None:
        raise OperationBlocked("published evidence release is unavailable")
    return _verify_release(release, ledger)
'''
text = text[:start] + "\n" + release_block.strip("\n") + "\n" + text[end:]
OP.write_text(text, encoding="utf-8")

old_prefix = '''    now = recorder.parse_utc(now)
    target_commit = canonical_preflight(root) if canonical_check else _git(root, "rev-parse", "HEAD")
    validate_activation_artifacts(root)

    if sys.version_info[:2] != (3, 12):
        raise OperationBlocked("activated runtime requires Python 3.12")

    ledger = recorder.EvidenceLedger(state_dir)
    if ledger.events():
        anchorer(ledger, target_commit)
'''
new_prefix = '''    now = recorder.parse_utc(now)
    if canonical_check:
        state_dir = _validate_recording_state_dir(state_dir)
        target_commit = canonical_preflight(root)
    else:
        if fetcher is None:
            raise OperationBlocked("noncanonical recording requires an injected synthetic fetcher")
        target_commit = _git(root, "rev-parse", "HEAD")
    validate_activation_artifacts(root)

    if sys.version_info[:2] != (3, 12):
        raise OperationBlocked("activated runtime requires Python 3.12")

    ledger = recorder.EvidenceLedger(state_dir)
    if canonical_check:
        reconcile_canonical_ledger(ledger)
    if ledger.events():
        anchorer(ledger, target_commit)
'''
once(OP, old_prefix, new_prefix, "record due preflight/reconcile")

once(
    OP,
    'def status(root: Path, state_dir: Path) -> dict[str, Any]:\n    authority = validate_activation_artifacts(root)\n',
    'def status(root: Path, state_dir: Path) -> dict[str, Any]:\n    state_dir = _validate_recording_state_dir(state_dir)\n    authority = validate_activation_artifacts(root)\n',
    "status canonical state directory",
)

runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
runtime["state_dir"] = CANONICAL_STATE_DIR
runtime["trusted_host_identity"] = {"method": "SHA256_CONTEXTUALIZED_SHA256_ETC_MACHINE_ID", "context": HOST_BINDING_CONTEXT, "digest": HOST_BINDING_DIGEST, "probe_host_binding_required": True}
runtime["release_tag_format"] = "order-flow-v1-evidence-{event_count:06d}-{head_event_digest_prefix24}"
runtime["release_body_schema"] = "ORDER_FLOW_V1_EVIDENCE_RELEASE_V1"
runtime["remote_reconciliation_required_before_provider_access"] = True
RUNTIME.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")

operation_blob = subprocess.check_output(["git", "hash-object", str(OP)], text=True).strip()
runtime = json.loads(RUNTIME.read_text(encoding="utf-8"))
runtime["operation_git_blob_sha"] = operation_blob
RUNTIME.write_text(json.dumps(runtime, indent=2, sort_keys=True) + "\n", encoding="utf-8")

append = r'''

def test_canonical_state_dir_is_fixed_and_xdg_override_is_ignored(monkeypatch):
    monkeypatch.setenv("XDG_STATE_HOME", "/tmp/not-authorized")
    assert operation.default_state_dir() == operation.CANONICAL_STATE_DIR


def test_trusted_host_binding_uses_campaign_specific_fingerprint(monkeypatch):
    monkeypatch.setattr(operation, "_trusted_host_fingerprint", lambda path=operation.MACHINE_ID_PATH: operation.TRUSTED_HOST_BINDING_DIGEST)
    result = operation.validate_trusted_host(ROOT)
    assert result["context"] == operation.HOST_BINDING_CONTEXT
    assert result["digest"] == operation.TRUSTED_HOST_BINDING_DIGEST


def test_wrong_trusted_host_fails_closed(tmp_path):
    import pytest
    machine_id = tmp_path / "machine-id"
    machine_id.write_text("different-machine\n", encoding="utf-8")
    with pytest.raises(operation.OperationBlocked, match="qualified trusted host"):
        operation.validate_trusted_host(ROOT, machine_id)


def test_noncanonical_recording_requires_injected_fetcher(tmp_path):
    import pytest
    now = recorder.hour(recorder.FIRST_WARMUP_CLOSE) + timedelta(minutes=5)
    with pytest.raises(operation.OperationBlocked, match="injected synthetic fetcher"):
        operation.record_due(ROOT, tmp_path, now=now, canonical_check=False, anchorer=lambda ledger, target: {"immutable": True})


def test_reconcile_restores_missing_local_ledger_from_remote(monkeypatch, tmp_path):
    import hashlib
    remote = recorder.EvidenceLedger(tmp_path / "remote")
    close = recorder.hour(recorder.FIRST_WARMUP_CLOSE)
    remote.record_batch(logical_close=close, rows=recorder.synthetic_batch(close), observed_at=close + timedelta(minutes=5))
    payload = remote.path.read_bytes()
    events = remote.events()
    metadata = {"schema": operation.EVIDENCE_RELEASE_SCHEMA, "event_count": 1, "head_event_digest": events[-1]["event_digest"], "ledger_sha256": hashlib.sha256(payload).hexdigest(), "previous_release_tag": None, "scientific_evaluation": "FORBIDDEN"}
    head = {"tag_name": operation._ledger_tag(events), "draft": False, "immutable": True, "_evidence_meta": metadata}
    monkeypatch.setattr(operation, "_evidence_release_state", lambda: {"published_head": head, "draft_head": None})
    monkeypatch.setattr(operation, "_download_release_bytes", lambda requested: payload)
    local = recorder.EvidenceLedger(tmp_path / "local")
    result = operation.reconcile_canonical_ledger(local)
    assert result["state"] == "RESTORED_REMOTE_HEAD"
    assert local.path.read_bytes() == payload
    assert local.events() == events


def test_runtime_pins_host_state_and_remote_reconciliation():
    runtime = json.loads((EXP / "prospective_runtime.json").read_text(encoding="utf-8"))
    assert runtime["state_dir"] == str(operation.CANONICAL_STATE_DIR)
    assert runtime["trusted_host_identity"] == {"method": "SHA256_CONTEXTUALIZED_SHA256_ETC_MACHINE_ID", "context": operation.HOST_BINDING_CONTEXT, "digest": operation.TRUSTED_HOST_BINDING_DIGEST, "probe_host_binding_required": True}
    assert runtime["remote_reconciliation_required_before_provider_access"] is True
    assert runtime["release_body_schema"] == operation.EVIDENCE_RELEASE_SCHEMA
'''
TEST.write_text(TEST.read_text(encoding="utf-8").rstrip() + "\n" + append, encoding="utf-8")

doc = DOC.read_text(encoding="utf-8")
if "## Canonical state + host binding" in doc:
    raise SystemExit("canonical state documentation already exists")
doc += f'''\n\n## Canonical state + host binding\n\nProduction recording is pinned to `{CANONICAL_STATE_DIR}`. `XDG_STATE_HOME` and\n`--state-dir` are not authority overrides for canonical recording. Before any\nprovider access, the runtime verifies a campaign-specific contextual fingerprint\nof `/etc/machine-id` against the Git-backed trusted-host binding and reconciles\nthe local cumulative ledger with the latest immutable GitHub evidence release.\nA missing/older local ledger is restored from the remote immutable head; any\ndivergence, competing draft, or more-than-one unanchored local event fails\nclosed. The reusable raw machine-id digest is not stored in Git.\n'''
DOC.write_text(doc, encoding="utf-8")
