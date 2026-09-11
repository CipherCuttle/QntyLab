from __future__ import annotations

import json
from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if new in text:
        return
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"expected exactly one repair anchor in {path}, found {count}: {old[:100]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def patch_ledger() -> None:
    path = "qntylab/research_ledger.py"
    replace_once(
        path,
        '''CANDIDATE_REOPENED_KEYS = {
    "event_id",
    "event_type",
    "candidate_id",
    "variant_id",
    "previous_decision_event_id",
    "reason",
    "material_change",
    "recorded_at_utc",
}
DECISION_KEYS = {''',
        '''CANDIDATE_REOPENED_KEYS = {
    "event_id",
    "event_type",
    "candidate_id",
    "variant_id",
    "previous_decision_event_id",
    "reason",
    "material_change",
    "recorded_at_utc",
}
CANDIDATE_REOPENED_OPTIONAL_KEYS = {
    "authorization_contract_path",
    "authorization_contract_sha256",
}
REOPEN_AUTHORIZATION_CONTRACT_KEYS = {
    "schema_version",
    "authorization_id",
    "reopen_event_id",
    "candidate_id",
    "variant_id",
    "allowed_research_intents",
    "authorized_trial_ids",
    "metadata",
}
DECISION_KEYS = {''',
    )
    replace_once(
        path,
        '''    elif event_type == "CANDIDATE_REOPENED":
        _require_keys(event, CANDIDATE_REOPENED_KEYS, event_type)
        _require_non_empty_string(event, ("event_id", "candidate_id", "variant_id", "previous_decision_event_id", "recorded_at_utc"))
        if not isinstance(event["reason"], str) or len(event["reason"].strip()) < 12:
            raise LedgerError("reopen reason must be concrete and non-empty")
        if not isinstance(event["material_change"], str) or not event["material_change"].strip():
            raise LedgerError("material_change must be a non-empty string")
''',
        '''    elif event_type == "CANDIDATE_REOPENED":
        _require_keys(event, CANDIDATE_REOPENED_KEYS, event_type, optional=CANDIDATE_REOPENED_OPTIONAL_KEYS)
        _require_non_empty_string(event, ("event_id", "candidate_id", "variant_id", "previous_decision_event_id", "recorded_at_utc"))
        if not isinstance(event["reason"], str) or len(event["reason"].strip()) < 12:
            raise LedgerError("reopen reason must be concrete and non-empty")
        if not isinstance(event["material_change"], str) or not event["material_change"].strip():
            raise LedgerError("material_change must be a non-empty string")
        contract_path = event.get("authorization_contract_path")
        contract_sha = event.get("authorization_contract_sha256")
        if (contract_path is None) != (contract_sha is None):
            raise LedgerError("reopen authorization contract path and SHA-256 must be declared together")
        if contract_path is not None:
            _require_non_empty_string(event, ("authorization_contract_path", "authorization_contract_sha256"))
            if Path(contract_path).is_absolute():
                raise LedgerError("reopen authorization contract path must be repository-relative")
            if len(contract_sha) != 64:
                raise LedgerError("reopen authorization contract SHA-256 must be 64 hex characters")
            try:
                int(contract_sha, 16)
            except ValueError as exc:
                raise LedgerError("reopen authorization contract SHA-256 must be hexadecimal") from exc
''',
    )
    replace_once(
        path,
        '''        variant["status"] = "PROPOSED"
        variant["latest_decision_event_id"] = None

    for event in history.trials:
''',
        '''        variant["status"] = "PROPOSED"
        variant["latest_decision_event_id"] = None
        for key in (
            "active_reopen_event_id",
            "reopen_authorization_contract_path",
            "reopen_authorization_contract_sha256",
        ):
            variant.pop(key, None)
        if event.get("authorization_contract_path") is not None:
            variant["active_reopen_event_id"] = event["event_id"]
            variant["reopen_authorization_contract_path"] = event["authorization_contract_path"]
            variant["reopen_authorization_contract_sha256"] = event["authorization_contract_sha256"]

    for event in history.trials:
''',
    )
    helper = '''

def _load_reopen_authorization_contract(*, variant: dict[str, Any], variant_id: str, root: Path) -> dict[str, Any] | None:
    path_value = variant.get("reopen_authorization_contract_path")
    sha_value = variant.get("reopen_authorization_contract_sha256")
    event_id_value = variant.get("active_reopen_event_id")
    if path_value is None and sha_value is None and event_id_value is None:
        return None
    if not all(isinstance(value, str) and value.strip() for value in (path_value, sha_value, event_id_value)):
        raise LedgerError("active reopen authorization state is incomplete")
    if Path(path_value).is_absolute():
        raise LedgerError("active reopen authorization contract path must be repository-relative")
    repo_root = root.parent.parent.resolve()
    contract_path = (repo_root / path_value).resolve()
    try:
        contract_path.relative_to(repo_root)
    except ValueError as exc:
        raise LedgerError("active reopen authorization contract escapes repository root") from exc
    if not contract_path.is_file():
        raise LedgerError(f"active reopen authorization contract missing: {path_value}")
    if sha256_path(contract_path) != sha_value:
        raise LedgerError("active reopen authorization contract SHA-256 mismatch")
    try:
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise LedgerError("active reopen authorization contract is malformed JSON") from exc
    if not isinstance(contract, dict):
        raise LedgerError("active reopen authorization contract must be a JSON object")
    extra = set(contract) - REOPEN_AUTHORIZATION_CONTRACT_KEYS
    missing = REOPEN_AUTHORIZATION_CONTRACT_KEYS - set(contract)
    if extra or missing:
        raise LedgerError(f"active reopen authorization contract keys invalid: extra={sorted(extra)} missing={sorted(missing)}")
    if contract["schema_version"] != "1.0.0":
        raise LedgerError("unsupported reopen authorization contract schema")
    for key in ("authorization_id", "reopen_event_id", "candidate_id", "variant_id"):
        if not isinstance(contract[key], str) or not contract[key].strip():
            raise LedgerError(f"reopen authorization contract {key} must be a non-empty string")
    if contract["reopen_event_id"] != event_id_value:
        raise LedgerError("reopen authorization contract event identity mismatch")
    if contract["candidate_id"] != variant["candidate_id"] or contract["variant_id"] != variant_id:
        raise LedgerError("reopen authorization contract variant identity mismatch")
    intents = contract["allowed_research_intents"]
    if not isinstance(intents, list) or not intents or len(intents) != len(set(intents)) or any(intent not in RESEARCH_INTENTS for intent in intents):
        raise LedgerError("reopen authorization contract allowed_research_intents invalid")
    trial_ids = contract["authorized_trial_ids"]
    if not isinstance(trial_ids, list) or not trial_ids or len(trial_ids) != len(set(trial_ids)) or not all(isinstance(item, str) and item.startswith("trial_") for item in trial_ids):
        raise LedgerError("reopen authorization contract authorized_trial_ids invalid")
    if not isinstance(contract["metadata"], dict):
        raise LedgerError("reopen authorization contract metadata must be an object")
    return contract
'''
    replace_once(path, "\ndef preflight(\n", helper + "\n\ndef preflight(\n")
    replace_once(
        path,
        '''    if trial_id in trial_index["trials"] and config.get("research_intent") != "REPLICATION":
        raise LedgerError("exact trial already completed")
    return {
''',
        '''    reopen_authorization = _load_reopen_authorization_contract(variant=variant, variant_id=variant_id, root=root)
    reopen_authorization_id = None
    if reopen_authorization is not None:
        reopen_authorization_id = reopen_authorization["authorization_id"]
        if config.get("research_intent") not in reopen_authorization["allowed_research_intents"]:
            raise LedgerError("research_intent not authorized by active reopen contract")
        if trial_id not in reopen_authorization["authorized_trial_ids"]:
            raise LedgerError("trial not authorized by active reopen contract")
    if trial_id in trial_index["trials"] and config.get("research_intent") != "REPLICATION":
        raise LedgerError("exact trial already completed")
    return {
''',
    )
    replace_once(
        path,
        '''        "research_intent": config.get("research_intent"),
        "status": status,
''',
        '''        "research_intent": config.get("research_intent"),
        "reopen_authorization_id": reopen_authorization_id,
        "status": status,
''',
    )


def patch_analysis_contract() -> None:
    path = Path("experiments/specs/h003_edge_falsification_v0_analysis_contract.json")
    value = json.loads(path.read_text(encoding="utf-8"))
    value["state_continuity"]["minimum_pre_block_history_closes"] = 193
    value["state_continuity"]["official_trial_role"] = (
        "An official qntylab.strategy_test path-attestation run must use an exact window frozen in "
        "experiments/specs/h003_edge_falsification_v0_trial_authorization.json. For non-reset reporting boundaries "
        "this supplies 193 preceding closes so the one-bar-shifted predecessor position is causally reconstructible. "
        "The analyzer must first match that official run on its full attested window, reconstruct H003 on the full "
        "window, and only then slice the reporting block. Passing a bare calendar-year close array directly to "
        "positions() is forbidden."
    )
    value["gap_and_input_semantics"]["OTHER_BLOCKS"]["policy"] = (
        "Use exact authoritative raw input. Every non-reset reporting block must use the exact 193-close prehistory "
        "window frozen in experiments/specs/h003_edge_falsification_v0_trial_authorization.json. qntylab.strategy_test "
        "must reject any unexpected gap in the attested window. Any newly discovered gap blocks the affected path and "
        "cannot be normalized after result inspection."
    )
    constraint = (
        "Any post-graveyard H003 strategy_test trial must be admitted by the SHA-pinned active reopen authorization "
        "contract at the central research_ledger.preflight boundary; prose-only authorization or wrapper-only checks "
        "are insufficient."
    )
    if constraint not in value["implementation_constraints"]:
        value["implementation_constraints"].insert(1, constraint)
    path.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")


def patch_prereg_test() -> None:
    path = Path("tests/test_h003_edge_falsification_v0_prereg.py")
    text = path.read_text(encoding="utf-8")
    text = text.replace(
        'assert continuity["minimum_pre_block_history_closes"] == 192',
        'assert continuity["minimum_pre_block_history_closes"] == 193',
    )
    text = text.replace(
        'assert "at least the preceding 192 contiguous hourly closes" in gap["OTHER_BLOCKS"]["policy"]',
        'assert "exact 193-close prehistory" in gap["OTHER_BLOCKS"]["policy"]',
    )
    path.write_text(text, encoding="utf-8")


def regenerate_reopen() -> None:
    from qntylab import research_ledger

    root = Path("experiments/research")
    event = json.loads((root / "h003_edge_falsification_v0/reopen_event.json").read_text(encoding="utf-8"))
    candidates_path = root / "candidates.jsonl"
    existing = [json.loads(line) for line in candidates_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    retained = [row for row in existing if row.get("event_id") != event["event_id"]]
    candidates_path.write_bytes(b"".join(research_ledger.canonical_bytes(row) + b"\n" for row in retained))
    research_ledger.append_canonical_event(event, root=root)
    issues = research_ledger.doctor(root=root)
    if issues:
        raise SystemExit("; ".join(issues))


if __name__ == "__main__":
    patch_ledger()
    patch_analysis_contract()
    patch_prereg_test()
    regenerate_reopen()
