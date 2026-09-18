import json
from pathlib import Path

import pytest

from qntylab import qntyspot_ink_dev_acquisition_v1 as acquisition
from qntylab import qntyspot_ink_source_qualification_v1 as qualification


def _block_hash(number: int) -> str:
    return "0x" + f"{number:064x}"


def _tx_hash(number: int) -> str:
    return "0x" + f"{number + 10_000:064x}"


def _sync_log(block: int, tx_index: int, log_index: int, reserve0: int, reserve1: int):
    return {
        "address": qualification.POOL,
        "blockNumber": hex(block),
        "blockHash": _block_hash(block),
        "transactionHash": _tx_hash(block),
        "transactionIndex": hex(tx_index),
        "logIndex": hex(log_index),
        "removed": False,
        "topics": [qualification.SYNC_TOPIC],
        "data": "0x" + f"{reserve0:064x}" + f"{reserve1:064x}",
    }


def _swap_log(block: int, tx_index: int, log_index: int):
    return {
        "address": qualification.POOL,
        "blockNumber": hex(block),
        "blockHash": _block_hash(block),
        "transactionHash": _tx_hash(block),
        "transactionIndex": hex(tx_index),
        "logIndex": hex(log_index),
        "removed": False,
        "topics": [acquisition.SWAP_TOPIC],
        "data": "0x",
    }


SYNC_LOGS = [
    _sync_log(10, 0, 0, 100, 200),
    _sync_log(12, 0, 0, 110, 190),
]
SWAP_LOGS = [_swap_log(11, 0, 0)]


class FakeRpc:
    def __init__(self, *, overreturn=False, stale_block=False):
        self.overreturn = overreturn
        self.stale_block = stale_block
        self.log_ranges = []

    def __call__(self, method, params):
        if method == "eth_getLogs":
            filt = params[0]
            start = int(filt["fromBlock"], 16)
            end = int(filt["toBlock"], 16)
            topic = filt["topics"][0].lower()
            self.log_ranges.append((topic, start, end))
            rows = SYNC_LOGS if topic == qualification.SYNC_TOPIC else SWAP_LOGS
            selected = [row for row in rows if start <= int(row["blockNumber"], 16) <= end]
            if self.overreturn and topic == qualification.SYNC_TOPIC and start == 10:
                selected = selected + [_sync_log(end + 1, 0, 0, 1, 1)]
            return selected
        if method == "eth_getBlockByNumber":
            number = int(params[0], 16)
            return {
                "number": hex(number),
                "hash": _block_hash(number + 1 if self.stale_block and number == 12 else number),
                "timestamp": hex(1_700_000_000 + number),
            }
        if method == "eth_getTransactionReceipt":
            tx_hash = params[0].lower()
            log = next(row for row in SWAP_LOGS if row["transactionHash"].lower() == tx_hash)
            block = int(log["blockNumber"], 16)
            return {
                "transactionHash": tx_hash,
                "blockHash": _block_hash(block),
                "blockNumber": hex(block),
                "status": "0x1",
                "gasUsed": hex(21_000),
                "effectiveGasPrice": hex(2_000_000_000),
            }
        raise AssertionError(method)


def _qualification(provider_id: str):
    identity_rows = [qualification._event_identity(log) for log in SYNC_LOGS]
    t0_log = identity_rows[0]
    receipt = {
        "artifact_type": "QNTYSPOT_INK_SOURCE_QUALIFICATION_RECEIPT_V1",
        "status": "PASS",
        "provider_id": provider_id,
        "chain_id": qualification.CHAIN_ID,
        "pool": qualification.POOL,
        "factory": qualification.FACTORY,
        "token0": qualification.KRAKMASK,
        "token1": qualification.WETH9,
        "t1_block": {"number": 20, "hash": _block_hash(20), "timestamp": 1_700_000_020},
        "pool_deployment_block": 9,
        "t0_block": {"number": 10, "hash": _block_hash(10), "timestamp": 1_700_000_010},
        "t0_sync_identity": t0_log,
        "dev_end_timestamp": 1_700_000_012,
        "dev_end_block": {"number": 12, "hash": _block_hash(12), "timestamp": 1_700_000_012},
        "history_seconds": {"total": 100, "dev": 60, "outer": 40},
        "bounded_probe": {
            "sync_log_identity_digest": qualification._digest(identity_rows),
            "receipt_probe_transaction_hash": identity_rows[0]["transaction_hash"],
            "receipt_probe_block_hash": identity_rows[0]["block_hash"],
        },
        "dev_log_coverage": {
            "from_block": 10,
            "to_block": 12,
            "query_span_blocks": 2,
            "chunk_count": 2,
            "worker_count": 2,
            "block_attestation_worker_count": 4,
            "sync_log_count": len(identity_rows),
            "sync_log_identity_digest": qualification._digest(identity_rows),
            "canonical_block_binding_verified": True,
            "every_chunk_repeated_deterministically": True,
            "every_chunk_whole_equals_split": True,
        },
        "outer_access_performed": False,
        "candidate_evaluation_performed": False,
    }
    receipt["receipt_digest"] = qualification._digest(receipt)
    return receipt


def _write_governance(root: Path):
    auth = root / acquisition.AUTHORIZATION_PATH
    activation = root / acquisition.HISTORICAL_ACTIVATION_PATH
    auth.parent.mkdir(parents=True, exist_ok=True)
    activation.parent.mkdir(parents=True, exist_ok=True)
    auth.write_text('{"authority":"stage-b"}\n', encoding="utf-8")
    activation.write_text('{"historical":"template"}\n', encoding="utf-8")


def test_sample_indices_are_frozen_evenly_spaced_rule():
    assert acquisition._sample_indices(0) == []
    assert acquisition._sample_indices(3) == [0, 1, 2]
    values = acquisition._sample_indices(100)
    assert len(values) == 30
    assert values[0] == 0
    assert values[-1] == 99
    assert values == [(i * 99) // 29 for i in range(30)]


def test_decode_sync_reserves_uses_integer_atomic_units():
    assert acquisition._decode_sync_reserves(SYNC_LOGS[0]) == (100, 200)


def test_decode_sync_reserves_rejects_non_uint112():
    bad = dict(SYNC_LOGS[0])
    bad["data"] = "0x" + f"{1 << 112:064x}" + f"{1:064x}"
    with pytest.raises(acquisition.AcquisitionError, match="uint112"):
        acquisition._decode_sync_reserves(bad)


def test_qualification_receipt_digest_is_verified():
    primary = _qualification("primary")
    secondary = _qualification("secondary")
    primary["history_seconds"]["dev"] += 1
    with pytest.raises(acquisition.AcquisitionError, match="receipt digest mismatch"):
        acquisition._validate_qualification_pair(primary, secondary)


def test_qualification_pair_requires_distinct_matching_providers():
    primary = _qualification("same")
    secondary = _qualification("same")
    with pytest.raises(acquisition.AcquisitionError, match="distinct providers"):
        acquisition._validate_qualification_pair(primary, secondary)

    primary = _qualification("primary")
    secondary = _qualification("secondary")
    secondary["dev_log_coverage"]["sync_log_identity_digest"] = "f" * 64
    with pytest.raises(acquisition.AcquisitionError, match="cross-provider"):
        acquisition._validate_qualification_pair(primary, secondary)


def test_materialize_dev_package_is_dev_only_deterministic_and_content_addressed(tmp_path: Path):
    _write_governance(tmp_path)
    primary = _qualification("primary")
    secondary = _qualification("secondary")
    rpc = FakeRpc()

    first = acquisition.materialize_dev_package(
        rpc,
        primary_qualification=primary,
        secondary_qualification=secondary,
        acquisition_provider_id="primary",
        canonical_qntylab_source_sha="c" * 40,
        output_dir=tmp_path / "out1",
        root=tmp_path,
        query_span=2,
        coverage_workers=2,
        block_workers=4,
    )
    second = acquisition.materialize_dev_package(
        FakeRpc(),
        primary_qualification=primary,
        secondary_qualification=secondary,
        acquisition_provider_id="primary",
        canonical_qntylab_source_sha="c" * 40,
        output_dir=tmp_path / "out2",
        root=tmp_path,
        query_span=2,
        coverage_workers=2,
        block_workers=4,
    )

    assert first["package_digest"] == second["package_digest"]
    assert first["row_or_event_counts"]["sync_reserve_rows"] == 2
    assert first["row_or_event_counts"]["swap_logs_for_gas_population"] == 1
    assert first["row_or_event_counts"]["gas_samples"] == 1
    assert first["discarded_outer_overfetch_count"] == 0
    assert first["performance_metrics_allowed"] is False
    assert first["candidate_evaluation_performed"] is False
    assert first["outer_access_performed"] is False
    assert first["outer_evaluation_count"] == 0
    assert first["min_max_block"] == {"min": 10, "max": 12}
    assert all(end <= 12 for _, _, end in rpc.log_ranges)

    rows = [
        json.loads(line)
        for line in (tmp_path / "out1/dev_reserves.jsonl").read_text().splitlines()
    ]
    assert [row["reserve0_atomic"] for row in rows] == [100, 110]
    assert [row["reserve1_atomic"] for row in rows] == [200, 190]
    assert all(isinstance(row["reserve0_atomic"], int) for row in rows)

    gas = json.loads((tmp_path / "out1/dev_gas_evidence.json").read_text())
    assert gas["mode"] == "SENSITIVITY_FALLBACK"
    assert gas["sample_count"] == 1
    assert gas["p50_gas_cost_wei"] == 21_000 * 2_000_000_000
    assert gas["p90_gas_cost_wei"] == 21_000 * 2_000_000_000

    for artifact in first["sha256_per_dataset_artifact"].values():
        assert len(artifact["sha256"]) == 64
        assert artifact["bytes"] > 0


def test_acquisition_requires_sync_identity_to_match_qualification(tmp_path: Path):
    _write_governance(tmp_path)
    primary = _qualification("primary")
    secondary = _qualification("secondary")
    primary["dev_log_coverage"]["sync_log_count"] += 1
    secondary["dev_log_coverage"]["sync_log_count"] += 1
    with pytest.raises(acquisition.AcquisitionError, match="Sync count"):
        acquisition.materialize_dev_package(
            FakeRpc(),
            primary_qualification=primary,
            secondary_qualification=secondary,
            acquisition_provider_id="primary",
            canonical_qntylab_source_sha="c" * 40,
            output_dir=tmp_path / "out",
            root=tmp_path,
            query_span=2,
        )


def test_acquisition_rejects_provider_overreturn_past_requested_dev(tmp_path: Path):
    _write_governance(tmp_path)
    with pytest.raises(acquisition.AcquisitionError, match="over-returned"):
        acquisition.materialize_dev_package(
            FakeRpc(overreturn=True),
            primary_qualification=_qualification("primary"),
            secondary_qualification=_qualification("secondary"),
            acquisition_provider_id="primary",
            canonical_qntylab_source_sha="c" * 40,
            output_dir=tmp_path / "out",
            root=tmp_path,
            query_span=2,
        )


def test_acquisition_rejects_stale_block_hash(tmp_path: Path):
    _write_governance(tmp_path)
    with pytest.raises(acquisition.AcquisitionError, match="canonical block metadata"):
        acquisition.materialize_dev_package(
            FakeRpc(stale_block=True),
            primary_qualification=_qualification("primary"),
            secondary_qualification=_qualification("secondary"),
            acquisition_provider_id="primary",
            canonical_qntylab_source_sha="c" * 40,
            output_dir=tmp_path / "out",
            root=tmp_path,
            query_span=2,
        )
