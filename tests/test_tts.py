import hashlib
import subprocess
import threading
import time
import wave
from pathlib import Path

from orchestrator import tts


def _pcm_wav(path: Path, seconds: float = 0.25) -> None:
    n = int(22050 * seconds)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00\x00" * n)


def _tiny_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(b"\x00\x00" * 100)


def _patch_io(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "ROOT", tmp_path)
    monkeypatch.setattr("orchestrator.r2.put_file", lambda *a, **k: None)
    manifests = []
    monkeypatch.setattr("orchestrator.archive.upsert_manifest", lambda p: manifests.append(p))
    return manifests


def test_wav_name_hashes_line_and_lowercases_speaker():
    line = "We still have a mortgage."
    name = tts._wav_name(1, 0, "Maris", line)
    digest = hashlib.sha256(f"maris\n{line}".encode("utf-8")).hexdigest()[:8]
    assert name == f"ep0001_00_maris_{digest}.wav"
    assert name == name.lower()
    assert tts._wav_name(1, 0, "MARIS", line) == name
    other = tts._wav_name(1, 0, "maris", "A different line")
    assert other != name
    assert other.startswith("ep0001_00_maris_")


def test_piper_timeout_grows_for_long_lines():
    assert tts._piper_timeout_sec("hi") == 60
    long_line = " ".join(["timestamp"] * 50)
    assert tts._piper_timeout_sec(long_line) >= 120
    assert tts._piper_timeout_sec(long_line) <= 180


def test_render_skips_existing_hashed_wav(tmp_path, monkeypatch):
    line = "hello there"
    scene = {
        "scene": "living_room",
        "topic": "skip",
        "source": "viewer",
        "beats": [
            {"speaker": "reed", "line": line, "emotion": "calm", "animation": "talking"},
        ],
    }
    dest = tmp_path / tts._wav_name(1, 0, "reed", line)
    _pcm_wav(dest, 0.25)
    assert tts._usable_wav(dest)

    def boom(*args, **kwargs):
        raise AssertionError("piper should not run")

    manifests = _patch_io(monkeypatch, tmp_path)
    monkeypatch.setattr(tts, "_run_piper", boom)
    monkeypatch.setattr(tts, "_render_line", boom)
    monkeypatch.setattr(tts, "piper_available", lambda: True)

    packet = tts.render(scene, 1, out_dir=tmp_path)
    assert packet["beats"][0]["duration_sec"] >= 0.2
    assert packet["beats"][0]["audio"].endswith(dest.name)
    stem = dest.name.removesuffix(".wav")
    hash8 = stem.rsplit("_", 1)[-1]
    assert len(hash8) == 8 and all(c in "0123456789abcdef" for c in hash8)
    assert manifests and manifests[0]["episode_id"] == 1


def test_same_line_twice_skips_second_render(tmp_path, monkeypatch):
    calls = []

    def fake_render(speaker, line, dest, models):
        calls.append(line)
        _pcm_wav(dest, 0.25)
        return 0.25

    _patch_io(monkeypatch, tmp_path)
    monkeypatch.setattr(tts, "_render_line", fake_render)
    scene = {
        "beats": [{"speaker": "reed", "line": "same words", "emotion": "calm", "animation": "talking"}],
    }
    first = tts.render(scene, 3, out_dir=tmp_path)
    second = tts.render(scene, 3, out_dir=tmp_path)
    assert calls == ["same words"]
    assert first["beats"][0]["audio"] == second["beats"][0]["audio"]
    assert Path(tmp_path / Path(first["beats"][0]["audio"]).name).is_file()


def test_render_synthesizes_beats_in_parallel_and_preserves_order(tmp_path, monkeypatch):
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_render(speaker, line, dest, models):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.06)
        _pcm_wav(dest, 0.25)
        with lock:
            active -= 1
        return 0.25

    _patch_io(monkeypatch, tmp_path)
    monkeypatch.setattr(tts, "_render_line", fake_render)
    lines = ["first", "second", "third", "fourth"]
    packet = tts.render(
        {
            "beats": [
                {"speaker": "reed", "line": line, "emotion": "calm", "animation": "talking"}
                for line in lines
            ]
        },
        19,
        out_dir=tmp_path,
    )
    assert max_active >= 2
    assert max_active <= tts._PIPER_PARALLELISM
    assert [beat["line"] for beat in packet["beats"]] == lines


def test_different_line_same_id_revoices(tmp_path, monkeypatch):
    calls = []

    def fake_render(speaker, line, dest, models):
        calls.append((speaker, line, dest.name))
        _pcm_wav(dest, 0.25)
        return 0.25

    _patch_io(monkeypatch, tmp_path)
    monkeypatch.setattr(tts, "_render_line", fake_render)
    a = {"beats": [{"speaker": "jinx", "line": "old episode line", "emotion": "scheming", "animation": "talking"}]}
    b = {"beats": [{"speaker": "jinx", "line": "brand new dialogue", "emotion": "scheming", "animation": "talking"}]}
    p1 = tts.render(a, 1, out_dir=tmp_path)
    p2 = tts.render(b, 1, out_dir=tmp_path)
    assert calls == [
        ("jinx", "old episode line", tts._wav_name(1, 0, "jinx", "old episode line")),
        ("jinx", "brand new dialogue", tts._wav_name(1, 0, "jinx", "brand new dialogue")),
    ]
    n1 = Path(p1["beats"][0]["audio"]).name
    n2 = Path(p2["beats"][0]["audio"]).name
    assert n1 != n2
    assert (tmp_path / n1).is_file()
    assert (tmp_path / n2).is_file()


def test_old_unhashed_wav_is_not_reused(tmp_path, monkeypatch):
    stale = tmp_path / "ep0001_00_reed.wav"
    _pcm_wav(stale, 0.5)
    calls = []

    def fake_render(speaker, line, dest, models):
        calls.append(dest.name)
        _pcm_wav(dest, 0.25)
        return 0.25

    _patch_io(monkeypatch, tmp_path)
    monkeypatch.setattr(tts, "_render_line", fake_render)
    scene = {
        "beats": [{"speaker": "reed", "line": "a brand new line", "emotion": "calm", "animation": "talking"}],
    }
    packet = tts.render(scene, 1, out_dir=tmp_path)
    audio_name = Path(packet["beats"][0]["audio"]).name
    assert calls == [audio_name]
    assert audio_name != "ep0001_00_reed.wav"
    assert audio_name.startswith("ep0001_00_reed_")
    assert audio_name.endswith(".wav")
    assert stale.is_file()


def test_tiny_wav_is_not_skipped(tmp_path, monkeypatch):
    line = "needs a real take"
    dest = tmp_path / tts._wav_name(1, 0, "reed", line)
    _tiny_wav(dest)
    assert dest.stat().st_size > 44
    assert tts._usable_wav(dest) is False
    calls = []

    def fake_render(speaker, line, dest, models):
        calls.append(dest.name)
        _pcm_wav(dest, 0.25)
        return 0.25

    _patch_io(monkeypatch, tmp_path)
    monkeypatch.setattr(tts, "_render_line", fake_render)
    packet = tts.render(
        {"beats": [{"speaker": "reed", "line": line, "emotion": "calm", "animation": "talking"}]},
        1,
        out_dir=tmp_path,
    )
    assert calls == [dest.name]
    assert tts._usable_wav(tmp_path / Path(packet["beats"][0]["audio"]).name)


def test_speaker_is_lowercased_in_packet_and_filename(tmp_path, monkeypatch):
    def fake_render(speaker, line, dest, models):
        assert speaker == "maris"
        _pcm_wav(dest, 0.25)
        return 0.25

    _patch_io(monkeypatch, tmp_path)
    monkeypatch.setattr(tts, "_render_line", fake_render)
    packet = tts.render(
        {"beats": [{"speaker": "Maris", "line": "Logged.", "emotion": "annoyed", "animation": "talking"}]},
        2,
        out_dir=tmp_path,
    )
    beat = packet["beats"][0]
    assert beat["speaker"] == "maris"
    name = Path(beat["audio"]).name
    assert "maris" in name
    assert "Maris" not in name
    assert name == tts._wav_name(2, 0, "maris", "Logged.")


def test_maris_line_produces_nonsilent_wav_path(tmp_path, monkeypatch):
    def fake_render(speaker, line, dest, models):
        _pcm_wav(dest, 0.4)
        return 0.4

    manifests = _patch_io(monkeypatch, tmp_path)
    monkeypatch.setattr(tts, "_render_line", fake_render)
    line = "Thursday August 27 2026 4:40 AM Mountain Time, logged."
    packet = tts.render(
        {
            "scene": "living_room",
            "topic": "clock",
            "beats": [{"speaker": "maris", "line": line, "emotion": "annoyed", "animation": "talking"}],
        },
        4,
        out_dir=tmp_path,
    )
    beat = packet["beats"][0]
    name = Path(beat["audio"]).name
    path = tmp_path / name
    assert name.startswith("ep0004_00_maris_")
    assert tts._usable_wav(path)
    assert beat["duration_sec"] >= 0.2
    assert manifests and manifests[0]["beats"][0]["audio"].endswith(name)


def test_run_piper_timeout_deletes_dest(tmp_path, monkeypatch):
    dest = tmp_path / "ep0001_00_maris_stub.wav"
    _tiny_wav(dest)

    def boom(*args, **kwargs):
        _tiny_wav(dest)
        raise subprocess.TimeoutExpired(cmd="piper", timeout=60)

    monkeypatch.setattr(tts.subprocess, "run", boom)
    ok = tts._run_piper("a very long maris timestamp line", tmp_path / "amy.onnx", dest)
    assert ok is False
    assert not dest.exists()


def test_normalize_float_wav_to_pcm(tmp_path):
    src = tmp_path / "float.wav"
    proc = subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=440:sample_rate=22050:duration=0.3",
            "-acodec",
            "pcm_f32le",
            str(src),
        ],
        capture_output=True,
        timeout=20,
    )
    assert proc.returncode == 0
    assert src.is_file()
    assert tts._usable_wav(src) is False
    assert tts._normalize_wav(src) is True
    assert tts._usable_wav(src)
    with wave.open(str(src), "rb") as wf:
        assert wf.getsampwidth() == 2
        assert wf.getnchannels() == 1
        assert wf.getframerate() == 22050
