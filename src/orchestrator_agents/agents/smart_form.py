from __future__ import annotations

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


class SmartFormBuilderAgent(StatelessSubAgent):
    """Direct-callable and orchestrator-callable smart form agent.

    The agent is stateless. The caller owns FormSessionState and passes it in every turn.
    """

    name = "smart_form_builder_agent"

    def run(self, agent_input: FormAgentInput) -> FormAgentOutput:
        state = agent_input.form_state or self._initial_state(agent_input.form_schema)
        message = agent_input.user_message.strip()
        lowered = message.lower()

        if lowered in {"cancel", "cancel form", "stop", "stop form"}:
            state.status = "cancelled"
            return FormAgentOutput(
                status="cancelled",
                updated_form_state=state,
                assistant_message="Okay, I cancelled the form workflow.",
                result_summary="User cancelled the form workflow.",
                completed=True,
                requires_user_input=False,
            )

        if state.status == "ready_for_review":
            return self._handle_review_response(agent_input, state)

        if state.status == "not_started":
            state.status = "in_progress"
            if state.current_field:
                state.pending_question = self._question_for_field(agent_input.form_schema, state.current_field)
                return FormAgentOutput(
                    status="in_progress",
                    updated_form_state=state,
                    assistant_message=state.pending_question,
                    result_summary=f"Started form. Next field: {state.current_field}.",
                    completed=False,
                    requires_user_input=True,
                )

        # If the orchestrator identified a field update, apply it deterministically.
        explicit_field = self._extract_explicit_field_update(message, agent_input.form_schema)
        if explicit_field:
            field_name, value = explicit_field
            state.fields[field_name] = value
        elif state.current_field and not self._looks_like_start_request(message):
            state.fields[state.current_field] = message

        state = self._validate_and_recompute(agent_input.form_schema, state)

        if state.validation_errors:
            field_name, error = next(iter(state.validation_errors.items()))
            state.current_field = field_name
            state.pending_question = f"{error} Please provide your {self._label_for_field(agent_input.form_schema, field_name)}."
            return FormAgentOutput(
                status="in_progress",
                updated_form_state=state,
                assistant_message=state.pending_question,
                result_summary=f"Validation failed for {field_name}.",
                completed=False,
                requires_user_input=True,
            )

        if state.missing_fields:
            next_field = state.missing_fields[0]
            state.current_field = next_field
            state.pending_question = self._question_for_field(agent_input.form_schema, next_field)
            return FormAgentOutput(
                status="in_progress",
                updated_form_state=state,
                assistant_message=state.pending_question,
                result_summary=f"Collected form progress. Next field: {next_field}.",
                completed=False,
                requires_user_input=True,
            )

        state.status = "ready_for_review"
        state.current_field = None
        state.pending_question = "Please review the completed form. Should I submit it?"
        return FormAgentOutput(
            status="ready_for_review",
            updated_form_state=state,
            assistant_message=self._render_review_message(state),
            result_summary="All required fields collected; awaiting user review.",
            completed=False,
            requires_user_input=True,
        )

    def invoke(self, task: AgentTask, artifact_store: JsonArtifactStore) -> AgentResult:
        user_id = task.context["user_id"]
        thread_id = task.context["thread_id"]
        form_schema = FormSchema.model_validate(task.context.get("form_schema") or DEFAULT_PROBLEM_FORM_SCHEMA.model_dump())
        form_state_raw = task.context.get("form_state")
        form_state = FormSessionState.model_validate(form_state_raw) if form_state_raw else None

        output = self.run(
            FormAgentInput(
                user_message=task.user_query,
                form_schema=form_schema,
                form_state=form_state,
                user_id=user_id,
                thread_id=thread_id,
                caller="orchestrator",
            )
        )

        artifact_ids: list[str] = []
        metadata = {
            "form_state": output.updated_form_state.model_dump(),
            "assistant_message": output.assistant_message,
            "used_context_keys": sorted(task.context.keys()),
        }

        if output.artifact_payload:
            previous_form_artifact_id = task.context.get("latest_form_artifact_id")
            artifact_id = artifact_store.put(
                user_id=user_id,
                namespace=("threads", thread_id, "artifacts"),
                artifact_type="smart_form",
                content=str(output.artifact_payload),
                summary=f"Completed smart form: {output.updated_form_state.form_id}",
                metadata={"created_by": self.name, "task_id": task.task_id, "fields": output.updated_form_state.fields},
                source_thread_id=thread_id,
                created_by=self.name,
                supersedes=previous_form_artifact_id,
            )
            artifact_ids.append(artifact_id)
            metadata["latest_form_artifact_id"] = artifact_id
            if previous_form_artifact_id:
                stale_ids, dependency_events = invalidate_dependents(
                    artifact_store=artifact_store,
                    user_id=user_id,
                    old_artifact_id=previous_form_artifact_id,
                    new_artifact_id=artifact_id,
                )
                metadata["stale_artifact_ids"] = stale_ids
                metadata["dependency_events"] = dependency_events

        return AgentResult(
            task_id=task.task_id,
            agent_name="smart_form_builder_agent",
            result=output.assistant_message,
            result_summary=output.result_summary,
            confidence=0.88,
            artifact_ids=artifact_ids,
            needs_followup=output.requires_user_input,
            metadata=metadata,
        )

    def _initial_state(self, schema: FormSchema) -> FormSessionState:
        required = [field.name for field in schema.fields if field.required]
        return FormSessionState(
            form_id=schema.form_id,
            status="not_started",
            fields={field.name: None for field in schema.fields},
            missing_fields=required,
            current_field=required[0] if required else None,
        )

    def _validate_and_recompute(self, schema: FormSchema, state: FormSessionState) -> FormSessionState:
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

    def _question_for_field(self, schema: FormSchema, field_name: str) -> str:
        return f"What is the {self._label_for_field(schema, field_name)}?"

    def _label_for_field(self, schema: FormSchema, field_name: str) -> str:
        return next((field.label for field in schema.fields if field.name == field_name), field_name)

    def _render_review_message(self, state: FormSessionState) -> str:
        lines = ["Please review the completed form:"]
        for key, value in state.fields.items():
            lines.append(f"- {key}: {value}")
        lines.append("\nShould I submit it?")
        return "\n".join(lines)

    def _handle_review_response(self, agent_input: FormAgentInput, state: FormSessionState) -> FormAgentOutput:
        message = agent_input.user_message.lower().strip()
        if message in {"yes", "y", "submit", "confirm", "looks good"}:
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

    def _looks_like_start_request(self, message: str) -> bool:
        q = message.lower()
        return any(term in q for term in {"fill", "form", "start", "define a problem", "problem statement"})

    def _extract_explicit_field_update(self, message: str, schema: FormSchema) -> tuple[str, str] | None:
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
