from __future__ import annotations

from orchestrator_agents.agents.base import StatelessSubAgent
from orchestrator_agents.schemas import AgentResult, AgentTask
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class WritingAgent(StatelessSubAgent):
    name = "writing_agent"

    def invoke(self, task: AgentTask, artifact_store: JsonArtifactStore) -> AgentResult:
        result = (
            "Polished response draft:\n"
            f"Original request: {task.user_query}\n\n"
            f"Instruction: {task.instruction}\n\n"
            "Draft: Clear, concise, audience-aware language with explicit next steps."
        )
        artifact_id = artifact_store.put(
            user_id=task.context["user_id"],
            namespace=("threads", task.context["thread_id"], "artifacts"),
            artifact_type="writing_draft",
            content=result,
            summary=result[:300],
            metadata={"created_by": self.name, "task_id": task.task_id},
            source_thread_id=task.context["thread_id"],
        )
        return AgentResult(
            task_id=task.task_id,
            agent_name="writing_agent",
            result=result,
            result_summary="Writing draft artifact created.",
            confidence=0.86,
            artifact_ids=[artifact_id],
            metadata={"used_context_keys": sorted(task.context.keys())},
        )
