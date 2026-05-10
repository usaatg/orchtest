from __future__ import annotations

from pathlib import Path
from uuid import uuid4

try:
    from langgraph.checkpoint.memory import InMemorySaver
except Exception:  # pragma: no cover
    InMemorySaver = None  # type: ignore[assignment]

from orchestrator_agents.graph import build_orchestrator_graph
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


def main() -> None:
    """Run a tiny multi-turn demo using one stable thread_id."""

    if InMemorySaver is None:
        raise RuntimeError(
            "LangGraph is not installed. Run: pip install -e '.[dev]'"
        )

    user_id = "demo_user"
    thread_id = f"thread_{uuid4().hex[:8]}"
    checkpointer = InMemorySaver()
    artifact_store = JsonArtifactStore(Path(".artifacts"))
    graph = build_orchestrator_graph(checkpointer=checkpointer, artifact_store=artifact_store)

    config = {"configurable": {"thread_id": thread_id}}

    turns = [
        "Can you create a LangGraph orchestrator codebase with subagents?",
        "Now research the latest docs first before coding next time.",
        "Rewrite the final explanation in a more executive tone.",
    ]

    for i, query in enumerate(turns, start=1):
        result = graph.invoke(
            {
                "user_query": query,
                "user_id": user_id,
                "thread_id": thread_id,
                "messages": [],
                "route_history": [],
                "handoff_history": [],
                "artifact_ids": [],
            },
            config=config,
        )
        print("=" * 80)
        print(f"TURN {i}")
        print(f"thread_id: {thread_id}")
        print(result["final_answer"])
        print(f"artifact_ids: {result.get('artifact_ids', [])}")

    snapshot = graph.get_state(config)
    print("=" * 80)
    print("LATEST CHECKPOINT KEYS")
    print(sorted(snapshot.values.keys()))
    print(f"Total route events: {len(snapshot.values.get('route_history', []))}")


if __name__ == "__main__":
    main()
