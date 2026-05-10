from __future__ import annotations

from orchestrator_agents.agents.base import StatelessSubAgent
from orchestrator_agents.schemas import AgentResult, AgentTask
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class CodingAgent(StatelessSubAgent):
    name = "coding_agent"

    def invoke(self, task: AgentTask, artifact_store: JsonArtifactStore) -> AgentResult:
        user_id = task.context["user_id"]
        thread_id = task.context["thread_id"]
        artifact_ids = task.context.get("available_artifact_ids", [])
        loaded_summaries: list[str] = []
        for artifact_id in artifact_ids:
            record = artifact_store.get_any_for_user(user_id=user_id, artifact_id=artifact_id)
            if record:
                loaded_summaries.append(f"{record.artifact_type}:{record.summary}")

        result = (
            "Coding implementation plan:\n"
            f"- Task: {task.instruction}\n"
            "- Use typed state, RoutePlan, policy gates, stateless subagents, artifact IDs, "
            "and checkpointed thread_id for multi-turn continuity.\n"
            f"- Artifact summaries considered: {loaded_summaries or 'none'}"
        )
        artifact_id = artifact_store.put(
            user_id=user_id,
            namespace=("threads", thread_id, "artifacts"),
            artifact_type="coding_plan",
            content=result,
            summary=result[:300],
            metadata={"created_by": self.name, "task_id": task.task_id, "input_artifact_ids": artifact_ids},
            source_thread_id=thread_id,
        )
        return AgentResult(
            task_id=task.task_id,
            agent_name="coding_agent",
            result=result,
            result_summary="Coding plan artifact created.",
            confidence=0.90,
            artifact_ids=[artifact_id],
            metadata={"used_context_keys": sorted(task.context.keys())},
        )
