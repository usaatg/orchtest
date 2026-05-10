from __future__ import annotations

from orchestrator_agents.agents.base import StatelessSubAgent
from orchestrator_agents.schemas import AgentResult, AgentTask
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class CodingAgent(StatelessSubAgent):
    name = "coding_agent"

    def invoke(self, task: AgentTask, artifact_store: JsonArtifactStore) -> AgentResult:
        prior_artifacts = task.context.get("available_artifact_ids", [])
        result = (
            "Coding plan:\n"
            f"- Task: {task.instruction}\n"
            "- Use typed state, structured routing, policy gates, stateless subagents, "
            "and checkpointed thread_id for multi-turn continuity.\n"
            f"- Available artifact IDs: {prior_artifacts}"
        )
        artifact_id = artifact_store.put(
            user_id=task.context["user_id"],
            thread_id=task.context["thread_id"],
            artifact_type="coding_plan",
            content=result,
            metadata={"created_by": self.name, "task_id": task.task_id},
        )
        return AgentResult(
            task_id=task.task_id,
            agent_name="coding_agent",
            result=result,
            confidence=0.90,
            artifact_ids=[artifact_id],
            metadata={"used_context_keys": sorted(task.context.keys())},
        )
