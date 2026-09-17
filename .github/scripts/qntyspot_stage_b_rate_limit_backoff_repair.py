from pathlib import Path

SOURCE = Path("qntylab/qntyspot_ink_source_qualification_v1.py")
TESTS = Path("tests/test_qntyspot_ink_source_qualification_v1.py")

source = SOURCE.read_text(encoding="utf-8")

old_imports = "import subprocess\nimport threading\nimport tomllib"
new_imports = "import subprocess\nimport threading\nimport time\nimport tomllib"
assert source.count(old_imports) == 1
source = source.replace(old_imports, new_imports)

old_constants = "DEFAULT_COVERAGE_WORKERS = 1\nMAX_COVERAGE_WORKERS = 16\nMAX_T0_SCAN_BLOCKS = 8192"
new_constants = "DEFAULT_COVERAGE_WORKERS = 1\nMAX_COVERAGE_WORKERS = 16\nDEFAULT_RATE_LIMIT_RETRIES = 5\nDEFAULT_RATE_LIMIT_BACKOFF_SECONDS = 2.0\nMAX_RATE_LIMIT_BACKOFF_SECONDS = 30.0\nMAX_T0_SCAN_BLOCKS = 8192"
assert source.count(old_constants) == 1
source = source.replace(old_constants, new_constants)

old_client = '''@dataclass
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
        for attempt in range(DEFAULT_RATE_LIMIT_RETRIES + 1):
            try:
                with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                    body = json.loads(response.read().decode("utf-8"))
                break
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt >= DEFAULT_RATE_LIMIT_RETRIES:
                    raise QualificationError(
                        f"JSON-RPC transport failure for {method}: {type(exc).__name__}"
                    ) from exc
                delay = min(
                    DEFAULT_RATE_LIMIT_BACKOFF_SECONDS * (2 ** attempt),
                    MAX_RATE_LIMIT_BACKOFF_SECONDS,
                )
                retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
                if retry_after is not None:
                    try:
                        retry_after_seconds = float(retry_after)
                    except (TypeError, ValueError):
                        retry_after_seconds = None
                    if retry_after_seconds is not None and retry_after_seconds >= 0:
                        delay = min(
                            max(delay, retry_after_seconds),
                            MAX_RATE_LIMIT_BACKOFF_SECONDS,
                        )
                time.sleep(delay)
            except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
                raise QualificationError(
                    f"JSON-RPC transport failure for {method}: {type(exc).__name__}"
                ) from exc
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
assert source.count(old_client) == 1
source = source.replace(old_client, new_client)
SOURCE.write_text(source, encoding="utf-8")

tests = TESTS.read_text(encoding="utf-8")
marker = "def test_json_rpc_client_retries_http_429_with_same_payload_and_request_id"
assert marker not in tests
addition = r'''


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
'''
TESTS.write_text(tests + addition, encoding="utf-8")
