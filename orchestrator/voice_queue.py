"""A small Piper pool. Viewer episodes first; archive backfill second.

Two or three workers so private showings can voice at once, but never a stampede
on a tiny Render box. Only one worker accepts archive backfill, so boot-time
reruns can never occupy every paid-viewer lane. Writers start before this queue
and only wait here after the scene exists.
"""

from __future__ import annotations

import itertools
import os
import queue
import threading
from typing import Any, Callable

HIGH = 0
LOW = 1
MIN_WORKERS = 2
MAX_WORKERS = 3

_high_jobs: queue.Queue = queue.Queue()
_low_jobs: queue.Queue = queue.Queue()
_seq = itertools.count()
_started = threading.Event()
_start_lock = threading.Lock()
_worker_count = 0


def _wanted_workers() -> int:
    raw = os.environ.get("PIPER_WORKERS", "").strip()
    try:
        n = int(raw) if raw else MAX_WORKERS
    except ValueError:
        n = MAX_WORKERS
    return max(MIN_WORKERS, min(MAX_WORKERS, n))


def start() -> None:
    """Start up to PIPER_WORKERS (clamped 2–3) daemon threads. Idempotent."""
    global _worker_count
    want = _wanted_workers()
    with _start_lock:
        _started.set()
        while _worker_count < want:
            _worker_count += 1
            # One mixed worker drains archive backfill when viewers are quiet.
            # Every other worker remains reserved for viewer episodes.
            allow_low = _worker_count == 1
            threading.Thread(
                target=_worker,
                args=(allow_low,),
                daemon=True,
                name=f"piper-queue-{_worker_count}",
            ).start()


def _next_job(allow_low: bool):
    try:
        return _high_jobs, _high_jobs.get(timeout=0.15)
    except queue.Empty:
        if not allow_low:
            return None, None
    try:
        return _low_jobs, _low_jobs.get(timeout=0.15)
    except queue.Empty:
        return None, None


def _worker(allow_low: bool) -> None:
    while True:
        source, item = _next_job(allow_low)
        if source is None or item is None:
            continue
        _n, job = item
        try:
            job()
        except Exception:
            pass
        finally:
            source.task_done()


def submit(priority: int, fn: Callable[[], Any]) -> None:
    start()
    target = _high_jobs if int(priority) <= HIGH else _low_jobs
    target.put((next(_seq), fn))


def voice_episode(
    scene: dict[str, Any],
    episode_id: int,
    *,
    priority: int = HIGH,
    progress=None,
    source: str = "viewer",
) -> dict[str, Any]:
    """Block until this scene is voiced. The pool is 2–3 workers; writers start before this wait."""
    start()
    done = threading.Event()
    box: dict[str, Any] = {"packet": None, "error": None}

    def job() -> None:
        try:
            from orchestrator.tts import render

            packet = render(scene, int(episode_id), progress=progress)
            packet["source"] = source or packet.get("source") or "viewer"
            box["packet"] = packet
        except Exception as exc:
            box["error"] = exc
        finally:
            done.set()

    submit(priority, job)
    done.wait()
    if box["error"]:
        raise box["error"]
    return box["packet"]
