import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "qntylab/qntyspot_ink_source_qualification_v1.py"
TESTS = ROOT / "tests/test_qntyspot_ink_source_qualification_v1.py"
AUTH = ROOT / "experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_research_v1/authorization.json"
STAGE_TESTS = ROOT / "tests/test_qntyspot_ink_shadow_performance_dev_acquisition_research_v1.py"


def patch_source() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    old = '''    canonical_receipt_hash = str(_block(rpc, receipt_block_number)["hash"]).lower()
    if receipt_block_hash.lower() != canonical_receipt_hash:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt block hash disagrees with canonical block metadata")

    event_records = [_event_identity(log) for log in ordered_a]
'''
    new = '''    canonical_receipt_hash = str(_block(rpc, receipt_block_number)["hash"]).lower()
    if receipt_block_hash.lower() != canonical_receipt_hash:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt block hash disagrees with canonical block metadata")
    if _hex_int(receipt.get("status")) != 1:
        raise QualificationError("STOP_SOURCE_CONFLICT: probed Sync receipt is not successful")
    gas_used = receipt.get("gasUsed")
    if not isinstance(gas_used, str):
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt gasUsed is missing or invalid")
    if _hex_int(gas_used) <= 0:
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt gasUsed is missing or invalid")
    effective_gas_price = receipt.get("effectiveGasPrice")
    if not isinstance(effective_gas_price, str):
        raise QualificationError("STOP_SOURCE_CONFLICT: receipt effectiveGasPrice is missing or invalid")
    _hex_int(effective_gas_price)

    event_records = [_event_identity(log) for log in ordered_a]
'''
    if old not in text:
        raise SystemExit("receipt validation anchor missing")
    text = text.replace(old, new, 1)

    old = '''    required_base = current.get("required_base_sha")
    if not isinstance(required_base, str) or not _git_is_ancestor(root, required_base, head):
        raise QualificationError("STOP_SOURCE_CONFLICT: Stage-B required canonical base is not an ancestor of HEAD")
'''
    new = '''    required_base = current.get("required_base_sha")
    if not isinstance(required_base, str) or not _git_is_ancestor(root, required_base, head):
        raise QualificationError("STOP_SOURCE_CONFLICT: Stage-B required canonical base is not an ancestor of HEAD")
    reviewed_candidate = current.get("reviewed_candidate_sha")
    if not isinstance(reviewed_candidate, str) or len(reviewed_candidate) != 40:
        raise QualificationError("STOP_SOURCE_CONFLICT: exact reviewed Stage-B candidate is not pinned")
    if not _git_is_ancestor(root, reviewed_candidate, head):
        raise QualificationError("STOP_SOURCE_CONFLICT: exact reviewed Stage-B candidate is not canonical")
'''
    if old not in text:
        raise SystemExit("reviewed candidate guard anchor missing")
    SOURCE.write_text(text.rstrip() + "\n", encoding="utf-8")


def patch_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")
    old = '''                "blockNumber": hex(self.sync_block),
                "status": "0x1",
            }
'''
    new = '''                "blockNumber": hex(self.sync_block),
                "status": "0x1",
                "gasUsed": "0x5208",
                "effectiveGasPrice": "0x3b9aca00",
            }
'''
    if old not in text:
        raise SystemExit("fake receipt anchor missing")
    text = text.replace(old, new, 1)

    old = '''        f'required_base_sha = "{required_base}"\\n',
        encoding="utf-8",
    )
'''
    new = '''        f'required_base_sha = "{required_base}"\\n'
        f'reviewed_candidate_sha = "{"c" * 40}"\\n',
        encoding="utf-8",
    )
'''
    if old not in text:
        raise SystemExit("canonical authority fixture anchor missing")
    text = text.replace(old, new, 1)

    old = '''    monkeypatch.setattr(qualifier, "_git_is_ancestor", lambda root, ancestor, descendant: ancestor == required_base)
    qualifier.assert_canonical_stage_b_authority(tmp_path)
'''
    new = '''    monkeypatch.setattr(
        qualifier,
        "_git_is_ancestor",
        lambda root, ancestor, descendant: ancestor in {required_base, "c" * 40},
    )
    qualifier.assert_canonical_stage_b_authority(tmp_path)
'''
    if old not in text:
        raise SystemExit("canonical authority ancestor fixture anchor missing")
    text = text.replace(old, new, 1)

    append = '''\n\ndef test_receipt_must_expose_frozen_gas_rule_fields():
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
        'reviewed_candidate_sha = "not-a-sha"\\n',
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
'''
    if "test_receipt_must_expose_frozen_gas_rule_fields" not in text:
        text = text.rstrip() + append
    TESTS.write_text(text.rstrip() + "\n", encoding="utf-8")


def patch_authorization() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    canonical = auth["canonicalization"]
    canonical["runtime_exact_reviewed_candidate_must_be_ancestor"] = True
    source = auth["source_qualification_contract"]
    source["receipt_gas_fields_required"] = ["gasUsed", "effectiveGasPrice"]
    checks = source["required_checks"]
    gas_check = "the DEV-eligible receipt is successful and exposes gasUsed and effectiveGasPrice required by the frozen gas rule"
    if gas_check not in checks:
        checks.append(gas_check)
    AUTH.write_text(json.dumps(auth, indent=2) + "\n", encoding="utf-8")


def patch_stage_tests() -> None:
    text = STAGE_TESTS.read_text(encoding="utf-8")
    old = '    assert auth["canonicalization"]["runtime_required_base_must_be_ancestor"] is True\n'
    new = old + '    assert auth["canonicalization"]["runtime_exact_reviewed_candidate_must_be_ancestor"] is True\n'
    if new not in text:
        if old not in text:
            raise SystemExit("stage canonical assertion anchor missing")
        text = text.replace(old, new, 1)
    old = '    assert source["cross_provider_material_identity_includes_dev_log_digest"] is True\n'
    new = old + '    assert source["receipt_gas_fields_required"] == ["gasUsed", "effectiveGasPrice"]\n'
    if new not in text:
        if old not in text:
            raise SystemExit("stage source assertion anchor missing")
        text = text.replace(old, new, 1)
    STAGE_TESTS.write_text(text.rstrip() + "\n", encoding="utf-8")


if __name__ == "__main__":
    patch_source()
    patch_tests()
    patch_authorization()
    patch_stage_tests()
