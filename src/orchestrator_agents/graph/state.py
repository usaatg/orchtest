from __future__ import annotations

import operator
from typing import Annotated, Any
from typing_extensions import NotRequired, TypedDict


class OrchestratorState(TypedDict):
    user_query: str
    user_id: str
    thread_id: str
    run_id: NotRequired[str]

    referenced_thread_ids: NotRequired[list[str]]
    referenced_artifact_ids: NotRequired[list[str]]
    imported_context: Annotated[list[dict[str, Any]], operator.add]

    active_workflow: NotRequired[str | None]
    active_form_schema: NotRequired[dict[str, Any]]
    active_form_state: NotRequired[dict[str, Any] | None]
    pending_dependency_action: NotRequired[dict[str, Any] | None]

    latest_form_artifact_id: NotRequired[str | None]
    latest_problem_statement_artifact_id: NotRequired[str | None]
    stale_artifact_ids: Annotated[list[str], operator.add]
    dependency_events: Annotated[list[dict[str, Any]], operator.add]

    normalized_query: NotRequired[str]
    route_plan: NotRequired[dict[str, Any]]
    route_verification: NotRequired[dict[str, Any]]
    route_policy_reason: NotRequired[str]
    selected_agent: NotRequired[str]
    current_agent: NotRequired[str]
    current_route_step_index: NotRequired[int]

    messages: Annotated[list[dict[str, Any]], operator.add]
    route_history: Annotated[list[dict[str, Any]], operator.add]
    handoff_history: Annotated[list[dict[str, Any]], operator.add]
    observability_events: Annotated[list[dict[str, Any]], operator.add]

    artifact_ids: Annotated[list[str], operator.add]
    latest_agent_result: NotRequired[dict[str, Any]]
    agent_results: Annotated[list[dict[str, Any]], operator.add]
    final_answer: NotRequired[str]
