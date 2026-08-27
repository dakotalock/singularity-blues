from orchestrator import archive

def test_archive_is_noop_without_database_url(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert archive.available() is False
    assert archive.init() is False
    assert archive.list_scenes() == []
    archive.upsert_episode({"episode_id": 1, "topic": "x", "beats": [{"speaker": "reed", "line": "hi"}]})
    archive.upsert_manifest({"episode_id": 1, "beats": [{"speaker": "reed", "line": "hi", "audio": "a.wav"}]})
    assert archive.list_memories() == []
    assert archive.list_voiced_packets() == []
    assert archive.voiced_ids() == set()

import json


class _FakeCursor:
    def __init__(self, store):
        self.store = store
        self._rows = []

    def execute(self, sql, params=None):
        blob = " ".join(str(sql).split()).lower()
        if "insert into" in blob and "audio_manifests" in blob:
            eid, packet_json = params
            if isinstance(packet_json, str):
                packet = json.loads(packet_json)
            else:
                packet = packet_json
            self.store[int(eid)] = packet
            self._rows = []
        elif "select packet_json" in blob and "audio_manifests" in blob:
            self._rows = [(self.store[k],) for k in sorted(self.store)]
        elif "select episode_id" in blob and "audio_manifests" in blob:
            self._rows = [(k,) for k in sorted(self.store)]
        else:
            self._rows = []
        return self

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _FakeConn:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return _FakeCursor(self.store)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def close(self):
        return None


def test_upsert_manifest_roundtrip_with_fake_connect(monkeypatch):
    store = {}
    monkeypatch.setattr(archive, "_connect", lambda: _FakeConn(store))
    packet = {
        "show_episode_id": 4,
        "episode_id": 99,
        "topic": "manifest",
        "beats": [{"speaker": "reed", "line": "hi", "audio": "a.wav"}],
    }
    archive.upsert_manifest(packet)
    got = archive.list_voiced_packets()
    assert len(got) == 1
    assert got[0]["topic"] == "manifest"
    assert archive.voiced_ids() == {4}
