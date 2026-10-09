"""The lesson player (backend/lessons.py): teach before practice, re-teach another way, remember what worked;
and the mini lesson story job (prompts.md section 7) on a fake model."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

_tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = str(Path(_tmp) / "lessons.db")

from fastapi.testclient import TestClient  # noqa: E402

from backend import db, lessons  # noqa: E402
from backend.content import load_content  # noqa: E402
from backend.llm import harness, jobs  # noqa: E402
from backend.llm.worker import worker  # noqa: E402
from backend.main import app  # noqa: E402

CONTENT = load_content()
RULES = CONTENT.rules


class LessonTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        worker.clear()

    def session(self, interests=("int_toys",)):
        group = self.client.post("/api/groups", json={"tutor_name": "T", "learners": [
            {"name": "Ana", "picture": "cat", "profile": "low_emergent", "interests": list(interests)}]}).json()
        child = group["learners"][0]["id"]
        s = self.client.post("/api/sessions", json={"group_id": group["id"], "present": [child]}).json()
        return s["id"], child

    def rows(self, sql, *args):
        with sqlite3.connect(db.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, args).fetchall()

    def expected(self, sid):
        return json.loads(self.rows("SELECT current_turn FROM sessions WHERE id = ?", sid)[0]["current_turn"])

    def play(self, sid, right):
        turn = self.client.get(f"/api/sessions/{sid}/next").json()
        current = self.expected(sid)
        answer = current["answer"]
        r = self.client.post(f"/api/sessions/{sid}/answer", json={
            "child_id": turn["child_id"], "item_id": turn["item"]["id"], "given": answer if right else answer[:-1],
            "hints_used": 0, "attempt": 1, "time_ms": 2000}).json()
        if r["next_action"] == "retry":
            r = self.client.post(f"/api/sessions/{sid}/answer", json={
                "child_id": turn["child_id"], "item_id": turn["item"]["id"], "given": answer, "hints_used": 0,
                "attempt": 2, "time_ms": 2000}).json()
        return turn, current, r

    def test_interest_catalog_for_the_sign_up(self):
        got = self.client.get("/api/interests").json()
        ids = {i["id"] for i in got}
        self.assertIn("int_toys", ids)
        self.assertNotIn("int_animals", ids)                      # no objects to write stories about
        self.assertEqual(set(got[0]), {"id", "label_fil", "label_en", "icon"})

    def test_a_new_skill_is_taught_before_its_first_item_only(self):
        sid, _ = self.session()
        turn, current, _ = self.play(sid, right=True)
        lesson = turn["lesson"]
        self.assertEqual((lesson["reason"], lesson["skill_id"]), ("new", current["skill_id"]))
        self.assertIn(lesson["style"], RULES.lessons["styles"])
        self.assertTrue(lesson["example"]["tiles"])
        self.assertTrue(lesson["steps"])
        nxt = self.client.get(f"/api/sessions/{sid}/next").json()
        if nxt["lesson"]:                                          # only when the next item is another skill
            self.assertNotEqual(nxt["lesson"]["skill_id"], lesson["skill_id"])

    def test_stuck_learner_is_retaught_in_another_style(self):
        sid, child = self.session()
        started = False
        for _ in range(10):
            _, _, r = self.play(sid, right=False)
            if r["method_started"]:
                started = True
                break
        self.assertTrue(started)
        nxt = self.client.get(f"/api/sessions/{sid}/next").json()
        self.assertEqual((nxt["mode"], nxt["lesson"]["reason"]), ("reteach", "reteach"))
        before = self.rows("SELECT style FROM lesson_views WHERE child_id = ? AND skill_id = ? ORDER BY id DESC "
                           "LIMIT 1 OFFSET 1", child, nxt["lesson"]["skill_id"])
        if before:
            self.assertNotEqual(nxt["lesson"]["style"], before[0]["style"])
        self.assertEqual(self.client.get(f"/api/sessions/{sid}/next").json()["lesson"], nxt["lesson"])  # same turn

    def test_a_lesson_is_judged_and_a_style_that_worked_comes_first(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA)
        conn.execute("INSERT INTO lesson_views (child_id, skill_id, style, reason) VALUES ('c', 'sk_ng', 'steps', 'new')")
        for right in (True, True, False):
            lessons.after_item(conn, RULES, "c", "sk_ng", right)
        self.assertEqual(tuple(conn.execute("SELECT worked, correct, total FROM lesson_views").fetchone()), (0, 2, 3))
        conn.execute("INSERT INTO lesson_views (child_id, skill_id, style, reason, worked) "
                     "VALUES ('c', 'sk_vowels', 'story', 'new', 1)")
        self.assertEqual(lessons.choose_style(conn, RULES, "c", "sk_cvc_final", "new", True), "story")
        self.assertEqual(lessons.choose_style(conn, RULES, "c", "sk_cvc_final", "new", False), "visual")
        self.assertEqual(lessons.choose_style(conn, RULES, "other", "sk_ng", "new", True), "visual")

    def test_story_lessons_use_an_approved_model_story_of_the_skill(self):
        sid, child = self.session()
        turn = self.client.get(f"/api/sessions/{sid}/next").json()
        skill = turn["lesson"]["skill_id"]
        with sqlite3.connect(db.DB_PATH) as conn:
            conn.execute("INSERT INTO generated_items (id, kind, child_id, payload) VALUES ('gl_1', 'lesson', ?, ?)",
                         (child, json.dumps({"skill_id": skill, "sentences": ["Si Ana ay may bola."],
                                             "words": ["bola"]})))
            conn.execute("INSERT INTO approvals (id, generated_item_id, status) VALUES ('a_1', 'gl_1', 'approved')")
            conn.row_factory = sqlite3.Row
            got = lessons._story(conn, CONTENT, child, next(s for s in CONTENT.data.skills if s.id == skill))
        self.assertEqual((got["source"], got["sentences"]), ("model", ["Si Ana ay may bola."]))

    def test_lesson_story_job_writes_a_checked_story_for_the_skill(self):
        _, child = self.session()
        saved = jobs.ask_model
        jobs.ask_model = lambda kind, user, v, learner: harness.tp.mock_output(kind, v, learner)
        try:
            jobs.run(jobs.Job("lesson", child_id=child, skill_id="sk_ng"), CONTENT)
            jobs.run(jobs.Job("lesson", child_id=child, skill_id="sk_ng"), CONTENT)     # not twice
        finally:
            jobs.ask_model = saved
        rows = self.rows("SELECT payload FROM generated_items WHERE kind = 'lesson' AND child_id = ?", child)
        self.assertEqual(len(rows), 1)
        p = json.loads(rows[0]["payload"])
        self.assertEqual((p["skill_id"], p["source"], len(p["sentences"])), ("sk_ng", "model", 3))
        self.assertTrue(any(w in " ".join(p["sentences"]) for w in p["words"]))
