from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph

from router_subagents.state import RouteName, RouterState
from router_subagents.subagents import (
    build_best_insights_graph,
    build_smart_form_builder_graph,
)
from router_subagents.threading import subagent_thread_id


def _last_human_text(messages: list | None) -> str:
    if not messages:
        return ""

    for message in reversed(messages):
        if isinstance(message, HumanMessage):
            return str(message.content)

        if isinstance(message, dict) and message.get("role") in {"human", "user"}:
            return str(message.get("content", ""))

    return ""


def _router_thread_id_from_config(config: RunnableConfig) -> str:
    configurable = config.get("configurable", {}) if config else {}
    thread_id = configurable.get("thread_id")
    if not thread_id:
        raise ValueError(
            "Router graph must be invoked with config['configurable']['thread_id']."
        )
    return str(thread_id)


def route_intent(text: str) -> RouteName:
    """Simple deterministic router. Replace this with an LLM intent classifier later."""
    lowered = text.lower()

    if any(token in lowered for token in ["form", "field", "questionnaire", "intake"]):
        return "smart_form_builder"

    if any(token in lowered for token in ["insight", "analyze", "recommend", "strategy"]):
        return "best_insights"

    return "unknown"


@dataclass(frozen=True)
class RouterRuntime:
    router_checkpointer: InMemorySaver
    smart_form_checkpointer: InMemorySaver
    best_insights_checkpointer: InMemorySaver


def build_router_runtime() -> RouterRuntime:
    """
    Create checkpointers for the router and subagents.

    For this demo, each graph gets its own in-memory checkpointer.
    In production, use durable checkpointers.
    """
    return RouterRuntime(
        router_checkpointer=InMemorySaver(),
        smart_form_checkpointer=InMemorySaver(),
        best_insights_checkpointer=InMemorySaver(),
    )


def build_router_graph(runtime: RouterRuntime):
    """
    Build the router graph.

    The router:
    1. Reads its own router thread ID from config.
    2. Routes the user message.
    3. Derives the chosen subagent's UUIDv5 thread ID from the router thread ID.
    4. Invokes that independently compiled subagent graph.
    """
    smart_form_graph = build_smart_form_builder_graph(runtime.smart_form_checkpointer)
    best_insights_graph = build_best_insights_graph(runtime.best_insights_checkpointer)

    builder = StateGraph(RouterState)

    def classify_route(state: RouterState) -> RouterState:
        text = _last_human_text(state.get("messages"))
        return {"route": route_intent(text)}

    def call_subagent(state: RouterState, config: RunnableConfig) -> RouterState:
        router_thread_id = _router_thread_id_from_config(config)
        route = state.get("route", "unknown")
        text = _last_human_text(state.get("messages"))

        if route == "smart_form_builder":
            derived_thread_id = subagent_thread_id(router_thread_id, route)
            result = smart_form_graph.invoke(
                {"messages": [HumanMessage(content=text)]},
                config={"configurable": {"thread_id": derived_thread_id}},
            )
            summary = result["messages"][-1].content
            return {
                "subagent_result": {
                    "agent": route,
                    "thread_id": derived_thread_id,
                    "form_fields": result.get("form_fields", []),
                    "call_count": result.get("call_count", 0),
                },
                "messages": [AIMessage(content=f"Router delegated to {route}. {summary}")],
            }

        if route == "best_insights":
            derived_thread_id = subagent_thread_id(router_thread_id, route)
            result = best_insights_graph.invoke(
                {"messages": [HumanMessage(content=text)]},
                config={"configurable": {"thread_id": derived_thread_id}},
            )
            summary = result["messages"][-1].content
            return {
                "subagent_result": {
                    "agent": route,
                    "thread_id": derived_thread_id,
                    "insights": result.get("insights", []),
                    "call_count": result.get("call_count", 0),
                },
                "messages": [AIMessage(content=f"Router delegated to {route}. {summary}")],
            }

        return {
            "subagent_result": {
                "agent": "unknown",
                "thread_id": None,
            },
            "messages": [
                AIMessage(
                    content=(
                        "Router could not confidently route this. "
                        "Try mentioning form fields or insights."
                    )
                )
            ],
        }

    builder.add_node("classify_route", classify_route)
    builder.add_node("call_subagent", call_subagent)

    builder.add_edge(START, "classify_route")
    builder.add_edge("classify_route", "call_subagent")
    builder.add_edge("call_subagent", END)

    return builder.compile(checkpointer=runtime.router_checkpointer)


def invoke_router(
    router_graph: Any,
    router_thread_id: str,
    user_text: str,
) -> RouterState:
    """Convenience wrapper for invoking the router with its stable router thread ID."""
    return router_graph.invoke(
        {"messages": [HumanMessage(content=user_text)]},
        config={"configurable": {"thread_id": router_thread_id}},
    )
