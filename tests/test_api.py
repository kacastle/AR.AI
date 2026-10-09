import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path

# Use a throwaway database; must be set before backend.db is imported.
_tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = str(Path(_tmp) / "test.db")

from fastapi.testclient import TestClient  # noqa: E402

from backend import db  # noqa: E402
from backend.content import load_content  # noqa: E402
from backend.engine.classifier import classify  # noqa: E402
from backend.engine.feedback import feedback_for  # noqa: E402
from backend.main import app  # noqa: E402

CONTENT = load_content()


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()  # runs startup: load content, create tables

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def make_session(self):
        group = self.client.post("/api/groups", json={
            "tutor_name": "Teacher", "learners": [
                {"name": "Ana", "picture": "cat", "profile": "low_emergent"},
                {"name": "Ben", "picture": "dog", "profile": "high_emergent"},
            ]}).json()
        ids = [c["id"] for c in group["learners"]]
        session = self.client.post("/api/sessions", json={"group_id": group["id"], "present": ids}).json()
        return group, session

    def test_login(self):
        self.assertEqual(self.client.post("/api/tutor/login", json={"pin": "0000"}).json(), {"ok": True})

    def test_group_roundtrip(self):
        group, _ = self.make_session()
        got = self.client.get(f"/api/groups/{group['id']}").json()
        self.assertEqual(got, group)
        self.assertEqual(set(got["learners"][0]), {"id", "name", "picture", "profile"})

    def test_bad_profile_rejected(self):
        r = self.client.post("/api/groups", json={
            "tutor_name": "T", "learners": [{"name": "X", "picture": "p", "profile": "nope"}]})
        self.assertEqual(r.status_code, 422)

    def test_session_and_story(self):
        _, session = self.make_session()
        self.assertEqual(set(session), {"id", "group_id", "present", "phase", "read_along_story_id"})
        story = self.client.get(f"/api/stories/{session['read_along_story_id']}").json()
        self.assertEqual(set(story), {"title", "paragraphs", "words", "audio_url"})
        self.assertEqual(story["title"], CONTENT.stories_by_id[session["read_along_story_id"]].title)

    def test_phase(self):
        _, session = self.make_session()
        r = self.client.post(f"/api/sessions/{session['id']}/phase", json={"phase": "stories"}).json()
        self.assertEqual(set(r), {"phase", "ends_at"})
        self.assertEqual(r["phase"], "stories")

    def test_next_returns_real_word_and_is_stable(self):
        _, session = self.make_session()
        turn = self.client.get(f"/api/sessions/{session['id']}/next").json()
        word = CONTENT.words_by_id[turn["item"]["id"]]
        self.assertEqual(turn["item"]["syllables"], word.syllables)
        self.assertEqual(turn["item"]["slots"], len(word.tiles))
        self.assertEqual(turn["child_name"], "Ana")
        self.assertEqual(turn["prefill"], word.tiles)  # new skill starts at support "show"
        # First skill is sk_vowels (letter_sound); its first task type is missing_letter: one vowel is missing.
        self.assertEqual(turn["task_type"], "missing_letter")
        self.assertIn(word.tiles[0], turn["item"]["tiles"])
        again = self.client.get(f"/api/sessions/{session['id']}/next").json()
        self.assertEqual(again, turn)

    def test_answer_hint_ladder_then_show_answer_then_rotation(self):
        _, session = self.make_session()
        sid = session["id"]
        turn = self.client.get(f"/api/sessions/{sid}/next").json()
        expected = CONTENT.words_by_id[turn["item"]["id"]].tiles

        def send(given, attempt):
            return self.client.post(f"/api/sessions/{sid}/answer", json={
                "child_id": turn["child_id"], "item_id": turn["item"]["id"], "given": given,
                "hints_used": attempt - 1, "attempt": attempt, "time_ms": 3000}).json()

        kinds = []
        for attempt in (1, 2, 3):
            r = send(["x"], attempt)
            self.assertEqual(r["next_action"], "retry")
            self.assertEqual(r["mistake_type"], classify(expected, ["x"]))
            self.assertIsNotNone(r["feedback"]["message_fil"])
            kinds.append(r["hint"]["kind"])
        self.assertEqual(kinds, ["replay_by_syllable", "highlight_slot", "first_tile"])
        r = send(["x"], 4)
        self.assertEqual(r["next_action"], "show_answer")
        self.assertEqual(r["answer"], expected)
        show = CONTENT.rules.feedback_templates["SHOW_ANSWER"]
        self.assertEqual(r["feedback"], {"message_fil": show.message_fil[0], "hint_fil": show.hint_fil})
        r = send(expected, 5)
        self.assertTrue(r["correct"])
        self.assertEqual(r["next_action"], "next")
        correct_lines = [line.format(name="Ana") for line in CONTENT.rules.feedback_templates["CORRECT"].message_fil]
        self.assertIn(r["feedback"]["message_fil"], correct_lines)
        self.assertEqual(set(r), {"correct", "mistake_type", "feedback", "hint", "next_action", "answer"})

        nxt = self.client.get(f"/api/sessions/{sid}/next").json()
        self.assertEqual(nxt["child_name"], "Ben")
        self.assertEqual(nxt["turn_number"], 2)

    def start_turn(self):
        _, session = self.make_session()
        sid = session["id"]
        turn = self.client.get(f"/api/sessions/{sid}/next").json()

        def send(given, attempt):
            return self.client.post(f"/api/sessions/{sid}/answer", json={
                "child_id": turn["child_id"], "item_id": turn["item"]["id"], "given": given,
                "hints_used": attempt - 1, "attempt": attempt, "time_ms": 3000}).json()
        return sid, turn, CONTENT.words_by_id[turn["item"]["id"]], send

    def events(self, sid):
        with sqlite3.connect(db.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM events WHERE session_id = ? ORDER BY id", (sid,)).fetchall()

    def test_wrong_answer_gets_mistake_type_and_template_feedback(self):
        sid, turn, word, send = self.start_turn()
        given = word.tiles[:-1]
        r = send(given, 1)
        code = classify(word.tiles, given)
        self.assertEqual(r["mistake_type"], code)
        want = feedback_for(CONTENT.rules, code, name="Ana", syllables=word.syllables, slots=len(word.tiles))
        self.assertEqual(r["feedback"], {"message_fil": want.message_fil, "hint_fil": want.hint_fil})
        self.assertNotIn("{", r["feedback"]["message_fil"] + (r["feedback"]["hint_fil"] or ""))
        self.assertEqual(r["hint"]["kind"], "replay_by_syllable")
        self.assertEqual(r["hint"]["audio"], f"/api/audio/{word.id}_slow.wav")

    def test_wrong_rebuild_after_show_answer_ends_the_item(self):
        sid, turn, word, send = self.start_turn()
        for attempt in (1, 2, 3, 4):
            send(["x"], attempt)
        r = send(["x"], 5)
        self.assertFalse(r["correct"])
        self.assertEqual(r["next_action"], "next")
        self.assertIsNone(r["hint"])
        nxt = self.client.get(f"/api/sessions/{sid}/next").json()
        self.assertEqual((nxt["child_name"], nxt["turn_number"]), ("Ben", 2))
        with sqlite3.connect(db.DB_PATH) as conn:
            attempts, wrong_streak, score = conn.execute(
                "SELECT attempts, wrong_streak, score FROM skill_state WHERE child_id = ?",
                (turn["child_id"],)).fetchone()
        self.assertEqual((attempts, wrong_streak), (1, 1))
        sc = CONTENT.rules.score
        self.assertAlmostEqual(score, sc.start_score + sc.alpha * (sc.result_values["wrong"] - sc.start_score))

    def test_each_answer_writes_one_event_with_turn_number(self):
        sid, turn, word, send = self.start_turn()
        send(word.tiles[:-1], 1)
        send(word.tiles, 2)
        nxt = self.client.get(f"/api/sessions/{sid}/next").json()
        self.client.post(f"/api/sessions/{sid}/answer", json={
            "child_id": nxt["child_id"], "item_id": nxt["item"]["id"],
            "given": CONTENT.words_by_id[nxt["item"]["id"]].tiles, "hints_used": 0, "attempt": 1, "time_ms": 2000})
        rows = self.events(sid)
        self.assertEqual([(e["turn_number"], e["attempt"], e["correct"]) for e in rows],
                         [(1, 1, 0), (1, 2, 1), (2, 1, 1)])
        self.assertEqual(rows[0]["mistake_type"], classify(word.tiles, word.tiles[:-1]))
        self.assertIsNone(rows[1]["mistake_type"])
        self.assertEqual({e["session_id"] for e in rows}, {sid})

    def test_turns_return_in_under_one_second(self):
        _, session = self.make_session()
        sid = session["id"]
        for _ in range(6):
            start = time.perf_counter()
            turn = self.client.get(f"/api/sessions/{sid}/next").json()
            self.assertLess(time.perf_counter() - start, 1.0)
            for attempt, given in ((1, ["x"]), (2, CONTENT.words_by_id[turn["item"]["id"]].tiles)):
                start = time.perf_counter()
                self.client.post(f"/api/sessions/{sid}/answer", json={
                    "child_id": turn["child_id"], "item_id": turn["item"]["id"], "given": given,
                    "hints_used": attempt - 1, "attempt": attempt, "time_ms": 1000})
                self.assertLess(time.perf_counter() - start, 1.0)

    def test_answer_for_wrong_item_is_rejected(self):
        _, session = self.make_session()
        turn = self.client.get(f"/api/sessions/{session['id']}/next").json()
        r = self.client.post(f"/api/sessions/{session['id']}/answer", json={
            "child_id": turn["child_id"], "item_id": "w_other", "given": [],
            "hints_used": 0, "attempt": 1, "time_ms": 1})
        self.assertEqual(r.status_code, 409)

    def test_summary_and_sheet(self):
        group, session = self.make_session()
        summary = self.client.get(f"/api/sessions/{session['id']}/summary").json()
        self.assertEqual(set(summary), {"learners", "group_note"})
        self.assertEqual(len(summary["learners"]), 2)
        first = summary["learners"][0]
        self.assertIn(first["next_focus_skill"], CONTENT.skills_by_id)
        self.assertIn(first["next_method"], CONTENT.rules.methods)

        sheet = self.client.get(f"/api/children/{group['learners'][0]['id']}/sheet").json()
        self.assertEqual(set(sheet), {"name", "date", "words", "sentence", "home_line_fil"})
        self.assertEqual(len(sheet["words"]), CONTENT.rules.practice_sheet.words)
        self.assertEqual(sheet["home_line_fil"], CONTENT.rules.practice_sheet.home_line_fil)

    def test_approvals_empty_and_unknown_404(self):
        self.assertEqual(self.client.get("/api/approvals").json(), [])
        self.assertEqual(self.client.post("/api/approvals/a_none", json={"approve": True}).status_code, 404)

    def test_audio(self):
        self.assertEqual(self.client.get("/api/audio/does_not_exist.wav").status_code, 404)
        self.assertEqual(self.client.get("/api/audio/bad.key.wav").status_code, 400)

    def test_cors_allows_frontend(self):
        r = self.client.options("/api/health", headers={
            "Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
        self.assertEqual(r.headers.get("access-control-allow-origin"), "http://localhost:5173")


if __name__ == "__main__":
    unittest.main()
