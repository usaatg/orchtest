from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable
from uuid import uuid4

from orchestrator_agents.schemas import ArtifactDependency, ArtifactRecord, ArtifactStatus


class JsonArtifactStore:
    """File-backed artifact store for local development.

    It supports versioned artifacts, supersession, dependency lookup, and staleness.
    Production replacements can use Postgres + blob storage or a document store.
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
        created_by: str = "unknown",
        depends_on: list[ArtifactDependency] | None = None,
        supersedes: str | None = None,
        status: ArtifactStatus = "current",
    ) -> str:
        namespace_tuple = tuple(namespace)
        artifact_id = f"artifact_{uuid4().hex[:12]}"
        version = self._next_version(user_id=user_id, namespace=namespace_tuple, artifact_type=artifact_type, supersedes=supersedes)

        if supersedes:
            old = self.get_any_for_user(user_id=user_id, artifact_id=supersedes)
            if old:
                old.status = "superseded"
                self.update(old)

        record = ArtifactRecord(
            artifact_id=artifact_id,
            user_id=user_id,
            namespace=namespace_tuple,
            artifact_type=artifact_type,
            content=content,
            summary=summary or content[:500],
            version=version,
            status=status,
            metadata=metadata or {},
            source_thread_id=source_thread_id,
            created_by=created_by,
            depends_on=depends_on or [],
            supersedes=supersedes,
        )
        self._write(record)
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

    def update(self, record: ArtifactRecord) -> None:
        self._write(record)

    def mark_status(self, *, user_id: str, artifact_id: str, status: ArtifactStatus, reason: str | None = None) -> ArtifactRecord | None:
        record = self.get_any_for_user(user_id=user_id, artifact_id=artifact_id)
        if not record:
            return None
        record.status = status
        if reason:
            record.metadata["status_reason"] = reason
        self.update(record)
        return record

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

    def list_all_for_user(self, *, user_id: str) -> list[ArtifactRecord]:
        base = self.root / user_id
        if not base.exists():
            return []
        return [
            ArtifactRecord.model_validate_json(p.read_text(encoding="utf-8"))
            for p in sorted(base.rglob("*.json"))
        ]

    def find_dependents(self, *, user_id: str, source_artifact_id: str) -> list[ArtifactRecord]:
        dependents: list[ArtifactRecord] = []
        for record in self.list_all_for_user(user_id=user_id):
            if record.status in {"archived", "superseded"}:
                continue
            if any(dep.artifact_id == source_artifact_id for dep in record.depends_on):
                dependents.append(record)
        return dependents

    def latest_by_type_for_thread(self, *, user_id: str, thread_id: str, artifact_type: str) -> ArtifactRecord | None:
        records = [
            r for r in self.list_for_thread(user_id=user_id, thread_id=thread_id)
            if r.artifact_type == artifact_type and r.status == "current"
        ]
        if not records:
            return None
        return sorted(records, key=lambda r: (r.version, r.created_at))[-1]

    def _write(self, record: ArtifactRecord) -> None:
        path = self._path(record.user_id, record.namespace, record.artifact_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")

    def _path(self, user_id: str, namespace: tuple[str, ...], artifact_id: str) -> Path:
        return self.root / user_id / Path(*namespace) / f"{artifact_id}.json"

    def _next_version(self, *, user_id: str, namespace: tuple[str, ...], artifact_type: str, supersedes: str | None) -> int:
        if supersedes:
            old = self.get_any_for_user(user_id=user_id, artifact_id=supersedes)
            if old:
                return old.version + 1
        existing = [r for r in self.list_namespace(user_id=user_id, namespace=namespace) if r.artifact_type == artifact_type]
        return max([r.version for r in existing], default=0) + 1
