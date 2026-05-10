from __future__ import annotations

from typing import NotRequired, TypedDict

from orchestrator_agents.agent_workflows._langgraph import END, START, StateGraph, require_langgraph
from orchestrator_agents.agents import CodingAgent, ResearchAgent, WritingAgent
from orchestrator_agents.schemas import AgentResult, AgentTask
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


class BasicAgentWorkflowState(TypedDict):
    """State contract for simple one-step subagent workflows.

    Direct mode callers pass an AgentTask-shaped dict in ``task``.
    Orchestrator mode builds the same AgentTask and invokes this graph.
    """

    task: dict
    agent_result: NotRequired[dict]
    final_answer: NotRequired[str]


def _build_basic_agent_graph(agent, *, checkpointer=None, artifact_store: JsonArtifactStore | None = None):
    require_langgraph()
    artifact_store = artifact_store or JsonArtifactStore()

    def invoke_agent_node(state: BasicAgentWorkflowState) -> dict:
        task = AgentTask.model_validate(state["task"])
        result: AgentResult = agent.invoke(task, artifact_store)
        return {
            "agent_result": result.model_dump(),
            "final_answer": result.result,
        }

    builder = StateGraph(BasicAgentWorkflowState)
    builder.add_node("invoke_agent", invoke_agent_node)
    builder.add_edge(START, "invoke_agent")
    builder.add_edge("invoke_agent", END)
    return builder.compile(checkpointer=checkpointer)


def build_research_agent_graph(*, checkpointer=None, artifact_store: JsonArtifactStore | None = None):
    """Build the direct/subagent-callable Research Agent LangGraph workflow."""

    return _build_basic_agent_graph(ResearchAgent(), checkpointer=checkpointer, artifact_store=artifact_store)


def build_coding_agent_graph(*, checkpointer=None, artifact_store: JsonArtifactStore | None = None):
    """Build the direct/subagent-callable Coding Agent LangGraph workflow."""

    return _build_basic_agent_graph(CodingAgent(), checkpointer=checkpointer, artifact_store=artifact_store)


def build_writing_agent_graph(*, checkpointer=None, artifact_store: JsonArtifactStore | None = None):
    """Build the direct/subagent-callable Writing Agent LangGraph workflow."""

    return _build_basic_agent_graph(WritingAgent(), checkpointer=checkpointer, artifact_store=artifact_store)
