from __future__ import annotations

from orchestrator_agents.schemas import DependencyEvent
from orchestrator_agents.storage.artifact_store import JsonArtifactStore


def invalidate_dependents(
    *,
    artifact_store: JsonArtifactStore,
    user_id: str,
    old_artifact_id: str,
    new_artifact_id: str,
) -> tuple[list[str], list[dict]]:
    """Mark all current artifacts that depend on old_artifact_id as stale."""
    stale_ids: list[str] = []
    events: list[dict] = []
    for dependent in artifact_store.find_dependents(user_id=user_id, source_artifact_id=old_artifact_id):
        reason = f"Depends on {old_artifact_id}, which was superseded by {new_artifact_id}."
        dependent.status = "stale"
        dependent.metadata["stale_reason"] = reason
        dependent.metadata["stale_due_to_artifact_id"] = new_artifact_id
        artifact_store.update(dependent)
        stale_ids.append(dependent.artifact_id)
        events.append(
            DependencyEvent(
                event_type="artifact_invalidated",
                source_artifact_id=old_artifact_id,
                new_artifact_id=new_artifact_id,
                affected_artifact_id=dependent.artifact_id,
                reason=reason,
            ).model_dump()
        )
    return stale_ids, events
