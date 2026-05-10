from __future__ import annotations

import operator
from typing import Annotated, TypedDict
from typing_extensions import NotRequired


class OrchestratorState(TypedDict):
    # Input for the current turn. With a checkpointer and stable thread_id, prior
    # state is retained while each turn adds a new user_query/messages entry.
    user_query: str
    user_id: str
    thread_id: str

    # Multi-turn transcript and event logs. Reducers append rather than replace.
    messages: Annotated[list[dict], operator.add]
    route_history: Annotated[list[dict], operator.add]
    handoff_history: Annotated[list[dict], operator.add]
    artifact_ids: Annotated[list[str], operator.add]

    # Current turn routing/execution data.
    run_id: NotRequired[str]
    current_agent: NotRequired[str]
    selected_agent: NotRequired[str]
    route_decision: NotRequired[dict]
    route_verification: NotRequired[dict]
    agent_result: NotRequired[str]
    final_answer: NotRequired[str]
    clarification_question: NotRequired[str]
