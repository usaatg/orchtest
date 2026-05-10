from __future__ import annotations

from orchestrator_agents.graph.state import OrchestratorState
from orchestrator_agents.schemas import AgentTask, RoutePlan


def build_agent_task(agent_name: str, state: OrchestratorState) -> AgentTask:
    """Package only the context the selected stateless subagent needs."""

    plan = RoutePlan.model_validate(state["route_plan"])
    step_index = state.get("current_route_step_index", 0)
    step = plan.steps[step_index]

    context = {
        "user_id": state["user_id"],
        "thread_id": state["thread_id"],
        "run_id": state.get("run_id"),
        "route_step_index": step_index,
        "available_artifact_ids": list(state.get("artifact_ids", [])) + list(step.input_artifact_ids),
        "imported_context": state.get("imported_context", []),
    }

    if agent_name == "coding_agent":
        context.update({"framework": "LangGraph", "preferred_language": "Python"})
    elif agent_name == "research_agent":
        context.update({"recency_requirement": "current_when_needed", "source_constraints": []})
    elif agent_name == "writing_agent":
        context.update({"tone": "clear", "audience": "technical stakeholder"})

    return AgentTask(
        # Use the RouteStep ID as the task ID so handoff events, observability events,
        # artifacts, and AgentResult records all correlate to the same subtask.
        task_id=step.step_id,
        target_agent=agent_name,  # type: ignore[arg-type]
        user_query=state["user_query"],
        instruction=step.task,
        context=context,
    )
