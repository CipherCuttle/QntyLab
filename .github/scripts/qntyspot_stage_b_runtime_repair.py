from pathlib import Path

SOURCE = Path("qntylab/qntyspot_ink_source_qualification_v1.py")
TESTS = Path("tests/test_qntyspot_ink_source_qualification_v1.py")

text = SOURCE.read_text()


def replace_once(old: str, new: str) -> None:
    global text
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one source match, found {count}: {old[:80]!r}")
    text = text.replace(old, new, 1)


replace_once(
    "import subprocess\nimport tomllib\nimport urllib.error\n",
    "import subprocess\nimport threading\nimport tomllib\nimport urllib.error\n",
)
replace_once(
    "from dataclasses import dataclass\n",
    "from concurrent.futures import ThreadPoolExecutor\nfrom dataclasses import dataclass, field\n",
)
replace_once(
    "DEFAULT_PROBE_SPAN = 256\nMAX_T0_SCAN_BLOCKS = 8192\n",
    "DEFAULT_PROBE_SPAN = 256\nDEFAULT_COVERAGE_WORKERS = 1\nMAX_COVERAGE_WORKERS = 16\nMAX_T0_SCAN_BLOCKS = 8192\n",
)

old_client = '''@dataclass
class JsonRpcClient:
    endpoint: str
    timeout_seconds: float = 20.0
    request_id: int = 0

    def call(self, method: str, params: list[Any]) -> Any:
        self.request_id += 1
        payload = _canonical_bytes({
            "jsonrpc": "2.0",
            "id": self.request_id,
            "method": method,
            "params": params,
        })
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise QualificationError(f"JSON-RPC transport failure for {method}: {type(exc).__name__}") from exc
        if not isinstance(body, dict) or body.get("id") != self.request_id:
            raise QualificationError(f"malformed JSON-RPC response for {method}")
        if body.get("error") is not None:
            error = body["error"]
            code = error.get("code") if isinstance(error, dict) else None
            raise QualificationError(f"JSON-RPC error for {method}: code={code}")
        if "result" not in body:
            raise QualificationError(f"JSON-RPC result missing for {method}")
        return body["result"]
'''
new_client = '''@dataclass
class JsonRpcClient:
    endpoint: str
    timeout_seconds: float = 20.0
    request_id: int = 0
    _request_id_lock: threading.Lock = field(default_factory=threading.Lock, init=False, repr=False)

    def call(self, method: str, params: list[Any]) -> Any:
        with self._request_id_lock:
            self.request_id += 1
            request_id = self.request_id
        payload = _canonical_bytes({
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params,
        })
        request = urllib.request.Request(
            self.endpoint,
            data=payload,
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "QntyLab-StageB-SourceQualification/1.0",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                body = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise QualificationError(f"JSON-RPC transport failure for {method}: {type(exc).__name__}") from exc
        if not isinstance(body, dict) or body.get("id") != request_id:
            raise QualificationError(f"malformed JSON-RPC response for {method}")
        if body.get("error") is not None:
            error = body["error"]
            code = error.get("code") if isinstance(error, dict) else None
            raise QualificationError(f"JSON-RPC error for {method}: code={code}")
        if "result" not in body:
            raise QualificationError(f"JSON-RPC result missing for {method}")
        return body["result"]
'''
replace_once(old_client, new_client)

start = text.index("def _dev_log_coverage(")
end = text.index("\ndef qualify_source(", start)
new_coverage = '''def _dev_log_coverage(
    rpc: RpcCall,
    start: int,
    end: int,
    query_span: int,
    canonical_block_hashes: dict[int, str] | None = None,
    workers: int = DEFAULT_COVERAGE_WORKERS,
) -> dict[str, Any]:
    if query_span < 2:
        raise QualificationError("qualification query span must be >= 2")
    if workers < 1 or workers > MAX_COVERAGE_WORKERS:
        raise QualificationError(
            f"coverage workers must be between 1 and {MAX_COVERAGE_WORKERS}"
        )

    chunks: list[tuple[int, int]] = []
    cursor = start
    while cursor <= end:
        chunk_end = min(end, cursor + query_span - 1)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + 1

    def fetch_chunk(bounds: tuple[int, int]) -> list[Mapping[str, Any]]:
        chunk_start, chunk_end = bounds
        whole_a = sorted(
            _sync_logs(rpc, chunk_start, chunk_end, canonical_block_hashes),
            key=_log_order_key,
        )
        whole_b = sorted(
            _sync_logs(rpc, chunk_start, chunk_end, canonical_block_hashes),
            key=_log_order_key,
        )
        whole_ids_a = _identities(whole_a)
        whole_ids_b = _identities(whole_b)
        if whole_ids_a != whole_ids_b:
            raise QualificationError(
                "STOP_SOURCE_CONFLICT: repeated DEV chunk request is nondeterministic"
            )
        if chunk_start < chunk_end:
            midpoint = (chunk_start + chunk_end) // 2
            left_ids = _identities(sorted(
                _sync_logs(rpc, chunk_start, midpoint, canonical_block_hashes),
                key=_log_order_key,
            ))
            right_ids = _identities(sorted(
                _sync_logs(rpc, midpoint + 1, chunk_end, canonical_block_hashes),
                key=_log_order_key,
            ))
            if sorted(whole_ids_a) != sorted(left_ids + right_ids):
                raise QualificationError(
                    "STOP_SOURCE_CONFLICT: DEV chunk whole-range logs disagree with split-range logs"
                )
        return whole_a

    records: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    def consume(whole_a: list[Mapping[str, Any]]) -> None:
        for log in whole_a:
            identity = _log_identity(log)
            if identity in seen:
                raise QualificationError(
                    "STOP_SOURCE_CONFLICT: duplicate canonical log identity across DEV chunks"
                )
            seen.add(identity)
            records.append(_event_identity(log))

    if workers == 1:
        for chunk in chunks:
            consume(fetch_chunk(chunk))
    else:
        with ThreadPoolExecutor(
            max_workers=workers,
            thread_name_prefix="qntyspot-dev-coverage",
        ) as executor:
            for offset in range(0, len(chunks), workers):
                batch = chunks[offset:offset + workers]
                futures = [executor.submit(fetch_chunk, chunk) for chunk in batch]
                for future in futures:
                    consume(future.result())

    return {
        "from_block": start,
        "to_block": end,
        "query_span_blocks": query_span,
        "chunk_count": len(chunks),
        "worker_count": workers,
        "sync_log_count": len(records),
        "sync_log_identity_digest": _digest(records),
        "canonical_block_binding_verified": True,
        "every_chunk_repeated_deterministically": True,
        "every_chunk_whole_equals_split": True,
    }
'''
text = text[:start] + new_coverage + text[end:]

replace_once(
    "def qualify_source(rpc: RpcCall, *, provider_id: str, probe_span: int = DEFAULT_PROBE_SPAN) -> dict[str, Any]:\n",
    "def qualify_source(\n    rpc: RpcCall,\n    *,\n    provider_id: str,\n    probe_span: int = DEFAULT_PROBE_SPAN,\n    coverage_workers: int = DEFAULT_COVERAGE_WORKERS,\n) -> dict[str, Any]:\n",
)
replace_once(
    "    if probe_span < 2:\n        raise QualificationError(\"qualification probe span must be >= 2\")\n\n    chain_id = _hex_int(rpc(\"eth_chainId\", []))\n",
    "    if probe_span < 2:\n        raise QualificationError(\"qualification probe span must be >= 2\")\n    if coverage_workers < 1 or coverage_workers > MAX_COVERAGE_WORKERS:\n        raise QualificationError(\n            f\"coverage workers must be between 1 and {MAX_COVERAGE_WORKERS}\"\n        )\n\n    chain_id = _hex_int(rpc(\"eth_chainId\", []))\n",
)
replace_once(
    "        probe_span,\n        canonical_block_hashes,\n    )\n    if coverage[\"to_block\"] != dev_end_number",
    "        probe_span,\n        canonical_block_hashes,\n        coverage_workers,\n    )\n    if coverage[\"to_block\"] != dev_end_number",
)
replace_once(
    "    parser.add_argument(\"--probe-span\", type=int, default=DEFAULT_PROBE_SPAN)\n",
    "    parser.add_argument(\"--probe-span\", type=int, default=DEFAULT_PROBE_SPAN)\n    parser.add_argument(\"--coverage-workers\", type=int, default=DEFAULT_COVERAGE_WORKERS)\n",
)
replace_once(
    "    primary = qualify_source(JsonRpcClient(endpoint).call, provider_id=args.provider_id, probe_span=args.probe_span)\n",
    "    primary = qualify_source(\n        JsonRpcClient(endpoint).call,\n        provider_id=args.provider_id,\n        probe_span=args.probe_span,\n        coverage_workers=args.coverage_workers,\n    )\n",
)
replace_once(
    "            probe_span=args.probe_span,\n        )\n        compare_sources(primary, secondary)\n",
    "            probe_span=args.probe_span,\n            coverage_workers=args.coverage_workers,\n        )\n        compare_sources(primary, secondary)\n",
)
SOURCE.write_text(text)

test_text = TESTS.read_text()
if "test_parallel_dev_coverage_matches_serial_material_identity" in test_text:
    raise SystemExit("runtime tests already present")
test_text = test_text.replace(
    "import json\nfrom pathlib import Path\n",
    "import json\nimport threading\nimport time\nfrom concurrent.futures import ThreadPoolExecutor\nfrom pathlib import Path\n",
    1,
)
test_text += '''


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
'''
TESTS.write_text(test_text)
