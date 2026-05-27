from router_subagents.router import build_router_graph, build_router_runtime, invoke_router
from router_subagents.threading import new_router_thread_id, subagent_thread_id


def test_router_delegates_to_smart_form_builder_with_deterministic_thread_id() -> None:
    router_thread_id = new_router_thread_id()
    runtime = build_router_runtime()
    router_graph = build_router_graph(runtime)

    result = invoke_router(
        router_graph,
        router_thread_id,
        "Create a form with customer name and email.",
    )

    assert result["route"] == "smart_form_builder"
    assert result["subagent_result"]["agent"] == "smart_form_builder"
    assert result["subagent_result"]["thread_id"] == subagent_thread_id(
        router_thread_id,
        "smart_form_builder",
    )
    assert "customer_name" in result["subagent_result"]["form_fields"]
    assert "email" in result["subagent_result"]["form_fields"]


def test_subagent_state_is_preserved_under_same_router_thread_id() -> None:
    router_thread_id = new_router_thread_id()
    runtime = build_router_runtime()
    router_graph = build_router_graph(runtime)

    first = invoke_router(
        router_graph,
        router_thread_id,
        "Create a form with customer name and email.",
    )
    second = invoke_router(
        router_graph,
        router_thread_id,
        "Update the form with budget and deadline fields.",
    )

    assert first["subagent_result"]["call_count"] == 1
    assert second["subagent_result"]["call_count"] == 2
    assert set(second["subagent_result"]["form_fields"]) >= {
        "customer_name",
        "email",
        "budget",
        "deadline",
    }


def test_different_router_thread_ids_isolate_subagent_state() -> None:
    runtime = build_router_runtime()
    router_graph = build_router_graph(runtime)

    router_thread_id_1 = new_router_thread_id()
    router_thread_id_2 = new_router_thread_id()

    first = invoke_router(
        router_graph,
        router_thread_id_1,
        "Create a form with customer name and email.",
    )
    second = invoke_router(
        router_graph,
        router_thread_id_2,
        "Create a form with budget.",
    )

    assert first["subagent_result"]["call_count"] == 1
    assert second["subagent_result"]["call_count"] == 1
    assert first["subagent_result"]["thread_id"] != second["subagent_result"]["thread_id"]


def test_router_delegates_to_best_insights() -> None:
    router_thread_id = new_router_thread_id()
    runtime = build_router_runtime()
    router_graph = build_router_graph(runtime)

    result = invoke_router(
        router_graph,
        router_thread_id,
        "Give me insights about this workflow.",
    )

    assert result["route"] == "best_insights"
    assert result["subagent_result"]["agent"] == "best_insights"
    assert result["subagent_result"]["thread_id"] == subagent_thread_id(
        router_thread_id,
        "best_insights",
    )
    assert result["subagent_result"]["call_count"] == 1
    assert len(result["subagent_result"]["insights"]) == 1
