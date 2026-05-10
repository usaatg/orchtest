from __future__ import annotations

from uuid import uuid4

from orchestrator_agents.schemas import RoutePlan, RouteStep


def _step(agent: str, task: str, output_key: str, input_artifact_ids: list[str] | None = None) -> RouteStep:
    return RouteStep(
        step_id=f"step_{uuid4().hex[:8]}",
        agent=agent,  # type: ignore[arg-type]
        task=task,
        input_artifact_ids=input_artifact_ids or [],
        output_key=output_key,
    )


def deterministic_route_plan(user_query: str, *, state: dict | None = None) -> RoutePlan | None:
    """High-precision deterministic routes, including sticky workflows."""
    state = state or {}
    q = user_query.lower().strip()

    # Sticky dependency resolution: answer to an orchestrator question should not be reclassified.
    pending = state.get("pending_dependency_action") or {}
    if state.get("active_workflow") == "dependency_resolution" and pending:
        if q in {"yes", "y", "update", "regenerate", "sure", "please do"}:
            return RoutePlan(
                mode="single_agent",
                steps=[_step("problem_statement_agent", "Regenerate stale problem statement from latest smart form.", "problem_statement")],
                confidence=0.96,
                ambiguity_score=0.02,
                requires_clarification=False,
                reasoning_summary="User approved dependency-resolution update.",
            )
        if q in {"no", "n", "not now", "skip"}:
            return RoutePlan(
                mode="fallback",
                confidence=0.95,
                ambiguity_score=0.02,
                requires_clarification=False,
                fallback_reason="User declined downstream artifact update.",
                reasoning_summary="User declined dependency-resolution update.",
            )
        return RoutePlan(
            mode="clarification",
            confidence=0.50,
            ambiguity_score=0.55,
            requires_clarification=True,
            clarification_question="Please answer yes or no: should I update the problem statement from the latest form?",
            reasoning_summary="Dependency-resolution confirmation needs a yes/no answer.",
        )

    # Sticky form workflow: treat next user message as answer/update for current form.
    form_state = state.get("active_form_state") or {}
    if state.get("active_workflow") == "form_fill" and form_state.get("status") in {"in_progress", "ready_for_review"}:
        return RoutePlan(
            mode="single_agent",
            steps=[_step("smart_form_builder_agent", "Continue active smart form workflow.", "smart_form_progress")],
            confidence=0.98,
            ambiguity_score=0.02,
            requires_clarification=False,
            reasoning_summary="Continuing active form workflow via sticky routing.",
        )

    # Updating an existing form should route to form builder first.
    if state.get("latest_form_artifact_id") and any(t in q for t in ["update the form", "change the form", "form answer", "stakeholder should", "target user should", "actually"]):
        return RoutePlan(
            mode="single_agent",
            steps=[_step("smart_form_builder_agent", "Update existing smart form artifact.", "smart_form_update")],
            confidence=0.86,
            ambiguity_score=0.12,
            requires_clarification=False,
            reasoning_summary="Request appears to update an existing smart form.",
        )

    form_terms = {"form", "fill out", "questionnaire", "intake", "onboarding", "problem discovery"}
    problem_terms = {"problem statement", "define a problem", "business problem"}
    research_terms = {"latest", "current", "research", "find", "sources", "cite", "paper", "docs"}
    coding_terms = {"python", "code", "build", "implement", "implementation", "api", "pytest", "debug", "workflow"}
    writing_terms = {"rewrite", "draft", "email", "summarize", "summary", "tone", "polish"}

    has_form = any(t in q for t in form_terms)
    has_problem = any(t in q for t in problem_terms)
    has_research = any(t in q for t in research_terms)
    has_coding = any(t in q for t in coding_terms)
    has_writing = any(t in q for t in writing_terms)

    # If user wants to define problem but no form exists, collect form first then generate problem statement.
    if has_problem and not state.get("latest_form_artifact_id"):
        return RoutePlan(
            mode="single_agent",
            steps=[_step("smart_form_builder_agent", "Collect structured problem-discovery form fields before generating problem statement.", "smart_form")],
            confidence=0.89,
            ambiguity_score=0.10,
            requires_clarification=False,
            reasoning_summary="Problem statement requires structured form inputs first.",
        )

    if has_problem and state.get("latest_form_artifact_id"):
        return RoutePlan(
            mode="single_agent",
            steps=[_step("problem_statement_agent", "Generate problem statement from latest form artifact.", "problem_statement")],
            confidence=0.88,
            ambiguity_score=0.11,
            requires_clarification=False,
            reasoning_summary="Latest smart form exists; route to problem statement agent.",
        )

    if has_form:
        return RoutePlan(
            mode="single_agent",
            steps=[_step("smart_form_builder_agent", "Start or continue smart form workflow.", "smart_form")],
            confidence=0.88,
            ambiguity_score=0.10,
            requires_clarification=False,
            reasoning_summary="Request is about filling or updating a form.",
        )

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
            confidence=0.40,
            second_best_agent="fallback_agent",
            second_best_confidence=0.35,
            ambiguity_score=0.80,
            requires_clarification=True,
            clarification_question="Can you clarify whether you want form filling, problem statement help, coding, research, or writing?",
            reasoning_summary="The request is too ambiguous to route safely.",
        )

    return None


def deterministic_route(user_query: str):
    plan = deterministic_route_plan(user_query)
    if plan is None:
        return None
    from orchestrator_agents.routing.service import route_plan_to_decision

    return route_plan_to_decision(plan)
