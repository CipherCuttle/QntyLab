from __future__ import annotations

from pathlib import Path

PATH = Path("qntylab/strategy_test.py")


def replace_once(text: str, old: str, new: str) -> str:
    if text.count(old) != 1:
        raise SystemExit(f"expected exactly one patch anchor, found {text.count(old)}: {old[:80]!r}")
    return text.replace(old, new, 1)


def main() -> None:
    text = PATH.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '''NORMALIZATION_PROVENANCE_KEYS = {
    "normalization_id",
    "normalization_version",
    "reason_code",
    "derived_input_path",
    "derived_input_sha256",
    "derived_manifest_path",
    "derived_manifest_sha256",
    "source_resolution_artifact_path",
    "source_resolution_artifact_sha256",
    "authoritative_raw_path",
    "authoritative_raw_sha256",
    "normalized_timestamp",
}
''',
        '''NORMALIZATION_PROVENANCE_KEYS = {
    "normalization_id",
    "normalization_version",
    "reason_code",
    "derived_input_path",
    "derived_input_sha256",
    "derived_manifest_path",
    "derived_manifest_sha256",
    "source_resolution_artifact_path",
    "source_resolution_artifact_sha256",
    "authoritative_raw_path",
    "authoritative_raw_sha256",
    "normalized_timestamp",
}
NORMALIZATION_PROVENANCE_OPTIONAL_KEYS = {
    "source_resolution_git_commit",
    "authoritative_raw_snapshot_manifest_path",
    "authoritative_raw_snapshot_manifest_git_commit",
}
''',
    )
    old = '''def _validate_normalization_provenance_shape(provenance: Any) -> None:
    if not isinstance(provenance, dict):
        raise ValueError("normalization_provenance must be an object")
    extra = set(provenance) - NORMALIZATION_PROVENANCE_KEYS
    missing = NORMALIZATION_PROVENANCE_KEYS - set(provenance)
    if extra:
        raise ValueError(f"unknown normalization_provenance keys: {sorted(extra)}")
    if missing:
        raise ValueError(f"missing normalization_provenance keys: {sorted(missing)}")
    for key in sorted(NORMALIZATION_PROVENANCE_KEYS):
        if not isinstance(provenance[key], str) or not provenance[key].strip():
            raise ValueError(f"normalization_provenance.{key} must be a non-empty string")
'''
    new = '''def _validate_normalization_provenance_shape(provenance: Any) -> None:
    if not isinstance(provenance, dict):
        raise ValueError("normalization_provenance must be an object")
    extra = set(provenance) - NORMALIZATION_PROVENANCE_KEYS - NORMALIZATION_PROVENANCE_OPTIONAL_KEYS
    missing = NORMALIZATION_PROVENANCE_KEYS - set(provenance)
    if extra:
        raise ValueError(f"unknown normalization_provenance keys: {sorted(extra)}")
    if missing:
        raise ValueError(f"missing normalization_provenance keys: {sorted(missing)}")
    for key in sorted(NORMALIZATION_PROVENANCE_KEYS | (set(provenance) & NORMALIZATION_PROVENANCE_OPTIONAL_KEYS)):
        if not isinstance(provenance[key], str) or not provenance[key].strip():
            raise ValueError(f"normalization_provenance.{key} must be a non-empty string")
    snapshot_keys = {"authoritative_raw_snapshot_manifest_path", "authoritative_raw_snapshot_manifest_git_commit"}
    if bool(set(provenance) & snapshot_keys) != snapshot_keys.issubset(provenance):
        raise ValueError("historical raw snapshot manifest path and git commit must be declared together")
'''
    text = replace_once(text, old, new)
    old = '''def _resolve_receipt_path(path_value: str, config_path: Path) -> Path:
    path = Path(path_value)
    if path.is_absolute():
        return path
    candidate = (Path.cwd() / path).resolve()
    if candidate.exists():
        return candidate
    return (config_path.parent / path).resolve()
'''
    new = old + '''

def _git_snapshot_bytes(commit: str, path_value: str, *, repo_root: Path | None = None) -> bytes:
    if len(commit) != 40 or any(ch not in "0123456789abcdef" for ch in commit.lower()):
        raise ValueError("historical provenance git commit must be a full 40-character hex SHA")
    path = Path(path_value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("historical provenance git path must be repository-relative")
    root = (repo_root or Path.cwd()).resolve()
    proc = subprocess.run(
        ["git", "show", f"{commit}:{path.as_posix()}"],
        cwd=root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode:
        raise FileNotFoundError(f"historical provenance git object unavailable: {commit}:{path.as_posix()}")
    return proc.stdout


def _sha256_csv_prefix_rows(path: Path, rows: int) -> tuple[str, str]:
    if rows < 1:
        raise ValueError("historical raw snapshot rows must be positive")
    lines = path.read_bytes().splitlines(keepends=True)
    if len(lines) < rows + 1:
        raise ValueError(f"authoritative raw has fewer than historical snapshot rows: need {rows}, got {max(0, len(lines)-1)}")
    prefix = b"".join(lines[: rows + 1])
    last_line = lines[rows].decode("utf-8").rstrip("\\r\\n")
    last_timestamp = last_line.split(",", 1)[0]
    return sha256_bytes(prefix), last_timestamp
'''
    text = replace_once(text, old, new)
    start = text.index('def validate_normalization_provenance(\n')
    end = text.index('\n\ndef _normalize_input_path', start)
    replacement = '''def validate_normalization_provenance(
    *,
    provenance: dict[str, Any] | None,
    normalized_input: Path,
    input_sha256: str,
    config_path: Path,
) -> dict[str, Any] | None:
    if provenance is None:
        return None
    _validate_normalization_provenance_shape(provenance)
    derived_input = _resolve_receipt_path(provenance["derived_input_path"], config_path)
    if derived_input.resolve() != normalized_input.resolve():
        raise ValueError("normalization provenance derived input path does not match run input")
    if provenance["derived_input_sha256"] != input_sha256:
        raise ValueError("normalization provenance derived input SHA-256 mismatch")
    manifest_path = _resolve_receipt_path(provenance["derived_manifest_path"], config_path)
    raw_path = _resolve_receipt_path(provenance["authoritative_raw_path"], config_path)
    if not manifest_path.exists():
        raise FileNotFoundError(f"missing normalization provenance derived manifest: {manifest_path}")
    if not raw_path.exists():
        raise FileNotFoundError(f"missing normalization provenance authoritative raw: {raw_path}")
    if sha256_path(manifest_path) != provenance["derived_manifest_sha256"]:
        raise ValueError("normalization provenance manifest SHA-256 mismatch")

    source_path = _resolve_receipt_path(provenance["source_resolution_artifact_path"], config_path)
    if source_path.exists():
        source_bytes = source_path.read_bytes()
    elif provenance.get("source_resolution_git_commit"):
        source_bytes = _git_snapshot_bytes(provenance["source_resolution_git_commit"], provenance["source_resolution_artifact_path"])
    else:
        raise FileNotFoundError(f"missing normalization provenance source-resolution artifact: {source_path}")
    if sha256_bytes(source_bytes) != provenance["source_resolution_artifact_sha256"]:
        raise ValueError("normalization provenance source-resolution SHA-256 mismatch")

    actual_raw_sha = sha256_path(raw_path)
    if actual_raw_sha != provenance["authoritative_raw_sha256"]:
        snapshot_path = provenance.get("authoritative_raw_snapshot_manifest_path")
        snapshot_commit = provenance.get("authoritative_raw_snapshot_manifest_git_commit")
        if not snapshot_path or not snapshot_commit:
            raise ValueError("normalization provenance authoritative raw SHA-256 mismatch")
        snapshot_bytes = _git_snapshot_bytes(snapshot_commit, snapshot_path)
        try:
            snapshot = json.loads(snapshot_bytes.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("historical raw snapshot manifest is invalid JSON") from exc
        if not isinstance(snapshot, dict):
            raise ValueError("historical raw snapshot manifest must be an object")
        rows = snapshot.get("rows")
        end = snapshot.get("end")
        if snapshot.get("sha256") != provenance["authoritative_raw_sha256"]:
            raise ValueError("historical raw snapshot manifest SHA identity mismatch")
        if not isinstance(rows, int) or isinstance(rows, bool) or rows < 1 or not isinstance(end, str) or not end:
            raise ValueError("historical raw snapshot manifest rows/end invalid")
        prefix_sha, prefix_end = _sha256_csv_prefix_rows(raw_path, rows)
        if prefix_sha != provenance["authoritative_raw_sha256"]:
            raise ValueError("authoritative raw no longer contains the exact historical byte prefix")
        if prefix_end != end:
            raise ValueError("authoritative raw historical prefix end timestamp mismatch")

    manifest = _load_json_object(manifest_path, "normalization manifest")
    expected = {
        "normalization_id": "normalization_id",
        "normalization_version": "normalization_version",
        "reason_code": "reason_code",
        "derived_input_path": "derived_path",
        "derived_input_sha256": "derived_sha256",
        "source_resolution_artifact_path": "source_resolution_artifact_path",
        "source_resolution_artifact_sha256": "source_resolution_artifact_sha256",
        "authoritative_raw_path": "authoritative_raw_path",
        "authoritative_raw_sha256": "authoritative_raw_sha256",
        "normalized_timestamp": "normalized_timestamp",
    }
    for provenance_key, manifest_key in expected.items():
        if provenance[provenance_key] != manifest.get(manifest_key):
            raise ValueError(f"normalization provenance {provenance_key} does not match manifest")
    if provenance.get("source_resolution_git_commit") is not None and manifest.get("source_resolution_commit") != provenance["source_resolution_git_commit"]:
        raise ValueError("normalization provenance source_resolution_git_commit does not match manifest")
    return {key: provenance[key] for key in sorted(set(provenance))}
'''
    text = text[:start] + replacement + text[end:]
    PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
