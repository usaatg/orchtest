from __future__ import annotations

from pathlib import Path
from uuid import uuid4

try:
    from langgraph.checkpoint.memory import InMemorySaver
except Exception:  # pragma: no cover
    InMemorySaver = None  # type: ignore[assignment]

from orchestrator_agents.graph import build_orchestrator_graph
from orchestrator_agents.storage import JsonArtifactStore, JsonMemoryStore


def main() -> None:
    if InMemorySaver is None:
        raise RuntimeError("Install dependencies first: pip install -e '.[dev]'")

    user_id = "demo_user"
    thread_id = "workflow_session_demo"
    artifact_store = JsonArtifactStore(Path(".artifacts"))
    memory_store = JsonMemoryStore(Path(".memory"))
    memory_store.put(
        user_id=user_id,
        namespace=("users", user_id, "memories"),
        memory_type="preference",
        content="User prefers production-grade Python examples.",
    )

    graph = build_orchestrator_graph(
        checkpointer=InMemorySaver(),
        artifact_store=artifact_store,
    )
    config = {"configurable": {"thread_id": thread_id, "user_id": user_id}}

    turns = [
        "I want to define a business problem statement",
        "Plant managers",
        "Manual daily reporting is slow",
        "Automated KPI summaries",
        "Delayed operational decisions",
        "yes",
        "Create the problem statement from my form",
        "Actually, stakeholder should be operations managers",
        "yes",
    ]

    state = None
    for i, query in enumerate(turns, start=1):
        print(f"\n--- Turn {i}: {query}")
        state = graph.invoke(
            {
                "user_query": query,
                "user_id": user_id,
                "thread_id": thread_id,
                "run_id": f"run_{uuid4().hex[:12]}",
                "messages": [],
                "route_history": [],
                "handoff_history": [],
                "observability_events": [],
                "agent_results": [],
                "artifact_ids": [],
                "imported_context": [],
                "referenced_thread_ids": [],
                "referenced_artifact_ids": [],
            },
            config=config,
        )
        print(f"selected_agent: {state.get('selected_agent')}")
        print(f"final_answer:\n{state.get('final_answer')}\n")

    if state:
        print("--- Route history")
        for event in state.get("route_history", []):
            print(event)
        print("--- Handoff history")
        for event in state.get("handoff_history", []):
            print(event)
        print("--- Artifact IDs")
        print(state.get("artifact_ids", []))


if __name__ == "__main__":
    main()
