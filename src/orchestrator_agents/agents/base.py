from __future__ import annotations

from abc import ABC, abstractmethod

from orchestrator_agents.schemas import AgentResult, AgentTask
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class StatelessSubAgent(ABC):
    """Base class for stateless subagents.

    Subagents receive explicit AgentTask/context and return AgentResult. They should not own
    hidden mutable workflow state. The orchestrator graph/checkpointer owns thread state.
    """

    name: str

    @abstractmethod
    def invoke(self, task: AgentTask, artifact_store: JsonArtifactStore) -> AgentResult:
        raise NotImplementedError
