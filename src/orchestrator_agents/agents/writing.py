from __future__ import annotations

from orchestrator_agents.agents.base import StatelessSubAgent
from orchestrator_agents.schemas import AgentResult, AgentTask
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class WritingAgent(StatelessSubAgent):
    name = "writing_agent"

    def invoke(self, task: AgentTask, artifact_store: JsonArtifactStore) -> AgentResult:
        result = (
            "Polished response draft:\n"
            f"{task.user_query}\n\n"
            "Suggested style: clear, concise, and audience-aware."
        )
        artifact_id = artifact_store.put(
            user_id=task.context["user_id"],
            thread_id=task.context["thread_id"],
            artifact_type="writing_draft",
            content=result,
            metadata={"created_by": self.name, "task_id": task.task_id},
        )
        return AgentResult(
            task_id=task.task_id,
            agent_name="writing_agent",
            result=result,
            confidence=0.86,
            artifact_ids=[artifact_id],
            metadata={"used_context_keys": sorted(task.context.keys())},
        )
