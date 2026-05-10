from __future__ import annotations

from orchestrator_agents.routing.deterministic import deterministic_route_plan
from orchestrator_agents.routing.llm_router import llm_route_plan
from orchestrator_agents.routing.policy import apply_route_plan_policy
from typing import Any, Mapping

from orchestrator_agents.registry import AGENT_REGISTRY
from orchestrator_agents.routing.verifier import verify_route_plan
from orchestrator_agents.schemas import Destination, RouteDecision, RoutePlan, RouteStep, RouteVerification


def route_plan_to_decision(plan: RoutePlan) -> RouteDecision:
    target: Destination = plan.first_destination
    return RouteDecision(
        primary_intent=plan.steps[0].output_key if plan.steps else plan.mode,
        target_agent=target,
        confidence=plan.confidence,
        second_best_agent=plan.second_best_agent,
        second_best_confidence=plan.second_best_confidence,
        ambiguity_score=plan.ambiguity_score,
        requires_clarification=plan.requires_clarification,
        clarification_question=plan.clarification_question,
        missing_inputs=plan.missing_inputs,
        reasoning_summary=plan.reasoning_summary,
    )


def decision_to_route_plan(decision: RouteDecision) -> RoutePlan:
    if decision.target_agent == "clarification_node":
        return RoutePlan(
            mode="clarification",
            confidence=decision.confidence,
            second_best_agent=decision.second_best_agent,
            second_best_confidence=decision.second_best_confidence,
            ambiguity_score=decision.ambiguity_score,
            requires_clarification=True,
            clarification_question=decision.clarification_question,
            missing_inputs=decision.missing_inputs,
            reasoning_summary=decision.reasoning_summary,
        )
    if decision.target_agent == "fallback_agent":
        return RoutePlan(
            mode="fallback",
            confidence=decision.confidence,
            second_best_agent=decision.second_best_agent,
            second_best_confidence=decision.second_best_confidence,
            ambiguity_score=decision.ambiguity_score,
            requires_clarification=False,
            fallback_reason=decision.reasoning_summary,
            missing_inputs=decision.missing_inputs,
            reasoning_summary=decision.reasoning_summary,
        )
    return RoutePlan(
        mode="single_agent",
        steps=[
            RouteStep(
                step_id="legacy_step",
                agent=decision.target_agent,
                task=decision.reasoning_summary,
                output_key=decision.primary_intent,
            )
        ],
        confidence=decision.confidence,
        second_best_agent=decision.second_best_agent,
        second_best_confidence=decision.second_best_confidence,
        ambiguity_score=decision.ambiguity_score,
        requires_clarification=decision.requires_clarification,
        clarification_question=decision.clarification_question,
        missing_inputs=decision.missing_inputs,
        reasoning_summary=decision.reasoning_summary,
    )


class RoutingService:
    """Reusable routing control plane shared across agentic workflows."""

    def decide_plan(
        self, user_query: str, *, state: Mapping[str, Any] | None = None
    ) -> tuple[RoutePlan, RouteVerification, Destination, str]:
        plan = deterministic_route_plan(user_query, state=dict(state or {})) or llm_route_plan(user_query)
        plan = self._apply_required_input_validation(plan, state or {"user_query": user_query})
        verification = verify_route_plan(plan)
        destination, policy_reason = apply_route_plan_policy(plan, verification)
        return plan, verification, destination, policy_reason

    def _apply_required_input_validation(
        self, plan: RoutePlan, state: Mapping[str, Any]
    ) -> RoutePlan:
        """Populate missing_inputs from AgentSpec.required_state_fields.

        The router proposes the plan, but required input validation should be deterministic
        and workflow-aware. This keeps the policy gate from sending an agent a task when
        mandatory state fields are absent.
        """
        if plan.mode not in {"single_agent", "multi_agent"} or not plan.steps:
            return plan

        missing: set[str] = set(plan.missing_inputs)
        for step in plan.steps:
            spec = AGENT_REGISTRY[step.agent]
            for field in spec.required_state_fields:
                value = state.get(field)
                if value is None or value == "":
                    missing.add(field)

        if not missing:
            return plan
        return plan.model_copy(update={"missing_inputs": sorted(missing)})

    # Backward-compatible v1 API.
    def decide(self, user_query: str) -> tuple[RouteDecision, RouteVerification, Destination]:
        plan, verification, destination, _reason = self.decide_plan(user_query)
        return route_plan_to_decision(plan), verification, destination
