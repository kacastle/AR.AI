"""One background thread that runs model jobs one at a time, so no request ever waits for the model.

Endpoints only call worker.submit(), which returns at once. Jobs run by jobs.PRIORITY (warm-up first,
then template audio, the summary, words, stories), first come first served within a priority.
start() queues the warm-up. LLM_WORKER=0 keeps the thread off (tests, simulate.py); jobs then wait in
the queue, and run_pending() runs them in the caller.
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
        self._current: Optional[jobs.Job] = None

    def submit(self, job: jobs.Job) -> None:
        """Queue a job by priority; a job that is already waiting or running is not queued again."""
        with self._lock:
            if job in self._queue or job == self._current:
                return
            rank = jobs.PRIORITY[job.kind]
            at = next((i for i, j in enumerate(self._queue) if jobs.PRIORITY[j.kind] > rank), len(self._queue))
            self._queue.insert(at, job)
            self._lock.notify()

    def busy(self) -> bool:
        """True while the thread runs a job."""
        return self._current is not None

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
        self.submit(jobs.Job("warmup"))
        self._thread = threading.Thread(target=self._loop, name="llm-worker", daemon=True)
        self._thread.start()
        jobs.log(f"worker started, model {jobs.model_name()}; warming up in the background")

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
                self._current = job
            try:
                jobs.run(job)
            finally:
                with self._lock:
                    self._current = None


worker = Worker()
