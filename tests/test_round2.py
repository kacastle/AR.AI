"""Feedback round 2: interest stories, vowel lessons, varied diagnostic, saved progress and returning learners,
level-matched worksheet, and the optional cloud model (local first)."""
import io
import json
import os
import random
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest import mock

_tmp = tempfile.mkdtemp()
os.environ["DB_PATH"] = str(Path(_tmp) / "round2.db")

from fastapi.testclient import TestClient  # noqa: E402

from backend import db  # noqa: E402
from backend.content import load_content  # noqa: E402
from backend.engine.selector import choose_item, skill_items  # noqa: E402
from backend.llm import client, fallbacks, prompts  # noqa: E402
from backend.main import app  # noqa: E402

CONTENT = load_content()
RULES = CONTENT.rules
SKILLS = {s.id: s for s in CONTENT.data.skills}


class ContentTest(unittest.TestCase):
    def test_every_interest_has_objects_and_a_plot_at_every_level(self):
        for interest in CONTENT.data.interests:
            self.assertTrue(interest.objects, interest.id)
            for level in (1, 2):
                plots = [p for p in CONTENT.data.story_plots
                         if p.level == level and set(p.fits_objects) & set(interest.objects)]
                self.assertTrue(plots, f"{interest.id} has no plot at level {level}")

    def test_letters_2_has_words_so_cv_2_can_unlock(self):
        self.assertTrue(skill_items(CONTENT, SKILLS["sk_letters_2"]))

    def test_story_case_never_fails_and_names_the_interest(self):
        for interest in CONTENT.data.interests:
            for level in (1, 2):
                learner = {"name": "Ana", "level": level, "interests": [interest.id], "weakest": "sk_cvcv_1"}
                v = prompts.story_case(learner, random.Random(1))
                self.assertIn(v["object"], interest.objects)
                self.assertEqual(v["interest"], interest.label_en.lower())
                _, user, unfilled = prompts.build("story", v)
                self.assertEqual(unfilled, [])
                self.assertIn(interest.label_en.lower(), user)

    def test_lesson_prompt_names_the_interest(self):
        learner = {"name": "Ana", "level": 1, "interests": ["int_food"], "weakest": "sk_cvcv_1"}
        v = prompts.lesson_case(learner, random.Random(1))
        _, user, unfilled = prompts.build("lesson", v)
        self.assertEqual(unfilled, [])
        self.assertIn("food", user)


class SelectorTest(unittest.TestCase):
    def test_diagnostic_items_differ_between_learners(self):
        items = skill_items(CONTENT, SKILLS["sk_vowels"])
        firsts = {choose_item(items, [], "easy", rng=random.Random(seed)).id for seed in range(20)}
        self.assertGreater(len(firsts), 1)

    def test_without_rng_the_choice_stays_deterministic(self):
        items = skill_items(CONTENT, SKILLS["sk_vowels"])
        self.assertEqual(len({choose_item(items, [], "easy").id for _ in range(5)}), 1)


class LibraryStoryTest(unittest.TestCase):
    def test_library_story_prefers_the_learners_interests(self):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.executescript(db.SCHEMA)
        for table, column, col_type in db.ADDED_COLUMNS:
            if column not in {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
        story = fallbacks.library_story(conn, CONTENT, "c", 2, ["int_food"], random.Random(0))
        self.assertIn("food", CONTENT.stories_by_id[story].interests)
        story = fallbacks.library_story(conn, CONTENT, "c", 2, ["int_farm"], random.Random(0))
        self.assertIn("farm", CONTENT.stories_by_id[story].interests)


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def group(self, diagnostic, interests=("int_toys",), name="Ana"):
        return self.client.post("/api/groups", json={"tutor_name": "T", "learners": [
            {"name": name, "picture": "cat", "profile": "low_emergent", "interests": list(interests),
             "diagnostic": diagnostic}]}).json()

    def session(self, diagnostic, interests=("int_toys",)):
        group = self.group(diagnostic, interests)
        child = group["learners"][0]["id"]
        s = self.client.post("/api/sessions", json={"group_id": group["id"], "present": [child]}).json()
        return s["id"], child

    def session_row(self, sid):
        with sqlite3.connect(db.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()

    def expected(self, sid):
        return json.loads(self.session_row(sid)["current_turn"])

    def answer(self, sid, right=True):
        turn = self.client.get(f"/api/sessions/{sid}/next").json()
        answer = self.expected(sid)["answer"]
        body = {"child_id": turn["child_id"], "item_id": turn["item"]["id"], "hints_used": 0, "time_ms": 2000}
        r = self.client.post(f"/api/sessions/{sid}/answer",
                             json={**body, "given": answer if right else answer[:-1], "attempt": 1}).json()
        if r["next_action"] == "retry":
            r = self.client.post(f"/api/sessions/{sid}/answer", json={**body, "given": answer, "attempt": 2}).json()
        return turn, r

    def finish_diagnostic(self, sid):
        for _ in range(40):
            turn = self.client.get(f"/api/sessions/{sid}/next").json()
            if turn["mode"] != "placement":
                return turn
            self.answer(sid, right=True)
        self.fail("the diagnostic did not end")

    def test_diagnostic_rotates_task_types_within_a_skill(self):
        sid, _ = self.session(diagnostic=True)
        tasks = []
        for _ in range(RULES.placement.items_per_skill):
            turn, _ = self.answer(sid)
            tasks.append(turn["task_type"])
        self.assertEqual(len(set(tasks)), RULES.placement.items_per_skill)

    def test_vowel_lesson_comes_first_even_after_a_passed_diagnostic(self):
        sid, _ = self.session(diagnostic=True)
        turn = self.finish_diagnostic(sid)
        lesson = turn["lesson"]
        self.assertIsNotNone(lesson)
        self.assertEqual((lesson["skill_id"], lesson["style"]), ("sk_vowels", "letters"))
        self.assertEqual([c["letter"] for c in lesson["letters"]], SKILLS["sk_vowels"].letters)
        for card in lesson["letters"]:
            self.assertTrue(card["word"].startswith(card["letter"]))
            self.assertEqual(card["audio"], f"/api/audio/syl_{card['letter']}.wav")
        self.answer(sid)
        nxt = self.client.get(f"/api/sessions/{sid}/next").json()["lesson"]
        self.assertTrue(nxt is None or nxt["skill_id"] != "sk_vowels")                   # shown once

    def test_returning_learner_keeps_progress_and_skips_the_diagnostic(self):
        sid, child = self.session(diagnostic=True)
        self.finish_diagnostic(sid)
        self.answer(sid)
        learners = self.client.get("/api/learners").json()
        me = next(x for x in learners if x["id"] == child)
        self.assertEqual(me["placement"], "done")
        self.assertIsNotNone(me["last_session"])
        group = self.client.post("/api/groups", json={"tutor_name": "T", "learners": [],
                                                      "existing_child_ids": [child]}).json()
        self.assertEqual([x["id"] for x in group["learners"]], [child])
        s2 = self.client.post("/api/sessions", json={"group_id": group["id"], "present": [child]}).json()
        self.assertNotEqual(self.client.get(f"/api/sessions/{s2['id']}/next").json()["mode"], "placement")
        p = self.client.get(f"/api/children/{child}/profile").json()
        self.assertTrue(p["history"])
        self.assertGreaterEqual(p["history"][-1]["mastered_count"], 1)
        self.assertEqual([x["skill_id"] for x in p["ladder"]],
                         [s.id for s in sorted(CONTENT.data.skills, key=lambda s: s.order)])
        bad = self.client.post("/api/groups", json={"tutor_name": "T", "learners": [], "existing_child_ids": ["nope"]})
        self.assertEqual(bad.status_code, 422)

    def test_sheet_matches_the_level_rotates_and_tells_the_parents(self):
        sid, child = self.session(diagnostic=False)
        with sqlite3.connect(db.DB_PATH) as conn:
            conn.execute("UPDATE children SET story_level = 2 WHERE id = ?", (child,))
        sentences = []
        for _ in range(3):
            sheet = self.client.get(f"/api/children/{child}/sheet").json()
            sentences.append(sheet["sentence"])
            note = sheet["parent_note"]
            self.assertEqual(note["story_level"], 2)
            self.assertTrue(note["level_label_fil"] and note["current_skill_fil"])
            self.assertEqual(note["total_skills"], len(CONTENT.data.skills))
        self.assertNotEqual(sentences[0], sentences[1])     # not the same sentence twice in a row
        level2 = {sn for st in CONTENT.data.stories if st.level == 2 for p in st.paragraphs
                  for sn in fallbacks.split_sentences(p)}
        self.assertTrue(all(s in level2 for s in sentences))

    def test_read_along_story_follows_the_learners_interests(self):
        sid, _ = self.session(diagnostic=False, interests=("int_animals",))
        story_id = self.session_row(sid)["read_along_story_id"]
        self.assertIn("animals", CONTENT.stories_by_id[story_id].interests)

    def test_interests_include_animals_now(self):
        ids = [i["id"] for i in self.client.get("/api/interests").json()]
        self.assertIn("int_animals", ids)


class CloudTest(unittest.TestCase):
    """LLM_PROVIDER=auto sends story jobs to Gemini when online with a key; the child's name never leaves."""

    @staticmethod
    def reply(text):
        body = {"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}]}
        return io.BytesIO(json.dumps(body).encode())

    def test_auto_uses_gemini_for_stories_and_strips_the_name(self):
        sent = {}

        def fake_urlopen(request, timeout):
            sent["url"], sent["body"] = request.full_url, json.loads(request.data)
            return self.reply('{"title": "Ang bola ni NAME_1"}')

        env = {"LLM_PROVIDER": "auto", "GEMINI_API_KEY": "k"}
        with mock.patch.dict(os.environ, env), mock.patch.object(client, "online", return_value=True), \
                mock.patch.object(client.urllib.request, "urlopen", fake_urlopen):
            text, done, provider = client.generate("story", "m", "sys", "Si Ana ay may bola.", 0.5, 100,
                                                   names=["Ana"])
        self.assertEqual(provider, "cloud")
        self.assertIn("generativelanguage.googleapis.com", sent["url"])
        self.assertNotIn("Ana", json.dumps(sent["body"]))
        self.assertEqual(json.loads(text)["title"], "Ang bola ni Ana")

    def test_local_by_default_and_for_other_jobs(self):
        with mock.patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
                mock.patch.object(client, "chat", return_value=("{}", "stop")):
            os.environ.pop("LLM_PROVIDER", None)
            self.assertEqual(client.generate("story", "m", "s", "u", 0.5, 10)[2], "local")
        with mock.patch.dict(os.environ, {"LLM_PROVIDER": "auto", "GEMINI_API_KEY": "k"}), \
                mock.patch.object(client, "online", return_value=True), \
                mock.patch.object(client, "chat", return_value=("{}", "stop")):
            self.assertEqual(client.generate("words", "m", "s", "u", 0.5, 10)[2], "local")

    def test_cloud_error_falls_back_to_local(self):
        with mock.patch.dict(os.environ, {"LLM_PROVIDER": "auto", "GEMINI_API_KEY": "k"}), \
                mock.patch.object(client, "online", return_value=True), \
                mock.patch.object(client, "gemini_chat", side_effect=client.ModelError("quota")), \
                mock.patch.object(client, "chat", return_value=("{}", "stop")):
            self.assertEqual(client.generate("story", "m", "s", "u", 0.5, 10)[2], "local")

    def test_offline_uses_local(self):
        with mock.patch.dict(os.environ, {"LLM_PROVIDER": "auto", "GEMINI_API_KEY": "k"}), \
                mock.patch.object(client, "online", return_value=False), \
                mock.patch.object(client, "chat", return_value=("{}", "stop")):
            self.assertEqual(client.generate("story", "m", "s", "u", 0.5, 10)[2], "local")


if __name__ == "__main__":
    unittest.main()
