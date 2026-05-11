from __future__ import annotations

from typing import Any, NotRequired, TypedDict, overload
from uuid import uuid4

from orchestrator_agents.agent_workflows._langgraph import END, START, StateGraph, require_langgraph
from orchestrator_agents.agents.base import StatelessSubAgent
from orchestrator_agents.dependencies import invalidate_dependents
from orchestrator_agents.schemas import (
    AgentResult,
    AgentTask,
    FormAgentInput,
    FormAgentOutput,
    FormFieldSpec,
    FormSchema,
    FormSessionState,
)
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


DEFAULT_PROBLEM_FORM_SCHEMA = FormSchema(
    form_id="problem_discovery_form",
    form_name="Problem Discovery Form",
    fields=[
        FormFieldSpec(name="stakeholder", label="primary stakeholder or user"),
        FormFieldSpec(name="current_pain", label="current pain or problem"),
        FormFieldSpec(name="desired_outcome", label="desired outcome"),
        FormFieldSpec(name="business_impact", label="business impact"),
    ],
)


class SmartFormWorkflowState(TypedDict):
    """State contract for the Smart Form Builder Agent LangGraph workflow.

    The graph is intentionally usable in two modes:
    - direct mode: caller passes user_message, form_schema, and optional form_state
    - orchestrated mode: caller passes an AgentTask plus artifact_store context
    """

    user_message: str
    user_id: NotRequired[str | None]
    thread_id: NotRequired[str | None]
    task_id: NotRequired[str]
    caller: NotRequired[str]
    form_schema: NotRequired[dict]
    form_state: NotRequired[dict | None]
    latest_form_artifact_id: NotRequired[str | None]

    normalized_message: NotRequired[str]
    working_form_state: NotRequired[dict]
    form_output: NotRequired[dict]
    agent_result: NotRequired[dict]
    artifact_ids: NotRequired[list[str]]
    latest_form_artifact_id_out: NotRequired[str | None]
    stale_artifact_ids: NotRequired[list[str]]
    dependency_events: NotRequired[list[dict]]
    final_answer: NotRequired[str]


class SmartFormBuilderAgent(StatelessSubAgent):
    """Smart Form Builder implemented as a reusable multi-node LangGraph workflow.

    The class exposes both direct and orchestrated entry points:
    - run(FormAgentInput) -> FormAgentOutput
    - invoke(FormAgentInput) -> FormAgentOutput
    - invoke(AgentTask, artifact_store=...) -> AgentResult

    The agent itself remains stateless: all form progress is provided in the input and
    returned in the output. The graph can also persist completed form artifacts when an
    artifact store and user/thread IDs are provided.
    """

    name = "smart_form_builder_agent"

    def __init__(self, *, artifact_store: JsonArtifactStore | None = None, checkpointer: Any = None) -> None:
        self.artifact_store = artifact_store or JsonArtifactStore()
        self.checkpointer = checkpointer

    def build_graph(self, *, checkpointer: Any = None, artifact_store: JsonArtifactStore | None = None):
        return build_smart_form_builder_agent_graph(
            checkpointer=checkpointer if checkpointer is not None else self.checkpointer,
            artifact_store=artifact_store or self.artifact_store,
        )

    def run(self, agent_input: FormAgentInput, *, config: dict | None = None) -> FormAgentOutput:
        """Run the direct smart-form workflow and return the form-specific output.

        If LangGraph is installed, this executes the multi-node graph. In lightweight
        test/demo environments where LangGraph is unavailable, it executes the same node
        pipeline synchronously so the direct contract remains usable.
        """

        state: SmartFormWorkflowState = {
            "user_message": agent_input.user_message,
            "user_id": agent_input.user_id,
            "thread_id": agent_input.thread_id,
            "caller": agent_input.caller,
            "form_schema": agent_input.form_schema.model_dump(),
            "form_state": agent_input.form_state.model_dump() if agent_input.form_state else None,
            "latest_form_artifact_id": None,
        }
        result = _execute_smart_form_workflow_state(
            state=state,
            artifact_store=self.artifact_store,
            checkpointer=self.checkpointer,
            config=config,
            prefer_langgraph=True,
        )
        return FormAgentOutput.model_validate(result["form_output"])

    @overload
    def invoke(self, input_value: FormAgentInput, artifact_store: None = None, *, config: dict | None = None) -> FormAgentOutput:
        ...

    @overload
    def invoke(self, input_value: AgentTask, artifact_store: JsonArtifactStore, *, config: dict | None = None) -> AgentResult:
        ...

    def invoke(
        self,
        input_value: FormAgentInput | AgentTask | None = None,
        artifact_store: JsonArtifactStore | None = None,
        *,
        task: AgentTask | None = None,
        config: dict | None = None,
    ) -> FormAgentOutput | AgentResult:
        """Invoke the agent directly or as an orchestrator subagent.

        Direct mode accepts FormAgentInput and returns FormAgentOutput.
        Orchestrated mode accepts AgentTask plus artifact_store and returns AgentResult.
        The keyword argument ``task=...`` is supported for backward compatibility.
        """

        input_value = input_value or task
        if input_value is None:
            raise ValueError("input_value or task is required")
        if isinstance(input_value, FormAgentInput):
            return self.run(input_value, config=config)
        if artifact_store is None:
            raise ValueError("artifact_store is required when invoking SmartFormBuilderAgent with an AgentTask")
        return self._invoke_task(input_value, artifact_store=artifact_store, config=config)

    def _invoke_task(self, task: AgentTask, *, artifact_store: JsonArtifactStore, config: dict | None = None) -> AgentResult:
        user_id = task.context["user_id"]
        thread_id = task.context["thread_id"]
        form_schema = FormSchema.model_validate(task.context.get("form_schema") or DEFAULT_PROBLEM_FORM_SCHEMA.model_dump())
        form_state_raw = task.context.get("form_state")

        state: SmartFormWorkflowState = {
            "user_message": task.user_query,
            "user_id": user_id,
            "thread_id": thread_id,
            "task_id": task.task_id,
            "caller": "orchestrator",
            "form_schema": form_schema.model_dump(),
            "form_state": form_state_raw,
            "latest_form_artifact_id": task.context.get("latest_form_artifact_id"),
        }
        result = _execute_smart_form_workflow_state(
            state=state,
            artifact_store=artifact_store,
            checkpointer=self.checkpointer,
            config=config,
            prefer_langgraph=True,
        )
        return AgentResult.model_validate(result["agent_result"])


# ---------------------------------------------------------------------------
# Multi-node LangGraph builder
# ---------------------------------------------------------------------------


def build_smart_form_builder_agent_graph(*, checkpointer: Any = None, artifact_store: JsonArtifactStore | None = None):
    """Build the Smart Form Builder Agent as a multi-node LangGraph graph.

    The graph can be called directly with raw form workflow fields or by the
    orchestrator through SmartFormBuilderAgent.invoke(AgentTask, artifact_store).
    """

    require_langgraph()
    artifact_store = artifact_store or JsonArtifactStore()

    builder = StateGraph(SmartFormWorkflowState)
    builder.add_node("normalize_input", _make_normalize_input_node())
    builder.add_node("apply_user_message", _make_apply_user_message_node())
    builder.add_node("validate_form", _make_validate_form_node())
    builder.add_node("produce_form_output", _make_produce_form_output_node())
    builder.add_node("persist_completed_form", _make_persist_completed_form_node(artifact_store))
    builder.add_node("build_agent_result", _make_build_agent_result_node())

    builder.add_edge(START, "normalize_input")
    builder.add_edge("normalize_input", "apply_user_message")
    builder.add_edge("apply_user_message", "validate_form")
    builder.add_edge("validate_form", "produce_form_output")
    builder.add_edge("produce_form_output", "persist_completed_form")
    builder.add_edge("persist_completed_form", "build_agent_result")
    builder.add_edge("build_agent_result", END)
    return builder.compile(checkpointer=checkpointer)


# ---------------------------------------------------------------------------
# Node factories. They are shared by the LangGraph graph and fallback executor.
# ---------------------------------------------------------------------------


def _make_normalize_input_node():
    def normalize_input_node(state: SmartFormWorkflowState) -> dict:
        schema = FormSchema.model_validate(state.get("form_schema") or DEFAULT_PROBLEM_FORM_SCHEMA.model_dump())
        form_state_raw = state.get("form_state")
        if form_state_raw:
            form_state = FormSessionState.model_validate(form_state_raw)
        else:
            form_state = _initial_state(schema)
        return {
            "task_id": state.get("task_id") or f"smart_form_{uuid4().hex[:12]}",
            "normalized_message": state.get("user_message", "").strip(),
            "form_schema": schema.model_dump(),
            "working_form_state": form_state.model_dump(),
            "artifact_ids": [],
            "stale_artifact_ids": [],
            "dependency_events": [],
        }

    return normalize_input_node


def _make_apply_user_message_node():
    def apply_user_message_node(state: SmartFormWorkflowState) -> dict:
        schema = FormSchema.model_validate(state["form_schema"])
        form_state = FormSessionState.model_validate(state["working_form_state"])
        message = state.get("normalized_message", "")
        lowered = message.lower()

        if lowered in {"cancel", "cancel form", "stop", "stop form"}:
            form_state.status = "cancelled"
            return {"working_form_state": form_state.model_dump()}

        if form_state.status == "not_started":
            form_state.status = "in_progress"
            if form_state.current_field:
                form_state.pending_question = _question_for_field(schema, form_state.current_field)
                return {"working_form_state": form_state.model_dump()}

        if form_state.status == "ready_for_review":
            # Defer review response handling to produce_form_output so it can create
            # a completion payload consistently.
            return {"working_form_state": form_state.model_dump()}

        explicit_field = _extract_explicit_field_update(message, schema)
        if explicit_field:
            field_name, value = explicit_field
            form_state.fields[field_name] = value
        elif form_state.current_field and not _looks_like_start_request(message):
            form_state.fields[form_state.current_field] = message

        return {"working_form_state": form_state.model_dump()}

    return apply_user_message_node


def _make_validate_form_node():
    def validate_form_node(state: SmartFormWorkflowState) -> dict:
        schema = FormSchema.model_validate(state["form_schema"])
        form_state = FormSessionState.model_validate(state["working_form_state"])
        if form_state.status in {"cancelled", "ready_for_review"}:
            return {"working_form_state": form_state.model_dump()}
        form_state = _validate_and_recompute(schema, form_state)
        return {"working_form_state": form_state.model_dump()}

    return validate_form_node


def _make_produce_form_output_node():
    def produce_form_output_node(state: SmartFormWorkflowState) -> dict:
        schema = FormSchema.model_validate(state["form_schema"])
        form_state = FormSessionState.model_validate(state["working_form_state"])
        message = state.get("normalized_message", "")

        if form_state.status == "cancelled":
            output = FormAgentOutput(
                status="cancelled",
                updated_form_state=form_state,
                assistant_message="Okay, I cancelled the form workflow.",
                result_summary="User cancelled the form workflow.",
                completed=True,
                requires_user_input=False,
            )
            return {"form_output": output.model_dump(), "final_answer": output.assistant_message}

        if form_state.status == "ready_for_review":
            output = _handle_review_response(message, form_state)
            return {"form_output": output.model_dump(), "working_form_state": output.updated_form_state.model_dump(), "final_answer": output.assistant_message}

        if form_state.validation_errors:
            field_name, error = next(iter(form_state.validation_errors.items()))
            form_state.current_field = field_name
            form_state.pending_question = f"{error} Please provide your {_label_for_field(schema, field_name)}."
            output = FormAgentOutput(
                status="in_progress",
                updated_form_state=form_state,
                assistant_message=form_state.pending_question,
                result_summary=f"Validation failed for {field_name}.",
                completed=False,
                requires_user_input=True,
            )
            return {"form_output": output.model_dump(), "working_form_state": form_state.model_dump(), "final_answer": output.assistant_message}

        if form_state.missing_fields:
            next_field = form_state.missing_fields[0]
            form_state.current_field = next_field
            form_state.pending_question = _question_for_field(schema, next_field)
            output = FormAgentOutput(
                status="in_progress",
                updated_form_state=form_state,
                assistant_message=form_state.pending_question,
                result_summary=f"Collected form progress. Next field: {next_field}.",
                completed=False,
                requires_user_input=True,
            )
            return {"form_output": output.model_dump(), "working_form_state": form_state.model_dump(), "final_answer": output.assistant_message}

        form_state.status = "ready_for_review"
        form_state.current_field = None
        form_state.pending_question = "Please review the completed form. Should I submit it?"
        output = FormAgentOutput(
            status="ready_for_review",
            updated_form_state=form_state,
            assistant_message=_render_review_message(form_state),
            result_summary="All required fields collected; awaiting user review.",
            completed=False,
            requires_user_input=True,
        )
        return {"form_output": output.model_dump(), "working_form_state": form_state.model_dump(), "final_answer": output.assistant_message}

    return produce_form_output_node


def _make_persist_completed_form_node(artifact_store: JsonArtifactStore):
    def persist_completed_form_node(state: SmartFormWorkflowState) -> dict:
        output = FormAgentOutput.model_validate(state["form_output"])
        user_id = state.get("user_id")
        thread_id = state.get("thread_id")
        if not output.artifact_payload or not user_id or not thread_id:
            return {"artifact_ids": [], "latest_form_artifact_id_out": state.get("latest_form_artifact_id")}

        previous_form_artifact_id = state.get("latest_form_artifact_id")
        artifact_id = artifact_store.put(
            user_id=user_id,
            namespace=("threads", thread_id, "artifacts"),
            artifact_type="smart_form",
            content=str(output.artifact_payload),
            summary=f"Completed smart form: {output.updated_form_state.form_id}",
            metadata={
                "created_by": "smart_form_builder_agent",
                "task_id": state["task_id"],
                "fields": output.updated_form_state.fields,
                "workflow_graph": "smart_form_builder_agent_graph",
            },
            source_thread_id=thread_id,
            created_by="smart_form_builder_agent",
            supersedes=previous_form_artifact_id,
        )
        updates: dict[str, Any] = {"artifact_ids": [artifact_id], "latest_form_artifact_id_out": artifact_id}
        if previous_form_artifact_id:
            stale_ids, dependency_events = invalidate_dependents(
                artifact_store=artifact_store,
                user_id=user_id,
                old_artifact_id=previous_form_artifact_id,
                new_artifact_id=artifact_id,
            )
            updates["stale_artifact_ids"] = stale_ids
            updates["dependency_events"] = dependency_events
        return updates

    return persist_completed_form_node


def _make_build_agent_result_node():
    def build_agent_result_node(state: SmartFormWorkflowState) -> dict:
        output = FormAgentOutput.model_validate(state["form_output"])
        metadata = {
            "form_state": output.updated_form_state.model_dump(),
            "assistant_message": output.assistant_message,
            "latest_form_artifact_id": state.get("latest_form_artifact_id_out"),
            "stale_artifact_ids": state.get("stale_artifact_ids", []),
            "dependency_events": state.get("dependency_events", []),
            "workflow_graph": "smart_form_builder_agent_graph",
        }
        result = AgentResult(
            task_id=state["task_id"],
            agent_name="smart_form_builder_agent",
            result=output.assistant_message,
            result_summary=output.result_summary,
            confidence=0.88,
            artifact_ids=state.get("artifact_ids", []),
            needs_followup=output.requires_user_input,
            metadata=metadata,
        )
        return {"agent_result": result.model_dump(), "final_answer": output.assistant_message}

    return build_agent_result_node


# ---------------------------------------------------------------------------
# Fallback executor used when LangGraph is unavailable.
# ---------------------------------------------------------------------------


def _execute_smart_form_workflow_state(
    *,
    state: SmartFormWorkflowState,
    artifact_store: JsonArtifactStore,
    checkpointer: Any = None,
    config: dict | None = None,
    prefer_langgraph: bool = True,
) -> SmartFormWorkflowState:
    if prefer_langgraph and StateGraph is not None:
        graph = build_smart_form_builder_agent_graph(checkpointer=checkpointer, artifact_store=artifact_store)
        return graph.invoke(state, config=config)  # type: ignore[no-any-return]

    # Manual execution mirrors the LangGraph node order for local tests without LangGraph.
    for node in [
        _make_normalize_input_node(),
        _make_apply_user_message_node(),
        _make_validate_form_node(),
        _make_produce_form_output_node(),
        _make_persist_completed_form_node(artifact_store),
        _make_build_agent_result_node(),
    ]:
        state.update(node(state))
    return state


# ---------------------------------------------------------------------------
# Pure helpers used by graph nodes.
# ---------------------------------------------------------------------------


def _initial_state(schema: FormSchema) -> FormSessionState:
    required = [field.name for field in schema.fields if field.required]
    return FormSessionState(
        form_id=schema.form_id,
        status="not_started",
        fields={field.name: None for field in schema.fields},
        missing_fields=required,
        current_field=required[0] if required else None,
    )


def _validate_and_recompute(schema: FormSchema, state: FormSessionState) -> FormSessionState:
    errors: dict[str, str] = {}
    for field in schema.fields:
        value = state.fields.get(field.name)
        if not value:
            continue
        if field.field_type == "email" and "@" not in str(value):
            errors[field.name] = "That does not look like a valid email."
        if field.field_type == "choice" and field.choices and value not in field.choices:
            errors[field.name] = f"Please choose one of: {', '.join(field.choices)}."
    state.validation_errors = errors
    state.missing_fields = [field.name for field in schema.fields if field.required and not state.fields.get(field.name)]
    return state


def _question_for_field(schema: FormSchema, field_name: str) -> str:
    return f"What is the {_label_for_field(schema, field_name)}?"


def _label_for_field(schema: FormSchema, field_name: str) -> str:
    return next((field.label for field in schema.fields if field.name == field_name), field_name)


def _render_review_message(state: FormSessionState) -> str:
    lines = ["Please review the completed form:"]
    for key, value in state.fields.items():
        lines.append(f"- {key}: {value}")
    lines.append("\nShould I submit it?")
    return "\n".join(lines)


def _handle_review_response(message: str, state: FormSessionState) -> FormAgentOutput:
    lowered = message.lower().strip()
    if lowered in {"yes", "y", "submit", "confirm", "looks good"}:
        state.status = "completed"
        return FormAgentOutput(
            status="completed",
            updated_form_state=state,
            assistant_message="Great — the form is complete.",
            result_summary="User confirmed the completed form.",
            completed=True,
            requires_user_input=False,
            artifact_payload={"type": "completed_form", "form_id": state.form_id, "fields": state.fields},
        )
    return FormAgentOutput(
        status="ready_for_review",
        updated_form_state=state,
        assistant_message="No problem. Tell me which field you want to change, such as 'stakeholder should be plant managers'.",
        result_summary="User did not confirm submission.",
        completed=False,
        requires_user_input=True,
    )


def _looks_like_start_request(message: str) -> bool:
    q = message.lower()
    return any(term in q for term in {"fill", "form", "start", "define a problem", "problem statement"})


def _extract_explicit_field_update(message: str, schema: FormSchema) -> tuple[str, str] | None:
    lowered = message.lower()
    for field in schema.fields:
        candidates = {field.name.lower(), field.label.lower()}
        for candidate in candidates:
            if candidate in lowered and any(marker in lowered for marker in [" should be ", " is ", " = ", " to "]):
                for marker in [" should be ", " is ", " = ", " to "]:
                    if marker in lowered:
                        value = message.split(marker.strip(), 1)[-1].strip(" .")
                        return field.name, value
    return None
