from uuid import UUID

import pytest

from router_subagents.threading import (
    make_thread_registry,
    new_router_thread_id,
    subagent_thread_id,
)


def test_router_thread_id_is_uuid() -> None:
    router_thread_id = new_router_thread_id()
    assert str(UUID(router_thread_id)) == router_thread_id


def test_subagent_thread_id_is_deterministic_uuid() -> None:
    router_thread_id = new_router_thread_id()

    first = subagent_thread_id(router_thread_id, "smart_form_builder")
    second = subagent_thread_id(router_thread_id, "smart_form_builder")

    assert first == second
    assert str(UUID(first)) == first


def test_different_subagents_get_different_thread_ids() -> None:
    router_thread_id = new_router_thread_id()

    smart_form_id = subagent_thread_id(router_thread_id, "smart_form_builder")
    best_insights_id = subagent_thread_id(router_thread_id, "best_insights")

    assert smart_form_id != best_insights_id


def test_different_router_threads_get_different_subagent_thread_ids() -> None:
    router_thread_id_1 = new_router_thread_id()
    router_thread_id_2 = new_router_thread_id()

    assert subagent_thread_id(router_thread_id_1, "smart_form_builder") != subagent_thread_id(
        router_thread_id_2,
        "smart_form_builder",
    )


def test_invalid_router_thread_id_raises() -> None:
    with pytest.raises(ValueError):
        subagent_thread_id("not-a-uuid", "smart_form_builder")


def test_thread_registry() -> None:
    router_thread_id = new_router_thread_id()
    registry = make_thread_registry(router_thread_id, ["Smart Form Builder", "best-insights"])

    assert registry["router"] == router_thread_id
    assert "smart_form_builder" in registry
    assert "best_insights" in registry
