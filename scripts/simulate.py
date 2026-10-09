"""Simulate one session with 3 learners through the real API (throwaway database).

Ana is always right, Ben starts wrong and then gets it, Mila is right 3 times and then
wrong 3 times in a row. Prints each turn and each learner's skill states at the end.

Usage: python scripts/simulate.py [turns_per_learner]
"""
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["DB_PATH"] = str(Path(tempfile.mkdtemp()) / "simulate.db")
os.environ.setdefault("LLM_WORKER", "0")   # the engine only; no model calls

from fastapi.testclient import TestClient  # noqa: E402

from backend.main import app  # noqa: E402

TURNS = int(sys.argv[1]) if len(sys.argv) > 1 else 14

# First-try outcome for each learner's n-th item (0-based).
LEARNERS = {
    "Ana": lambda n: True,
    "Ben": lambda n: n >= 4,
    "Mila": lambda n: n % 6 < 3,
}


def db():
    conn = sqlite3.connect(os.environ["DB_PATH"])
    conn.row_factory = sqlite3.Row
    return conn


def skill_rows(child_id):
    with db() as conn:
        return conn.execute("SELECT skill_id, score, support_level, attempts, mastered_at FROM skill_state "
                            "WHERE child_id = ? ORDER BY rowid", (child_id,)).fetchall()


def main():
    with TestClient(app) as client:
        group = client.post("/api/groups", json={"tutor_name": "Teacher", "learners": [
            {"name": name, "picture": "star", "profile": "low_emergent"} for name in LEARNERS]}).json()
        ids = {l["name"]: l["id"] for l in group["learners"]}
        session = client.post("/api/sessions", json={"group_id": group["id"], "present": list(ids.values())}).json()
        sid = session["id"]
        count = {name: 0 for name in LEARNERS}
        seen = {name: {"skills": set(), "supports": set()} for name in LEARNERS}

        print(f"{'turn':>4}  {'learner':<5} {'skill':<14} {'task':<19} {'item':<10} {'support':<6} first  score after")
        for _ in range(TURNS * len(LEARNERS)):
            turn = client.get(f"/api/sessions/{sid}/next").json()
            name = turn["child_name"]
            with db() as conn:
                current = json.loads(conn.execute("SELECT current_turn FROM sessions WHERE id = ?",
                                                  (sid,)).fetchone()[0])
            right = LEARNERS[name](count[name])
            count[name] += 1
            body = {"child_id": turn["child_id"], "item_id": turn["item"]["id"], "hints_used": 0, "time_ms": 3000}
            if not right:
                client.post(f"/api/sessions/{sid}/answer", json={**body, "given": ["x"], "attempt": 1})
            r = client.post(f"/api/sessions/{sid}/answer",
                            json={**body, "given": current["answer"], "attempt": 1 if right else 2}).json()
            assert r["next_action"] == "next", r

            state = next(s for s in skill_rows(turn["child_id"]) if s["skill_id"] == current["skill_id"])
            seen[name]["skills"].add(current["skill_id"])
            seen[name]["supports"].add(turn["support_level"])
            seen[name]["supports"].add(state["support_level"])
            tag = " (easy item)" if current["is_easy"] else (" (review)" if current["is_review"] else "")
            print(f"{turn['turn_number']:>4}  {name:<5} {current['skill_id']:<14} {turn['task_type']:<19} "
                  f"{turn['item']['id']:<10} {turn['support_level']:<6} {'yes' if right else 'no ':<5}  "
                  f"{state['score']:.2f} {state['support_level']}{' MASTERED' if state['mastered_at'] else ''}{tag}")

        print("\nSkill states after the session:")
        ok = True
        for name, child_id in ids.items():
            print(f"  {name}:")
            for s in skill_rows(child_id):
                print(f"    {s['skill_id']:<14} score {s['score']:.2f}  support {s['support_level']:<6} "
                      f"attempts {s['attempts']:>2}{'  mastered' if s['mastered_at'] else ''}")
            moved = len(seen[name]["supports"]) > 1
            ok &= moved and bool(skill_rows(child_id))
            print(f"    support levels seen: {sorted(seen[name]['supports'])}; skills practiced: "
                  f"{sorted(seen[name]['skills'])}")
        print("\nOK: every learner's skill score and support level changed." if ok else
              "\nFAIL: a learner's support level did not change.")
        return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
