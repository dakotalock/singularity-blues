from orchestrator import archive

def test_archive_is_noop_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert archive.available() is False
    assert archive.init() is False
    assert archive.list_scenes() == []
    archive.upsert_episode({"episode_id": 1, "topic": "x", "beats": [{"speaker": "reed", "line": "hi"}]})
    assert archive.list_memories() == []
