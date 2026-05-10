from __future__ import annotations

from orchestrator_agents.registry import AGENT_REGISTRY
from orchestrator_agents.schemas import RouteDecision

ROUTER_SYSTEM_PROMPT = """
You are a routing classifier for a multi-agent workflow.
Your job is only to choose the best subagent. Do not solve the user's task.

Available agents:
{agent_catalog}

Rules:
- Choose exactly one target_agent unless clarification is required.
- If the request requires current/source-backed research, choose research_agent first.
- If the request asks for implementation, debugging, architecture, or tests, choose coding_agent.
- If the request asks for rewriting, summarization, emails, or tone changes, choose writing_agent.
- If the request is ambiguous or confidence is low, choose clarification_node.
- Return structured output matching RouteDecision.
""".strip()


def render_agent_catalog() -> str:
    lines = []
    for spec in AGENT_REGISTRY.values():
        lines.append(
            f"- {spec.name}: {spec.description}\n"
            f"  Owns intents: {', '.join(spec.owns_intents)}\n"
            f"  Positive examples: {', '.join(spec.positive_examples)}\n"
            f"  Negative examples: {', '.join(spec.negative_examples)}"
        )
    return "\n".join(lines)


def llm_route(user_query: str) -> RouteDecision:
    """LLM router boundary.

    This example intentionally uses a deterministic fallback so the repo can run
    without credentials. In production, replace this body with something like:

        router = llm.with_structured_output(RouteDecision)
        return router.invoke([
            {"role": "system", "content": ROUTER_SYSTEM_PROMPT.format(
                agent_catalog=render_agent_catalog()
            )},
            {"role": "user", "content": user_query},
        ])
    """

    _ = ROUTER_SYSTEM_PROMPT.format(agent_catalog=render_agent_catalog())

    return RouteDecision(
        primary_intent="unclear",
        target_agent="clarification_node",
        confidence=0.42,
        second_best_agent="fallback_agent",
        second_best_confidence=0.36,
        ambiguity_score=0.78,
        requires_clarification=True,
        clarification_question=(
            "Can you clarify whether you want research, coding help, or writing/editing help?"
        ),
        reasoning_summary="No high-confidence deterministic route matched, and fallback router is uncertain.",
    )
