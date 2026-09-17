import json
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
