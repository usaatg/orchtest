from __future__ import annotations

from typing import Any, NotRequired, TypedDict
from uuid import uuid4

from orchestrator_agents.agent_workflows._langgraph import END, START, StateGraph, require_langgraph
from orchestrator_agents.agents.smart_form import DEFAULT_PROBLEM_FORM_SCHEMA, SmartFormBuilderAgent
from orchestrator_agents.dependencies import invalidate_dependents
from orchestrator_agents.schemas import AgentResult, FormAgentInput, FormAgentOutput, FormSchema, FormSessionState
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class SmartFormWorkflowState(TypedDict):
    """State contract for the Smart Form Builder LangGraph workflow.

    This workflow is direct-callable by a UI/API and orchestrator-callable as a subagent.
    The caller owns the thread/session; this graph owns the internal form-processing steps.
    """

    user_message: str
    user_id: str
    thread_id: str
    task_id: NotRequired[str]
    caller: NotRequired[str]
    form_schema: NotRequired[dict]
    form_state: NotRequired[dict | None]
    latest_form_artifact_id: NotRequired[str | None]

    normalized_message: NotRequired[str]
    form_output: NotRequired[dict]
    agent_result: NotRequired[dict]
    artifact_ids: NotRequired[list[str]]
    latest_form_artifact_id_out: NotRequired[str | None]
    stale_artifact_ids: NotRequired[list[str]]
    dependency_events: NotRequired[list[dict]]
    final_answer: NotRequired[str]


def build_smart_form_builder_agent_graph(*, checkpointer=None, artifact_store: JsonArtifactStore | None = None):
    """Build the reusable Smart Form Builder Agent workflow.

    Direct mode example input::

        {
            "user_message": "I want to fill out the problem form",
            "user_id": "u1",
            "thread_id": "form-session-1",
            "form_schema": DEFAULT_PROBLEM_FORM_SCHEMA.model_dump(),
            "form_state": None,
        }

    Orchestrator mode passes the same shape through an adapter node.
    """

    require_langgraph()
    artifact_store = artifact_store or JsonArtifactStore()
    agent = SmartFormBuilderAgent()

    def normalize_node(state: SmartFormWorkflowState) -> dict:
        return {
            "normalized_message": state["user_message"].strip(),
            "task_id": state.get("task_id") or f"smart_form_{uuid4().hex[:12]}",
        }

    def run_form_node(state: SmartFormWorkflowState) -> dict:
        form_schema = FormSchema.model_validate(state.get("form_schema") or DEFAULT_PROBLEM_FORM_SCHEMA.model_dump())
        form_state_raw = state.get("form_state")
        form_state = FormSessionState.model_validate(form_state_raw) if form_state_raw else None
        output: FormAgentOutput = agent.run(
            FormAgentInput(
                user_message=state["normalized_message"],
                form_schema=form_schema,
                form_state=form_state,
                user_id=state["user_id"],
                thread_id=state["thread_id"],
                caller="orchestrator" if state.get("caller") == "orchestrator" else "direct",
            )
        )
        return {"form_output": output.model_dump(), "final_answer": output.assistant_message}

    def persist_artifact_node(state: SmartFormWorkflowState) -> dict:
        output = FormAgentOutput.model_validate(state["form_output"])
        artifact_ids: list[str] = []
        latest_form_artifact_id = state.get("latest_form_artifact_id")
        stale_ids: list[str] = []
        dependency_events: list[dict] = []

        if output.artifact_payload:
            artifact_id = artifact_store.put(
                user_id=state["user_id"],
                namespace=("threads", state["thread_id"], "artifacts"),
                artifact_type="smart_form",
                content=str(output.artifact_payload),
                summary=f"Completed smart form: {output.updated_form_state.form_id}",
                metadata={
                    "created_by": "smart_form_builder_agent",
                    "task_id": state["task_id"],
                    "fields": output.updated_form_state.fields,
                },
                source_thread_id=state["thread_id"],
                created_by="smart_form_builder_agent",
                supersedes=latest_form_artifact_id,
            )
            artifact_ids.append(artifact_id)
            if latest_form_artifact_id:
                stale_ids, dependency_events = invalidate_dependents(
                    artifact_store=artifact_store,
                    user_id=state["user_id"],
                    old_artifact_id=latest_form_artifact_id,
                    new_artifact_id=artifact_id,
                )
            latest_form_artifact_id = artifact_id

        result = AgentResult(
            task_id=state["task_id"],
            agent_name="smart_form_builder_agent",
            result=output.assistant_message,
            result_summary=output.result_summary,
            confidence=0.88,
            artifact_ids=artifact_ids,
            needs_followup=output.requires_user_input,
            metadata={
                "form_state": output.updated_form_state.model_dump(),
                "assistant_message": output.assistant_message,
                "latest_form_artifact_id": latest_form_artifact_id,
                "stale_artifact_ids": stale_ids,
                "dependency_events": dependency_events,
                "workflow_graph": "smart_form_builder_agent_graph",
            },
        )
        return {
            "agent_result": result.model_dump(),
            "artifact_ids": artifact_ids,
            "latest_form_artifact_id_out": latest_form_artifact_id,
            "stale_artifact_ids": stale_ids,
            "dependency_events": dependency_events,
        }

    builder = StateGraph(SmartFormWorkflowState)
    builder.add_node("normalize", normalize_node)
    builder.add_node("run_form_logic", run_form_node)
    builder.add_node("persist_artifact", persist_artifact_node)
    builder.add_edge(START, "normalize")
    builder.add_edge("normalize", "run_form_logic")
    builder.add_edge("run_form_logic", "persist_artifact")
    builder.add_edge("persist_artifact", END)
    return builder.compile(checkpointer=checkpointer)
