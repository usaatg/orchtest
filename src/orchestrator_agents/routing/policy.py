from __future__ import annotations

from orchestrator_agents.registry import AGENT_REGISTRY
from orchestrator_agents.schemas import Destination, RouteDecision, RouteVerification

ROUTE_CONFIDENCE_THRESHOLD = 0.75
HIGH_RISK_CONFIDENCE_THRESHOLD = 0.85
AMBIGUITY_THRESHOLD = 0.35
MIN_MARGIN_BETWEEN_TOP_TWO = 0.15


def apply_route_policy(decision: RouteDecision, verification: RouteVerification) -> Destination:
    """Final deterministic policy gate.

    The LLM/router proposes; this policy gate decides whether the proposed route
    is allowed. This is the most important piece for production routing quality.
    """

    if not verification.approved:
        return verification.corrected_destination or "clarification_node"

    if decision.target_agent in {"clarification_node", "fallback_agent"}:
        return decision.target_agent

    spec = AGENT_REGISTRY.get(decision.target_agent)
    if spec is None or not spec.enabled:
        return "fallback_agent"

    if decision.requires_clarification:
        return "clarification_node"

    required_threshold = (
        HIGH_RISK_CONFIDENCE_THRESHOLD if spec.risk_level == "high" else ROUTE_CONFIDENCE_THRESHOLD
    )
    if decision.confidence < required_threshold:
        return "clarification_node"

    if decision.ambiguity_score > AMBIGUITY_THRESHOLD:
        return "clarification_node"

    if decision.second_best_confidence is not None:
        if decision.confidence - decision.second_best_confidence < MIN_MARGIN_BETWEEN_TOP_TWO:
            return "clarification_node"

    if decision.missing_inputs:
        return "clarification_node"

    return decision.target_agent
