from pathlib import Path

from orchestrator_agents.storage import JsonArtifactStore, JsonMemoryStore


def test_artifact_store_same_thread_and_cross_thread_lookup(tmp_path: Path):
    store = JsonArtifactStore(tmp_path / "artifacts")
    artifact_id = store.put(
        user_id="u1",
        namespace=("threads", "t1", "artifacts"),
        artifact_type="research_summary",
        content="Long research content",
        summary="Short summary",
        source_thread_id="t1",
    )

    same_thread = store.get(user_id="u1", namespace=("threads", "t1", "artifacts"), artifact_id=artifact_id)
    assert same_thread.content == "Long research content"

    cross_thread = store.get_any_for_user(user_id="u1", artifact_id=artifact_id)
    assert cross_thread is not None
    assert cross_thread.source_thread_id == "t1"


def test_memory_store_is_separate_from_artifacts(tmp_path: Path):
    memory = JsonMemoryStore(tmp_path / "memory")
    memory_id = memory.put(
        user_id="u1",
        namespace=("users", "u1", "memories"),
        memory_type="preference",
        content="Prefers production-grade examples.",
    )
    records = memory.list_namespace(user_id="u1", namespace=("users", "u1", "memories"))
    assert records[0].memory_id == memory_id
    assert records[0].memory_type == "preference"
