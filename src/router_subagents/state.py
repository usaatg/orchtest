from __future__ import annotations

from typing import Annotated, Any, Literal, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


RouteName = Literal["smart_form_builder", "best_insights", "unknown"]


class RouterState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    route: RouteName
    subagent_result: dict[str, Any]


class SmartFormState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    form_fields: list[str]
    call_count: int


class BestInsightsState(TypedDict, total=False):
    messages: Annotated[list[BaseMessage], add_messages]
    insights: list[str]
    call_count: int
