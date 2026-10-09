"""Seed the demo database with 3 fake returning learners and 3 past sessions each, so the progress graph and
the returning-learner picker have something to show. Fake names only; never real child data.

Usage (repo root, venv active):  python scripts/seed_demo.py           (uses DB_PATH or data/tutor.db)
                                  python scripts/seed_demo.py --fresh   (deletes the database first)

Runs the real API in-process (no server, no model): the diagnostic, tile answers and story quizzes go through
the same endpoints as the app, then the session dates are moved back one day per session.
"""
import argparse
import json
import os
import random
import sqlite3
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
os.environ.setdefault("LLM_WORKER", "0")      # no model jobs while seeding

# (name, picture, interests, chance to answer right): one strong, one middle, one beginner learner.
LEARNERS = [
    ("Ana", "cat", ["int_animals", "int_food"], 0.9),
    ("Ben", "dog", ["int_vehicles", "int_basketball"], 0.7),
    ("Mila", "star", ["int_nature", "int_music"], 0.5),
]
SESSIONS = 3
ITEMS_PER_SESSION = 12


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fresh", action="store_true", help="delete the database first")
    args = parser.parse_args()

    from backend import db
    if args.fresh and db.DB_PATH.exists():
        db.DB_PATH.unlink()
    from fastapi.testclient import TestClient
    from backend.main import app

    rnd = random.Random(7)
    with TestClient(app) as api:
        group = api.post("/api/groups", json={"tutor_name": "Demo Tutor", "learners": [
            {"name": n, "picture": p, "profile": "low_emergent", "interests": i, "diagnostic": True}
            for n, p, i, _ in LEARNERS]}).json()
        ids = [c["id"] for c in group["learners"]]
        skill = {c["id"]: s for c, (_, _, _, s) in zip(group["learners"], LEARNERS)}
        session_ids = []
        for _ in range(SESSIONS):
            s = api.post("/api/sessions", json={"group_id": group["id"], "present": ids}).json()
            session_ids.append(s["id"])
            for _ in range(ITEMS_PER_SESSION * len(ids)):
                turn = api.get(f"/api/sessions/{s['id']}/next").json()
                with sqlite3.connect(db.DB_PATH) as conn:
                    answer = json.loads(conn.execute("SELECT current_turn FROM sessions WHERE id = ?",
                                                     (s["id"],)).fetchone()[0])["answer"]
                body = {"child_id": turn["child_id"], "item_id": turn["item"]["id"], "hints_used": 0,
                        "time_ms": rnd.randint(3000, 12000)}
                right = rnd.random() < skill[turn["child_id"]]
                r = api.post(f"/api/sessions/{s['id']}/answer",
                             json={**body, "given": answer if right else answer[:-1], "attempt": 1}).json()
                if r["next_action"] == "retry":
                    api.post(f"/api/sessions/{s['id']}/answer", json={**body, "given": answer, "attempt": 2})
            # Each learner's story quiz moves their story level.
            while (q := api.get(f"/api/sessions/{s['id']}/story_turn").json()) is not None:
                choices = q["question"]["choices"]
                api.post(f"/api/sessions/{s['id']}/story_answer", json={
                    "child_id": q["child_id"], "question_id": q["question"]["id"],
                    "choice": choices[0] if rnd.random() < skill[q["child_id"]] else choices[-1]})

    # Spread the sessions over the last days, oldest first.
    with sqlite3.connect(db.DB_PATH) as conn:
        for k, sid in enumerate(session_ids):
            day = date.today() - timedelta(days=SESSIONS - k)
            conn.execute("UPDATE sessions SET started_at = ? WHERE id = ?", (f"{day} 09:00:00", sid))
            conn.execute("UPDATE events SET created_at = ? WHERE session_id = ?", (f"{day} 09:00:00", sid))
            conn.execute("UPDATE progress_snapshots SET day = ? WHERE session_id = ?", (str(day), sid))
    print(f"Seeded {len(ids)} learners x {SESSIONS} sessions into {db.DB_PATH}")
    print("Open the app and choose 'Returning learners' (or 'New group' then the picker).")


if __name__ == "__main__":
    main()
