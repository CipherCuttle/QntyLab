import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from qntylab import qntyspot_ink_source_qualification_v1 as qualifier


def address_word(address: str) -> str:
    return "0x" + ("0" * 24) + address[2:].lower()


def block_hash(number: int) -> str:
    return "0x" + f"{number:064x}"


class FakeRpc:
    def __init__(self, *, chain_id=qualifier.CHAIN_ID, nondeterministic=False, truncate_whole=False, block_seconds=12 * 60 * 60, stale_log_block_hash=False, wrong_receipt_tx=False):
        self.chain_id = chain_id
        self.nondeterministic = nondeterministic
        self.truncate_whole = truncate_whole
        self.block_seconds = block_seconds
        self.stale_log_block_hash = stale_log_block_hash
        self.wrong_receipt_tx = wrong_receipt_tx
        self.log_calls = 0
        self.log_ranges = []
        self.whole_log_range = None
        self.whole_range_calls = 0
        self.cutoff = qualifier._cutoff_timestamp()
        self.deployment_block = 10
        self.sync_block = 20

    def _block(self, number: int):
        # block 99 lands exactly on frozen T1, block 100 is later.
        timestamp = self.cutoff + ((number - 99) * self.block_seconds)
        return {
            "number": hex(number),
            "hash": block_hash(number),
            "timestamp": hex(timestamp),
        }

    def _sync(self):
        number = self.sync_block
        return {
            "address": qualifier.POOL,
            "blockNumber": hex(number),
            "blockHash": block_hash(number + 1) if self.stale_log_block_hash else block_hash(number),
            "transactionHash": "0x" + ("ab" * 32),
            "transactionIndex": "0x1",
            "logIndex": "0x2",
            "removed": False,
            "topics": [qualifier.SYNC_TOPIC],
            # Deliberate canary: qualification must never decode/copy this field.
            "data": "0x" + ("deadbeef" * 16),
        }

    def __call__(self, method, params):
        if method == "eth_chainId":
            return hex(self.chain_id)
        if method == "eth_blockNumber":
            return hex(100)
        if method == "eth_getBlockByNumber":
            return self._block(int(params[0], 16))
        if method == "eth_getCode":
            address, tag = params
            if address.lower() == qualifier.POOL.lower() and tag != "latest":
                return "0x6001600055" if int(tag, 16) >= self.deployment_block else "0x"
            return "0x6001600055"
        if method == "eth_call":
            selector = params[0]["data"]
            if selector == qualifier.TOKEN0_SELECTOR:
                return address_word(qualifier.KRAKMASK)
            if selector == qualifier.TOKEN1_SELECTOR:
                return address_word(qualifier.WETH9)
            if selector == qualifier.FACTORY_SELECTOR:
                return address_word(qualifier.FACTORY)
            raise AssertionError(selector)
        if method == "eth_getLogs":
            self.log_calls += 1
            start = int(params[0]["fromBlock"], 16)
            end = int(params[0]["toBlock"], 16)
            self.log_ranges.append((start, end))
            contains = start <= self.sync_block <= end

            # T0 discovery uses singleton requests. The first multi-block request
            # is the integrity probe's whole range; halves are strictly smaller.
            if end > start:
                if self.whole_log_range is None:
                    self.whole_log_range = (start, end)
                if (start, end) == self.whole_log_range:
                    self.whole_range_calls += 1
                    if self.nondeterministic and self.whole_range_calls == 2:
                        return []
                    if self.truncate_whole:
                        return []
            return [self._sync()] if contains else []
        if method == "eth_getTransactionReceipt":
            return {
                "transactionHash": ("0x" + ("cd" * 32)) if self.wrong_receipt_tx else params[0],
                "blockHash": block_hash(self.sync_block),
                "blockNumber": hex(self.sync_block),
                "status": "0x1",
                "gasUsed": "0x5208",
                "effectiveGasPrice": "0x3b9aca00",
            }
        raise AssertionError(method)


def test_source_qualification_passes_and_never_requests_outer_economic_logs():
    rpc = FakeRpc()
    receipt = qualifier.qualify_source(rpc, provider_id="primary-archive")
    assert receipt["status"] == "PASS"
    assert receipt["chain_id"] == 57073
    assert receipt["t1_block"]["number"] == 99
    assert receipt["pool_deployment_block"] == 10
    assert receipt["t0_block"]["number"] == 20
    assert receipt["dev_end_block"]["number"] == 67
    assert receipt["bounded_probe"]["from_block"] == 20
    assert receipt["bounded_probe"]["to_block"] == 67
    assert receipt["bounded_probe"]["sync_log_count"] == 1
    assert receipt["outer_request_count"] == 0
    assert receipt["history_seconds"]["total"] >= qualifier.MIN_TOTAL_HISTORY_SECONDS
    assert receipt["history_seconds"]["dev"] >= qualifier.MIN_DEV_HISTORY_SECONDS
    assert receipt["history_seconds"]["outer"] >= qualifier.MIN_OUTER_HISTORY_SECONDS
    assert receipt["dev_log_coverage"]["from_block"] == 20
    assert receipt["dev_log_coverage"]["to_block"] == 67
    assert receipt["dev_log_coverage"]["canonical_block_binding_verified"] is True
    assert receipt["outer_access_performed"] is False
    assert all(end <= receipt["dev_end_block"]["number"] for _, end in rpc.log_ranges)


def test_source_qualification_does_not_decode_or_serialize_economic_log_data_or_endpoint():
    rpc = FakeRpc()
    receipt = qualifier.qualify_source(rpc, provider_id="primary-archive")
    assert receipt["raw_log_data_decoded"] is False
    assert receipt["raw_log_data_serialized"] is False
    encoded = json.dumps(receipt)
    assert "deadbeef" not in encoded
    assert "http://" not in encoded and "https://" not in encoded
    assert "RAW_SYNC_ECONOMIC_DATA_NOT_DECODED_OR_SERIALIZED" in receipt["checks"]


def test_wrong_chain_fails_closed_before_log_probe():
    rpc = FakeRpc(chain_id=1)
    with pytest.raises(qualifier.QualificationError, match="chain ID"):
        qualifier.qualify_source(rpc, provider_id="wrong-chain")
    assert rpc.log_calls == 0


def test_repeated_request_nondeterminism_stops_source():
    rpc = FakeRpc(nondeterministic=True)
    with pytest.raises(qualifier.QualificationError, match="nondeterministic"):
        qualifier.qualify_source(rpc, provider_id="unstable")


def test_whole_vs_split_range_mismatch_detects_silent_truncation():
    rpc = FakeRpc(truncate_whole=True)
    with pytest.raises(qualifier.QualificationError, match="whole-range logs disagree"):
        qualifier.qualify_source(rpc, provider_id="truncated")


def test_provider_id_cannot_be_endpoint_or_apikey_label():
    rpc = FakeRpc()
    for provider_id in ("https://rpc.example/key", "foo?key=secret", "apikey-prod"):
        with pytest.raises(qualifier.QualificationError, match="non-secret label"):
            qualifier.qualify_source(rpc, provider_id=provider_id)


def test_cross_provider_material_disagreement_fails_closed():
    primary = qualifier.qualify_source(FakeRpc(), provider_id="primary")
    secondary = dict(primary)
    secondary["t1_block"] = dict(primary["t1_block"], hash="0x" + ("ff" * 32))
    with pytest.raises(qualifier.QualificationError, match="cross-provider"):
        qualifier.compare_sources(primary, secondary)


def test_receipt_digest_writer_is_deterministic_and_does_not_mutate_input(tmp_path: Path):
    value = qualifier.qualify_source(FakeRpc(), provider_id="primary")
    before = json.loads(json.dumps(value))
    path = tmp_path / "receipt.json"
    qualifier._write_receipt(path, value)
    written = json.loads(path.read_text(encoding="utf-8"))
    assert value == before
    assert written["receipt_digest"] == qualifier._digest(value)


def test_candidate_branch_guard_happens_before_endpoint_use(tmp_path: Path, monkeypatch):
    projects = tmp_path / "docs/state"
    projects.mkdir(parents=True)
    (projects / "projects.toml").write_text(
        "schema_version = 1\n"
        "[[project]]\n"
        f'project_id = "{qualifier.PREDECESSOR_ID}"\n'
        'state = "CLOSED_PASS"\n'
        'implementation_authorized = false\n'
        "[[project]]\n"
        f'project_id = "{qualifier.PROJECT_ID}"\n'
        'state = "ACTIVE_RESEARCH"\n'
        'implementation_authorized = true\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(qualifier, "_git", lambda root, *args: "research/qntyspot-shadow-performance-dev-acquisition-v1")
    with pytest.raises(qualifier.QualificationError, match="forbidden outside canonical master"):
        qualifier.assert_canonical_stage_b_authority(tmp_path)

def test_frozen_minimum_history_is_fail_closed():
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
        "schema_version = 1\n"
        "[[project]]\n"
        f'project_id = "{qualifier.PREDECESSOR_ID}"\n'
        'state = "CLOSED_PASS"\n'
        'implementation_authorized = false\n'
        "[[project]]\n"
        f'project_id = "{qualifier.PROJECT_ID}"\n'
        'state = "ACTIVE_RESEARCH"\n'
        'implementation_authorized = true\n'
        f'required_base_sha = "{required_base}"\n'
        f'reviewed_candidate_sha = "{"c" * 40}"\n',
        encoding="utf-8",
    )

    def fake_git(root, *args):
        if args == ("branch", "--show-current"):
            return "master"
        if args == ("status", "--porcelain"):
            return ""
        if args in (("rev-parse", "HEAD"), ("rev-parse", "origin/master")):
            return "a" * 40
        if args == ("remote", "get-url", "origin"):
            return "git@github.com:CipherCuttle/QntyLab.git"
        raise AssertionError(args)

    monkeypatch.setattr(qualifier, "_git", fake_git)
    monkeypatch.setattr(qualifier, "_git_fetch_origin_master", lambda root: None)
    monkeypatch.setattr(
        qualifier,
        "_git_is_ancestor",
        lambda root, ancestor, descendant: ancestor in {required_base, "c" * 40},
    )
    qualifier.assert_canonical_stage_b_authority(tmp_path)

def test_receipt_must_expose_frozen_gas_rule_fields():
    class MissingGasRpc(FakeRpc):
        def __call__(self, method, params):
            value = super().__call__(method, params)
            if method == "eth_getTransactionReceipt":
                value = dict(value)
                value.pop("gasUsed", None)
                value.pop("effectiveGasPrice", None)
            return value

    with pytest.raises(qualifier.QualificationError, match="gasUsed"):
        qualifier.qualify_source(MissingGasRpc(), provider_id="missing-gas")


def test_canonical_authority_requires_reviewed_candidate_pin(tmp_path: Path, monkeypatch):
    projects = tmp_path / "docs/state"
    projects.mkdir(parents=True)
    required_base = "e" * 40
    (projects / "projects.toml").write_text(
        "schema_version = 1\n"
        "[[project]]\n"
        f'project_id = "{qualifier.PREDECESSOR_ID}"\n'
        'state = "CLOSED_PASS"\n'
        'implementation_authorized = false\n'
        "[[project]]\n"
        f'project_id = "{qualifier.PROJECT_ID}"\n'
        'state = "ACTIVE_RESEARCH"\n'
        'implementation_authorized = true\n'
        f'required_base_sha = "{required_base}"\n'
        'reviewed_candidate_sha = "not-a-sha"\n',
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
    with pytest.raises(qualifier.QualificationError, match="reviewed Stage-B candidate is not pinned"):
        qualifier.assert_canonical_stage_b_authority(tmp_path)


def test_canonical_authority_rejects_reviewed_candidate_not_in_canonical_history(tmp_path: Path, monkeypatch):
    projects = tmp_path / "docs/state"
    projects.mkdir(parents=True)
    required_base = "e" * 40
    reviewed = "c" * 40
    (projects / "projects.toml").write_text(
        "schema_version = 1\n"
        "[[project]]\n"
        f'project_id = "{qualifier.PREDECESSOR_ID}"\n'
        'state = "CLOSED_PASS"\n'
        'implementation_authorized = false\n'
        "[[project]]\n"
        f'project_id = "{qualifier.PROJECT_ID}"\n'
        'state = "ACTIVE_RESEARCH"\n'
        'implementation_authorized = true\n'
        f'required_base_sha = "{required_base}"\n'
        f'reviewed_candidate_sha = "{reviewed}"\n',
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

    calls = []
    def fake_ancestor(root, ancestor, descendant):
        calls.append(ancestor)
        return ancestor == required_base

    monkeypatch.setattr(qualifier, "_git", fake_git)
    monkeypatch.setattr(qualifier, "_git_fetch_origin_master", lambda root: None)
    monkeypatch.setattr(qualifier, "_git_is_ancestor", fake_ancestor)
    with pytest.raises(qualifier.QualificationError, match="reviewed Stage-B candidate is not canonical"):
        qualifier.assert_canonical_stage_b_authority(tmp_path)
    assert calls == [required_base, reviewed]

def test_full_dev_coverage_detects_silent_truncation_in_later_chunk():
    class LateTruncationRpc(FakeRpc):
        extra_sync_block = 50

        def _sync_at(self, number):
            value = dict(self._sync())
            value["blockNumber"] = hex(number)
            value["blockHash"] = block_hash(number)
            value["transactionHash"] = "0x" + f"{number:064x}"
            return value

        def __call__(self, method, params):
            if method != "eth_getLogs":
                return super().__call__(method, params)
            self.log_calls += 1
            start = int(params[0]["fromBlock"], 16)
            end = int(params[0]["toBlock"], 16)
            self.log_ranges.append((start, end))
            # With probe_span=16, 36..51 is the second full DEV coverage chunk.
            # Simulate a provider that silently drops its log only on that whole
            # request while the adjacent half request still reveals block 50.
            if (start, end) == (36, 51):
                return []
            logs = []
            for number in (self.sync_block, self.extra_sync_block):
                if start <= number <= end:
                    logs.append(self._sync_at(number))
            return logs

    with pytest.raises(qualifier.QualificationError, match="DEV chunk whole-range logs disagree"):
        qualifier.qualify_source(LateTruncationRpc(), provider_id="late-truncation", probe_span=16)


def test_canonical_authority_rejects_noncanonical_origin(tmp_path: Path, monkeypatch):
    projects = tmp_path / "docs/state"
    projects.mkdir(parents=True)
    required_base = "e" * 40
    reviewed = "c" * 40
    (projects / "projects.toml").write_text(
        "schema_version = 1\n"
        "[[project]]\n"
        f'project_id = "{qualifier.PREDECESSOR_ID}"\n'
        'state = "CLOSED_PASS"\n'
        'implementation_authorized = false\n'
        "[[project]]\n"
        f'project_id = "{qualifier.PROJECT_ID}"\n'
        'state = "ACTIVE_RESEARCH"\n'
        'implementation_authorized = true\n'
        f'required_base_sha = "{required_base}"\n'
        f'reviewed_candidate_sha = "{reviewed}"\n',
        encoding="utf-8",
    )

    def fake_git(root, *args):
        if args == ("branch", "--show-current"):
            return "master"
        if args == ("status", "--porcelain"):
            return ""
        if args in (("rev-parse", "HEAD"), ("rev-parse", "origin/master")):
            return "a" * 40
        if args == ("remote", "get-url", "origin"):
            return "https://github.com/attacker/QntyLab.git"
        raise AssertionError(args)

    monkeypatch.setattr(qualifier, "_git", fake_git)
    monkeypatch.setattr(qualifier, "_git_fetch_origin_master", lambda root: None)
    monkeypatch.setattr(qualifier, "_git_is_ancestor", lambda root, ancestor, descendant: True)
    with pytest.raises(qualifier.QualificationError, match="canonical GitHub repository"):
        qualifier.assert_canonical_stage_b_authority(tmp_path)



def test_parallel_dev_coverage_matches_serial_material_identity():
    serial = qualifier.qualify_source(
        FakeRpc(), provider_id="serial", probe_span=16, coverage_workers=1
    )
    parallel = qualifier.qualify_source(
        FakeRpc(), provider_id="parallel", probe_span=16, coverage_workers=4
    )
    assert qualifier.material_identity(serial) == qualifier.material_identity(parallel)
    assert parallel["dev_log_coverage"]["worker_count"] == 4
    assert parallel["dev_log_coverage"]["chunk_count"] == serial["dev_log_coverage"]["chunk_count"]


def test_invalid_parallel_worker_count_fails_before_network_use():
    rpc = FakeRpc()
    with pytest.raises(qualifier.QualificationError, match="coverage workers"):
        qualifier.qualify_source(rpc, provider_id="workers-zero", coverage_workers=0)
    assert rpc.log_calls == 0


def test_json_rpc_client_uses_explicit_transport_identity_and_thread_safe_ids(monkeypatch):
    seen_ids = []
    seen_user_agents = []
    seen_lock = threading.Lock()

    class Response:
        def __init__(self, payload):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return self.payload

    def fake_urlopen(request, timeout):
        payload = json.loads(request.data.decode("utf-8"))
        with seen_lock:
            seen_ids.append(payload["id"])
            seen_user_agents.append(dict(request.header_items()).get("User-agent"))
        time.sleep(0.005)
        return Response(json.dumps({"jsonrpc": "2.0", "id": payload["id"], "result": "0xdec1"}).encode())

    monkeypatch.setattr(qualifier.urllib.request, "urlopen", fake_urlopen)
    client = qualifier.JsonRpcClient("https://rpc.example")
    with ThreadPoolExecutor(max_workers=8) as executor:
        values = list(executor.map(lambda _: client.call("eth_chainId", []), range(32)))
    assert values == ["0xdec1"] * 32
    assert sorted(seen_ids) == list(range(1, 33))
    assert set(seen_user_agents) == {"QntyLab-StageB-SourceQualification/1.0"}



def test_json_rpc_client_retries_http_429_with_same_payload_and_request_id(monkeypatch):
    seen_payloads = []
    sleeps = []
    attempts = 0

    class Response:
        def __init__(self, payload):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return self.payload

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        seen_payloads.append(request.data)
        payload = json.loads(request.data.decode("utf-8"))
        if attempts <= 2:
            raise qualifier.urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                {"Retry-After": "0"},
                None,
            )
        return Response(json.dumps({
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": "0xdec1",
        }).encode())

    monkeypatch.setattr(qualifier.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(qualifier.time, "sleep", sleeps.append)
    client = qualifier.JsonRpcClient("https://rpc.example")
    assert client.call("eth_chainId", []) == "0xdec1"
    assert attempts == 3
    assert len(set(seen_payloads)) == 1
    assert json.loads(seen_payloads[0].decode("utf-8"))["id"] == 1
    assert client.request_id == 1
    assert sleeps == [2.0, 4.0]


def test_json_rpc_client_honors_retry_after_with_bounded_cap(monkeypatch):
    sleeps = []
    attempts = 0

    class Response:
        def __init__(self, payload):
            self.payload = payload
        def __enter__(self):
            return self
        def __exit__(self, exc_type, exc, tb):
            return False
        def read(self):
            return self.payload

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        payload = json.loads(request.data.decode("utf-8"))
        if attempts == 1:
            raise qualifier.urllib.error.HTTPError(
                request.full_url,
                429,
                "Too Many Requests",
                {"Retry-After": "120"},
                None,
            )
        return Response(json.dumps({
            "jsonrpc": "2.0",
            "id": payload["id"],
            "result": "ok",
        }).encode())

    monkeypatch.setattr(qualifier.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(qualifier.time, "sleep", sleeps.append)
    assert qualifier.JsonRpcClient("https://rpc.example").call("eth_chainId", []) == "ok"
    assert sleeps == [qualifier.MAX_RATE_LIMIT_BACKOFF_SECONDS]


def test_json_rpc_client_exhausts_429_retries_fail_closed(monkeypatch):
    attempts = 0
    sleeps = []

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        raise qualifier.urllib.error.HTTPError(
            request.full_url,
            429,
            "Too Many Requests",
            {},
            None,
        )

    monkeypatch.setattr(qualifier, "DEFAULT_RATE_LIMIT_RETRIES", 2)
    monkeypatch.setattr(qualifier, "DEFAULT_RATE_LIMIT_BACKOFF_SECONDS", 0.1)
    monkeypatch.setattr(qualifier, "MAX_RATE_LIMIT_BACKOFF_SECONDS", 0.2)
    monkeypatch.setattr(qualifier.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(qualifier.time, "sleep", sleeps.append)
    with pytest.raises(qualifier.QualificationError, match="HTTPError"):
        qualifier.JsonRpcClient("https://rpc.example").call("eth_getLogs", [])
    assert attempts == 3
    assert sleeps == [0.1, 0.2]


def test_json_rpc_client_does_not_retry_non_429_http_errors(monkeypatch):
    attempts = 0
    sleeps = []

    def fake_urlopen(request, timeout):
        nonlocal attempts
        attempts += 1
        raise qualifier.urllib.error.HTTPError(
            request.full_url,
            403,
            "Forbidden",
            {},
            None,
        )

    monkeypatch.setattr(qualifier.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(qualifier.time, "sleep", sleeps.append)
    with pytest.raises(qualifier.QualificationError, match="HTTPError"):
        qualifier.JsonRpcClient("https://rpc.example").call("eth_chainId", [])
    assert attempts == 1
    assert sleeps == []


def test_parallel_block_attestation_fetches_unique_headers_concurrently_and_caches():
    class HeaderRpc:
        def __init__(self):
            self.lock = threading.Lock()
            self.active = 0
            self.max_active = 0
            self.block_calls = []

        def __call__(self, method, params):
            if method == "eth_getLogs":
                start = int(params[0]["fromBlock"], 16)
                end = int(params[0]["toBlock"], 16)
                rows = []
                for number in range(start, end + 1):
                    rows.append({
                        "address": qualifier.POOL,
                        "blockNumber": hex(number),
                        "blockHash": block_hash(number),
                        "transactionHash": "0x" + f"{number:064x}",
                        "transactionIndex": "0x0",
                        "logIndex": "0x0",
                        "removed": False,
                        "topics": [qualifier.SYNC_TOPIC],
                        "data": "0x",
                    })
                return rows
            if method == "eth_getBlockByNumber":
                number = int(params[0], 16)
                with self.lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                    self.block_calls.append(number)
                time.sleep(0.01)
                with self.lock:
                    self.active -= 1
                return {
                    "number": hex(number),
                    "hash": block_hash(number),
                    "timestamp": "0x1",
                }
            raise AssertionError(method)

    rpc = HeaderRpc()
    cache = {}
    first = qualifier._sync_logs(
        rpc, 10, 13, cache, block_attestation_workers=4
    )
    assert len(first) == 4
    assert sorted(rpc.block_calls) == [10, 11, 12, 13]
    assert rpc.max_active >= 2

    second = qualifier._sync_logs(
        rpc, 10, 13, cache, block_attestation_workers=4
    )
    assert len(second) == 4
    assert sorted(rpc.block_calls) == [10, 11, 12, 13]


def test_parallel_block_attestation_still_rejects_stale_log_hash():
    class StaleHeaderRpc:
        def __call__(self, method, params):
            if method == "eth_getLogs":
                return [
                    {
                        "address": qualifier.POOL,
                        "blockNumber": "0xa",
                        "blockHash": block_hash(11),
                        "transactionHash": "0x" + ("ab" * 32),
                        "transactionIndex": "0x0",
                        "logIndex": "0x0",
                        "removed": False,
                        "topics": [qualifier.SYNC_TOPIC],
                        "data": "0x",
                    }
                ]
            if method == "eth_getBlockByNumber":
                return {
                    "number": "0xa",
                    "hash": block_hash(10),
                    "timestamp": "0x1",
                }
            raise AssertionError(method)

    with pytest.raises(qualifier.QualificationError, match="canonical block metadata"):
        qualifier._sync_logs(
            StaleHeaderRpc(), 10, 10, {}, block_attestation_workers=4
        )


def test_parallel_block_attestation_preserves_material_identity():
    serial = qualifier.qualify_source(
        FakeRpc(),
        provider_id="serial-block-attestation",
        probe_span=16,
        coverage_workers=2,
        block_attestation_workers=1,
    )
    parallel = qualifier.qualify_source(
        FakeRpc(),
        provider_id="parallel-block-attestation",
        probe_span=16,
        coverage_workers=2,
        block_attestation_workers=4,
    )
    assert qualifier.material_identity(serial) == qualifier.material_identity(parallel)
    assert serial["dev_log_coverage"]["block_attestation_worker_count"] == 1
    assert parallel["dev_log_coverage"]["block_attestation_worker_count"] == 4


def test_invalid_block_attestation_worker_count_fails_before_network_use():
    rpc = FakeRpc()
    with pytest.raises(qualifier.QualificationError, match="block attestation workers"):
        qualifier.qualify_source(
            rpc,
            provider_id="block-workers-zero",
            block_attestation_workers=0,
        )
    assert rpc.log_calls == 0


def test_timestamp_lookup_steps_back_from_unretrievable_advertised_head():
    class HeadSkewRpc(FakeRpc):
        def __call__(self, method, params):
            if method == "eth_blockNumber":
                return hex(100)
            if method == "eth_getBlockByNumber" and int(params[0], 16) == 100:
                return None
            return super().__call__(method, params)

    block = qualifier.find_block_at_or_before_timestamp(
        HeadSkewRpc(), qualifier._cutoff_timestamp()
    )
    assert qualifier._hex_int(block["number"]) == 99
    assert qualifier._hex_int(block["timestamp"]) == qualifier._cutoff_timestamp()


def test_timestamp_lookup_fails_when_advertised_head_gap_exceeds_bound(monkeypatch):
    class MissingHeadRpc(FakeRpc):
        def __call__(self, method, params):
            if method == "eth_blockNumber":
                return hex(100)
            if method == "eth_getBlockByNumber":
                number = int(params[0], 16)
                if number >= 98:
                    return None
            return super().__call__(method, params)

    monkeypatch.setattr(qualifier, "MAX_HEAD_LOOKBACK_BLOCKS", 1)
    with pytest.raises(
        qualifier.QualificationError,
        match="unavailable within bounded metadata lookback",
    ):
        qualifier.find_block_at_or_before_timestamp(
            MissingHeadRpc(), qualifier._cutoff_timestamp()
        )


def test_timestamp_lookup_does_not_hide_malformed_non_null_head():
    class MalformedHeadRpc(FakeRpc):
        def __call__(self, method, params):
            if method == "eth_blockNumber":
                return hex(100)
            if method == "eth_getBlockByNumber" and int(params[0], 16) == 100:
                return "not-a-block"
            return super().__call__(method, params)

    with pytest.raises(qualifier.QualificationError, match="historical block malformed"):
        qualifier.find_block_at_or_before_timestamp(
            MalformedHeadRpc(), qualifier._cutoff_timestamp()
        )
