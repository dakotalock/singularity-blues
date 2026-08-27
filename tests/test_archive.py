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
    assert archive.next_episode_id() is None

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

class _IdStore:
    def __init__(self, episodes=None, manifests=None):
        self.episodes = dict(episodes or {})
        self.manifests = dict(manifests or {})


class _IdCursor:
    def __init__(self, store):
        self.store = store
        self._rows = []
        self.rowcount = 0

    def execute(self, sql, params=None):
        blob = " ".join(str(sql).split()).lower()
        if "pg_advisory_xact_lock" in blob:
            self._rows = [(True,)]
            self.rowcount = 1
        elif "greatest" in blob and "max(" in blob:
            max_ep = max(self.store.episodes) if self.store.episodes else 0
            max_man = max(self.store.manifests) if self.store.manifests else 0
            self._rows = [(max(max_ep, max_man),)]
            self.rowcount = 1
        elif "insert into" in blob and "episodes" in blob:
            eid = int(params[0])
            self.store.episodes[eid] = {"id": eid, "topic": params[1] if params else ""}
            self._rows = []
            self.rowcount = 1
        else:
            self._rows = []
            self.rowcount = 0
        return self

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return list(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _IdConn:
    def __init__(self, store):
        self.store = store

    def cursor(self):
        return _IdCursor(self.store)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def close(self):
        return None


def test_next_episode_id_uses_max_across_episodes_and_manifests(monkeypatch):
    store = _IdStore(episodes={3: {}, 10: {}}, manifests={7: {}, 12: {}})
    monkeypatch.setattr(archive, "_connect", lambda: _IdConn(store))
    got = archive.next_episode_id()
    assert got == 13
    assert 13 in store.episodes


def test_next_episode_id_starts_at_one_when_empty(monkeypatch):
    store = _IdStore()
    monkeypatch.setattr(archive, "_connect", lambda: _IdConn(store))
    assert archive.next_episode_id() == 1
    assert 1 in store.episodes
