"""P2-8: warm-up at startup, timed model calls, job order, DEMO_FAST, and turns that never wait."""
import os
import tempfile
import threading
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("DB_PATH", str(Path(tempfile.mkdtemp()) / "test.db"))

from fastapi.testclient import TestClient  # noqa: E402

import backend.main as main  # noqa: E402
from backend.llm import client, harness, jobs  # noqa: E402
from backend.llm.worker import Worker, worker  # noqa: E402
from backend.main import app  # noqa: E402
from backend.tts import audio  # noqa: E402

tp = harness.tp


class FakeSpeaker:
    rate = 1000

    def say_timed(self, text):
        n = len(text.split())
        return np.full(100 * n, 0.5, dtype=np.float32), [(100 * i, 100 * i + 80) for i in range(n)]

    def say(self, text):
        return self.say_timed(text)[0]


@pytest.fixture
def fakes(monkeypatch, tmp_path):
    calls = []

    def model(kind, prompt, v, learner):
        calls.append(kind)
        return tp.mock_output(kind, v, learner)

    monkeypatch.setattr(jobs, "ask_model", model)
    monkeypatch.setattr(jobs, "get_speaker", lambda: FakeSpeaker())
    monkeypatch.setattr(audio, "AUDIO_DIR", tmp_path)
    worker.clear()
    jobs.CALL_TIMES.clear()
    yield calls
    worker.clear()


@pytest.fixture
def api():
    with TestClient(app) as c:
        yield c


def new_session(api, n=2):
    names = ["Ana", "Ben", "Carlo"][:n]
    group = api.post("/api/groups", json={"tutor_name": "T", "learners": [
        {"name": x, "picture": "p", "profile": "low_emergent", "interests": ["int_food", "int_toys"]}
        for x in names]}).json()
    session = api.post("/api/sessions", json={"group_id": group["id"],
                                              "present": [c["id"] for c in group["learners"]]}).json()
    return group, session


# ---------- job order ----------

def test_jobs_run_in_priority_order_then_first_come_first_served():
    w = Worker()
    for job in [jobs.Job("story", child_id="a"), jobs.Job("words", child_id="a"), jobs.Job("story", child_id="b"),
                jobs.Job("summary", session_id="s"), jobs.Job("story_audio", story_id="t"), jobs.Job("warmup")]:
        w.submit(job)
    assert [(j.kind, j.child_id) for j in w.pending()] == [
        ("warmup", None), ("story_audio", None), ("summary", None), ("words", "a"), ("story", "a"), ("story", "b")]


def test_session_start_queues_words_and_template_audio_and_the_summary_phase_queues_summary_then_stories(api, fakes):
    _, session = new_session(api)
    assert sorted(j.kind for j in worker.pending()) == ["lesson", "lesson", "story", "story", "story_audio",
                                                        "story_audio", "words", "words"]
    worker.clear()
    api.post(f"/api/sessions/{session['id']}/phase", json={"phase": "summary"})
    assert [j.kind for j in worker.pending()] == ["summary", "story", "story"]   # the summary is never stuck behind


# ---------- warm-up and timing log ----------

def test_warmup_loads_the_model_and_the_voice_and_logs_seconds(monkeypatch, fakes, capsys):
    loaded = []
    monkeypatch.setattr(client, "warm", lambda model: loaded.append(model))
    jobs.run(jobs.Job("warmup"))
    assert loaded == [jobs.model_name()]
    out = capsys.readouterr().out
    assert "warm-up" in out and " s" in out
    assert [c["what"] for c in jobs.CALL_TIMES] == ["warm-up model", "warm-up voice"]


def test_worker_start_queues_the_warmup_first(monkeypatch):
    w = Worker()
    monkeypatch.setenv("LLM_WORKER", "1")
    monkeypatch.setattr(w, "_loop", lambda: None)       # do not run anything in this test
    w.start()
    assert w.pending()[0].kind == "warmup"
    w.stop()


def test_every_model_call_is_logged_with_its_seconds(api, fakes, capsys):
    group, session = new_session(api)
    api.post(f"/api/sessions/{session['id']}/phase", json={"phase": "summary"})
    worker.run_pending()
    out = capsys.readouterr().out
    kinds = [c["what"] for c in jobs.CALL_TIMES]
    assert kinds.count("story") == 2 and kinds.count("words") == 2 and kinds.count("summary") == 1
    assert all(c["seconds"] >= 0 for c in jobs.CALL_TIMES)
    assert out.count(" s,") >= len(jobs.CALL_TIMES)     # one console line per call, with the seconds
    assert any(c["what"] == "story audio" for c in jobs.CALL_TIMES)


def test_warm_calls_ollama_load_with_keep_alive(monkeypatch):
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"done": true, "done_reason": "load"}'

    def fake_urlopen(request, timeout):
        import json
        seen.append((request.full_url, json.loads(request.data)))
        return Response()

    monkeypatch.setattr(client.urllib.request, "urlopen", fake_urlopen)
    client._down_until = 0.0
    client.warm("gemma4:e4b")
    url, body = seen[0]
    assert url.endswith("/api/generate")
    assert body == {"model": "gemma4:e4b", "keep_alive": "30m"}


# ---------- DEMO_FAST ----------

def test_demo_fast_makes_phases_one_minute_and_items_twenty_seconds(api, monkeypatch):
    monkeypatch.setattr(main, "DEMO_FAST", True)
    _, session = new_session(api)
    worker.clear()
    turn = api.get(f"/api/sessions/{session['id']}/next").json()
    assert turn["seconds"] == 20
    for phase in ("tiles", "stories", "summary"):
        r = api.post(f"/api/sessions/{session['id']}/phase", json={"phase": phase}).json()
        left = (datetime.fromisoformat(r["ends_at"]) - datetime.now().astimezone()).total_seconds()
        assert 55 <= left <= 61
    worker.clear()


def test_without_demo_fast_the_rules_json_times_are_used(api, monkeypatch):
    monkeypatch.setattr(main, "DEMO_FAST", False)
    _, session = new_session(api)
    worker.clear()
    assert api.get(f"/api/sessions/{session['id']}/next").json()["seconds"] == 60
    r = api.post(f"/api/sessions/{session['id']}/phase", json={"phase": "tiles"}).json()
    left = (datetime.fromisoformat(r["ends_at"]) - datetime.now().astimezone()).total_seconds()
    assert left > 30 * 60


# ---------- no turn waits for the model ----------

def test_turns_stay_fast_while_the_worker_runs_a_slow_model(api, monkeypatch, tmp_path):
    busy = threading.Event()

    def slow_model(kind, prompt, v, learner):
        busy.set()
        time.sleep(1.5)
        return tp.mock_output(kind, v, learner)

    monkeypatch.setattr(jobs, "ask_model", slow_model)
    monkeypatch.setattr(jobs, "get_speaker", lambda: FakeSpeaker())
    monkeypatch.setattr(audio, "AUDIO_DIR", tmp_path)
    monkeypatch.setattr(client, "warm", lambda model: None)
    monkeypatch.setenv("LLM_WORKER", "1")
    w = Worker()
    monkeypatch.setattr(main, "worker", w)
    w.start()
    try:
        _, session = new_session(api)
        sid = session["id"]
        api.post(f"/api/sessions/{sid}/phase", json={"phase": "summary"})   # summary + stories: slow model calls
        assert busy.wait(10), "the worker never called the model"
        slowest = 0.0
        for _ in range(6):
            start = time.perf_counter()
            turn = api.get(f"/api/sessions/{sid}/next").json()
            api.post(f"/api/sessions/{sid}/answer", json={
                "child_id": turn["child_id"], "item_id": turn["item"]["id"], "given": turn["prefill"],
                "hints_used": 0, "attempt": 1, "time_ms": 1000})
            slowest = max(slowest, time.perf_counter() - start)
        assert slowest < 1.0, f"a turn took {slowest:.2f} s while the model worked"
        assert w.pending() or w.busy(), "the model work should still be going on"
    finally:
        w.clear()
        w.stop()


def test_a_job_that_is_running_is_not_queued_again(monkeypatch):
    """GET /summary during the summary phase must not queue the summary the worker is writing right now."""
    running, release = threading.Event(), threading.Event()

    def fake_run(job, content=None):
        if job.kind == "summary":
            running.set()
            release.wait(5)

    monkeypatch.setattr(jobs, "run", fake_run)
    monkeypatch.setenv("LLM_WORKER", "1")
    w = Worker()
    w.start()
    try:
        w.submit(jobs.Job("summary", session_id="s1"))
        assert running.wait(5)
        w.submit(jobs.Job("summary", session_id="s1"))
        assert w.pending() == []
        w.submit(jobs.Job("summary", session_id="s2"))    # a different job still queues
        assert w.pending() == [jobs.Job("summary", session_id="s2")]
    finally:
        release.set()
        w.clear()
        w.stop()
