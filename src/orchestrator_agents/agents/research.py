from __future__ import annotations

from orchestrator_agents.agents.base import StatelessSubAgent
from orchestrator_agents.schemas import AgentResult, AgentTask
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class ResearchAgent(StatelessSubAgent):
    name = "research_agent"

    def invoke(self, task: AgentTask, artifact_store: JsonArtifactStore) -> AgentResult:
        # Replace this deterministic demo implementation with a real research agent
        # that has web/search tools and citation handling.
        result = (
            "Research summary:\n"
            f"- Query: {task.user_query}\n"
            "- Recommended approach: gather source-backed evidence, synthesize findings, "
            "and produce concise artifacts for downstream agents."
        )
        artifact_id = artifact_store.put(
            user_id=task.context["user_id"],
            thread_id=task.context["thread_id"],
            artifact_type="research_summary",
            content=result,
            metadata={"created_by": self.name, "task_id": task.task_id},
        )
        return AgentResult(
            task_id=task.task_id,
            agent_name="research_agent",
            result=result,
            confidence=0.88,
            artifact_ids=[artifact_id],
            metadata={"used_context_keys": sorted(task.context.keys())},
        )
