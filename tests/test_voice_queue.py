import threading
import time

from orchestrator import voice_queue


def test_voice_queue_serializes_jobs(monkeypatch):
    active = 0
    max_active = 0
    lock = threading.Lock()

    def fake_render(scene, eid, progress=None, out_dir=None):
        nonlocal active, max_active
        with lock:
            active += 1
            max_active = max(max_active, active)
        time.sleep(0.08)
        with lock:
            active -= 1
        return {"episode_id": int(eid), "beats": [{"audio": "x.wav", "duration_sec": 0.1}] * 4}

    monkeypatch.setattr("orchestrator.tts.render", fake_render)
    voice_queue.start()

    results = []
    errors = []

    def run(eid):
        try:
            results.append(voice_queue.voice_episode({"beats": []}, eid, priority=voice_queue.HIGH))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=run, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()
    assert errors == []
    assert 2 <= max_active <= 3
    assert len(results) == 3
