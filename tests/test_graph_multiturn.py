from pathlib import Path

import pytest

from orchestrator_agents.graph import build_orchestrator_graph
from orchestrator_agents.storage.artifact_store import JsonArtifactStore

try:
    from langgraph.checkpoint.memory import InMemorySaver
except Exception:  # pragma: no cover
    InMemorySaver = None


@pytest.mark.skipif(InMemorySaver is None, reason="LangGraph is not installed")
def test_multiturn_same_thread_accumulates_state_and_route_plan(tmp_path: Path):
    graph = build_orchestrator_graph(
        checkpointer=InMemorySaver(),
        artifact_store=JsonArtifactStore(tmp_path / "artifacts"),
    )
    config = {"configurable": {"thread_id": "thread_test_001", "user_id": "user_test"}}

    base = {
        "user_id": "user_test",
        "thread_id": "thread_test_001",
        "messages": [],
        "route_history": [],
        "handoff_history": [],
        "observability_events": [],
        "artifact_ids": [],
        "agent_results": [],
        "imported_context": [],
        "referenced_thread_ids": [],
        "referenced_artifact_ids": [],
    }

    first = graph.invoke(
        {**base, "user_query": "Find the latest LangGraph docs and build Python code"},
        config=config,
    )
    assert [r["agent_name"] for r in first["agent_results"][-2:]] == [
        "research_agent",
        "coding_agent",
    ]

    result = graph.invoke({**base, "user_query": "Rewrite that explanation clearly"}, config=config)

    assert len(result["messages"]) >= 4
    assert len(result["route_history"]) >= 2
    assert any(a.startswith("artifact_") for a in result["artifact_ids"])


@pytest.mark.skipif(InMemorySaver is None, reason="LangGraph is not installed")
def test_new_thread_can_reference_old_thread_artifacts(tmp_path: Path):
    store = JsonArtifactStore(tmp_path / "artifacts")
    old_artifact_id = store.put(
        user_id="user_test",
        namespace=("threads", "old_thread", "artifacts"),
        artifact_type="research_summary",
        content="Previous research content",
        summary="Previous research summary",
        source_thread_id="old_thread",
    )
    graph = build_orchestrator_graph(checkpointer=InMemorySaver(), artifact_store=store)
    result = graph.invoke(
        {
            "user_id": "user_test",
            "thread_id": "new_thread",
            "user_query": "Build Python code using prior research",
            "messages": [],
            "route_history": [],
            "handoff_history": [],
            "observability_events": [],
            "artifact_ids": [],
            "agent_results": [],
            "imported_context": [],
            "referenced_thread_ids": ["old_thread"],
            "referenced_artifact_ids": [old_artifact_id],
        },
        config={"configurable": {"thread_id": "new_thread", "user_id": "user_test"}},
    )
    assert len(result["imported_context"]) >= 1
