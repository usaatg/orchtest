from __future__ import annotations

import ast
from typing import Any, NotRequired, TypedDict
from uuid import uuid4

from orchestrator_agents.agent_workflows._langgraph import END, START, StateGraph, require_langgraph
from orchestrator_agents.agents.problem_statement import ProblemStatementAgent
from orchestrator_agents.schemas import AgentResult, ProblemStatementInput, ProblemStatementOutput
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class ProblemStatementWorkflowState(TypedDict):
    """State contract for the Problem Statement Agent LangGraph workflow."""

    user_message: str
    user_id: str
    thread_id: str
    task_id: NotRequired[str]
    caller: NotRequired[str]
    form_artifact_id: str
    latest_problem_statement_artifact_id: NotRequired[str | None]
    update_reason: NotRequired[str | None]

    form_artifact: NotRequired[dict]
    form_content: NotRequired[dict[str, Any]]
    problem_output: NotRequired[dict]
    agent_result: NotRequired[dict]
    artifact_ids: NotRequired[list[str]]
    latest_problem_statement_artifact_id_out: NotRequired[str | None]
    final_answer: NotRequired[str]


def build_problem_statement_agent_graph(*, checkpointer=None, artifact_store: JsonArtifactStore | None = None):
    """Build the reusable Problem Statement Agent workflow.

    Direct and orchestrated callers both pass a form artifact ID. The graph loads the
    artifact, generates/validates the statement, saves a versioned artifact, and returns
    a structured AgentResult.
    """

    require_langgraph()
    artifact_store = artifact_store or JsonArtifactStore()
    agent = ProblemStatementAgent()

    def load_form_artifact_node(state: ProblemStatementWorkflowState) -> dict:
        artifact = artifact_store.get_any_for_user(user_id=state["user_id"], artifact_id=state["form_artifact_id"])
        if not artifact:
            result = AgentResult(
                task_id=state.get("task_id") or f"problem_statement_{uuid4().hex[:12]}",
                agent_name="problem_statement_agent",
                result="I could not find the referenced smart form artifact.",
                result_summary="Form artifact not found.",
                confidence=0.25,
                needs_followup=True,
                metadata={"missing_inputs": ["form_artifact_id"]},
            )
            return {"agent_result": result.model_dump(), "final_answer": result.result}
        try:
            form_content = ast.literal_eval(artifact.content)
        except Exception:
            form_content = {"fields": artifact.metadata.get("fields", {})}
        return {
            "task_id": state.get("task_id") or f"problem_statement_{uuid4().hex[:12]}",
            "form_artifact": artifact.model_dump(),
            "form_content": form_content,
        }

    def draft_statement_node(state: ProblemStatementWorkflowState) -> dict:
        if state.get("agent_result"):
            return {}
        artifact = state["form_artifact"]
        output: ProblemStatementOutput = agent.run(
            ProblemStatementInput(
                user_message=state.get("user_message", ""),
                form_artifact_id=artifact["artifact_id"],
                form_artifact_version=artifact["version"],
                form_content=state["form_content"],
                previous_problem_statement_artifact_id=state.get("latest_problem_statement_artifact_id"),
                update_reason=state.get("update_reason"),
                user_id=state["user_id"],
                thread_id=state["thread_id"],
                caller="orchestrator" if state.get("caller") == "orchestrator" else "direct",
            )
        )
        return {"problem_output": output.model_dump(), "final_answer": output.assistant_message}

    def persist_problem_statement_node(state: ProblemStatementWorkflowState) -> dict:
        if state.get("agent_result"):
            return {}
        output = ProblemStatementOutput.model_validate(state["problem_output"])
        artifact_id = artifact_store.put(
            user_id=state["user_id"],
            namespace=("threads", state["thread_id"], "artifacts"),
            artifact_type="problem_statement",
            content=str(output.artifact_payload),
            summary=output.result_summary,
            metadata={
                "created_by": "problem_statement_agent",
                "task_id": state["task_id"],
                "problem_statement": output.problem_statement,
            },
            source_thread_id=state["thread_id"],
            created_by="problem_statement_agent",
            depends_on=output.depends_on,
            supersedes=output.supersedes,
        )
        result = AgentResult(
            task_id=state["task_id"],
            agent_name="problem_statement_agent",
            result=output.assistant_message,
            result_summary=output.result_summary,
            confidence=0.91,
            artifact_ids=[artifact_id],
            needs_followup=False,
            metadata={
                "latest_problem_statement_artifact_id": artifact_id,
                "depends_on": [d.model_dump() for d in output.depends_on],
                "supersedes": output.supersedes,
                "workflow_graph": "problem_statement_agent_graph",
            },
        )
        return {
            "agent_result": result.model_dump(),
            "artifact_ids": [artifact_id],
            "latest_problem_statement_artifact_id_out": artifact_id,
        }

    builder = StateGraph(ProblemStatementWorkflowState)
    builder.add_node("load_form_artifact", load_form_artifact_node)
    builder.add_node("draft_statement", draft_statement_node)
    builder.add_node("persist_problem_statement", persist_problem_statement_node)
    builder.add_edge(START, "load_form_artifact")
    builder.add_edge("load_form_artifact", "draft_statement")
    builder.add_edge("draft_statement", "persist_problem_statement")
    builder.add_edge("persist_problem_statement", END)
    return builder.compile(checkpointer=checkpointer)
