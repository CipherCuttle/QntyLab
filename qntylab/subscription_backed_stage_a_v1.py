"""Deterministic, non-model controller contract for subscription-backed Stage-A V1.

This module only schedules and seals a bounded comparison.  Product adapters
own product invocation; the controller never solves, reviews, patches, or
scores the frozen task.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence


EXPERIMENT_ID = "SUBSCRIPTION_BACKED_STAGE_A_V1"
DSH_ARM = "DSH_TREATMENT"
NATIVE_ARM = "NATIVE_BASELINE"
ARM_ORDER = (DSH_ARM, NATIVE_ARM)
ROLE_ORDER = ("BUILDER", "TEST", "HOSTILE_REVIEWER", "VERIFIER")
ROLE_MAPPING = {
    "CONTROLLER": "DETERMINISTIC_NON_MODEL_CONTROLLER",
    "BUILDER": "CODEX_PROFILE_A",
    "HOSTILE_REVIEWER": "CLAUDE_CODE_PRODUCT",
    "VERIFIER": "CODEX_PROFILE_B",
}
REPAIR_ROLE = "BUILDER"
TARGETED_REREVIEW_ROLE = "HOSTILE_REVIEWER"
API_KEY_NAMES = (
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
    "OPENROUTER_API_KEY",
)
MAX_MACHINE_RETRIES = 2
MAX_REVIEW_LOOPS = 1


class FailClosed(RuntimeError):
    """Raised when a frozen hard gate or authority boundary is not proven."""


@dataclass(frozen=True)
class ProductSettings:
    product: str
    profile: str
    auth_class: str
    config_digest: str
    version: str
    model_selector: str = "NOT_EXPOSED"
    reasoning_setting: str = "NOT_EXPOSED"
    sandbox_mode: str = "NOT_EXPOSED"
    approval_mode: str = "NOT_EXPOSED"
    tool_permissions: tuple[str, ...] = ()
    environment_policy: str = "FROZEN_AND_CAPTURED"


@dataclass(frozen=True)
class AuthorityState:
    canonical_merge_verified: bool
    v0_supersession_canonical: bool
    episode_count: int = 1
    episode_consumed: bool = False


@dataclass(frozen=True)
class WorkspaceEvidence:
    answer_key_resolvable: bool = False
    git_remotes_visible: bool = False
    sealed_refs_visible: bool = False
    packed_objects_visible: bool = False

    def passes_answer_key_firewall(self) -> bool:
        return not any(
            (
                self.answer_key_resolvable,
                self.git_remotes_visible,
                self.sealed_refs_visible,
                self.packed_objects_visible,
            )
        )


@dataclass(frozen=True)
class Invocation:
    arm_id: str
    role: str
    phase: str
    session_id: str
    prompt_bytes: bytes
    retry_index: int


@dataclass(frozen=True)
class DispatchResult:
    status: str = "COMPLETED"
    severity: str = "NONE"
    machine_retryable: bool = False
    api_keys_present: tuple[str, ...] = ()
    parent_llm_requests: int = 0
    parent_llm_provider: str = "NONE"
    process_owned: bool = True
    rate_limit_event: str | None = None
    product_config_digest: str | None = None


class Adapter(Protocol):
    transport: str
    workspace_evidence: WorkspaceEvidence

    def dispatch(self, invocation: Invocation) -> DispatchResult:
        ...


class DSHProvider(Protocol):
    def start(self, invocation: Invocation) -> DispatchResult:
        ...


class NativeProductTransport(Protocol):
    def start(self, invocation: Invocation) -> DispatchResult:
        ...


class DSHManagedProductAdapter:
    """Adapter boundary for the pinned DSH SubagentRuntime/provider path."""

    transport = "DSH_MANAGED_PRODUCT_SUBAGENT_ORCHESTRATION_V1"

    def __init__(self, provider: DSHProvider, workspace_evidence: WorkspaceEvidence):
        self._provider = provider
        self.workspace_evidence = workspace_evidence

    def dispatch(self, invocation: Invocation) -> DispatchResult:
        return self._provider.start(invocation)


class NativeDirectProductAdapter:
    """Adapter boundary for direct product invocation, with no DSH runtime."""

    transport = "NATIVE_DIRECT_PRODUCT_ORCHESTRATION_V1"

    def __init__(self, transport: NativeProductTransport, workspace_evidence: WorkspaceEvidence):
        self._transport = transport
        self.workspace_evidence = workspace_evidence

    def dispatch(self, invocation: Invocation) -> DispatchResult:
        return self._transport.start(invocation)


@dataclass(frozen=True)
class FrozenSpec:
    task_digest: str
    scorer_digest: str
    intervention_digest: str
    gate_digest: str
    receipt_digest: str
    role_prompts: Mapping[str, bytes]
    treatment_settings: Mapping[str, ProductSettings]
    baseline_settings: Mapping[str, ProductSettings]
    derived_arm_order: tuple[str, ...] = ARM_ORDER
    max_machine_retries: int = MAX_MACHINE_RETRIES


@dataclass
class ArmReceipt:
    arm_id: str
    transport: str
    events: list[dict[str, Any]] = field(default_factory=list)
    initial_dispatch_count: dict[str, int] = field(default_factory=dict)
    sealed: bool = False
    answer_key_firewall: str = "UNPROVEN"
    rate_limit_events: list[str] = field(default_factory=list)
    termination: str = "NOT_STARTED"


@dataclass
class EpisodeResult:
    classification: str
    receipts: tuple[ArmReceipt, ...]
    scorer_released: bool


def _settings_without_transport(settings: Mapping[str, ProductSettings]) -> dict[str, ProductSettings]:
    return {role: settings[role] for role in ("BUILDER", "HOSTILE_REVIEWER", "VERIFIER")}


def validate_preflight(spec: FrozenSpec, authority: AuthorityState) -> None:
    if not authority.canonical_merge_verified:
        raise FailClosed("V1 execution authority is branch-local; canonical merge is unverified")
    if not authority.v0_supersession_canonical:
        raise FailClosed("V0 execution authority has not been canonically superseded")
    if authority.episode_count != 1:
        raise FailClosed("V1 authority must authorize exactly one episode")
    if authority.episode_consumed:
        raise FailClosed("V1 episode authority has already been consumed")
    if spec.derived_arm_order != ARM_ORDER:
        raise FailClosed("arm order differs from the frozen derived order")
    if tuple(spec.role_prompts) != tuple(ROLE_MAPPING):
        raise FailClosed("role prompt identity is incomplete or reordered")
    if _settings_without_transport(spec.treatment_settings) != _settings_without_transport(spec.baseline_settings):
        raise FailClosed("observable product settings differ between arms")
    if spec.max_machine_retries < 0:
        raise FailClosed("negative retry ceiling")


class DeterministicController:
    """Owns scheduling, bounded retry accounting, and post-termination release."""

    def __init__(
        self,
        spec: FrozenSpec,
        authority: AuthorityState,
        scorer_release: Callable[[tuple[ArmReceipt, ...]], None],
    ):
        validate_preflight(spec, authority)
        self.spec = spec
        self.authority = authority
        self._scorer_release = scorer_release
        self._episode_started = False

    def run_episode(self, adapters: Mapping[str, Adapter]) -> EpisodeResult:
        if self._episode_started:
            raise FailClosed("controller cannot run a second V1 episode")
        if tuple(adapters) != ARM_ORDER:
            raise FailClosed("adapters do not follow frozen arm order")
        self._episode_started = True
        receipts: list[ArmReceipt] = []
        for arm_id in ARM_ORDER:
            receipts.append(self._run_arm(arm_id, adapters[arm_id]))
        if not all(receipt.sealed for receipt in receipts):
            raise FailClosed("scorer release requires both sealed arm receipts")
        sealed = tuple(receipts)
        self._scorer_release(sealed)
        if any(receipt.rate_limit_events for receipt in receipts):
            classification = "STAGE_A_V1_INVALID_ENVIRONMENT_OR_PRODUCT_CAPACITY"
        else:
            classification = "AWAITING_FROZEN_SCORER"
        return EpisodeResult(classification, sealed, scorer_released=True)

    def _run_arm(self, arm_id: str, adapter: Adapter) -> ArmReceipt:
        receipt = ArmReceipt(arm_id=arm_id, transport=adapter.transport)
        if not adapter.workspace_evidence.passes_answer_key_firewall():
            raise FailClosed(f"answer-key firewall failed for {arm_id}")
        receipt.answer_key_firewall = "PASS"
        builder = self._run_role(receipt, adapter, arm_id, "BUILDER", "initial")
        if builder.status == "RATE_LIMIT":
            return receipt
        self._run_role(receipt, adapter, arm_id, "TEST", "controller_test")
        review = self._run_role(receipt, adapter, arm_id, "HOSTILE_REVIEWER", "initial")
        if review.status == "RATE_LIMIT":
            return receipt
        if review.status == "REPAIR_REQUIRED" and review.severity in {"CRITICAL", "HIGH"}:
            repair = self._run_role(receipt, adapter, arm_id, REPAIR_ROLE, "repair")
            if repair.status == "RATE_LIMIT":
                return receipt
            rereview = self._run_role(receipt, adapter, arm_id, TARGETED_REREVIEW_ROLE, "targeted_rereview")
            if rereview.status == "RATE_LIMIT":
                return receipt
            if rereview.status == "REPAIR_REQUIRED" and rereview.severity in {"CRITICAL", "HIGH"}:
                raise FailClosed("Critical/High finding remains after the single targeted rereview")
        verifier = self._run_role(receipt, adapter, arm_id, "VERIFIER", "initial")
        if verifier.status == "RATE_LIMIT":
            return receipt
        receipt.termination = "TERMINATED"
        receipt.sealed = True
        return receipt

    def _run_role(
        self,
        receipt: ArmReceipt,
        adapter: Adapter,
        arm_id: str,
        role: str,
        phase: str,
    ) -> DispatchResult:
        if role == "TEST":
            receipt.events.append({"role": role, "phase": phase, "controller_owned": True})
            return DispatchResult()
        if role not in self.spec.role_prompts:
            raise FailClosed(f"missing frozen prompt for {role}")
        retry_index = 0
        while True:
            session_id = f"{arm_id}:{role}:{phase}:{retry_index}"
            invocation = Invocation(
                arm_id=arm_id,
                role=role,
                phase=phase,
                session_id=session_id,
                prompt_bytes=self.spec.role_prompts[role],
                retry_index=retry_index,
            )
            if phase == "initial":
                receipt.initial_dispatch_count[role] = receipt.initial_dispatch_count.get(role, 0) + 1
            result = adapter.dispatch(invocation)
            self._validate_result(result, adapter, role)
            receipt.events.append(
                {
                    "role": role,
                    "phase": phase,
                    "session_id": session_id,
                    "retry_index": retry_index,
                    "status": result.status,
                }
            )
            if result.rate_limit_event:
                receipt.rate_limit_events.append(result.rate_limit_event)
            if result.status == "RATE_LIMIT":
                receipt.termination = "RATE_LIMIT"
                receipt.sealed = True
                return result
            if result.status not in {"COMPLETED", "REPAIR_REQUIRED", "RETRYABLE"}:
                raise FailClosed(f"unrecognized or failed product result: {result.status}")
            if result.status == "RETRYABLE" and not result.machine_retryable:
                raise FailClosed("retryable product result did not declare machine retryability")
            if result.status != "RETRYABLE" or not result.machine_retryable:
                return result
            if retry_index >= self.spec.max_machine_retries:
                raise FailClosed(f"machine retry ceiling exceeded for {arm_id}:{role}")
            retry_index += 1

    @staticmethod
    def _validate_result(result: DispatchResult, adapter: Adapter, role: str) -> None:
        if result.api_keys_present:
            raise FailClosed(f"model API key present during {role}: {result.api_keys_present}")
        if result.parent_llm_requests != 0 or result.parent_llm_provider != "NONE":
            raise FailClosed("DSH parent LLM activity detected")
        if not result.process_owned:
            raise FailClosed("controller does not own the worker process")
        if result.product_config_digest is not None and not result.product_config_digest:
            raise FailClosed("empty product configuration identity")
        if adapter.transport not in {
            "DSH_MANAGED_PRODUCT_SUBAGENT_ORCHESTRATION_V1",
            "NATIVE_DIRECT_PRODUCT_ORCHESTRATION_V1",
        }:
            raise FailClosed("unknown arm transport")


def derive_arm_order(experiment_id: str = EXPERIMENT_ID) -> tuple[str, ...]:
    import hashlib

    return tuple(sorted(ARM_ORDER, key=lambda arm: hashlib.sha256(f"{experiment_id}:{arm}".encode()).hexdigest()))


__all__ = [
    "API_KEY_NAMES",
    "ARM_ORDER",
    "AuthorityState",
    "DispatchResult",
    "DSHManagedProductAdapter",
    "DSHProvider",
    "DeterministicController",
    "EpisodeResult",
    "FailClosed",
    "FrozenSpec",
    "Invocation",
    "NativeDirectProductAdapter",
    "ProductSettings",
    "ROLE_MAPPING",
    "ROLE_ORDER",
    "WorkspaceEvidence",
    "derive_arm_order",
    "validate_preflight",
]
