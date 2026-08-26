import time
from pathlib import Path

from orchestrator.gemini import TOASTER_APPLICATION_SCENE


def _packet(tmp: Path, eid: int, topic: str, duration: float = 0.2) -> dict:
    beats = []
    for i, beat in enumerate(TOASTER_APPLICATION_SCENE["beats"][:4]):
        wav = tmp / f"ep{eid:04d}_{i:02d}_{beat['speaker']}.wav"
        wav.write_bytes(b"RIFF....WAVEfmt ")
        beats.append(
            {
                **beat,
                "audio": str(wav),
                "duration_sec": duration,
            }
        )
    return {
        "episode_id": eid,
        "scene": "living_room",
        "topic": topic,
        "source": "seed",
        "beats": beats,
    }


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
    pl.pin(_packet(tmp_path, 1, "a", duration=0.05))
    pl.pin(_packet(tmp_path, 2, "b", duration=0.05))
    # Two pins. Current is episode 2. Force the clock due.
    pl._state["started_at"] = time.time() - 30
    nxt = pl.current()
    assert nxt["show_episode_id"] in (1, 2)
    assert nxt["episode_id"] >= 3


def test_empty_current_has_no_beats(tmp_path, monkeypatch):
    pl = _reset(monkeypatch, tmp_path)
    got = pl.current()
    assert got.get("beats") == [] or got.get("episode_id") is None
