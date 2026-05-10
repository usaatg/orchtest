from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from orchestrator_agents.schemas import ArtifactRecord


class JsonArtifactStore:
    """Tiny file-backed artifact store for demos and local development.

    Production replacement options: Postgres, S3/blob storage, vector/document store.
    State should carry artifact IDs and short summaries; this store carries large outputs.
    """

    def __init__(self, root: str | Path = ".artifacts") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        *,
        user_id: str,
        namespace: Iterable[str],
        artifact_type: str,
        content: str,
        summary: str | None = None,
        metadata: dict[str, Any] | None = None,
        source_thread_id: str | None = None,
    ) -> str:
        artifact_id = f"artifact_{uuid4().hex[:12]}"
        record = ArtifactRecord(
            artifact_id=artifact_id,
            user_id=user_id,
            namespace=tuple(namespace),
            artifact_type=artifact_type,
            content=content,
            summary=summary or content[:500],
            metadata=metadata or {},
            source_thread_id=source_thread_id,
        )
        path = self._path(user_id, record.namespace, artifact_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        return artifact_id

    def get(self, *, user_id: str, namespace: Iterable[str], artifact_id: str) -> ArtifactRecord:
        path = self._path(user_id, tuple(namespace), artifact_id)
        return ArtifactRecord.model_validate_json(path.read_text(encoding="utf-8"))

    def get_any_for_user(self, *, user_id: str, artifact_id: str) -> ArtifactRecord | None:
        base = self.root / user_id
        if not base.exists():
            return None
        for path in base.rglob(f"{artifact_id}.json"):
            return ArtifactRecord.model_validate_json(path.read_text(encoding="utf-8"))
        return None

    def list_namespace(self, *, user_id: str, namespace: Iterable[str]) -> list[ArtifactRecord]:
        directory = self.root / user_id / Path(*tuple(namespace))
        if not directory.exists():
            return []
        return [
            ArtifactRecord.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(directory.glob("*.json"))
        ]

    def list_for_thread(self, *, user_id: str, thread_id: str) -> list[ArtifactRecord]:
        return self.list_namespace(user_id=user_id, namespace=("threads", thread_id, "artifacts"))

    def _path(self, user_id: str, namespace: tuple[str, ...], artifact_id: str) -> Path:
        return self.root / user_id / Path(*namespace) / f"{artifact_id}.json"
