from __future__ import annotations

from uuid import UUID, uuid4, uuid5


# Do not change this after production data exists.
# Changing it would change every deterministic subagent thread ID.
AGENT_NAMESPACE = UUID("8c7f9c1e-7f41-4f94-9c3a-92f21f8ef001")


def new_router_thread_id() -> str:
    """Create a new UUIDv4 router thread ID for a new conversation."""
    return str(uuid4())


def subagent_thread_id(router_thread_id: str, subagent_name: str) -> str:
    """
    Derive a stable UUIDv5 thread ID for a subagent from the router thread ID.

    Same router_thread_id + same subagent_name => same subagent thread ID.
    Different router_thread_id => different subagent thread ID.
    """
    router_uuid = UUID(router_thread_id)
    normalized_name = normalize_agent_name(subagent_name)
    return str(uuid5(AGENT_NAMESPACE, f"{router_uuid}:{normalized_name}"))


def normalize_agent_name(agent_name: str) -> str:
    """Normalize subagent names so aliases/casing do not create accidental new threads."""
    normalized = agent_name.strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        raise ValueError("agent_name cannot be empty")
    return normalized


def make_thread_registry(router_thread_id: str, subagent_names: list[str]) -> dict[str, str]:
    """Return router + subagent thread IDs in one dictionary."""
    # Validate it early.
    UUID(router_thread_id)

    registry = {"router": router_thread_id}
    for name in subagent_names:
        normalized = normalize_agent_name(name)
        registry[normalized] = subagent_thread_id(router_thread_id, normalized)

    return registry
