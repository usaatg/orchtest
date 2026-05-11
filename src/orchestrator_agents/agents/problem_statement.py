from __future__ import annotations

import ast
from typing import Any, NotRequired, TypedDict, overload
from uuid import uuid4

from orchestrator_agents.agent_workflows._langgraph import END, START, StateGraph, require_langgraph
from orchestrator_agents.agents.base import StatelessSubAgent
from orchestrator_agents.schemas import (
    AgentResult,
    AgentTask,
    ArtifactDependency,
    ProblemStatementInput,
    ProblemStatementOutput,
)
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class ProblemStatementWorkflowState(TypedDict):
    """State contract for the Problem Statement Agent LangGraph workflow."""

    user_message: str
    user_id: NotRequired[str | None]
    thread_id: NotRequired[str | None]
    task_id: NotRequired[str]
    caller: NotRequired[str]

    # Direct mode can pass form content directly.
    form_artifact_id: NotRequired[str | None]
    form_artifact_version: NotRequired[int]
    form_content: NotRequired[dict[str, Any] | None]
    latest_problem_statement_artifact_id: NotRequired[str | None]
    update_reason: NotRequired[str | None]

    # Internal workflow fields.
    loaded_form_artifact: NotRequired[dict | None]
    normalized_form_content: NotRequired[dict[str, Any]]
    problem_statement: NotRequired[str]
    problem_output: NotRequired[dict]
    validation_errors: NotRequired[list[str]]
    agent_result: NotRequired[dict]
    artifact_ids: NotRequired[list[str]]
    latest_problem_statement_artifact_id_out: NotRequired[str | None]
    final_answer: NotRequired[str]


class ProblemStatementAgent(StatelessSubAgent):
    """Problem Statement Agent implemented as a reusable multi-node LangGraph workflow.

    Entry points:
    - run(ProblemStatementInput) -> ProblemStatementOutput
    - invoke(ProblemStatementInput) -> ProblemStatementOutput
    - invoke(AgentTask, artifact_store=...) -> AgentResult
    """

    name = "problem_statement_agent"

    def __init__(self, *, artifact_store: JsonArtifactStore | None = None, checkpointer: Any = None) -> None:
        self.artifact_store = artifact_store or JsonArtifactStore()
        self.checkpointer = checkpointer

    def build_graph(self, *, checkpointer: Any = None, artifact_store: JsonArtifactStore | None = None):
        return build_problem_statement_agent_graph(
            checkpointer=checkpointer if checkpointer is not None else self.checkpointer,
            artifact_store=artifact_store or self.artifact_store,
        )

    def run(self, agent_input: ProblemStatementInput, *, config: dict | None = None) -> ProblemStatementOutput:
        state: ProblemStatementWorkflowState = {
            "user_message": agent_input.user_message,
            "user_id": agent_input.user_id,
            "thread_id": agent_input.thread_id,
            "caller": agent_input.caller,
            "form_artifact_id": agent_input.form_artifact_id,
            "form_artifact_version": agent_input.form_artifact_version,
            "form_content": agent_input.form_content,
            "latest_problem_statement_artifact_id": agent_input.previous_problem_statement_artifact_id,
            "update_reason": agent_input.update_reason,
        }
        result = _execute_problem_statement_workflow_state(
            state=state,
            artifact_store=self.artifact_store,
            checkpointer=self.checkpointer,
            config=config,
            prefer_langgraph=True,
            persist_direct_output=False,
        )
        return ProblemStatementOutput.model_validate(result["problem_output"])

    @overload
    def invoke(self, input_value: ProblemStatementInput, artifact_store: None = None, *, config: dict | None = None) -> ProblemStatementOutput:
        ...

    @overload
    def invoke(self, input_value: AgentTask, artifact_store: JsonArtifactStore, *, config: dict | None = None) -> AgentResult:
        ...

    def invoke(
        self,
        input_value: ProblemStatementInput | AgentTask | None = None,
        artifact_store: JsonArtifactStore | None = None,
        *,
        task: AgentTask | None = None,
        config: dict | None = None,
    ) -> ProblemStatementOutput | AgentResult:
        input_value = input_value or task
        if input_value is None:
            raise ValueError("input_value or task is required")
        if isinstance(input_value, ProblemStatementInput):
            return self.run(input_value, config=config)
        if artifact_store is None:
            raise ValueError("artifact_store is required when invoking ProblemStatementAgent with an AgentTask")
        return self._invoke_task(input_value, artifact_store=artifact_store, config=config)

    def _invoke_task(self, task: AgentTask, *, artifact_store: JsonArtifactStore, config: dict | None = None) -> AgentResult:
        user_id = task.context["user_id"]
        thread_id = task.context["thread_id"]
        form_artifact_id = task.context.get("latest_form_artifact_id") or task.context.get("form_artifact_id")
        state: ProblemStatementWorkflowState = {
            "user_message": task.user_query,
            "user_id": user_id,
            "thread_id": thread_id,
            "task_id": task.task_id,
            "caller": "orchestrator",
            "form_artifact_id": form_artifact_id,
            "latest_problem_statement_artifact_id": task.context.get("latest_problem_statement_artifact_id"),
            "update_reason": task.context.get("update_reason"),
        }
        result = _execute_problem_statement_workflow_state(
            state=state,
            artifact_store=artifact_store,
            checkpointer=self.checkpointer,
            config=config,
            prefer_langgraph=True,
            persist_direct_output=True,
        )
        return AgentResult.model_validate(result["agent_result"])


# ---------------------------------------------------------------------------
# Multi-node LangGraph builder
# ---------------------------------------------------------------------------


def build_problem_statement_agent_graph(*, checkpointer: Any = None, artifact_store: JsonArtifactStore | None = None):
    """Build the Problem Statement Agent as a multi-node LangGraph graph."""

    require_langgraph()
    artifact_store = artifact_store or JsonArtifactStore()
    builder = StateGraph(ProblemStatementWorkflowState)
    builder.add_node("resolve_form_context", _make_resolve_form_context_node(artifact_store))
    builder.add_node("draft_problem_statement", _make_draft_problem_statement_node())
    builder.add_node("validate_problem_statement", _make_validate_problem_statement_node())
    builder.add_node("produce_problem_output", _make_produce_problem_output_node())
    builder.add_node("persist_problem_statement", _make_persist_problem_statement_node(artifact_store))
    builder.add_node("build_agent_result", _make_build_agent_result_node())

    builder.add_edge(START, "resolve_form_context")
    builder.add_edge("resolve_form_context", "draft_problem_statement")
    builder.add_edge("draft_problem_statement", "validate_problem_statement")
    builder.add_edge("validate_problem_statement", "produce_problem_output")
    builder.add_edge("produce_problem_output", "persist_problem_statement")
    builder.add_edge("persist_problem_statement", "build_agent_result")
    builder.add_edge("build_agent_result", END)
    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Node factories
# ---------------------------------------------------------------------------


def _make_resolve_form_context_node(artifact_store: JsonArtifactStore):
    def resolve_form_context_node(state: ProblemStatementWorkflowState) -> dict:
        task_id = state.get("task_id") or f"problem_statement_{uuid4().hex[:12]}"
        form_content = state.get("form_content")
        if form_content:
            return {
                "task_id": task_id,
                "normalized_form_content": form_content,
                "form_artifact_version": state.get("form_artifact_version", 1),
            }

        user_id = state.get("user_id")
        form_artifact_id = state.get("form_artifact_id")
        if not user_id or not form_artifact_id:
            result = _missing_form_result(task_id=task_id, reason="Missing form artifact ID.")
            return {"task_id": task_id, "agent_result": result.model_dump(), "final_answer": result.result}

        artifact = artifact_store.get_any_for_user(user_id=user_id, artifact_id=form_artifact_id)
        if not artifact:
            result = _missing_form_result(task_id=task_id, reason="Form artifact not found.")
            return {"task_id": task_id, "agent_result": result.model_dump(), "final_answer": result.result}

        try:
            parsed = ast.literal_eval(artifact.content)
        except Exception:
            parsed = {"fields": artifact.metadata.get("fields", {})}
        return {
            "task_id": task_id,
            "loaded_form_artifact": artifact.model_dump(),
            "normalized_form_content": parsed,
            "form_artifact_id": artifact.artifact_id,
            "form_artifact_version": artifact.version,
        }

    return resolve_form_context_node


def _make_draft_problem_statement_node():
    def draft_problem_statement_node(state: ProblemStatementWorkflowState) -> dict:
        if state.get("agent_result"):
            return {}
        fields = _extract_fields(state.get("normalized_form_content") or {})
        stakeholder = fields.get("stakeholder") or fields.get("target_user") or "the target users"
        pain = fields.get("current_pain") or fields.get("pain_point") or "a meaningful workflow challenge"
        outcome = fields.get("desired_outcome") or "a better measurable outcome"
        impact = fields.get("business_impact") or "business performance"

        statement = (
            f"{stakeholder} need a better way to address {pain} so they can achieve {outcome}, "
            f"because the current situation negatively affects {impact}."
        )
        if state.get("update_reason"):
            statement += f" This version was updated because: {state['update_reason']}."
        return {"problem_statement": statement}

    return draft_problem_statement_node


def _make_validate_problem_statement_node():
    def validate_problem_statement_node(state: ProblemStatementWorkflowState) -> dict:
        if state.get("agent_result"):
            return {}
        errors: list[str] = []
        statement = state.get("problem_statement", "")
        if len(statement.strip()) < 30:
            errors.append("problem_statement_too_short")
        if "because" not in statement.lower():
            errors.append("missing_causal_reason")
        return {"validation_errors": errors}

    return validate_problem_statement_node


def _make_produce_problem_output_node():
    def produce_problem_output_node(state: ProblemStatementWorkflowState) -> dict:
        if state.get("agent_result"):
            return {}
        form_artifact_id = state.get("form_artifact_id") or "direct_form_input"
        form_artifact_version = int(state.get("form_artifact_version") or 1)
        statement = state["problem_statement"]
        dependency = ArtifactDependency(
            artifact_id=form_artifact_id,
            artifact_type="smart_form",
            version=form_artifact_version,
        )
        output = ProblemStatementOutput(
            problem_statement=statement,
            assistant_message=f"Here is the problem statement:\n\n{statement}",
            result_summary="Problem statement generated from the latest smart form artifact.",
            artifact_payload={"type": "problem_statement", "problem_statement": statement},
            depends_on=[dependency],
            supersedes=state.get("latest_problem_statement_artifact_id"),
        )
        return {"problem_output": output.model_dump(), "final_answer": output.assistant_message}

    return produce_problem_output_node


def _make_persist_problem_statement_node(artifact_store: JsonArtifactStore):
    def persist_problem_statement_node(state: ProblemStatementWorkflowState) -> dict:
        if state.get("agent_result"):
            return {}
        output = ProblemStatementOutput.model_validate(state["problem_output"])
        user_id = state.get("user_id")
        thread_id = state.get("thread_id")
        # Direct run() without user/thread IDs returns output only. Direct graph callers can
        # pass user_id/thread_id to persist artifacts if desired.
        if not user_id or not thread_id:
            return {"artifact_ids": [], "latest_problem_statement_artifact_id_out": state.get("latest_problem_statement_artifact_id")}

        artifact_id = artifact_store.put(
            user_id=user_id,
            namespace=("threads", thread_id, "artifacts"),
            artifact_type="problem_statement",
            content=str(output.artifact_payload),
            summary=output.result_summary,
            metadata={
                "created_by": "problem_statement_agent",
                "task_id": state["task_id"],
                "problem_statement": output.problem_statement,
                "workflow_graph": "problem_statement_agent_graph",
                "validation_errors": state.get("validation_errors", []),
            },
            source_thread_id=thread_id,
            created_by="problem_statement_agent",
            depends_on=output.depends_on,
            supersedes=output.supersedes,
        )
        return {"artifact_ids": [artifact_id], "latest_problem_statement_artifact_id_out": artifact_id}

    return persist_problem_statement_node


def _make_build_agent_result_node():
    def build_agent_result_node(state: ProblemStatementWorkflowState) -> dict:
        if state.get("agent_result"):
            return {}
        output = ProblemStatementOutput.model_validate(state["problem_output"])
        result = AgentResult(
            task_id=state["task_id"],
            agent_name="problem_statement_agent",
            result=output.assistant_message,
            result_summary=output.result_summary,
            confidence=0.91 if not state.get("validation_errors") else 0.75,
            artifact_ids=state.get("artifact_ids", []),
            needs_followup=False,
            metadata={
                "latest_problem_statement_artifact_id": state.get("latest_problem_statement_artifact_id_out"),
                "depends_on": [d.model_dump() for d in output.depends_on],
                "supersedes": output.supersedes,
                "validation_errors": state.get("validation_errors", []),
                "workflow_graph": "problem_statement_agent_graph",
            },
        )
        return {"agent_result": result.model_dump(), "final_answer": output.assistant_message}

    return build_agent_result_node


# ---------------------------------------------------------------------------
# Fallback executor
# ---------------------------------------------------------------------------


def _execute_problem_statement_workflow_state(
    *,
    state: ProblemStatementWorkflowState,
    artifact_store: JsonArtifactStore,
    checkpointer: Any = None,
    config: dict | None = None,
    prefer_langgraph: bool = True,
    persist_direct_output: bool = True,
) -> ProblemStatementWorkflowState:
    # The graph itself decides whether to persist based on user_id/thread_id. The
    # persist_direct_output flag is retained for clarity and future extension.
    _ = persist_direct_output
    if prefer_langgraph and StateGraph is not None:
        graph = build_problem_statement_agent_graph(checkpointer=checkpointer, artifact_store=artifact_store)
        return graph.invoke(state, config=config)  # type: ignore[no-any-return]

    for node in [
        _make_resolve_form_context_node(artifact_store),
        _make_draft_problem_statement_node(),
        _make_validate_problem_statement_node(),
        _make_produce_problem_output_node(),
        _make_persist_problem_statement_node(artifact_store),
        _make_build_agent_result_node(),
    ]:
        state.update(node(state))
    return state


# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


def _extract_fields(form_content: dict[str, Any]) -> dict[str, Any]:
    return form_content.get("fields", form_content)


def _missing_form_result(*, task_id: str, reason: str) -> AgentResult:
    return AgentResult(
        task_id=task_id,
        agent_name="problem_statement_agent",
        result="I need a completed smart form before I can define the problem statement.",
        result_summary=reason,
        confidence=0.30,
        needs_followup=True,
        metadata={"missing_inputs": ["latest_form_artifact_id"]},
    )
