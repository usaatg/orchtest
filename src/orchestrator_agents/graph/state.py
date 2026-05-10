from __future__ import annotations

import operator
from typing import Annotated, Any
from typing_extensions import NotRequired, TypedDict


class OrchestratorState(TypedDict):
    # User/session identity
    user_query: str
    user_id: str
    thread_id: str
    run_id: NotRequired[str]

    # Cross-thread/artifact references
    referenced_thread_ids: NotRequired[list[str]]
    referenced_artifact_ids: NotRequired[list[str]]
    imported_context: Annotated[list[dict[str, Any]], operator.add]

    # Routing
    normalized_query: NotRequired[str]
    route_plan: NotRequired[dict[str, Any]]
    route_verification: NotRequired[dict[str, Any]]
    route_policy_reason: NotRequired[str]
    selected_agent: NotRequired[str]
    current_agent: NotRequired[str]
    current_route_step_index: NotRequired[int]

    # Histories and telemetry
    messages: Annotated[list[dict[str, Any]], operator.add]
    route_history: Annotated[list[dict[str, Any]], operator.add]
    handoff_history: Annotated[list[dict[str, Any]], operator.add]
    observability_events: Annotated[list[dict[str, Any]], operator.add]

    # Artifacts/results
    artifact_ids: Annotated[list[str], operator.add]
    latest_agent_result: NotRequired[dict[str, Any]]
    agent_results: Annotated[list[dict[str, Any]], operator.add]
    final_answer: NotRequired[str]
