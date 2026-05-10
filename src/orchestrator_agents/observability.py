from __future__ import annotations

from typing import Any

from orchestrator_agents.schemas import ObservabilityEvent


def make_event(
    *,
    event_type: str,
    thread_id: str,
    run_id: str,
    agent_id: str | None = None,
    task_id: str | None = None,
    handoff_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return ObservabilityEvent(
        event_type=event_type,
        thread_id=thread_id,
        run_id=run_id,
        agent_id=agent_id,
        task_id=task_id,
        handoff_id=handoff_id,
        payload=payload or {},
    ).model_dump()
