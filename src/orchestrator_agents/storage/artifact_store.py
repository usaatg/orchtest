from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4
from datetime import datetime, timezone


class JsonArtifactStore:
    """Tiny file-backed artifact store for demos and local development.

    In production, replace this with Postgres/S3/blob storage/vector DB depending on
    artifact size and retrieval needs. The key design idea remains the same:
    keep large/durable outputs out of graph state and store artifact IDs in state.
    """

    def __init__(self, root: str | Path = ".artifacts") -> None:
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def put(
        self,
        *,
        user_id: str,
        thread_id: str,
        artifact_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        artifact_id = f"artifact_{uuid4().hex[:12]}"
        record = {
            "artifact_id": artifact_id,
            "user_id": user_id,
            "thread_id": thread_id,
            "artifact_type": artifact_type,
            "content": content,
            "metadata": metadata or {},
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        path = self._path(user_id, thread_id, artifact_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(record, indent=2), encoding="utf-8")
        return artifact_id

    def get(self, *, user_id: str, thread_id: str, artifact_id: str) -> dict[str, Any]:
        path = self._path(user_id, thread_id, artifact_id)
        return json.loads(path.read_text(encoding="utf-8"))

    def list_for_thread(self, *, user_id: str, thread_id: str) -> list[dict[str, Any]]:
        directory = self.root / user_id / thread_id
        if not directory.exists():
            return []
        return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(directory.glob("*.json"))]

    def _path(self, user_id: str, thread_id: str, artifact_id: str) -> Path:
        return self.root / user_id / thread_id / f"{artifact_id}.json"
