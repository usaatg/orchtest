from __future__ import annotations

from orchestrator_agents.schemas import RoutePlan

ROUTER_SYSTEM_PROMPT = """
You are an orchestration router for a multi-agent system.
Choose a route plan. Do not answer the user. Do not call tools.
Prefer clarification when the request is ambiguous. Prefer research before coding when current facts/sources are required.
Return structured output matching RoutePlan.
"""


def llm_route_plan(user_query: str) -> RoutePlan:
    """Mock structured LLM router.

    Replace this with:
        router = llm.with_structured_output(RoutePlan)
        router.invoke([...])
    """
    return RoutePlan(
        mode="fallback",
        steps=[],
        confidence=0.62,
        ambiguity_score=0.30,
        requires_clarification=False,
        fallback_reason="No specialist route matched; use general fallback.",
        reasoning_summary="The request did not match a specialist route with high confidence.",
    )


# Backward-compatible alias.
def llm_route(user_query: str):
    from orchestrator_agents.routing.service import route_plan_to_decision

    return route_plan_to_decision(llm_route_plan(user_query))
