import json
from pathlib import Path

import pytest

from qntylab import qntyspot_ink_source_qualification_v1 as qualifier


def address_word(address: str) -> str:
    return "0x" + ("0" * 24) + address[2:].lower()


def block_hash(number: int) -> str:
    return "0x" + f"{number:064x}"


class FakeRpc:
    def __init__(self, *, chain_id=qualifier.CHAIN_ID, nondeterministic=False, truncate_whole=False):
        self.chain_id = chain_id
        self.nondeterministic = nondeterministic
        self.truncate_whole = truncate_whole
        self.log_calls = 0
        self.log_ranges = []
        self.whole_log_range = None
        self.whole_range_calls = 0
        self.cutoff = qualifier._cutoff_timestamp()
        self.deployment_block = 10
        self.sync_block = 20

    def _block(self, number: int):
        # block 99 lands exactly on frozen T1, block 100 is later.
        timestamp = self.cutoff + ((number - 99) * 10)
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
            "blockHash": block_hash(number),
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
                "transactionHash": params[0],
                "blockHash": block_hash(self.sync_block),
                "blockNumber": hex(self.sync_block),
                "status": "0x1",
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
