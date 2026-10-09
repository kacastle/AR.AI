"""The learning loop beyond one item (backend/adapt.py): diagnostic, pace, re-teach methods that the learner
remembers, stars, interest words, and the profile for parents."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = str(Path(_tmp) / "adapt.db")

from fastapi.testclient import TestClient  # noqa: E402

from backend import adapt, db  # noqa: E402
from backend.content import load_content  # noqa: E402
from backend.engine.selector import choose_item  # noqa: E402
from backend.main import app  # noqa: E402

CONTENT = load_content()
RULES = CONTENT.rules


def memory_db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(db.SCHEMA)
    for table, column, col_type in db.ADDED_COLUMNS:
        if column not in {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}:
            conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    return conn


def event(conn, correct, mistake=None, time_ms=3000, skill="sk_cvc_final"):
    conn.execute("INSERT INTO events (session_id, child_id, item_id, task_type, skill_id, given, correct, mistake_type, "
                 "hints_used, attempt, time_ms, support_level, next_action) "
                 "VALUES ('s', 'c', 'w', 'dictation_letters', ?, '[]', ?, ?, 0, 1, ?, 'alone', 'next')",
                 (skill, int(correct), mistake, time_ms))


class UnitTest(unittest.TestCase):
    def test_same_mistake_twice_starts_the_first_method_and_it_is_judged(self):
        conn = memory_db()
        event(conn, False, "P_OMIT_FINAL")
        self.assertIsNone(adapt.after_item(conn, RULES, "c", "sk_cvc_final", False))   # once is not enough
        event(conn, False, "P_OMIT_FINAL")
        self.assertEqual(adapt.after_item(conn, RULES, "c", "sk_cvc_final", False), "syllable_color_clap")
        pick = adapt.method_for_pick(RULES, adapt.active_method(conn, "c"))
        self.assertEqual(pick["effect"], {"task_type": "dictation_syllables", "difficulty": "easy"})
        for _ in range(RULES.methods["syllable_color_clap"].items_after):
            adapt.after_item(conn, RULES, "c", "sk_cvc_final", True)
        run = conn.execute("SELECT * FROM method_runs").fetchone()
        self.assertEqual((run["worked"], run["correct"], run["total"]), (1, 3, 3))
        self.assertIsNone(adapt.active_method(conn, "c"))

    def test_the_learner_is_remembered_a_failed_method_is_skipped_a_working_one_comes_first(self):
        conn = memory_db()
        conn.execute("INSERT INTO method_runs (child_id, skill_id, mistake_type, method, items_left, worked) "
                     "VALUES ('c', 'sk_ng', 'O_NG', 'ng_sound_pairs', 0, 0)")
        self.assertEqual(adapt.choose_method(conn, RULES, "c", "O_NG"), "syllable_tiles_then_letters")
        conn.execute("INSERT INTO method_runs (child_id, skill_id, mistake_type, method, items_left, worked) "
                     "VALUES ('c', 'sk_ng', 'O_NG', 'syllable_tiles_then_letters', 0, 1)")
        self.assertEqual(adapt.choose_method(conn, RULES, "c", "O_NG"), "syllable_tiles_then_letters")
        self.assertEqual(adapt.choose_method(conn, RULES, "other", "O_NG"), "ng_sound_pairs")   # per learner

    def test_pace_slow_rule_stars_and_streak(self):
        conn = memory_db()
        self.assertIsNone(adapt.pace(conn, "c", RULES))
        for _ in range(5):
            event(conn, True, time_ms=2000)
        self.assertEqual(adapt.pace(conn, "c", RULES), "fast")
        self.assertFalse(adapt.last_was_slow(conn, "c", RULES))
        event(conn, False, time_ms=(RULES.timing.slow_seconds + 5) * 1000)
        self.assertTrue(adapt.last_was_slow(conn, "c", RULES))
        event(conn, True)
        self.assertEqual((adapt.stars(conn, "c"), adapt.streak(conn, "c")), (6, 1))

    def test_interest_words_come_first(self):
        words = [w for w in CONTENT.data.words if w.kind == "word"][:3]
        self.assertEqual(choose_item(words, [], "normal", prefer=[words[2].text]).id, words[2].id)
        self.assertEqual(choose_item(words, [], "normal").id, words[0].id)


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def session(self, diagnostic):
        group = self.client.post("/api/groups", json={"tutor_name": "T", "learners": [
            {"name": "Ana", "picture": "cat", "profile": "low_emergent", "interests": ["int_toys"],
             "diagnostic": diagnostic}]}).json()
        child = group["learners"][0]["id"]
        s = self.client.post("/api/sessions", json={"group_id": group["id"], "present": [child]}).json()
        return s["id"], child

    def expected(self, sid):
        with sqlite3.connect(db.DB_PATH) as conn:
            return json.loads(conn.execute("SELECT current_turn FROM sessions WHERE id = ?", (sid,)).fetchone()[0])

    def post(self, sid, turn, given, attempt=1, time_ms=2000):
        return self.client.post(f"/api/sessions/{sid}/answer", json={
            "child_id": turn["child_id"], "item_id": turn["item"]["id"], "given": given, "hints_used": 0,
            "attempt": attempt, "time_ms": time_ms}).json()

    def answer(self, sid, right, time_ms=2000):
        """One item: right on the first try, or wrong (last tile left out) and then right on attempt 2."""
        turn = self.client.get(f"/api/sessions/{sid}/next").json()
        answer = self.expected(sid)["answer"]
        r = self.post(sid, turn, answer if right else answer[:-1], time_ms=time_ms)
        if r["next_action"] == "retry":
            r = self.post(sid, turn, answer, attempt=2, time_ms=time_ms)
        return turn, r

    def test_diagnostic_first_then_practice_with_the_placed_profile(self):
        sid, child = self.session(diagnostic=True)
        modes = []
        for _ in range(40):
            turn, r = self.answer(sid, right=True)
            modes.append(turn["mode"])
            if turn["mode"] == "placement":
                self.assertEqual(turn["support_level"], "alone")
                self.assertEqual(r["next_action"], "next")             # one try only
            else:
                break
        self.assertEqual(modes[0], "placement")
        self.assertNotEqual(modes[-1], "placement")
        p = self.client.get(f"/api/children/{child}/profile").json()
        self.assertEqual((p["diagnostic"], p["profile"]), ("done", "high_emergent"))
        self.assertTrue(p["mastered"])

    def test_failed_diagnostic_stops_early_and_places_low(self):
        sid, child = self.session(diagnostic=True)
        n = 0
        while self.client.get(f"/api/sessions/{sid}/next").json()["mode"] == "placement":
            self.answer(sid, right=False)
            n += 1
        self.assertEqual(n, RULES.placement.stop_after_failed_skills * RULES.placement.items_per_skill)
        self.assertEqual(self.client.get(f"/api/children/{child}/profile").json()["profile"], "low_emergent")

    def test_no_diagnostic_by_default(self):
        sid, _ = self.session(diagnostic=False)
        self.assertNotEqual(self.client.get(f"/api/sessions/{sid}/next").json()["mode"], "placement")

    def test_repeated_mistake_reteaches_with_a_method_shown_to_the_tutor(self):
        sid, child = self.session(diagnostic=False)
        started = None
        for _ in range(8):
            _, r = self.answer(sid, right=False)
            if r["method_started"]:
                started = r["method_started"]
                break
        self.assertIsNotNone(started)
        nxt = self.client.get(f"/api/sessions/{sid}/next").json()
        self.assertEqual((nxt["mode"], nxt["method"]), ("reteach", started))
        self.assertEqual(nxt["method_note"], RULES.methods[started].description_en)
        self.assertNotEqual(nxt["support_level"], "alone")
        methods = self.client.get(f"/api/children/{child}/profile").json()["methods"]
        self.assertEqual((methods[0]["method"], methods[0]["worked"]), (started, None))   # still running

    def test_profile_for_parents(self):
        sid, child = self.session(diagnostic=False)
        self.answer(sid, right=True, time_ms=2000)
        p = self.client.get(f"/api/children/{child}/profile").json()
        for key in ("interests", "story_level", "pace", "current_skill", "mastered", "strengths", "needs_work",
                    "methods", "stars", "streak", "sessions"):
            self.assertIn(key, p)
        self.assertEqual(p["interests"][0]["id"], "int_toys")
        self.assertEqual((p["stars"], p["pace"], len(p["sessions"])), (1, "fast", 1))
        self.assertEqual(self.client.get("/api/children/nobody/profile").status_code, 404)
