import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "qntylab/qntyspot_ink_source_qualification_v1.py"
TESTS = ROOT / "tests/test_qntyspot_ink_source_qualification_v1.py"
AUTH = ROOT / "experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_research_v1/authorization.json"
STAGE_TESTS = ROOT / "tests/test_qntyspot_ink_shadow_performance_dev_acquisition_research_v1.py"


def replace_function(source: str, name: str, replacement: str) -> str:
    start = source.index(f"def {name}(")
    next_def = source.find("\n\ndef ", start + 1)
    end = len(source) if next_def == -1 else next_def + 2
    return source[:start] + replacement.rstrip() + "\n\n" + source[end:]


def patch_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    anchor = "MAX_T0_SCAN_BLOCKS = 8192\n"
    addition = (
        "MIN_TOTAL_HISTORY_SECONDS = 30 * 24 * 60 * 60\n"
        "MIN_DEV_HISTORY_SECONDS = 18 * 24 * 60 * 60\n"
        "MIN_OUTER_HISTORY_SECONDS = 12 * 24 * 60 * 60\n"
    )
    if addition not in text:
        if text.count(anchor) != 1:
            raise SystemExit("source constants anchor missing")
        text = text.replace(anchor, anchor + addition, 1)

    event_anchor = '''def _log_order_key(log: Mapping[str, Any]) -> tuple[int, int, int]:
    return (
        _hex_int(log.get("blockNumber")),
        _hex_int(log.get("transactionIndex")),
        _hex_int(log.get("logIndex")),
    )
'''
    event_add = '''\n\ndef _event_identity(log: Mapping[str, Any]) -> dict[str, Any]:
    block_hash, tx_hash, _ = _log_identity(log)
    block_number, transaction_index, log_index = _log_order_key(log)
    return {
        "block_number": block_number,
        "transaction_index": transaction_index,
        "log_index": log_index,
        "block_hash": block_hash,
        "transaction_hash": tx_hash,
    }
'''
    if "def _event_identity(" not in text:
        if event_anchor not in text:
            raise SystemExit("event identity anchor missing")
        text = text.replace(event_anchor, event_anchor + event_add, 1)

    text = replace_function(text, "_sync_logs", '''
def _sync_logs(
    rpc: RpcCall,
    start: int,
    end: int,
    canonical_block_hashes: dict[int, str] | None = None,
) -> list[Mapping[str, Any]]:
    if start > end:
        return []
    result = rpc("eth_getLogs", [{
        "address": POOL,
        "fromBlock": hex(start),
        "toBlock": hex(end),
        "topics": [SYNC_TOPIC],
    }])
    if not isinstance(result, list) or not all(isinstance(row, dict) for row in result):
        raise QualificationError("eth_getLogs returned malformed result")

    cache = canonical_block_hashes if canonical_block_hashes is not None else {}
    for row in result:
        if _norm_address(row.get("address")) != _norm_address(POOL):
            raise QualificationError("STOP_SOURCE_CONFLICT: provider returned a log for the wrong address")
        topics = row.get("topics")
        if not isinstance(topics, list) or not topics or not isinstance(topics[0], str) or topics[0].lower() != SYNC_TOPIC:
            raise QualificationError("STOP_SOURCE_CONFLICT: provider returned a non-Sync log")
        block_number = _hex_int(row.get("blockNumber"))
        if not start <= block_number <= end:
            raise QualificationError("STOP_SOURCE_CONFLICT: provider over-returned a log outside the requested range")
        canonical_hash = cache.get(block_number)
        if canonical_hash is None:
            canonical_hash = str(_block(rpc, block_number)["hash"]).lower()
            cache[block_number] = canonical_hash
        row_hash = row.get("blockHash")
        if not isinstance(row_hash, str) or row_hash.lower() != canonical_hash:
            raise QualificationError("STOP_SOURCE_CONFLICT: log block hash disagrees with canonical block metadata")
        _log_order_key(row)
        _log_identity(row)
    return result
''')

    text = replace_function(text, "find_t0_sync", '''
def find_t0_sync(
    rpc: RpcCall,
    deployment_block: int,
    t1_block: int,
    *,
    max_scan_blocks: int = MAX_T0_SCAN_BLOCKS,
    canonical_block_hashes: dict[int, str] | None = None,
) -> tuple[Mapping[str, Any], Mapping[str, Any]]:
    """Find T0 with singleton Sync queries so no future interval is pre-opened."""
    if max_scan_blocks < 1:
        raise QualificationError("T0 scan limit must be positive")
    last = min(t1_block, deployment_block + max_scan_blocks - 1)
    for number in range(deployment_block, last + 1):
        logs = _sync_logs(rpc, number, number, canonical_block_hashes)
        if logs:
            first = min(logs, key=_log_order_key)
            block = _block(rpc, number)
            if _log_identity(first)[0] != str(block["hash"]).lower():
                raise QualificationError("STOP_SOURCE_CONFLICT: T0 Sync is not bound to canonical block metadata")
            return block, first
    raise QualificationError(
        "STOP_SOURCE_CONFLICT: no eligible Sync observation found within outcome-blind T0 scan bound"
    )
''')

    history_anchor = '''def _dev_end_timestamp(t0_timestamp: int) -> int:
    t1_timestamp = _cutoff_timestamp()
    if t0_timestamp >= t1_timestamp:
        raise QualificationError("STOP_SOURCE_CONFLICT: T0 does not precede frozen T1")
    return t0_timestamp + ((t1_timestamp - t0_timestamp) * 3) // 5
'''
    history_add = '''\n\ndef _validate_history_window(t0_timestamp: int, dev_end_timestamp: int) -> dict[str, int]:
    t1_timestamp = _cutoff_timestamp()
    total = t1_timestamp - t0_timestamp
    dev = dev_end_timestamp - t0_timestamp
    outer = t1_timestamp - dev_end_timestamp
    if (
        total < MIN_TOTAL_HISTORY_SECONDS
        or dev < MIN_DEV_HISTORY_SECONDS
        or outer < MIN_OUTER_HISTORY_SECONDS
    ):
        raise QualificationError(
            "INSUFFICIENT_HISTORY: frozen 30-day total / 18-day DEV / 12-day OUTER minimum is not met"
        )
    return {
        "total": total,
        "dev": dev,
        "outer": outer,
    }
'''
    if "def _validate_history_window(" not in text:
        if history_anchor not in text:
            raise SystemExit("history anchor missing")
        text = text.replace(history_anchor, history_anchor + history_add, 1)

    text = replace_function(text, "_bounded_log_integrity_probe", '''
def _bounded_log_integrity_probe(
    rpc: RpcCall,
    t0_block: int,
    dev_end_block: int,
    span: int,
    canonical_block_hashes: dict[int, str] | None = None,
) -> dict[str, Any]:
    if span < 2:
        raise QualificationError("qualification probe span must be >= 2")
    start = t0_block
    end = min(dev_end_block, t0_block + span - 1)
    if end <= start:
        raise QualificationError("STOP_SOURCE_CONFLICT: DEV interval is too short for split-range integrity probe")
    midpoint = (start + end) // 2

    whole_a = _sync_logs(rpc, start, end, canonical_block_hashes)
    whole_b = _sync_logs(rpc, start, end, canonical_block_hashes)
    ordered_a = sorted(whole_a, key=_log_order_key)
    ordered_b = sorted(whole_b, key=_log_order_key)
    whole_ids_a = _identities(ordered_a)
    whole_ids_b = _identities(ordered_b)
    if whole_ids_a != whole_ids_b:
        raise QualificationError("STOP_SOURCE_CONFLICT: repeated historical log request is nondeterministic")

    left = sorted(_sync_logs(rpc, start, midpoint, canonical_block_hashes), key=_log_order_key)
    right = sorted(_sync_logs(rpc, midpoint + 1, end, canonical_block_hashes), key=_log_order_key)
    left_ids = _identities(left)
    right_ids = _identities(right)
    combined = sorted(left_ids + right_ids)
    if sorted(whole_ids_a) != combined:
        raise QualificationError("STOP_SOURCE_CONFLICT: whole-range logs disagree with split-range logs")
    if not ordered_a:
        raise QualificationError("STOP_SOURCE_CONFLICT: no Sync log available in DEV-bounded receipt probe")

    first = ordered_a[0]
    first_id = _log_identity(first)
    receipt = rpc("eth_getTransactionReceipt", [first_id[1]])
    if not isinstance(receipt, dict):
        raise QualificationError("STOP_SOURCE_CONFLICT: historical transaction receipt unavailable")
    receipt_tx_hash = receipt.get("transactionHash")
    receipt_block_hash = receipt.get("blockHash")
    receipt_block_number = _hex_int(receipt.get("blockNumber"))
    if not isinstance(receipt_tx_hash, str) or receipt_tx_hash.lower() != first_id[1]:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt transaction hash disagrees with probed log")
    if not isinstance(receipt_block_hash, str) or receipt_block_hash.lower() != first_id[0]:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt/log canonical block disagreement")
    if not start <= receipt_block_number <= end:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt escaped DEV-bounded probe range")
    canonical_receipt_hash = str(_block(rpc, receipt_block_number)["hash"]).lower()
    if receipt_block_hash.lower() != canonical_receipt_hash:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt block hash disagrees with canonical block metadata")

    event_records = [_event_identity(log) for log in ordered_a]
    return {
        "from_block": start,
        "to_block": end,
        "span_blocks": end - start + 1,
        "sync_log_count": len(event_records),
        "sync_log_identity_digest": _digest(event_records),
        "receipt_probe_transaction_hash": first_id[1],
        "receipt_probe_block_hash": first_id[0],
    }
''')

    coverage_marker = "\n\ndef qualify_source("
    coverage_function = '''\n\ndef _dev_log_coverage(
    rpc: RpcCall,
    start: int,
    end: int,
    query_span: int,
    canonical_block_hashes: dict[int, str] | None = None,
) -> dict[str, Any]:
    if query_span < 2:
        raise QualificationError("qualification query span must be >= 2")
    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    chunk_count = 0
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + query_span - 1)
        logs = sorted(
            _sync_logs(rpc, cursor, chunk_end, canonical_block_hashes),
            key=_log_order_key,
        )
        for log in logs:
            identity = _log_identity(log)
            if identity in seen:
                raise QualificationError("STOP_SOURCE_CONFLICT: duplicate canonical log identity across DEV chunks")
            seen.add(identity)
            records.append(_event_identity(log))
        chunk_count += 1
        cursor = chunk_end + 1
    return {
        "from_block": start,
        "to_block": end,
        "query_span_blocks": query_span,
        "chunk_count": chunk_count,
        "sync_log_count": len(records),
        "sync_log_identity_digest": _digest(records),
        "canonical_block_binding_verified": True,
    }
'''
    if "def _dev_log_coverage(" not in text:
        if coverage_marker not in text:
            raise SystemExit("coverage insertion marker missing")
        text = text.replace(coverage_marker, coverage_function + coverage_marker, 1)

    text = replace_function(text, "qualify_source", '''
def qualify_source(rpc: RpcCall, *, provider_id: str, probe_span: int = DEFAULT_PROBE_SPAN) -> dict[str, Any]:
    if not provider_id or any(token in provider_id.lower() for token in ("http://", "https://", "?key=", "apikey")):
        raise QualificationError("provider_id must be a non-secret label, never an endpoint URL")
    if probe_span < 2:
        raise QualificationError("qualification probe span must be >= 2")

    chain_id = _hex_int(rpc("eth_chainId", []))
    if chain_id != CHAIN_ID:
        raise QualificationError(f"STOP_SOURCE_CONFLICT: chain ID {chain_id} != {CHAIN_ID}")

    for label, address in (("pool", POOL), ("factory", FACTORY)):
        code = rpc("eth_getCode", [address, "latest"])
        if not _has_code(code):
            raise QualificationError(f"STOP_SOURCE_CONFLICT: {label} bytecode unavailable")

    token0 = _pool_call(rpc, TOKEN0_SELECTOR)
    token1 = _pool_call(rpc, TOKEN1_SELECTOR)
    if {token0, token1} != {_norm_address(KRAKMASK), _norm_address(WETH9)}:
        raise QualificationError("STOP_SOURCE_CONFLICT: pool token identity mismatch")
    pool_factory = _pool_call(rpc, FACTORY_SELECTOR)
    if pool_factory != _norm_address(FACTORY):
        raise QualificationError("STOP_SOURCE_CONFLICT: pool factory mismatch")

    t1 = find_block_at_or_before_timestamp(rpc, _cutoff_timestamp())
    t1_number = _hex_int(t1["number"])
    t1_timestamp = _hex_int(t1["timestamp"])
    if t1_timestamp > _cutoff_timestamp():
        raise QualificationError("STOP_SOURCE_CONFLICT: T1 block search crossed the frozen cutoff")

    canonical_block_hashes: dict[int, str] = {t1_number: str(t1["hash"]).lower()}
    deployment_block = find_first_code_block(rpc, POOL, t1_number)
    t0, t0_log = find_t0_sync(
        rpc,
        deployment_block,
        t1_number,
        canonical_block_hashes=canonical_block_hashes,
    )
    t0_number = _hex_int(t0["number"])
    t0_timestamp = _hex_int(t0["timestamp"])
    if _hex_int(t0_log["blockNumber"]) != t0_number:
        raise QualificationError("STOP_SOURCE_CONFLICT: T0 Sync/block disagreement")

    dev_end_timestamp = _dev_end_timestamp(t0_timestamp)
    history_seconds = _validate_history_window(t0_timestamp, dev_end_timestamp)
    dev_end = find_block_at_or_before_timestamp(rpc, dev_end_timestamp)
    dev_end_number = _hex_int(dev_end["number"])
    if dev_end_number < t0_number or _hex_int(dev_end["timestamp"]) > dev_end_timestamp:
        raise QualificationError("STOP_SOURCE_CONFLICT: mechanical DEV_END block is invalid")
    canonical_block_hashes[dev_end_number] = str(dev_end["hash"]).lower()

    probe = _bounded_log_integrity_probe(
        rpc,
        t0_number,
        dev_end_number,
        probe_span,
        canonical_block_hashes,
    )
    if probe["to_block"] > dev_end_number:
        raise QualificationError("STOP_SOURCE_CONFLICT: economic probe crossed DEV_END")

    coverage = _dev_log_coverage(
        rpc,
        t0_number,
        dev_end_number,
        probe_span,
        canonical_block_hashes,
    )
    if coverage["to_block"] != dev_end_number or coverage["from_block"] != t0_number:
        raise QualificationError("STOP_SOURCE_CONFLICT: DEV coverage did not span the full required range")
    if coverage["sync_log_count"] < 1:
        raise QualificationError("STOP_SOURCE_CONFLICT: DEV coverage contains no Sync observations")

    checks = [
        "CHAIN_ID_EXACT",
        "POOL_BYTECODE_PRESENT",
        "FACTORY_BYTECODE_PRESENT",
        "POOL_TOKEN_IDENTITY_EXACT",
        "POOL_FACTORY_EXACT",
        "T1_METADATA_RETRIEVABLE_WITHOUT_ECONOMIC_OUTER_REQUEST",
        "POOL_DEPLOYMENT_BOUNDARY_RETRIEVABLE",
        "T0_ESTABLISHED_OUTCOME_BLIND_BY_SINGLETON_SYNC_SCAN",
        "FROZEN_MINIMUM_HISTORY_30_18_12_DAYS",
        "DEV_END_COMPUTED_MECHANICALLY_BEFORE_MULTI_BLOCK_ECONOMIC_PROBE",
        "ECONOMIC_REQUESTS_HARD_CAPPED_AT_DEV_END",
        "EVERY_RETURNED_SYNC_BOUND_TO_CANONICAL_BLOCK_HASH",
        "BOUNDED_DEV_SYNC_LOG_RETRIEVAL",
        "REPEATED_REQUEST_DETERMINISTIC",
        "WHOLE_EQUALS_SPLIT_RANGE",
        "FULL_DEV_LOG_RANGE_COVERED_IN_BOUNDED_CHUNKS",
        "DEV_RECEIPT_TRANSACTION_AND_BLOCK_IDENTITY_BOUND",
        "RAW_SYNC_ECONOMIC_DATA_NOT_DECODED_OR_SERIALIZED",
    ]
    return {
        "artifact_type": "QNTYSPOT_INK_SOURCE_QUALIFICATION_RECEIPT_V1",
        "project_id": PROJECT_ID,
        "status": "PASS",
        "provider_id": provider_id,
        "provider_endpoint_serialized": False,
        "outcome_blind": True,
        "chain_id": chain_id,
        "pool": _norm_address(POOL),
        "factory": pool_factory,
        "token0": token0,
        "token1": token1,
        "frozen_cutoff_utc": CUTOFF_UTC,
        "t1_block": _block_summary(t1),
        "pool_deployment_block": deployment_block,
        "t0_block": _block_summary(t0),
        "t0_sync_identity": _event_identity(t0_log),
        "dev_end_timestamp": dev_end_timestamp,
        "dev_end_block": _block_summary(dev_end),
        "history_seconds": history_seconds,
        "bounded_probe": probe,
        "dev_log_coverage": coverage,
        "checks": checks,
        "raw_log_data_decoded": False,
        "raw_log_data_serialized": False,
        "outer_request_count": 0,
        "candidate_evaluation_performed": False,
        "outer_access_performed": False,
    }
''')

    text = replace_function(text, "material_identity", '''
def material_identity(receipt: Mapping[str, Any]) -> dict[str, Any]:
    probe = receipt["bounded_probe"]
    coverage = receipt["dev_log_coverage"]
    return {
        "chain_id": receipt["chain_id"],
        "pool": receipt["pool"],
        "factory": receipt["factory"],
        "tokens": sorted((receipt["token0"], receipt["token1"])),
        "t1_block": receipt["t1_block"],
        "pool_deployment_block": receipt["pool_deployment_block"],
        "t0_block": receipt["t0_block"],
        "t0_sync_identity": receipt["t0_sync_identity"],
        "dev_end_timestamp": receipt["dev_end_timestamp"],
        "dev_end_block": receipt["dev_end_block"],
        "history_seconds": receipt["history_seconds"],
        "bounded_probe_identity_digest": probe["sync_log_identity_digest"],
        "receipt_probe_transaction_hash": probe["receipt_probe_transaction_hash"],
        "receipt_probe_block_hash": probe["receipt_probe_block_hash"],
        "dev_log_coverage_identity_digest": coverage["sync_log_identity_digest"],
        "dev_log_coverage_count": coverage["sync_log_count"],
    }
''')

    git_anchor = '''def _git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()
'''
    git_add = '''\n\ndef _git_fetch_origin_master(root: Path) -> None:
    result = subprocess.run(
        ["git", "fetch", "--quiet", "origin", "master"],
        cwd=root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        raise QualificationError("canonical authority check could not refresh origin/master")


def _git_is_ancestor(root: Path, ancestor: str, descendant: str) -> bool:
    return subprocess.run(
        ["git", "merge-base", "--is-ancestor", ancestor, descendant],
        cwd=root,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    ).returncode == 0
'''
    if "def _git_fetch_origin_master(" not in text:
        if git_anchor not in text:
            raise SystemExit("git helper anchor missing")
        text = text.replace(git_anchor, git_anchor + git_add, 1)

    text = replace_function(text, "assert_canonical_stage_b_authority", '''
def assert_canonical_stage_b_authority(root: Path = Path(".")) -> None:
    branch = _git(root, "branch", "--show-current")
    if branch != "master":
        raise QualificationError("real source qualification is forbidden outside canonical master")
    if _git(root, "status", "--porcelain"):
        raise QualificationError("real source qualification requires a clean canonical worktree")

    _git_fetch_origin_master(root)
    try:
        head = _git(root, "rev-parse", "HEAD")
        origin_master = _git(root, "rev-parse", "origin/master")
    except subprocess.CalledProcessError as exc:
        raise QualificationError("canonical authority check could not resolve HEAD/origin/master") from exc
    if head != origin_master:
        raise QualificationError("STOP_SOURCE_CONFLICT: local master is not exact refreshed origin/master")

    registry = tomllib.loads((root / "docs/state/projects.toml").read_text(encoding="utf-8"))["project"]
    rows = {row["project_id"]: row for row in registry}
    current = rows.get(PROJECT_ID)
    predecessor = rows.get(PREDECESSOR_ID)
    if not current or current.get("state") != "ACTIVE_RESEARCH" or current.get("implementation_authorized") is not True:
        raise QualificationError("canonical Stage-B ACTIVE_RESEARCH authority is absent")
    if not predecessor or predecessor.get("state") != "CLOSED_PASS" or predecessor.get("implementation_authorized") is not False:
        raise QualificationError("Stage-A predecessor is not closed before Stage-B network authority")
    required_base = current.get("required_base_sha")
    if not isinstance(required_base, str) or not _git_is_ancestor(root, required_base, head):
        raise QualificationError("STOP_SOURCE_CONFLICT: Stage-B required canonical base is not an ancestor of HEAD")
''')

    SOURCE.write_text(text.rstrip() + "\n", encoding="utf-8")


def patch_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")
    text = text.replace(
        "def __init__(self, *, chain_id=qualifier.CHAIN_ID, nondeterministic=False, truncate_whole=False):",
        "def __init__(self, *, chain_id=qualifier.CHAIN_ID, nondeterministic=False, truncate_whole=False, block_seconds=12 * 60 * 60, stale_log_block_hash=False, wrong_receipt_tx=False):",
        1,
    )
    text = text.replace(
        "        self.truncate_whole = truncate_whole\n",
        "        self.truncate_whole = truncate_whole\n        self.block_seconds = block_seconds\n        self.stale_log_block_hash = stale_log_block_hash\n        self.wrong_receipt_tx = wrong_receipt_tx\n",
        1,
    )
    text = text.replace(
        '        timestamp = self.cutoff + ((number - 99) * 10)\n',
        '        timestamp = self.cutoff + ((number - 99) * self.block_seconds)\n',
        1,
    )
    text = text.replace(
        '            "blockHash": block_hash(number),\n',
        '            "blockHash": block_hash(number + 1) if self.stale_log_block_hash else block_hash(number),\n',
        1,
    )
    text = text.replace(
        '                "transactionHash": params[0],\n',
        '                "transactionHash": ("0x" + ("cd" * 32)) if self.wrong_receipt_tx else params[0],\n',
        1,
    )
    text = text.replace(
        '    assert receipt["outer_request_count"] == 0\n',
        '    assert receipt["outer_request_count"] == 0\n    assert receipt["history_seconds"]["total"] >= qualifier.MIN_TOTAL_HISTORY_SECONDS\n    assert receipt["history_seconds"]["dev"] >= qualifier.MIN_DEV_HISTORY_SECONDS\n    assert receipt["history_seconds"]["outer"] >= qualifier.MIN_OUTER_HISTORY_SECONDS\n    assert receipt["dev_log_coverage"]["from_block"] == 20\n    assert receipt["dev_log_coverage"]["to_block"] == 67\n    assert receipt["dev_log_coverage"]["canonical_block_binding_verified"] is True\n',
        1,
    )

    append = '''\n\ndef test_frozen_minimum_history_is_fail_closed():
    rpc = FakeRpc(block_seconds=10)
    with pytest.raises(qualifier.QualificationError, match="INSUFFICIENT_HISTORY"):
        qualifier.qualify_source(rpc, provider_id="too-short")


def test_stale_fork_log_hash_is_rejected_against_canonical_block_metadata():
    rpc = FakeRpc(stale_log_block_hash=True)
    with pytest.raises(qualifier.QualificationError, match="canonical block metadata"):
        qualifier.qualify_source(rpc, provider_id="stale-fork")


def test_receipt_transaction_identity_must_match_probed_log():
    rpc = FakeRpc(wrong_receipt_tx=True)
    with pytest.raises(qualifier.QualificationError, match="receipt transaction hash"):
        qualifier.qualify_source(rpc, provider_id="wrong-receipt")


def test_full_dev_range_is_covered_in_bounded_chunks():
    rpc = FakeRpc()
    receipt = qualifier.qualify_source(rpc, provider_id="chunked", probe_span=16)
    coverage = receipt["dev_log_coverage"]
    assert coverage["from_block"] == receipt["t0_block"]["number"]
    assert coverage["to_block"] == receipt["dev_end_block"]["number"]
    assert coverage["query_span_blocks"] == 16
    assert coverage["chunk_count"] == 3
    assert all(end <= receipt["dev_end_block"]["number"] for _, end in rpc.log_ranges)


def test_cross_provider_dev_log_identity_disagreement_fails_closed():
    primary = qualifier.qualify_source(FakeRpc(), provider_id="primary")
    secondary = json.loads(json.dumps(primary))
    secondary["dev_log_coverage"]["sync_log_identity_digest"] = "f" * 64
    with pytest.raises(qualifier.QualificationError, match="cross-provider"):
        qualifier.compare_sources(primary, secondary)


def test_canonical_authority_rejects_dirty_master_before_network_use(tmp_path: Path, monkeypatch):
    def fake_git(root, *args):
        if args == ("branch", "--show-current"):
            return "master"
        if args == ("status", "--porcelain"):
            return " M docs/state/projects.toml"
        raise AssertionError(args)

    monkeypatch.setattr(qualifier, "_git", fake_git)
    with pytest.raises(qualifier.QualificationError, match="clean canonical worktree"):
        qualifier.assert_canonical_stage_b_authority(tmp_path)


def test_canonical_authority_rejects_divergent_local_master(tmp_path: Path, monkeypatch):
    def fake_git(root, *args):
        if args == ("branch", "--show-current"):
            return "master"
        if args == ("status", "--porcelain"):
            return ""
        if args == ("rev-parse", "HEAD"):
            return "a" * 40
        if args == ("rev-parse", "origin/master"):
            return "b" * 40
        raise AssertionError(args)

    monkeypatch.setattr(qualifier, "_git", fake_git)
    monkeypatch.setattr(qualifier, "_git_fetch_origin_master", lambda root: None)
    with pytest.raises(qualifier.QualificationError, match="exact refreshed origin/master"):
        qualifier.assert_canonical_stage_b_authority(tmp_path)


def test_canonical_authority_accepts_clean_exact_origin_master_with_required_base(tmp_path: Path, monkeypatch):
    projects = tmp_path / "docs/state"
    projects.mkdir(parents=True)
    required_base = "e" * 40
    (projects / "projects.toml").write_text(
        "schema_version = 1\\n"
        "[[project]]\\n"
        f'project_id = "{qualifier.PREDECESSOR_ID}"\\n'
        'state = "CLOSED_PASS"\\n'
        'implementation_authorized = false\\n'
        "[[project]]\\n"
        f'project_id = "{qualifier.PROJECT_ID}"\\n'
        'state = "ACTIVE_RESEARCH"\\n'
        'implementation_authorized = true\\n'
        f'required_base_sha = "{required_base}"\\n',
        encoding="utf-8",
    )

    def fake_git(root, *args):
        if args == ("branch", "--show-current"):
            return "master"
        if args == ("status", "--porcelain"):
            return ""
        if args in (("rev-parse", "HEAD"), ("rev-parse", "origin/master")):
            return "a" * 40
        raise AssertionError(args)

    monkeypatch.setattr(qualifier, "_git", fake_git)
    monkeypatch.setattr(qualifier, "_git_fetch_origin_master", lambda root: None)
    monkeypatch.setattr(qualifier, "_git_is_ancestor", lambda root, ancestor, descendant: ancestor == required_base)
    qualifier.assert_canonical_stage_b_authority(tmp_path)
'''
    if "test_frozen_minimum_history_is_fail_closed" not in text:
        text = text.rstrip() + append + "\n"
    TESTS.write_text(text, encoding="utf-8")


def patch_authorization() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    canonical = auth["canonicalization"]
    canonical["runtime_required_branch"] = "master"
    canonical["runtime_requires_clean_worktree"] = True
    canonical["runtime_refresh_origin_master_before_check"] = True
    canonical["runtime_head_must_equal_refreshed_origin_master"] = True
    canonical["runtime_required_base_must_be_ancestor"] = True

    frozen = auth["frozen_scientific_binding"]
    frozen["minimum_history_days"] = {"total_calendar_history": 30, "dev": 18, "outer": 12}
    frozen["insufficient_history_state"] = "INSUFFICIENT_HISTORY"

    source = auth["source_qualification_contract"]
    source["full_dev_log_identity_coverage_required"] = True
    source["provider_range_limit_strategy"] = "scan the complete DEV block interval in non-overlapping chunks no wider than the validated probe span"
    source["canonical_log_block_binding_required"] = True
    source["receipt_transaction_and_block_binding_required"] = True
    source["cross_provider_material_identity_includes_dev_log_digest"] = True
    source["required_checks"] = [
        "chain ID equals 57073",
        "pool bytecode exists",
        "factory bytecode exists",
        "pool token0/token1 are exactly KRAKMASK and WETH9 in either order",
        "pool factory equals the frozen InkySwap V2 factory",
        "historical T1 block metadata is retrievable without requesting OUTER economic observations",
        "historical pool deployment boundary is retrievable from bytecode",
        "T0 is established outcome-blind by singleton Sync requests",
        "the preregistered 30-day total / 18-day DEV / 12-day OUTER minimum-history rule passes",
        "DEV_END is computed mechanically before any multi-block economic log request",
        "every economic log request is bounded at or before DEV_END",
        "every returned Sync log block hash agrees with canonical block metadata",
        "pool Sync log retrieval works on a bounded DEV historical probe",
        "repeated historical requests are deterministic",
        "whole-range logs equal the union of adjacent half-range logs",
        "the complete DEV block interval is covered in bounded non-overlapping log-query chunks",
        "the receipt transaction hash and block hash agree with the probed log and canonical block metadata",
        "cross-provider material comparison includes T0, DEV_END, probe receipt, and complete DEV log-identity digest",
    ]
    AUTH.write_text(json.dumps(auth, indent=2) + "\n", encoding="utf-8")


def patch_stage_tests() -> None:
    text = STAGE_TESTS.read_text(encoding="utf-8")
    text = text.replace(
        '    assert auth["canonicalization"]["effective_only_after_exact_canonical_merge"] is True\n',
        '    assert auth["canonicalization"]["effective_only_after_exact_canonical_merge"] is True\n    assert auth["canonicalization"]["runtime_requires_clean_worktree"] is True\n    assert auth["canonicalization"]["runtime_refresh_origin_master_before_check"] is True\n    assert auth["canonicalization"]["runtime_head_must_equal_refreshed_origin_master"] is True\n    assert auth["canonicalization"]["runtime_required_base_must_be_ancestor"] is True\n',
        1,
    )
    text = text.replace(
        '    assert frozen["scientific_design_mutation"] is False\n',
        '    assert frozen["scientific_design_mutation"] is False\n    assert frozen["minimum_history_days"] == {"total_calendar_history": 30, "dev": 18, "outer": 12}\n    assert frozen["insufficient_history_state"] == "INSUFFICIENT_HISTORY"\n',
        1,
    )
    text = text.replace(
        '    assert source["silent_truncation_or_nondeterminism"] == "STOP_SOURCE_CONFLICT"\n',
        '    assert source["silent_truncation_or_nondeterminism"] == "STOP_SOURCE_CONFLICT"\n    assert source["full_dev_log_identity_coverage_required"] is True\n    assert source["canonical_log_block_binding_required"] is True\n    assert source["receipt_transaction_and_block_binding_required"] is True\n    assert source["cross_provider_material_identity_includes_dev_log_digest"] is True\n',
        1,
    )
    STAGE_TESTS.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_source()
    patch_tests()
    patch_authorization()
    patch_stage_tests()
