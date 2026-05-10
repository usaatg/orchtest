from __future__ import annotations

from orchestrator_agents.routing.deterministic import deterministic_route
from orchestrator_agents.routing.llm_router import llm_route
from orchestrator_agents.routing.policy import apply_route_policy
from orchestrator_agents.routing.verifier import verify_route
from orchestrator_agents.schemas import Destination, RouteDecision, RouteVerification


class RoutingService:
    """Reusable routing service.

    This can be shared across workflows. The graph node should call this service
    rather than embedding route logic directly in the LangGraph node.
    """

    def decide(self, user_query: str) -> tuple[RouteDecision, RouteVerification, Destination]:
        decision = deterministic_route(user_query) or llm_route(user_query)
        verification = verify_route(decision)
        destination = apply_route_policy(decision, verification)
        return decision, verification, destination
