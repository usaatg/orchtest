from __future__ import annotations

from orchestrator_agents.schemas import RouteDecision


def deterministic_route(user_query: str) -> RouteDecision | None:
    """High-precision deterministic routing rules.

    Keep these conservative. Rules should have low false-positive rates. The LLM
    router can handle softer semantic cases.
    """

    q = user_query.lower()

    research_terms = [
        "latest",
        "current docs",
        "research",
        "find sources",
        "cite",
        "paper",
        "compare products",
    ]
    coding_terms = [
        "langgraph",
        "python",
        "pytest",
        "fastapi",
        "github actions",
        "debug",
        "traceback",
        "codebase",
        "api",
    ]
    writing_terms = [
        "rewrite",
        "draft an email",
        "write an email",
        "summarize this",
        "make this sound",
        "tone",
    ]

    # Priority rule: current/source-backed requests go to research first.
    if any(term in q for term in research_terms):
        return RouteDecision(
            primary_intent="research",
            target_agent="research_agent",
            confidence=0.91,
            second_best_agent="coding_agent" if any(term in q for term in coding_terms) else None,
            second_best_confidence=0.65 if any(term in q for term in coding_terms) else None,
            ambiguity_score=0.08,
            requires_clarification=False,
            reasoning_summary="Matched high-confidence research/current-information terminology.",
        )

    if any(term in q for term in coding_terms):
        return RouteDecision(
            primary_intent="coding",
            target_agent="coding_agent",
            confidence=0.90,
            second_best_agent=None,
            second_best_confidence=None,
            ambiguity_score=0.10,
            requires_clarification=False,
            reasoning_summary="Matched high-confidence software engineering terminology.",
        )

    if any(term in q for term in writing_terms):
        return RouteDecision(
            primary_intent="writing",
            target_agent="writing_agent",
            confidence=0.88,
            second_best_agent=None,
            second_best_confidence=None,
            ambiguity_score=0.10,
            requires_clarification=False,
            reasoning_summary="Matched high-confidence writing/editing terminology.",
        )

    return None
