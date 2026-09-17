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
    text = replace_function(text, "_dev_log_coverage", '''
def _dev_log_coverage(
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
        whole_a = sorted(
            _sync_logs(rpc, cursor, chunk_end, canonical_block_hashes),
            key=_log_order_key,
        )
        whole_b = sorted(
            _sync_logs(rpc, cursor, chunk_end, canonical_block_hashes),
            key=_log_order_key,
        )
        whole_ids_a = _identities(whole_a)
        whole_ids_b = _identities(whole_b)
        if whole_ids_a != whole_ids_b:
            raise QualificationError(
                "STOP_SOURCE_CONFLICT: repeated DEV chunk request is nondeterministic"
            )
        if cursor < chunk_end:
            midpoint = (cursor + chunk_end) // 2
            left_ids = _identities(sorted(
                _sync_logs(rpc, cursor, midpoint, canonical_block_hashes),
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
        for log in whole_a:
            identity = _log_identity(log)
            if identity in seen:
                raise QualificationError(
                    "STOP_SOURCE_CONFLICT: duplicate canonical log identity across DEV chunks"
                )
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
        "every_chunk_repeated_deterministically": True,
        "every_chunk_whole_equals_split": True,
    }
''')

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
    reviewed_candidate = current.get("reviewed_candidate_sha")
    if not isinstance(reviewed_candidate, str) or len(reviewed_candidate) != 40:
        raise QualificationError("STOP_SOURCE_CONFLICT: exact reviewed Stage-B candidate is not pinned")
    if not _git_is_ancestor(root, reviewed_candidate, head):
        raise QualificationError("STOP_SOURCE_CONFLICT: exact reviewed Stage-B candidate is not canonical")

    origin_url = _git(root, "remote", "get-url", "origin").strip().rstrip("/")
    if origin_url.endswith(".git"):
        origin_url = origin_url[:-4]
    if origin_url.startswith("git@github.com:"):
        origin_url = "https://github.com/" + origin_url[len("git@github.com:"):]
    elif origin_url.startswith("ssh://git@github.com/"):
        origin_url = "https://github.com/" + origin_url[len("ssh://git@github.com/"):]
    if origin_url.lower() != "https://github.com/ciphercuttle/qntylab":
        raise QualificationError(
            "STOP_SOURCE_CONFLICT: origin does not identify canonical GitHub repository CipherCuttle/QntyLab"
        )
''')
    SOURCE.write_text(text.rstrip() + "\n", encoding="utf-8")


def patch_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")
    acceptance_old = '''        if args in (("rev-parse", "HEAD"), ("rev-parse", "origin/master")):
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
'''
    acceptance_new = '''        if args in (("rev-parse", "HEAD"), ("rev-parse", "origin/master")):
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
'''
    if acceptance_old not in text:
        raise SystemExit("canonical acceptance fixture anchor missing")
    text = text.replace(acceptance_old, acceptance_new, 1)

    append = '''\n\ndef test_full_dev_coverage_detects_silent_truncation_in_later_chunk():
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
        "schema_version = 1\\n"
        "[[project]]\\n"
        f'project_id = "{qualifier.PREDECESSOR_ID}"\\n'
        'state = "CLOSED_PASS"\\n'
        'implementation_authorized = false\\n'
        "[[project]]\\n"
        f'project_id = "{qualifier.PROJECT_ID}"\\n'
        'state = "ACTIVE_RESEARCH"\\n'
        'implementation_authorized = true\\n'
        f'required_base_sha = "{required_base}"\\n'
        f'reviewed_candidate_sha = "{reviewed}"\\n',
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
'''
    if "test_full_dev_coverage_detects_silent_truncation_in_later_chunk" not in text:
        text = text.rstrip() + append
    TESTS.write_text(text.rstrip() + "\n", encoding="utf-8")


def patch_authorization() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    canonical = auth["canonicalization"]
    canonical["runtime_origin_repository_must_match"] = "CipherCuttle/QntyLab"
    source = auth["source_qualification_contract"]
    source["full_dev_chunk_integrity_validation"] = "REPEAT_PLUS_WHOLE_EQUALS_SPLIT_EACH_CHUNK"
    checks = source["required_checks"]
    remote_check = "runtime origin must identify canonical GitHub repository CipherCuttle/QntyLab before network authority"
    chunk_check = "every bounded DEV coverage chunk is repeated deterministically and equals the union of adjacent half-range requests"
    if remote_check not in checks:
        checks.append(remote_check)
    if chunk_check not in checks:
        checks.append(chunk_check)
    AUTH.write_text(json.dumps(auth, indent=2) + "\n", encoding="utf-8")


def patch_stage_tests() -> None:
    text = STAGE_TESTS.read_text(encoding="utf-8")
    anchor = '    assert auth["canonicalization"]["runtime_exact_reviewed_candidate_must_be_ancestor"] is True\n'
    addition = '    assert auth["canonicalization"]["runtime_origin_repository_must_match"] == "CipherCuttle/QntyLab"\n'
    if addition not in text:
        if anchor not in text:
            raise SystemExit("canonical origin assertion anchor missing")
        text = text.replace(anchor, anchor + addition, 1)
    anchor = '    assert source["receipt_gas_fields_required"] == ["gasUsed", "effectiveGasPrice"]\n'
    addition = '    assert source["full_dev_chunk_integrity_validation"] == "REPEAT_PLUS_WHOLE_EQUALS_SPLIT_EACH_CHUNK"\n'
    if addition not in text:
        if anchor not in text:
            raise SystemExit("chunk integrity assertion anchor missing")
        text = text.replace(anchor, anchor + addition, 1)
    STAGE_TESTS.write_text(text.rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    patch_source()
    patch_tests()
    patch_authorization()
    patch_stage_tests()
