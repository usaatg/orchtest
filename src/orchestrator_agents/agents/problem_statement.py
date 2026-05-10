from __future__ import annotations

import ast

from orchestrator_agents.agents.base import StatelessSubAgent
from orchestrator_agents.schemas import (
    AgentResult,
    AgentTask,
    ArtifactDependency,
    ProblemStatementInput,
    ProblemStatementOutput,
)
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class ProblemStatementAgent(StatelessSubAgent):
    """Direct-callable and orchestrator-callable problem statement agent."""

    name = "problem_statement_agent"

    def run(self, agent_input: ProblemStatementInput) -> ProblemStatementOutput:
        fields = agent_input.form_content.get("fields", agent_input.form_content)
        stakeholder = fields.get("stakeholder") or fields.get("target_user") or "the target users"
        pain = fields.get("current_pain") or fields.get("pain_point") or "a meaningful workflow challenge"
        outcome = fields.get("desired_outcome") or "a better measurable outcome"
        impact = fields.get("business_impact") or "business performance"

        statement = (
            f"{stakeholder} need a better way to address {pain} so they can achieve {outcome}, "
            f"because the current situation negatively affects {impact}."
        )
        if agent_input.update_reason:
            statement += f" This version was updated because: {agent_input.update_reason}."

        dependency = ArtifactDependency(
            artifact_id=agent_input.form_artifact_id,
            artifact_type="smart_form",
            version=agent_input.form_artifact_version,
        )
        return ProblemStatementOutput(
            problem_statement=statement,
            assistant_message=f"Here is the problem statement:\n\n{statement}",
            result_summary="Problem statement generated from the latest smart form artifact.",
            artifact_payload={"type": "problem_statement", "problem_statement": statement},
            depends_on=[dependency],
            supersedes=agent_input.previous_problem_statement_artifact_id,
        )

    def invoke(self, task: AgentTask, artifact_store: JsonArtifactStore) -> AgentResult:
        user_id = task.context["user_id"]
        thread_id = task.context["thread_id"]
        form_artifact_id = task.context.get("latest_form_artifact_id") or task.context.get("form_artifact_id")
        if not form_artifact_id:
            return AgentResult(
                task_id=task.task_id,
                agent_name="problem_statement_agent",
                result="I need a completed smart form before I can define the problem statement.",
                result_summary="Missing form artifact.",
                confidence=0.30,
                needs_followup=True,
                metadata={"missing_inputs": ["latest_form_artifact_id"]},
            )

        form_artifact = artifact_store.get_any_for_user(user_id=user_id, artifact_id=form_artifact_id)
        if not form_artifact:
            return AgentResult(
                task_id=task.task_id,
                agent_name="problem_statement_agent",
                result="I could not find the referenced smart form artifact.",
                result_summary="Form artifact not found.",
                confidence=0.25,
                needs_followup=True,
            )

        try:
            form_content = ast.literal_eval(form_artifact.content)
        except Exception:
            form_content = {"fields": form_artifact.metadata.get("fields", {})}

        output = self.run(
            ProblemStatementInput(
                user_message=task.user_query,
                form_artifact_id=form_artifact.artifact_id,
                form_artifact_version=form_artifact.version,
                form_content=form_content,
                previous_problem_statement_artifact_id=task.context.get("latest_problem_statement_artifact_id"),
                update_reason=task.context.get("update_reason"),
                user_id=user_id,
                thread_id=thread_id,
                caller="orchestrator",
            )
        )
        artifact_id = artifact_store.put(
            user_id=user_id,
            namespace=("threads", thread_id, "artifacts"),
            artifact_type="problem_statement",
            content=str(output.artifact_payload),
            summary=output.result_summary,
            metadata={"created_by": self.name, "task_id": task.task_id, "problem_statement": output.problem_statement},
            source_thread_id=thread_id,
            created_by=self.name,
            depends_on=output.depends_on,
            supersedes=output.supersedes,
        )
        return AgentResult(
            task_id=task.task_id,
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
                "used_context_keys": sorted(task.context.keys()),
            },
        )
