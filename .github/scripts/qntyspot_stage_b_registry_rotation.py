from pathlib import Path

STAGE_A = "QNTYSPOT_INK_SHADOW_PERFORMANCE_RESEARCH_V1"
STAGE_B = "QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_RESEARCH_V1"
STAGE_B_NEXT = (
    "STAGE_B_CANONICALIZATION_CANDIDATE: no market-network execution is effective on this branch. "
    "After exact canonical merge, run outcome-blind source qualification. Only a qualification PASS may unlock "
    "DEV-only acquisition; candidate evaluation, OUTER access, QntySpot mutation, Order Flow mutation, Hetzner "
    "access, trading, signing, broadcast, and capital remain unauthorized."
)
STAGE_A_CLOSED_NEXT = (
    "CLOSED_PASS: Stage-A parallel-research reauthorization is canonical and consumed. "
    "The sole ACTIVE_RESEARCH successor is QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_RESEARCH_V1. "
    "Stage A remains immutable historical governance and grants no current network, economic-data, candidate-evaluation, "
    "OUTER, QntySpot mutation, trading, signing, broadcast, or capital authority."
)


def project_block(source: str, project_id: str):
    marker = f'project_id = "{project_id}"'
    start = source.index(marker)
    block_start = source.rfind('[[project]]', 0, start)
    next_block = source.find('\n[[project]]', start)
    block_end = len(source) if next_block == -1 else next_block
    return block_start, block_end, source[block_start:block_end]


def replace_function(source: str, name: str, replacement: str) -> str:
    start = source.index(f'def {name}(')
    next_def = source.find('\n\ndef ', start + 1)
    end = len(source) if next_def == -1 else next_def + 2
    return source[:start] + replacement.rstrip() + '\n\n' + source[end:]


def patch_registry() -> None:
    projects = Path('docs/state/projects.toml')
    text = projects.read_text(encoding='utf-8')
    a_start, a_end, a = project_block(text, STAGE_A)
    for old, new in (
        ('state = "ACTIVE_RESEARCH"', 'state = "CLOSED_PASS"'),
        ('implementation_authorized = true', 'implementation_authorized = false'),
        ('implementation_completed = false', 'implementation_completed = true'),
    ):
        if a.count(old) != 1:
            raise SystemExit(f'Stage-A expected exactly one {old!r}')
        a = a.replace(old, new, 1)
    if 'superseded_by = ' not in a:
        anchor = 'phase_type = "GOVERNANCE_ONLY"\n'
        if a.count(anchor) != 1:
            raise SystemExit('Stage-A phase_type anchor missing')
        a = a.replace(anchor, anchor + f'superseded_by = ["{STAGE_B}"]\n', 1)
    old_next_prefix = 'next_action = "STAGE_A_ACTIVE_RESEARCH:'
    next_start = a.index(old_next_prefix)
    next_end = a.find('\n', next_start)
    if next_end == -1:
        next_end = len(a)
    a = a[:next_start] + f'next_action = "{STAGE_A_CLOSED_NEXT}"' + a[next_end:]
    text = text[:a_start] + a + text[a_end:]

    if f'project_id = "{STAGE_B}"' in text:
        raise SystemExit('Stage-B project row already exists')
    stage_b = f'''

[[project]]
project_id = "{STAGE_B}"
display_name = "QntySpot Ink shadow performance DEV acquisition research V1"
state = "ACTIVE_RESEARCH"
authority_level = "BOUNDED_DEV_SOURCE_QUALIFICATION_AND_ACQUISITION"
phase_type = "DEV_DATA_ACQUISITION"
supersedes = ["{STAGE_A}"]
superseded_by = []
authoritative_artifacts = [
  "docs/state/projects.toml",
  "docs/CURRENT_ROADMAP.md",
  "experiments/research/qntyspot_ink_shadow_performance_v0/preregistration.json",
  "experiments/research/qntyspot_ink_shadow_performance_research_v1/authorization.json",
  "experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_research_v1/authorization.json",
  "qntylab/qntyspot_ink_source_qualification_v1.py",
  "tests/test_qntyspot_ink_shadow_performance_dev_acquisition_research_v1.py",
  "tests/test_qntyspot_ink_source_qualification_v1.py",
]
required_base_sha = "ea2dd02964c2e91196bb153a212ec0f8aae50b42"
parent_project_id = "{STAGE_A}"
preregistration_digest = "27ce60c68133f40d9496df1db6009de07957ed8a9bd68b0715cc6c54fe05d18a"
qntyspot_source_commit = "b9a84c59bd43e7697ee970d2a7571647e5de4501"
historical_data_cutoff_utc = "2026-08-25T17:02:37Z"
ink_chain_id = 57073
inkyswap_v2_pool = "0xed11ed4b195e84ba9b74c4d6ce13b7a43b354264"
candidate_count = 12
dev_percentage = "60%"
outer_percentage = "40%"
dev_end_formula = "T0 + floor(0.60 * (T1 - T0))"
outer_initial_access = "INACCESSIBLE"
scientific_design_mutation = false
activation_effective_on_branch = false
source_qualification_authorized_after_canonical_merge = true
market_data_access_authorized_after_canonical_merge = true
source_qualification_pass_required_before_dev_acquisition = true
candidate_evaluation_authorized = false
outer_access_authorized = false
research_ledger_mutation_authorized = false
qntyspot_repository_mutation_authorized = false
implementation_authorized = true
implementation_completed = false
source_qualification_receipt_present = false
dev_dataset_present = false
dev_manifest_present = false
market_network_count = 0
market_data_acquisition_count = 0
historical_outcome_read_count = 0
backtest_count = 0
strategy_test_count = 0
outer_evaluation_count = 0
research_ledger_state_changed = false
qntyspot_changed = false
order_flow_changed = false
hetzner_touched = false
qntyspot_execution_authority = "NONE"
trading_authority = "NONE"
capital_authority = "NONE"
signing_authority = "NONE"
approval_authority = "NONE"
broadcast_authority = "NONE"
promotion_authority = "NONE"
hostile_review_required = true
hostile_review_count = 0
targeted_rereview_used = false
merge_authority = "NONE"
next_action = "{STAGE_B_NEXT}"
'''
    projects.write_text(text.rstrip() + stage_b, encoding='utf-8')


def patch_stage_a_tests() -> None:
    path = Path('tests/test_qntyspot_ink_shadow_performance_research_v1.py')
    test = path.read_text(encoding='utf-8')
    const_anchor = 'PROJECT_ID = "QNTYSPOT_INK_SHADOW_PERFORMANCE_RESEARCH_V1"\n'
    if 'STAGE_B_ID = ' not in test:
        if test.count(const_anchor) != 1:
            raise SystemExit('Stage-A PROJECT_ID anchor missing')
        test = test.replace(const_anchor, const_anchor + f'STAGE_B_ID = "{STAGE_B}"\n', 1)

    test = replace_function(test, 'test_fresh_active_research_lane_coexists_with_order_flow_without_execution_authority_leak', f'''
def test_stage_a_is_closed_while_stage_b_coexists_with_order_flow_without_execution_authority_leak():
    rows = project_rows()
    ordinary_active = [row for row in rows if row["state"] == "ACTIVE"]
    active_research = [row for row in rows if row["state"] == "ACTIVE_RESEARCH"]
    assert [row["project_id"] for row in ordinary_active] == [ORDER_FLOW_ID]
    assert [row["project_id"] for row in active_research] == [STAGE_B_ID]
    stage_a = project(PROJECT_ID)
    assert stage_a["state"] == "CLOSED_PASS"
    assert stage_a["implementation_authorized"] is False
    assert stage_a["implementation_completed"] is True
    assert stage_a["superseded_by"] == [STAGE_B_ID]
    research = active_research[0]
    assert research["implementation_authorized"] is True
    assert research["implementation_completed"] is False
    assert research["trading_authority"] == "NONE"
    assert research["capital_authority"] == "NONE"
    assert research["signing_authority"] == "NONE"
    assert research["broadcast_authority"] == "NONE"
    validated = project_context.validate_projects_registry(ROOT, tomllib.loads(PROJECTS_PATH.read_text(encoding="utf-8")))
    projection = project_context.execution_authority_projection(ROOT, validated)
    assert projection["issues"] == []
    assert projection["active_project"]["project_id"] == ORDER_FLOW_ID
    assert PROJECT_ID not in projection["identity_by_project"]
    assert STAGE_B_ID not in projection["identity_by_project"]
''')
    test = replace_function(test, 'test_context_projects_operational_and_research_actions_independently', '''
def test_context_projects_operational_and_stage_b_research_actions_independently():
    data = project_context.context_data(ROOT)
    assert data["active_project"]["project_id"] == ORDER_FLOW_ID
    assert data["active_research_project"]["project_id"] == STAGE_B_ID
    assert data["current_permitted_next_action"] == project(ORDER_FLOW_ID)["next_action"]
    assert data["current_permitted_research_action"] == project(STAGE_B_ID)["next_action"]
''')
    test = replace_function(test, 'test_project_row_binds_the_authorization_and_preserves_zero_execution_receipts', '''
def test_stage_a_project_row_is_closed_and_preserves_zero_execution_receipts():
    authorization = load_json(AUTH_PATH)
    row = project(PROJECT_ID)
    assert row["state"] == "CLOSED_PASS"
    assert row["implementation_authorized"] is False
    assert row["implementation_completed"] is True
    assert row["superseded_by"] == [STAGE_B_ID]
    assert row["authority_level"] == "BOUNDED_PARALLEL_RESEARCH_REAUTHORIZATION"
    assert row["historical_preregistration_digest"] == PREREG_DIGEST
    assert row["qntyspot_source_commit"] == QNTYSPOT_SOURCE
    assert row["candidate_count"] == 12
    assert row["outer_initial_access"] == "INACCESSIBLE"
    assert row["scientific_design_mutation"] is False
    assert row["market_data_acquisition_count"] == 0
    assert row["backtest_count"] == 0
    assert row["strategy_test_count"] == 0
    assert row["outer_evaluation_count"] == 0
    assert row["research_ledger_state_changed"] is False
    assert row["qntyspot_changed"] is False
    assert row["order_flow_changed"] is False
    assert row["hetzner_touched"] is False
    assert authorization["project_id"] == row["project_id"]
    assert "experiments/research/qntyspot_ink_shadow_performance_dev_acquisition_activation_v0/activation.json" not in row["authoritative_artifacts"]
''')
    test = replace_function(test, 'test_generated_roadmap_names_the_active_research_lane', '''
def test_generated_roadmap_names_stage_b_as_the_active_research_lane():
    expected = (
        "- `QntySpot Ink shadow performance DEV acquisition research V1` — `ACTIVE_RESEARCH`. "
        + project(STAGE_B_ID)["next_action"]
    )
    roadmap = project_context._roadmap_bytes(ROOT).decode("utf-8")
    assert expected in roadmap
    assert "`QntySpot Ink shadow performance research V1` — `ACTIVE_RESEARCH`" not in roadmap
''')
    path.write_text(test, encoding='utf-8')


def patch_generic_context_test() -> None:
    path = Path('tests/test_project_context_v0.py')
    text = path.read_text(encoding='utf-8')
    old_id = '- Active research project: `QNTYSPOT_INK_SHADOW_PERFORMANCE_RESEARCH_V1`.'
    new_id = '- Active research project: `QNTYSPOT_INK_SHADOW_PERFORMANCE_DEV_ACQUISITION_RESEARCH_V1`.'
    if text.count(old_id) != 1:
        raise SystemExit('generic context Stage-A active-research expectation missing')
    text = text.replace(old_id, new_id, 1)
    old_action = (
        '- Permitted research action: STAGE_A_ACTIVE_RESEARCH: finish this governance-only reauthorization and canonicalize it. '
        'Before exact canonical merge: no market-data/economic access. After exact canonical merge: Stage B may qualify sources and acquire DEV-only evidence under the frozen firewall. '
        'Candidate evaluation, OUTER access, QntySpot mutation, trading, signing, broadcast, and capital remain unauthorized.'
    )
    new_action = '- Permitted research action: ' + STAGE_B_NEXT
    if text.count(old_action) != 1:
        raise SystemExit('generic context Stage-A research action expectation missing')
    path.write_text(text.replace(old_action, new_action, 1), encoding='utf-8')


if __name__ == '__main__':
    patch_registry()
    patch_stage_a_tests()
    patch_generic_context_test()
