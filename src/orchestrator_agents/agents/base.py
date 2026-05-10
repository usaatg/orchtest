from __future__ import annotations

from abc import ABC, abstractmethod

from orchestrator_agents.schemas import AgentResult, AgentTask
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class StatelessSubAgent(ABC):
    """Base class for stateless subagents.

    The subagent receives explicit task/context and returns structured output.
    It does not own hidden conversation state. The orchestrator graph owns thread state.
    """

    name: str

    @abstractmethod
    def invoke(self, task: AgentTask, artifact_store: JsonArtifactStore) -> AgentResult:
        raise NotImplementedError
