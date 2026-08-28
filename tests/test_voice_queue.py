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


def test_archive_backfill_cannot_occupy_every_viewer_lane():
    low_gate = threading.Event()
    low_started = 0
    lock = threading.Lock()

    def low_job():
        nonlocal low_started
        with lock:
            low_started += 1
        low_gate.wait(timeout=3)

    for _ in range(3):
        voice_queue.submit(voice_queue.LOW, low_job)

    deadline = time.time() + 1.5
    while time.time() < deadline:
        with lock:
            if low_started:
                break
        time.sleep(0.01)
    with lock:
        assert low_started == 1

    high_done = [threading.Event(), threading.Event()]
    for event in high_done:
        voice_queue.submit(voice_queue.HIGH, event.set)
    assert all(event.wait(timeout=1.5) for event in high_done)
    with lock:
        assert low_started == 1

    low_gate.set()
    voice_queue._low_jobs.join()
