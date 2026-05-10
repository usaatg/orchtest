from pathlib import Path

import pytest

from orchestrator_agents.graph import build_orchestrator_graph
from orchestrator_agents.storage.artifact_store import JsonArtifactStore

try:
    from langgraph.checkpoint.memory import InMemorySaver
except Exception:  # pragma: no cover
    InMemorySaver = None


@pytest.mark.skipif(InMemorySaver is None, reason="LangGraph is not installed")
def test_multiturn_same_thread_accumulates_state(tmp_path: Path):
    graph = build_orchestrator_graph(
        checkpointer=InMemorySaver(),
        artifact_store=JsonArtifactStore(tmp_path / "artifacts"),
    )
    config = {"configurable": {"thread_id": "thread_test_001"}}

    base = {
        "user_id": "user_test",
        "thread_id": "thread_test_001",
        "messages": [],
        "route_history": [],
        "handoff_history": [],
        "artifact_ids": [],
    }

    graph.invoke({**base, "user_query": "Build this in Python with LangGraph"}, config=config)
    result = graph.invoke({**base, "user_query": "Rewrite that explanation clearly"}, config=config)

    assert len(result["messages"]) >= 4
    assert len(result["route_history"]) >= 4
    assert "artifact_" in result["artifact_ids"][-1]
