import time
import wave
from pathlib import Path

from orchestrator.gemini import TOASTER_APPLICATION_SCENE


def _packet(tmp: Path, eid: int, topic: str, duration: float = 0.2, source: str = "seed") -> dict:
    beats = []
    for i, beat in enumerate(TOASTER_APPLICATION_SCENE["beats"][:4]):
        wav = tmp / f"ep{eid:04d}_{i:02d}_{beat['speaker']}.wav"
        wav.write_bytes(b"RIFF....WAVEfmt ")
        beats.append({**beat, "audio": str(wav), "duration_sec": duration})
    return {"episode_id": eid, "scene": "living_room", "topic": topic, "source": source, "beats": beats}


def _reset(monkeypatch, tmp: Path):
    import orchestrator.playlist as pl
    monkeypatch.setattr(pl, "PLAYLIST_PATH", tmp / "playlist.json")
    monkeypatch.setattr(pl, "TTS_DIR", tmp)
    monkeypatch.setattr(pl, "NOW_PLAYING_PATH", tmp / "now_playing.json")
    pl._state = None
    return pl


def test_pin_then_current_keeps_airing_until_due(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    served = pl.pin(_packet(tmp_path, 7, "toaster"))
    assert served["show_episode_id"] == 7
    assert served["episode_id"] == 1
    assert len(served["beats"]) == 4
    again = pl.current()
    assert again["episode_id"] == 1
    assert again["show_episode_id"] == 7


def test_advance_after_duration_changes_play_id(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    first = pl.pin(_packet(tmp_path, 1, "a", duration=0.05, source="viewer"))
    second = pl.pin(_packet(tmp_path, 2, "b", duration=0.05, source="viewer"))
    assert second["show_episode_id"] == 1
    assert second["episode_id"] == first["episode_id"]
    assert pl._state.get("queued") == [1]
    pl._state["started_at"] = time.time() - 30
    nxt = pl.current()
    assert nxt["show_episode_id"] == 2
    assert nxt["episode_id"] == first["episode_id"] + 1
    assert pl._state.get("queued") in ([], None)


def test_pin_while_playing_does_not_interrupt(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    first = pl.pin(_packet(tmp_path, 11, "alpha", source="viewer"))
    airing = first["episode_id"]
    pl.pin(_packet(tmp_path, 12, "beta", source="viewer"))
    cur = pl.current()
    assert cur["show_episode_id"] == 11
    assert cur["episode_id"] == airing


def test_repin_current_episode_is_idempotent_and_eta_is_now(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    packet = _packet(tmp_path, 14, "already airing", source="viewer")
    first = pl.pin(packet)
    second = pl.pin(packet)
    assert second["episode_id"] == first["episode_id"]
    assert second["show_episode_id"] == 14
    assert pl._state.get("queued") == []
    assert pl.seconds_until_episode(14) == 0.0
    assert pl.format_eta_copy(pl.seconds_until_episode(14)) == "on now"


def test_eta_ignores_stale_duplicate_of_current_episode(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    pl.pin(_packet(tmp_path, 15, "already airing", source="viewer"))
    pl._state["queued"] = [pl._state["index"]]
    assert pl.seconds_until_episode(15) == 0.0
    assert abs(pl.queued_wait_seconds() - pl.remaining_seconds()) < 0.05


def test_duration_uses_wav_length(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    monkeypatch.setattr(pl, "ROOT", tmp_path)
    beats = []
    for i, beat in enumerate(TOASTER_APPLICATION_SCENE["beats"][:4]):
        wav_path = tmp_path / f"real_{i}.wav"
        with wave.open(str(wav_path), "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(8000)
            wf.writeframes(b"\x00\x00" * 8000)
        beats.append({**beat, "audio": str(wav_path), "duration_sec": 0.05})
    packet = {
        "episode_id": 9,
        "scene": "living_room",
        "topic": "wavlen",
        "source": "viewer",
        "beats": beats,
    }
    dur = pl._duration(packet)
    speech = 4.0 + 4 * pl.HOLD_SEC
    expected = speech * pl.DURATION_MULT + pl.LAST_BEAT_PAD
    assert dur > 4.0
    assert dur != 0.2
    assert dur >= expected - 1e-6
    assert pl.GRACE_SEC >= 12.0


def test_empty_current_has_no_beats(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    got = pl.current()
    assert got.get("beats") == [] or got.get("episode_id") is None


def test_random_reruns_prefer_non_seed(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    pl.pin(_packet(tmp_path, 1, "seed ep", source="seed"))
    pl.pin(_packet(tmp_path, 2, "viewer a", source="viewer"))
    pl.pin(_packet(tmp_path, 3, "viewer b", source="autonomous"))
    sources = []
    for _ in range(24):
        idx = pl._random_index(pl._state["packets"])
        sources.append(pl._state["packets"][idx]["source"])
    assert "seed" not in sources
    assert set(sources) <= {"viewer", "autonomous"}


def test_boot_picks_random_non_seed(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    monkeypatch.setattr("orchestrator.archive.init", lambda: False)
    monkeypatch.setattr("orchestrator.archive.list_voiced_packets", lambda: [])
    monkeypatch.setattr("orchestrator.archive.list_scenes", lambda: [])
    monkeypatch.setattr("orchestrator.archive.voiced_ids", lambda: set())
    pl.pin(_packet(tmp_path, 1, "seed ep", source="seed"))
    pl.pin(_packet(tmp_path, 2, "viewer a", source="viewer"))
    pl.pin(_packet(tmp_path, 3, "viewer b", source="autonomous"))
    picks = set()
    for _ in range(12):
        served = pl.ensure_voiced_boot(mem=None)
        picks.add(served["show_episode_id"])
    assert 1 not in picks
    assert picks <= {2, 3}


def test_eta_returns_remaining_seconds(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    pl.pin(_packet(tmp_path, 21, "eta-ep", duration=0.2, source="viewer"))
    rem = pl.remaining_seconds()
    assert rem > 0
    snap = pl.snapshot()
    assert snap["remaining_seconds"] > 0
    assert snap["remaining_seconds"] == rem or abs(snap["remaining_seconds"] - rem) < 2
    copy = pl.format_eta_copy(rem)
    assert "airs in about" in copy or copy == "on now"
    assert pl.format_eta_copy(0) == "on now"
    assert pl.format_eta_copy(3) == "on now"
    assert "1m" in pl.format_eta_copy(40)


def test_board_lists_queued_titles(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    pl.pin(_packet(tmp_path, 1, "Break the fourth wall by Dakota", source="viewer"))
    pl.pin(_packet(tmp_path, 2, "Programming tips by Rook", source="viewer"))
    pl.pin(_packet(tmp_path, 3, "Reviewer 2 by GPT SOL", source="viewer"))
    b = pl.board()
    assert b["now"] == "Break the fourth wall by Dakota"
    assert [x["topic"] for x in b["queue"]] == [
        "Programming tips by Rook",
        "Reviewer 2 by GPT SOL",
    ]


def _drain_voice_queue(timeout=8.0):
    import orchestrator.voice_queue as vq

    vq.start()
    deadline = time.time() + timeout
    while time.time() < deadline:
        if getattr(vq._jobs, "unfinished_tasks", 0) == 0:
            return
        time.sleep(0.02)
    remaining = getattr(vq._jobs, "unfinished_tasks", None)
    raise AssertionError(f"voice queue still has unfinished_tasks={remaining}")


def test_packet_wav_ok_without_local_files(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    packet = {
        "episode_id": 1,
        "beats": [
            {"speaker": "reed", "line": "a", "audio": "data/tts/ep0001_00_reed.wav", "duration_sec": 1.0},
            {"speaker": "maris", "line": "b", "audio": "data/tts/ep0001_01_maris.wav", "duration_sec": 1.0},
            {"speaker": "jinx", "line": "c", "audio": "data/tts/ep0001_02_jinx.wav", "duration_sec": 1.0},
            {"speaker": "quill", "line": "d", "audio": "data/tts/ep0001_03_quill.wav", "duration_sec": 1.0},
        ],
    }
    assert pl._packet_wav_ok(packet) is True
    empty = {
        "episode_id": 1,
        "beats": [{**b, "audio": ""} for b in packet["beats"]],
    }
    assert pl._packet_wav_ok(empty) is False
    short = {"episode_id": 1, "beats": packet["beats"][:3]}
    assert pl._packet_wav_ok(short) is False


class _FakeMem:
    def restore_from_archive(self):
        return None

    def insert_episode(self, *args, **kwargs):
        return 99


def test_ingest_airs_first_then_voices_the_rest(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    calls = []

    def fake_render(scene, eid, progress=None, out_dir=None):
        calls.append(int(eid))
        return _packet(tmp_path, int(eid), scene.get("topic") or f"ep {eid}", source="viewer")

    monkeypatch.setattr("orchestrator.tts.render", fake_render)
    monkeypatch.setattr("orchestrator.archive.init", lambda: True)
    monkeypatch.setattr("orchestrator.archive.list_voiced_packets", lambda: [])
    monkeypatch.setattr("orchestrator.archive.voiced_ids", lambda: set())
    monkeypatch.setattr("orchestrator.archive.upsert_episode", lambda p: None)
    monkeypatch.setattr("orchestrator.archive.upsert_manifest", lambda p: None)
    scenes = [
        {"id": i, "scene": {"topic": f"ep {i}", "source": "viewer", "beats": [{"speaker": "reed", "line": "hi"}]}}
        for i in range(1, 9)
    ]
    monkeypatch.setattr("orchestrator.archive.list_scenes", lambda: scenes)
    served = pl.ensure_voiced_boot(_FakeMem())
    _drain_voice_queue()
    assert calls == [8, 7, 6, 5, 4, 3, 2, 1]
    topics = [p["topic"] for p in pl._state["packets"]]
    assert "ep 8" in topics
    assert "ep 1" in topics
    assert served.get("beats")
    assert served.get("show_episode_id") == 8


def test_manifests_restore_without_piper(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    calls = []

    def fake_render(scene, eid, progress=None, out_dir=None):
        calls.append(int(eid))
        return _packet(tmp_path, int(eid), scene.get("topic") or f"ep {eid}", source="viewer")

    voiced = [
        _packet(tmp_path, 8, "ep 8", source="viewer"),
        _packet(tmp_path, 3, "ep 3", source="viewer"),
    ]
    monkeypatch.setattr("orchestrator.tts.render", fake_render)
    monkeypatch.setattr("orchestrator.archive.init", lambda: True)
    monkeypatch.setattr("orchestrator.archive.list_voiced_packets", lambda: voiced)
    monkeypatch.setattr("orchestrator.archive.voiced_ids", lambda: {8, 3})
    monkeypatch.setattr("orchestrator.archive.upsert_episode", lambda p: None)
    monkeypatch.setattr("orchestrator.archive.upsert_manifest", lambda p: None)
    scenes = [
        {"id": i, "scene": {"topic": f"ep {i}", "source": "viewer", "beats": [{"speaker": "reed", "line": "hi"}]}}
        for i in range(1, 9)
    ]
    monkeypatch.setattr("orchestrator.archive.list_scenes", lambda: scenes)
    served = pl.ensure_voiced_boot(_FakeMem())
    assert 8 not in calls
    assert 3 not in calls
    _drain_voice_queue()
    assert set(calls) == {1, 2, 4, 5, 6, 7}
    topics = [p["topic"] for p in pl._state["packets"]]
    assert "ep 8" in topics
    assert "ep 3" in topics
    assert served.get("beats")
