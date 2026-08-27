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
    assert pl._state.get("queued") == 1
    pl._state["started_at"] = time.time() - 30
    nxt = pl.current()
    assert nxt["show_episode_id"] == 2
    assert nxt["episode_id"] == first["episode_id"] + 1
    assert pl._state.get("queued") is None


def test_pin_while_playing_does_not_interrupt(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    first = pl.pin(_packet(tmp_path, 11, "alpha", source="viewer"))
    airing = first["episode_id"]
    pl.pin(_packet(tmp_path, 12, "beta", source="viewer"))
    cur = pl.current()
    assert cur["show_episode_id"] == 11
    assert cur["episode_id"] == airing


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
    pl.pin(_packet(tmp_path, 1, "seed ep", source="seed"))
    pl.pin(_packet(tmp_path, 2, "viewer a", source="viewer"))
    pl.pin(_packet(tmp_path, 3, "viewer b", source="autonomous"))
    picks = set()
    for _ in range(12):
        served = pl.ensure_voiced_boot(mem=None)
        picks.add(served["show_episode_id"])
    assert 1 not in picks
    assert picks <= {2, 3}
