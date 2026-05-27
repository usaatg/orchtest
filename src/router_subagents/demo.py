from __future__ import annotations

from pprint import pprint

from router_subagents.router import build_router_graph, build_router_runtime, invoke_router
from router_subagents.threading import (
    make_thread_registry,
    new_router_thread_id,
    subagent_thread_id,
)


def main() -> None:
    runtime = build_router_runtime()
    router_graph = build_router_graph(runtime)

    # This ID is created once when the conversation opens.
    # Store it in your application session/database.
    router_thread_id = new_router_thread_id()

    registry = make_thread_registry(
        router_thread_id,
        ["smart_form_builder", "best_insights"],
    )

    print("\n=== Thread registry ===")
    pprint(registry)

    print("\n=== Call 1: routes to smart_form_builder ===")
    result_1 = invoke_router(
        router_graph,
        router_thread_id,
        "Build a form that collects customer name, email, budget, and deadline.",
    )
    pprint(result_1["subagent_result"])
    print(result_1["messages"][-1].content)

    print("\n=== Call 2: routes to best_insights ===")
    result_2 = invoke_router(
        router_graph,
        router_thread_id,
        "Give me insights on this agent workflow architecture.",
    )
    pprint(result_2["subagent_result"])
    print(result_2["messages"][-1].content)

    print("\n=== Call 3: routes back to smart_form_builder and preserves its subagent state ===")
    result_3 = invoke_router(
        router_graph,
        router_thread_id,
        "Update the form with a date field.",
    )
    pprint(result_3["subagent_result"])
    print(result_3["messages"][-1].content)

    print("\n=== Deterministic ID proof ===")
    print("smart_form thread from registry:  ", registry["smart_form_builder"])
    print(
        "smart_form thread recalculated:  ",
        subagent_thread_id(router_thread_id, "smart_form_builder"),
    )


if __name__ == "__main__":
    main()
