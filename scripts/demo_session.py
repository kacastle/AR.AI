"""A full demo session against the real app, timed: DEMO_FAST phases, the real model worker, real audio.

Starts the app (the model and the voice warm up in the background), waits for the warm-up, then runs one
session with 3 learners (fake names): tiles for 1 minute (each learner takes a few seconds per item),
stories for 1 minute, summary for 1 minute. Prints the session time, the slowest request, where the summary
came from, and the time of every model call. Then it waits for the background work that comes after a
session (next session's stories) and prints those calls too.

Needs Ollama running with OLLAMA_MODEL (default gemma4:e4b). Uses a throwaway database and audio folder.

Usage: python scripts/demo_session.py            full run
       python scripts/demo_session.py --no-wait  stop when the session ends
"""
import os
import random
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
TMP = Path(tempfile.mkdtemp())
os.environ["DB_PATH"] = str(TMP / "demo.db")
os.environ["DEMO_FAST"] = "1"
os.environ["LLM_WORKER"] = "1"

from fastapi.testclient import TestClient  # noqa: E402

from backend.content import load_content  # noqa: E402
from backend.llm import jobs  # noqa: E402
from backend.llm.worker import worker  # noqa: E402
from backend.main import app  # noqa: E402
from backend.tts import audio  # noqa: E402

audio.AUDIO_DIR = TMP / "audio"           # new story audio goes here; word audio stays in audio_cache/
CONTENT = load_content()
LEARNERS = [
    {"name": "Ana", "picture": "cat", "profile": "low_emergent", "interests": ["int_food", "int_toys"]},
    {"name": "Ben", "picture": "dog", "profile": "high_emergent", "interests": ["int_vehicles", "int_basketball"]},
    {"name": "Carlo", "picture": "bird", "profile": "low_emergent", "interests": ["int_drawing", "int_music"]},
]
FIRST_TRY_RIGHT = {"Ana": 0.9, "Ben": 0.5, "Carlo": 0.7}
rnd = random.Random(7)
slowest = [0.0, ""]


def say(message: str) -> None:
    print(f"[demo] {datetime.now():%H:%M:%S} {message}", flush=True)


def call(client, method, url, **kwargs):
    start = time.perf_counter()
    r = getattr(client, method)(url, **kwargs)
    took = time.perf_counter() - start
    if took > slowest[0]:
        slowest[:] = [took, f"{method.upper()} {url.split('/api/')[1]}"]
    r.raise_for_status()
    return r.json() if r.headers.get("content-type", "").startswith("application/json") else r


def answer_for(turn) -> list[str]:
    item = turn["item"]
    if turn["task_type"] == "sentence_builder":
        return next(s.word_tiles for s in CONTENT.sentences if s.id == item["id"])
    word = CONTENT.words_by_id[item["id"]]
    return list(word.syllables) if turn["task_type"] == "dictation_syllables" else list(word.tiles)


def until(ends_at: str) -> float:
    return (datetime.fromisoformat(ends_at) - datetime.now().astimezone()).total_seconds()


def tiles_phase(c, sid):
    ends = call(c, "post", f"/api/sessions/{sid}/phase", json={"phase": "tiles"})["ends_at"]
    turns = 0
    while until(ends) > 4:
        turn = call(c, "get", f"/api/sessions/{sid}/next")
        right = answer_for(turn)
        time.sleep(rnd.uniform(2.0, 4.0))                         # the learner places tiles
        ok_first = rnd.random() < FIRST_TRY_RIGHT[turn["child_name"]]
        for attempt in range(1, 6):
            given = right if (ok_first or attempt > 1) else (right[:-1] or ["x"])
            r = call(c, "post", f"/api/sessions/{sid}/answer", json={
                "child_id": turn["child_id"], "item_id": turn["item"]["id"], "given": given,
                "hints_used": attempt - 1, "attempt": attempt, "time_ms": 3000})
            if r["next_action"] == "next":
                break
            time.sleep(1.0)                                         # listens to the hint, tries again
        turns += 1
    time.sleep(max(0, until(ends)))
    say(f"tiles: {turns} turns, timer was {turn['seconds']} s per item")


def stories_phase(c, sid, session):
    ends = call(c, "post", f"/api/sessions/{sid}/phase", json={"phase": "stories"})["ends_at"]
    for child_id, story_id in session["story_ids"].items():
        story = call(c, "get", f"/api/stories/{story_id}")
        sound = c.get(story["audio_url"]).status_code
        name = next(x for x in LEARNERS if x["name"] in " ".join(story["paragraphs"]))["name"] \
            if story_id.startswith("ts_") else "library"
        say(f"stories: {story_id} '{story['title']}' ({len(story['words'])} words, audio {sound}, for {name})")
    time.sleep(max(0, until(ends)))


def summary_phase(c, sid):
    first = call(c, "get", f"/api/sessions/{sid}/summary")
    ends = call(c, "post", f"/api/sessions/{sid}/phase", json={"phase": "summary"})["ends_at"]
    got, source, start = first, "code template", time.time()
    while until(ends) > 0:
        got = call(c, "get", f"/api/sessions/{sid}/summary")
        if got != first:
            source = f"the model, after {time.time() - start:.0f} s"
            break
        time.sleep(2)
    say(f"summary from {source}:")
    for x in got["learners"]:
        print("         ", x["summary"])
    if got["group_note"]:
        print("          note:", got["group_note"])
    time.sleep(max(0, until(ends)))


def print_calls(title, calls):
    print(f"\n{title}")
    for x in calls:
        print(f"  {x['seconds']:6.1f} s  {x['label']}: {x['result']}")


def main():
    with TestClient(app) as c:
        say("app started; waiting for the warm-up")
        t = time.time()
        while time.time() - t < 300 and len([x for x in jobs.CALL_TIMES if x["what"].startswith("warm-up")]) < 2:
            time.sleep(0.5)
        g = call(c, "post", "/api/groups", json={"tutor_name": "Demo", "learners": LEARNERS})
        start = time.time()
        session = call(c, "post", "/api/sessions", json={"group_id": g["id"],
                                                         "present": [x["id"] for x in g["learners"]]})
        sid = session["id"]
        say(f"session {sid} started")
        tiles_phase(c, sid)
        stories_phase(c, sid, session)
        summary_phase(c, sid)
        took = time.time() - start
        in_session = list(jobs.CALL_TIMES)
        print(f"\nSession: {took / 60:.1f} min ({took:.0f} s). Slowest request: {slowest[0] * 1000:.0f} ms "
              f"({slowest[1]}).")
        print_calls("Model and voice calls until the end of the session:", in_session)
        if "--no-wait" not in sys.argv:
            say("waiting for the background work after the session (next session's stories)")
            t = time.time()
            while (worker.pending() or worker.busy()) and time.time() - t < 600:
                time.sleep(1)
            print_calls("Model and voice calls after the session:", jobs.CALL_TIMES[len(in_session):])
            print(f"\nWaiting for the tutor: {len(c.get('/api/approvals').json())} items in /api/approvals")
        ok = 3 * 60 - 5 <= took <= 4 * 60 and slowest[0] < 1.0     # three 1-minute phases = 180 s
        print("\nOK: the session took 3 to 4 minutes and no request waited for the model." if ok else
              "\nFAIL: the session was not 3 to 4 minutes, or a request took 1 s or more.")
        sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
