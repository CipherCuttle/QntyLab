import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROJECTS = ROOT / "docs/state/projects.toml"
AUTH = ROOT / "experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_research_v1/authorization.json"
TESTS = ROOT / "tests/test_qntyspot_ink_shadow_performance_dev_acquisition_research_v1.py"
PROJECT_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_RESEARCH_V1"
REVIEWED_SHA = "3668d8f93481492b8e209f8fd6996fd3b558eb63"


def patch_projects() -> None:
    text = PROJECTS.read_text(encoding="utf-8")
    marker = f'project_id = "{PROJECT_ID}"'
    start = text.index(marker)
    block_start = text.rfind("[[project]]", 0, start)
    next_block = text.find("\n[[project]]", start)
    if next_block == -1:
        next_block = len(text)
    block = text[block_start:next_block]

    base_line = 'required_base_sha = "ea2dd02964c2e91196bb153a212ec0f8aae50b42"\n'
    reviewed_line = f'reviewed_candidate_sha = "{REVIEWED_SHA}"\n'
    if reviewed_line not in block:
        if base_line not in block:
            raise SystemExit("Stage-B required_base_sha anchor missing")
        block = block.replace(base_line, base_line + reviewed_line, 1)

    block = block.replace("hostile_review_count = 0\n", "hostile_review_count = 1\n", 1)
    block = block.replace("targeted_rereview_used = false\n", "targeted_rereview_used = true\n", 1)

    receipt_anchor = 'hostile_review_count = 1\ntargeted_rereview_used = true\n'
    receipt = (
        'hostile_review_count = 1\n'
        'hostile_review_mode = "OWNER_AUTHORIZED_SAME_CHAT_HOSTILE_REVIEW_SUBSTITUTE"\n'
        'hostile_review_independence_claimed = false\n'
        'hostile_review_initial_critical_total = 0\n'
        'hostile_review_initial_high_total = 5\n'
        f'hostile_review_repaired_candidate_sha = "{REVIEWED_SHA}"\n'
        'targeted_rereview_used = true\n'
        'targeted_rereview_count = 1\n'
        'targeted_rereview_scope = "H1_H5_REPAIR_SURFACE_AND_REVIEWED_CANDIDATE_PIN"\n'
        'targeted_rereview_verdict = "PASS_NO_CRITICAL_HIGH"\n'
        'targeted_rereview_new_critical_total = 0\n'
        'targeted_rereview_new_high_total = 0\n'
    )
    if 'hostile_review_mode = "OWNER_AUTHORIZED_SAME_CHAT_HOSTILE_REVIEW_SUBSTITUTE"' not in block:
        if receipt_anchor not in block:
            raise SystemExit("Stage-B review receipt anchor missing")
        block = block.replace(receipt_anchor, receipt, 1)

    text = text[:block_start] + block + text[next_block:]
    PROJECTS.write_text(text, encoding="utf-8")


def patch_auth() -> None:
    auth = json.loads(AUTH.read_text(encoding="utf-8"))
    canonical = auth["canonicalization"]
    canonical["reviewed_candidate_sha"] = REVIEWED_SHA

    policy = auth["review_policy"]
    policy.clear()
    policy.update({
        "independent_hostile_review_requirement_originally_declared": True,
        "owner_authorized_same_chat_substitution": True,
        "review_mode": "OWNER_AUTHORIZED_SAME_CHAT_HOSTILE_REVIEW_SUBSTITUTE",
        "reviewer_independence_claimed": False,
        "hostile_review_count": 1,
        "initial_critical_total": 0,
        "initial_high_total": 5,
        "repaired_candidate_sha": REVIEWED_SHA,
        "targeted_rereview_used": True,
        "targeted_rereview_count": 1,
        "targeted_rereview_scope": "H1_H5_REPAIR_SURFACE_AND_REVIEWED_CANDIDATE_PIN",
        "targeted_rereview_verdict": "PASS_NO_CRITICAL_HIGH",
        "targeted_rereview_new_critical_total": 0,
        "targeted_rereview_new_high_total": 0,
        "merge_authority": "NONE",
    })
    AUTH.write_text(json.dumps(auth, indent=2) + "\n", encoding="utf-8")


def patch_tests() -> None:
    text = TESTS.read_text(encoding="utf-8")
    anchor = '    assert auth["canonicalization"]["runtime_origin_repository_must_match"] == "CipherCuttle/QntyLab"\n'
    extra = (
        anchor
        + f'    assert auth["canonicalization"]["reviewed_candidate_sha"] == row["reviewed_candidate_sha"] == "{REVIEWED_SHA}"\n'
        + '    assert row["hostile_review_count"] == 1\n'
        + '    assert row["hostile_review_mode"] == "OWNER_AUTHORIZED_SAME_CHAT_HOSTILE_REVIEW_SUBSTITUTE"\n'
        + '    assert row["hostile_review_independence_claimed"] is False\n'
        + '    assert row["hostile_review_initial_high_total"] == 5\n'
        + '    assert row["targeted_rereview_used"] is True\n'
        + '    assert row["targeted_rereview_count"] == 1\n'
        + '    assert row["targeted_rereview_verdict"] == "PASS_NO_CRITICAL_HIGH"\n'
        + '    assert auth["review_policy"]["owner_authorized_same_chat_substitution"] is True\n'
        + '    assert auth["review_policy"]["reviewer_independence_claimed"] is False\n'
        + '    assert auth["review_policy"]["merge_authority"] == "NONE"\n'
    )
    if f'auth["canonicalization"]["reviewed_candidate_sha"]' not in text:
        if anchor not in text:
            raise SystemExit("Stage-B canonicalization assertion anchor missing")
        text = text.replace(anchor, extra, 1)
    TESTS.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_projects()
    patch_auth()
    patch_tests()
