from __future__ import annotations

from orchestrator_agents.registry import AGENT_REGISTRY
from orchestrator_agents.schemas import RouteDecision, RouteVerification


def verify_route(decision: RouteDecision) -> RouteVerification:
    """Deterministic verification layer for route safety.

    In production you can add an LLM verifier here, but deterministic checks should
    remain because they are easier to test and reason about.
    """

    if decision.target_agent in {"clarification_node", "fallback_agent"}:
        return RouteVerification(
            approved=True,
            confidence=1.0,
            reason="Non-specialist destination is always allowed.",
        )

    spec = AGENT_REGISTRY.get(decision.target_agent)
    if spec is None:
        return RouteVerification(
            approved=False,
            corrected_destination="fallback_agent",
            confidence=1.0,
            reason="Target agent is not registered.",
        )

    if not spec.enabled:
        return RouteVerification(
            approved=False,
            corrected_destination="fallback_agent",
            confidence=1.0,
            reason="Target agent is disabled.",
        )

    return RouteVerification(
        approved=True,
        confidence=0.95,
        reason=f"Target agent {decision.target_agent} is registered and enabled.",
    )
