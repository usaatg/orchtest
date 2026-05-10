from __future__ import annotations

from orchestrator_agents.registry import AGENT_REGISTRY
from orchestrator_agents.schemas import Destination, RoutePlan, RouteVerification

RISK_THRESHOLDS = {
    "low": 0.70,
    "medium": 0.78,
    "high": 0.85,
}
AMBIGUITY_THRESHOLD = 0.35
MIN_MARGIN_BETWEEN_TOP_TWO = 0.15


def apply_route_plan_policy(plan: RoutePlan, verification: RouteVerification) -> tuple[Destination, str]:
    """The router proposes; this deterministic gate decides."""

    if not verification.approved:
        return verification.corrected_destination or "clarification_node", verification.reason

    if plan.mode == "clarification" or plan.requires_clarification:
        return "clarification_node", "Route plan requires clarification."

    if plan.mode == "fallback":
        return "fallback_agent", plan.fallback_reason or "No specialist route matched."

    if not plan.steps:
        return "fallback_agent", "No executable steps were provided."

    if plan.ambiguity_score > AMBIGUITY_THRESHOLD:
        return "clarification_node", "Ambiguity score is above policy threshold."

    if plan.second_best_confidence is not None:
        if plan.confidence - plan.second_best_confidence < MIN_MARGIN_BETWEEN_TOP_TWO:
            return "clarification_node", "Top route confidence margin is too small."

    if plan.missing_inputs:
        return "clarification_node", "Route plan has missing required inputs."

    # Risk-aware threshold: require the max threshold across all planned agents.
    required = 0.0
    for step in plan.steps:
        spec = AGENT_REGISTRY[step.agent]
        threshold = spec.confidence_threshold_override or RISK_THRESHOLDS[spec.risk_level]
        required = max(required, threshold)

    if plan.confidence < required:
        return "clarification_node", f"Route confidence {plan.confidence:.2f} below required {required:.2f}."

    return plan.steps[0].agent, "Route plan passed policy gate."


# Backward-compatible alias.
def apply_route_policy(decision, verification) -> Destination:
    from orchestrator_agents.routing.service import decision_to_route_plan

    destination, _reason = apply_route_plan_policy(decision_to_route_plan(decision), verification)
    return destination
