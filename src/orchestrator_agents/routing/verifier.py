from __future__ import annotations

from orchestrator_agents.registry import AGENT_REGISTRY
from orchestrator_agents.schemas import RoutePlan, RouteVerification


def verify_route_plan(plan: RoutePlan) -> RouteVerification:
    """Deterministic verification layer. Add LLM verifier in production if needed."""

    if plan.mode in {"clarification", "fallback"}:
        return RouteVerification(
            approved=True,
            confidence=1.0,
            reason=f"Control mode {plan.mode} is allowed.",
        )

    if not plan.steps:
        return RouteVerification(
            approved=False,
            corrected_destination="fallback_agent",
            confidence=1.0,
            reason="Executable route plan has no steps.",
        )

    for step in plan.steps:
        spec = AGENT_REGISTRY.get(step.agent)
        if spec is None:
            return RouteVerification(
                approved=False,
                corrected_destination="fallback_agent",
                confidence=1.0,
                reason=f"Step agent {step.agent} is not registered.",
            )
        if not spec.enabled:
            return RouteVerification(
                approved=False,
                corrected_destination="fallback_agent",
                confidence=1.0,
                reason=f"Step agent {step.agent} is disabled.",
            )

    return RouteVerification(
        approved=True,
        confidence=0.95,
        reason="All route plan steps reference registered enabled agents.",
    )


# Backward-compatible alias.
def verify_route(decision):
    from orchestrator_agents.routing.service import decision_to_route_plan

    return verify_route_plan(decision_to_route_plan(decision))
