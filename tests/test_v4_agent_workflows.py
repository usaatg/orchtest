from pathlib import Path

import pytest

from orchestrator_agents.agents.smart_form import DEFAULT_PROBLEM_FORM_SCHEMA
from orchestrator_agents.agent_workflows import (
    build_coding_agent_graph,
    build_problem_statement_agent_graph,
    build_smart_form_builder_agent_graph,
)
from orchestrator_agents.schemas import AgentTask
from orchestrator_agents.storage.artifact_store import JsonArtifactStore

try:
    from langgraph.checkpoint.memory import InMemorySaver
except Exception:  # pragma: no cover
    InMemorySaver = None


@pytest.mark.skipif(InMemorySaver is None, reason="LangGraph is not installed")
def test_smart_form_builder_graph_can_be_called_directly(tmp_path: Path):
    store = JsonArtifactStore(tmp_path / "artifacts")
    graph = build_smart_form_builder_agent_graph(checkpointer=InMemorySaver(), artifact_store=store)
    config = {"configurable": {"thread_id": "direct_form_thread", "user_id": "u1"}}

    out1 = graph.invoke(
        {
            "user_message": "I want to define a problem",
            "user_id": "u1",
            "thread_id": "direct_form_thread",
            "form_schema": DEFAULT_PROBLEM_FORM_SCHEMA.model_dump(),
            "form_state": None,
        },
        config=config,
    )
    assert out1["agent_result"]["agent_name"] == "smart_form_builder_agent"
    assert "primary stakeholder" in out1["final_answer"]

    form_state = out1["form_output"]["updated_form_state"]
    for message in [
        "Plant managers",
        "Manual reporting is slow",
        "Automated KPI summaries",
        "Delayed decisions",
        "yes",
    ]:
        out1 = graph.invoke(
            {
                "user_message": message,
                "user_id": "u1",
                "thread_id": "direct_form_thread",
                "form_schema": DEFAULT_PROBLEM_FORM_SCHEMA.model_dump(),
                "form_state": form_state,
                "latest_form_artifact_id": out1.get("latest_form_artifact_id_out"),
            },
            config=config,
        )
        form_state = out1["form_output"]["updated_form_state"]

    assert out1["agent_result"]["artifact_ids"]
    assert out1["latest_form_artifact_id_out"]


@pytest.mark.skipif(InMemorySaver is None, reason="LangGraph is not installed")
def test_problem_statement_graph_can_be_called_directly(tmp_path: Path):
    store = JsonArtifactStore(tmp_path / "artifacts")
    form_id = store.put(
        user_id="u1",
        namespace=("threads", "problem_thread", "artifacts"),
        artifact_type="smart_form",
        content="{'fields': {'stakeholder': 'Plant managers', 'current_pain': 'manual reporting is slow', 'desired_outcome': 'automated KPI summaries', 'business_impact': 'faster decisions'}}",
        summary="completed smart form",
        source_thread_id="problem_thread",
        created_by="smart_form_builder_agent",
    )
    graph = build_problem_statement_agent_graph(checkpointer=InMemorySaver(), artifact_store=store)
    result = graph.invoke(
        {
            "user_message": "Create the problem statement",
            "user_id": "u1",
            "thread_id": "problem_thread",
            "form_artifact_id": form_id,
        },
        config={"configurable": {"thread_id": "problem_thread", "user_id": "u1"}},
    )
    assert result["agent_result"]["agent_name"] == "problem_statement_agent"
    assert "Plant managers" in result["final_answer"]
    assert result["latest_problem_statement_artifact_id_out"]


@pytest.mark.skipif(InMemorySaver is None, reason="LangGraph is not installed")
def test_simple_subagent_graph_has_same_direct_contract(tmp_path: Path):
    store = JsonArtifactStore(tmp_path / "artifacts")
    graph = build_coding_agent_graph(checkpointer=InMemorySaver(), artifact_store=store)
    task = AgentTask(
        task_id="code_1",
        target_agent="coding_agent",
        user_query="Build a LangGraph router",
        instruction="Build a LangGraph router",
        context={"user_id": "u1", "thread_id": "code_thread", "framework": "LangGraph"},
    )
    result = graph.invoke(
        {"task": task.model_dump()},
        config={"configurable": {"thread_id": "code_thread", "user_id": "u1"}},
    )
    assert result["agent_result"]["agent_name"] == "coding_agent"
    assert result["agent_result"]["artifact_ids"]
