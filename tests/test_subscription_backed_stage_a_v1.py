from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from qntylab.subscription_backed_stage_a_v1 import (
    ARM_ORDER,
    AuthorityState,
    DispatchResult,
    DSHManagedProductAdapter,
    DeterministicController,
    FailClosed,
    FrozenSpec,
    NativeDirectProductAdapter,
    ProductSettings,
    ROLE_MAPPING,
    WorkspaceEvidence,
    derive_arm_order,
)


@dataclass
class FakeProduct:
    review_status: DispatchResult = field(default_factory=DispatchResult)
    calls: list[object] = field(default_factory=list)
    provider_calls: int = 0

    def start(self, invocation):
        self.calls.append(invocation)
        if invocation.role == "HOSTILE_REVIEWER" and invocation.phase == "initial":
            return self.review_status
        if invocation.role == "BUILDER" and invocation.phase == "repair":
            return DispatchResult()
        return DispatchResult()


class RateLimitedProduct(FakeProduct):
    def start(self, invocation):
        self.calls.append(invocation)
        return DispatchResult(status="RATE_LIMIT", rate_limit_event="SUBSCRIPTION_THROTTLED")


def settings() -> dict[str, ProductSettings]:
    return {
        "BUILDER": ProductSettings("CODEX", "/profile/a", "CHATGPT_SUBSCRIPTION", "codex-a", "codex-cli 0.147.0"),
        "HOSTILE_REVIEWER": ProductSettings("CLAUDE_CODE", "/profile/claude", "CLAUDE_SUBSCRIPTION", "claude", "2.1.223"),
        "VERIFIER": ProductSettings("CODEX", "/profile/b", "CHATGPT_SUBSCRIPTION", "codex-b", "codex-cli 0.147.0"),
    }


def spec(**overrides) -> FrozenSpec:
    values = {
        "task_digest": "task",
        "scorer_digest": "scorer",
        "intervention_digest": "intervention",
        "gate_digest": "gate",
        "receipt_digest": "receipt",
        "role_prompts": {
            "CONTROLLER": b"controller",
            "BUILDER": b"builder",
            "HOSTILE_REVIEWER": b"review",
            "VERIFIER": b"verify",
        },
        "treatment_settings": settings(),
        "baseline_settings": settings(),
    }
    values.update(overrides)
    return FrozenSpec(**values)


def controller(specification=None, authority=None, released=None):
    released = [] if released is None else released
    return DeterministicController(
        specification or spec(),
        authority or AuthorityState(canonical_merge_verified=True, v0_supersession_canonical=True),
        released.append,
    ), released


def adapters(treatment=None, baseline=None):
    treatment = treatment or FakeProduct()
    baseline = baseline or FakeProduct()
    return (
        {"DSH_TREATMENT": DSHManagedProductAdapter(treatment, WorkspaceEvidence()), "NATIVE_BASELINE": NativeDirectProductAdapter(baseline, WorkspaceEvidence())},
        treatment,
        baseline,
    )


def test_frozen_arm_order_and_role_mapping_are_shared():
    assert derive_arm_order() == ("DSH_TREATMENT", "NATIVE_BASELINE")
    assert ARM_ORDER == ("DSH_TREATMENT", "NATIVE_BASELINE")
    assert ROLE_MAPPING == {
        "CONTROLLER": "DETERMINISTIC_NON_MODEL_CONTROLLER",
        "BUILDER": "CODEX_PROFILE_A",
        "HOSTILE_REVIEWER": "CLAUDE_CODE_PRODUCT",
        "VERIFIER": "CODEX_PROFILE_B",
    }


def test_treatment_calls_dsh_provider_and_baseline_bypasses_it():
    control, released = controller()
    arm_adapters, treatment, baseline = adapters()
    result = control.run_episode(arm_adapters)
    assert result.classification == "AWAITING_FROZEN_SCORER"
    assert released and all(receipt.sealed for receipt in released[0])
    assert treatment.calls and baseline.calls
    assert all(call.arm_id == "DSH_TREATMENT" for call in treatment.calls)
    assert all(call.arm_id == "NATIVE_BASELINE" for call in baseline.calls)
    assert {call.role for call in treatment.calls} == {"BUILDER", "HOSTILE_REVIEWER", "VERIFIER"}


def test_role_order_is_identical_and_controller_test_is_non_model():
    control, _ = controller()
    arm_adapters, _, _ = adapters()
    result = control.run_episode(arm_adapters)
    for receipt in result.receipts:
        assert [(event["role"], event["phase"]) for event in receipt.events] == [
            ("BUILDER", "initial"),
            ("TEST", "controller_test"),
            ("HOSTILE_REVIEWER", "initial"),
            ("VERIFIER", "initial"),
        ]
        assert all(event.get("role") != "CONTROLLER" for event in receipt.events)


def test_targeted_rereview_only_follows_critical_or_high_repair():
    reviewer = FakeProduct(review_status=DispatchResult(status="REPAIR_REQUIRED", severity="HIGH"))
    control, _ = controller()
    arm_adapters, _, baseline = adapters(treatment=reviewer)
    result = control.run_episode(arm_adapters)
    treatment_events = result.receipts[0].events
    assert [(event["role"], event["phase"]) for event in treatment_events] == [
        ("BUILDER", "initial"),
        ("TEST", "controller_test"),
        ("HOSTILE_REVIEWER", "initial"),
        ("BUILDER", "repair"),
        ("HOSTILE_REVIEWER", "targeted_rereview"),
        ("VERIFIER", "initial"),
    ]
    assert [(call.role, call.phase) for call in reviewer.calls] == [
        ("BUILDER", "initial"),
        ("HOSTILE_REVIEWER", "initial"),
        ("BUILDER", "repair"),
        ("HOSTILE_REVIEWER", "targeted_rereview"),
        ("VERIFIER", "initial"),
    ]
    assert len(baseline.calls) == 3


def test_medium_review_does_not_trigger_repair_or_rereview():
    reviewer = FakeProduct(review_status=DispatchResult(status="REPAIR_REQUIRED", severity="MEDIUM"))
    control, _ = controller()
    arm_adapters, _, _ = adapters(treatment=reviewer)
    result = control.run_episode(arm_adapters)
    assert [(call.role, call.phase) for call in reviewer.calls] == [
        ("BUILDER", "initial"),
        ("HOSTILE_REVIEWER", "initial"),
        ("VERIFIER", "initial"),
    ]
    assert result.classification == "AWAITING_FROZEN_SCORER"


def test_scorer_release_waits_for_both_sealed_receipts_and_one_episode_only():
    control, released = controller()
    arm_adapters, _, _ = adapters()
    result = control.run_episode(arm_adapters)
    assert result.scorer_released is True
    assert len(released) == 1
    assert all(receipt.sealed for receipt in released[0])
    with pytest.raises(FailClosed, match="second V1 episode"):
        control.run_episode(arm_adapters)


def test_one_initial_dispatch_per_role_and_arm():
    control, _ = controller()
    arm_adapters, _, _ = adapters()
    result = control.run_episode(arm_adapters)
    for receipt in result.receipts:
        assert receipt.initial_dispatch_count == {"BUILDER": 1, "HOSTILE_REVIEWER": 1, "VERIFIER": 1}


def test_branch_local_authority_and_unsuperseded_v0_fail_closed():
    with pytest.raises(FailClosed, match="branch-local"):
        controller(authority=AuthorityState(False, True))
    with pytest.raises(FailClosed, match="superseded"):
        controller(authority=AuthorityState(True, False))


def test_product_profile_mismatch_fails_closed():
    changed = settings()
    changed["VERIFIER"] = ProductSettings("CODEX", "/profile/other", "CHATGPT_SUBSCRIPTION", "different", "codex-cli 0.147.0")
    with pytest.raises(FailClosed, match="observable product settings"):
        controller(specification=spec(baseline_settings=changed))


def test_api_key_presence_fails_closed():
    class ApiKeyProduct(FakeProduct):
        def start(self, invocation):
            return DispatchResult(api_keys_present=("OPENAI_API_KEY",))

    control, _ = controller()
    arm_adapters, _, _ = adapters(treatment=ApiKeyProduct())
    with pytest.raises(FailClosed, match="API key"):
        control.run_episode(arm_adapters)


def test_parent_dsh_llm_activity_fails_closed():
    class ParentLlmProduct(FakeProduct):
        def start(self, invocation):
            return DispatchResult(parent_llm_requests=1, parent_llm_provider="OPENAI")

    control, _ = controller()
    arm_adapters, _, _ = adapters(treatment=ParentLlmProduct())
    with pytest.raises(FailClosed, match="parent LLM"):
        control.run_episode(arm_adapters)


def test_rate_limit_is_invalid_capacity_not_scientific_win():
    control, released = controller()
    arm_adapters, _, baseline = adapters(treatment=RateLimitedProduct())
    result = control.run_episode(arm_adapters)
    assert result.classification == "STAGE_A_V1_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY"
    assert all(receipt.sealed for receipt in result.receipts)
    assert result.receipts[0].rate_limit_events == ["SUBSCRIPTION_THROTTLED"]
    assert len(baseline.calls) == 3
    assert released


def test_answer_key_firewall_fails_closed_before_any_dispatch():
    control, _ = controller()
    arm_adapters, treatment, _ = adapters()
    arm_adapters["DSH_TREATMENT"] = DSHManagedProductAdapter(
        treatment,
        WorkspaceEvidence(answer_key_resolvable=True),
    )
    with pytest.raises(FailClosed, match="answer-key firewall"):
        control.run_episode(arm_adapters)
    assert treatment.calls == []


def test_retry_ceiling_is_shared_and_enforced():
    class RetryProduct(FakeProduct):
        def start(self, invocation):
            self.calls.append(invocation)
            if invocation.role == "BUILDER":
                return DispatchResult(status="RETRYABLE", machine_retryable=True)
            return DispatchResult()

    control, _ = controller()
    arm_adapters, treatment, _ = adapters(treatment=RetryProduct())
    with pytest.raises(FailClosed, match="retry ceiling"):
        control.run_episode(arm_adapters)
    assert len(treatment.calls) == 3
