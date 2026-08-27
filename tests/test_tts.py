import wave
from pathlib import Path

from orchestrator import tts


def _tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00\x00" * 2205)


def test_render_skips_existing_wav(tmp_path, monkeypatch):
    scene = {
        "scene": "living_room",
        "topic": "skip",
        "source": "viewer",
        "beats": [
            {"speaker": "reed", "line": "hello there", "emotion": "calm", "animation": "talking"},
        ],
    }
    dest = tmp_path / "ep0001_00_reed.wav"
    _tiny_wav(dest)
    assert dest.stat().st_size > 44

    def boom(*args, **kwargs):
        raise AssertionError("piper should not run")

    monkeypatch.setattr(tts, "ROOT", tmp_path)
    monkeypatch.setattr(tts, "_run_piper", boom)
    monkeypatch.setattr(tts, "_render_line", boom)
    monkeypatch.setattr(tts, "piper_available", lambda: True)
    monkeypatch.setattr("orchestrator.r2.put_file", boom)
    manifests = []
    monkeypatch.setattr("orchestrator.archive.upsert_manifest", lambda p: manifests.append(p))

    packet = tts.render(scene, 1, out_dir=tmp_path)
    assert packet["beats"][0]["duration_sec"] > 0
    assert packet["beats"][0]["audio"].endswith("ep0001_00_reed.wav")
    assert manifests and manifests[0]["episode_id"] == 1
