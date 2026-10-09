"""One background thread that runs model jobs one at a time, so no request ever waits for the model.

Endpoints only call worker.submit(), which returns at once. LLM_WORKER=0 keeps the thread off
(tests, simulate.py); jobs then wait in the queue, and run_pending() runs them in the caller.
"""
import os
import threading
from collections import deque
from typing import Optional

from backend.llm import jobs


class Worker:
    def __init__(self):
        self._queue: deque[jobs.Job] = deque()
        self._lock = threading.Condition()
        self._thread: Optional[threading.Thread] = None
        self._stopping = False

    def submit(self, job: jobs.Job) -> None:
        """Queue a job; a job that is already waiting is not queued twice."""
        with self._lock:
            if job not in self._queue:
                self._queue.append(job)
                self._lock.notify()

    def pending(self) -> list[jobs.Job]:
        with self._lock:
            return list(self._queue)

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()

    def run_pending(self) -> None:
        """Run every queued job now, in this thread (tests)."""
        while True:
            with self._lock:
                if not self._queue:
                    return
                job = self._queue.popleft()
            jobs.run(job)

    def start(self) -> None:
        if os.environ.get("LLM_WORKER", "1") == "0" or self._thread is not None:
            return
        self._stopping = False
        self._thread = threading.Thread(target=self._loop, name="llm-worker", daemon=True)
        self._thread.start()
        jobs.log(f"worker started, model {jobs.model_name()}")

    def stop(self) -> None:
        with self._lock:
            self._stopping = True
            self._lock.notify()
        if self._thread is not None:
            self._thread.join(timeout=1)   # a model call in progress is not waited for (daemon thread)
            self._thread = None

    def _loop(self) -> None:
        while True:
            with self._lock:
                while not self._queue and not self._stopping:
                    self._lock.wait()
                if self._stopping:
                    return
                job = self._queue.popleft()
            jobs.run(job)


worker = Worker()
