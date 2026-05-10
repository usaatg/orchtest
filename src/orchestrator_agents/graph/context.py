from __future__ import annotations

from orchestrator_agents.agents.smart_form import DEFAULT_PROBLEM_FORM_SCHEMA
from orchestrator_agents.schemas import AgentTask, RoutePlan


def build_agent_task(agent_name: str, state: dict) -> AgentTask:
    plan = RoutePlan.model_validate(state["route_plan"])
    idx = state.get("current_route_step_index", 0)
    step = plan.steps[idx] if plan.steps else None
    task_id = step.step_id if step else f"{agent_name}_task"
    instruction = step.task if step else state.get("user_query", "")

    base_context = {
        "user_id": state["user_id"],
        "thread_id": state["thread_id"],
        "run_id": state.get("run_id"),
        "imported_context": state.get("imported_context", []),
        "available_artifact_ids": state.get("artifact_ids", []),
        "latest_form_artifact_id": state.get("latest_form_artifact_id"),
        "latest_problem_statement_artifact_id": state.get("latest_problem_statement_artifact_id"),
        "active_workflow": state.get("active_workflow"),
    }

    if agent_name == "smart_form_builder_agent":
        base_context.update(
            {
                "form_schema": state.get("active_form_schema") or DEFAULT_PROBLEM_FORM_SCHEMA.model_dump(),
                "form_state": state.get("active_form_state"),
                "latest_form_artifact_id": state.get("latest_form_artifact_id"),
            }
        )
    elif agent_name == "problem_statement_agent":
        base_context.update(
            {
                "form_artifact_id": state.get("latest_form_artifact_id"),
                "latest_form_artifact_id": state.get("latest_form_artifact_id"),
                "latest_problem_statement_artifact_id": state.get("latest_problem_statement_artifact_id"),
                "update_reason": state.get("pending_dependency_action", {}).get("reason") if state.get("pending_dependency_action") else None,
            }
        )
    elif agent_name == "coding_agent":
        base_context.update({"code_context": state.get("code_context"), "framework": state.get("framework", "LangGraph")})
    elif agent_name == "research_agent":
        base_context.update({"recency_requirement": "current"})
    elif agent_name == "writing_agent":
        base_context.update({"tone": state.get("tone", "clear")})

    return AgentTask(
        task_id=task_id,
        target_agent=agent_name,  # type: ignore[arg-type]
        user_query=state["user_query"],
        instruction=instruction,
        context=base_context,
    )
