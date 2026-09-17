from pathlib import Path

OLD = "3668d8f93481492b8e209f8fd6996fd3b558eb63"
NEW = "2649ba0606e432974971f99f1fa347c569e1454c"

replacements = {
    Path("docs/state/projects.toml"): (
        f'reviewed_candidate_sha = "{OLD}"',
        f'reviewed_candidate_sha = "{NEW}"',
    ),
    Path("experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_research_v1/authorization.json"): (
        f'"reviewed_candidate_sha": "{OLD}"',
        f'"reviewed_candidate_sha": "{NEW}"',
    ),
    Path("tests/test_qntyspot_ink_shadow_performance_dev_acquisition_research_v1.py"): (
        f'auth["canonicalization"]["reviewed_candidate_sha"] == row["reviewed_candidate_sha"] == "{OLD}"',
        f'auth["canonicalization"]["reviewed_candidate_sha"] == row["reviewed_candidate_sha"] == "{NEW}"',
    ),
}

for path, (old, new) in replacements.items():
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{path}: expected one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")
