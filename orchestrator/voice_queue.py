"""A small Piper pool. Viewer episodes first; archive backfill second.

Two or three workers so private showings can voice at once, but never a stampede
on a tiny Render box. Writers are never blocked on this queue: they start first
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

_jobs: queue.PriorityQueue = queue.PriorityQueue()
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
            threading.Thread(
                target=_worker, daemon=True, name=f"piper-queue-{_worker_count}"
            ).start()


def _worker() -> None:
    while True:
        _prio, _n, job = _jobs.get()
        try:
            job()
        except Exception:
            pass
        finally:
            _jobs.task_done()


def submit(priority: int, fn: Callable[[], Any]) -> None:
    start()
    _jobs.put((int(priority), next(_seq), fn))


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
