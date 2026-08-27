"""One Piper worker. Viewer episodes first; archive backfill second. Never overlap synthesis."""

from __future__ import annotations

import itertools
import queue
import threading
from typing import Any, Callable

HIGH = 0
LOW = 1

_jobs: queue.PriorityQueue = queue.PriorityQueue()
_seq = itertools.count()
_started = threading.Event()


def start() -> None:
    if _started.is_set():
        return
    _started.set()
    threading.Thread(target=_worker, daemon=True, name="piper-queue").start()


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
    """Block until this scene is voiced on the single Piper worker."""
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
