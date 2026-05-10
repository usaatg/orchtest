from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from orchestrator_agents.schemas import MemoryRecord


class JsonMemoryStore:
    """Simple file-backed memory store distinct from graph checkpoint state.

    Use it for durable user/project/agent facts. Use ArtifactStore for generated outputs.
    """

    def __init__(self, root: str | Path = ".memory") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        *,
        user_id: str,
        namespace: Iterable[str],
        memory_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        memory_id = f"memory_{uuid4().hex[:12]}"
        record = MemoryRecord(
            memory_id=memory_id,
            user_id=user_id,
            namespace=tuple(namespace),
            memory_type=memory_type,
            content=content,
            metadata=metadata or {},
        )
        path = self._path(user_id, record.namespace, memory_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return memory_id

    def list_namespace(self, *, user_id: str, namespace: Iterable[str]) -> list[MemoryRecord]:
        directory = self.root / user_id / Path(*tuple(namespace))
        if not directory.exists():
            return []
        return [
            MemoryRecord.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(directory.glob("*.json"))
        ]

    def _path(self, user_id: str, namespace: tuple[str, ...], memory_id: str) -> Path:
        return self.root / user_id / Path(*namespace) / f"{memory_id}.json"
