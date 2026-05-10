"""Reusable LangGraph workflows for subagents.

Each workflow is designed to be invoked directly by a UI/API or invoked as a subagent
node from the orchestrator workflow. The public contract is intentionally structured:
input state -> compiled LangGraph workflow -> structured output state.
"""

from orchestrator_agents.agent_workflows.basic import (
    build_coding_agent_graph,
    build_research_agent_graph,
    build_writing_agent_graph,
)
from orchestrator_agents.agent_workflows.problem_statement import build_problem_statement_agent_graph
from orchestrator_agents.agent_workflows.smart_form import build_smart_form_builder_agent_graph

__all__ = [
    "build_coding_agent_graph",
    "build_research_agent_graph",
    "build_writing_agent_graph",
    "build_smart_form_builder_agent_graph",
    "build_problem_statement_agent_graph",
]
