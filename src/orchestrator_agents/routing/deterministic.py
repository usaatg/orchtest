from __future__ import annotations

from uuid import uuid4

from orchestrator_agents.schemas import RoutePlan, RouteStep


def _step(agent: str, task: str, output_key: str) -> RouteStep:
    return RouteStep(step_id=f"step_{uuid4().hex[:8]}", agent=agent, task=task, output_key=output_key)  # type: ignore[arg-type]


def deterministic_route_plan(user_query: str) -> RoutePlan | None:
    """High-precision rules only. Avoid broad brittle keyword matching."""

    q = user_query.lower()
    research_terms = {"latest", "current", "research", "find", "sources", "cite", "paper", "docs"}
    coding_terms = {"python", "code", "build", "implement", "implementation", "api", "pytest", "debug", "workflow"}
    coding_context_terms = {"langgraph", "langchain"}
    writing_terms = {"rewrite", "draft", "email", "summarize", "summary", "tone", "polish"}

    has_research = any(t in q for t in research_terms)
    has_coding = any(t in q for t in coding_terms)
    has_coding_context = any(t in q for t in coding_context_terms)
    # LangGraph/LangChain alone can be research subject matter; require an action term for coding.
    has_coding = has_coding or (has_coding_context and any(t in q for t in {"build", "code", "implement", "python", "debug", "workflow"}))
    has_writing = any(t in q for t in writing_terms)

    # Multi-agent route plan: current/source-backed info first, then implementation.
    if has_research and has_coding:
        return RoutePlan(
            mode="multi_agent",
            steps=[
                _step("research_agent", "Gather concise source-backed context for the implementation task.", "research_summary"),
                _step("coding_agent", "Generate implementation guidance using the research artifact(s).", "coding_plan"),
            ],
            confidence=0.90,
            second_best_agent="coding_agent",
            second_best_confidence=0.68,
            ambiguity_score=0.10,
            requires_clarification=False,
            reasoning_summary="Request requires research first and coding second.",
        )

    if has_coding:
        return RoutePlan(
            mode="single_agent",
            steps=[_step("coding_agent", "Handle the software engineering request.", "coding_result")],
            confidence=0.88,
            ambiguity_score=0.10,
            requires_clarification=False,
            reasoning_summary="High-confidence coding/software terminology matched.",
        )

    if has_research:
        return RoutePlan(
            mode="single_agent",
            steps=[_step("research_agent", "Handle the research/source-backed request.", "research_result")],
            confidence=0.84,
            ambiguity_score=0.14,
            requires_clarification=False,
            reasoning_summary="High-confidence research/current-info terminology matched.",
        )

    if has_writing:
        return RoutePlan(
            mode="single_agent",
            steps=[_step("writing_agent", "Handle the writing/rewriting request.", "writing_result")],
            confidence=0.86,
            ambiguity_score=0.10,
            requires_clarification=False,
            reasoning_summary="High-confidence writing terminology matched.",
        )

    if len(q.split()) <= 8 and any(term in q for term in {"agent", "workflow", "this", "thing", "help"}):
        return RoutePlan(
            mode="clarification",
            steps=[],
            confidence=0.40,
            second_best_agent="fallback_agent",
            second_best_confidence=0.35,
            ambiguity_score=0.80,
            requires_clarification=True,
            clarification_question="Can you clarify whether you want coding help, research, or writing help?",
            reasoning_summary="The request is too ambiguous to route safely.",
        )

    return None


# Backward-compatible alias for older tests/code.
def deterministic_route(user_query: str):
    plan = deterministic_route_plan(user_query)
    if plan is None:
        return None
    from orchestrator_agents.routing.service import route_plan_to_decision

    return route_plan_to_decision(plan)
