from __future__ import annotations

from orchestrator_agents.agents.base import StatelessSubAgent
from orchestrator_agents.schemas import AgentResult, AgentTask
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class ResearchAgent(StatelessSubAgent):
    name = "research_agent"

    def invoke(self, task: AgentTask, artifact_store: JsonArtifactStore) -> AgentResult:
        imported = task.context.get("imported_context", [])
        prior = task.context.get("available_artifact_ids", [])
        result = (
            "Research summary:\n"
            f"- Query: {task.user_query}\n"
            f"- Instruction: {task.instruction}\n"
            f"- Imported context items: {len(imported)}\n"
            f"- Available artifacts before research: {prior}\n"
            "- Recommendation: capture current/source-backed findings as an artifact, then pass "
            "only the artifact ID and short summary to downstream agents."
        )
        artifact_id = artifact_store.put(
            user_id=task.context["user_id"],
            namespace=("threads", task.context["thread_id"], "artifacts"),
            artifact_type="research_summary",
            content=result,
            summary=result[:300],
            metadata={"created_by": self.name, "task_id": task.task_id},
            source_thread_id=task.context["thread_id"],
        )
        return AgentResult(
            task_id=task.task_id,
            agent_name="research_agent",
            result=result,
            result_summary="Research artifact created with concise implementation context.",
            confidence=0.88,
            artifact_ids=[artifact_id],
            metadata={"used_context_keys": sorted(task.context.keys())},
        )
