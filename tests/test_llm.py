"""The background model step: stories, practice words and summaries. A fake model stands in for Ollama."""
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("DB_PATH", str(Path(tempfile.mkdtemp()) / "test.db"))

import numpy as np  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from backend import db, summary  # noqa: E402
from backend.content import load_content  # noqa: E402
from backend.llm import client, harness, jobs  # noqa: E402
from backend.llm.worker import worker  # noqa: E402
from backend.main import app  # noqa: E402
from backend.tts import audio  # noqa: E402

CONTENT = load_content()
tp = harness.tp


class FakeModel:
    """Answers like the harness's mock_output; `bad` = how many calls give broken JSON first."""

    def __init__(self, bad=0):
        self.calls, self.bad = [], bad

    def __call__(self, kind, prompt, v, learner):
        self.calls.append(kind)
        if self.bad:
            self.bad -= 1
            return "not json"
        return tp.mock_output(kind, v, learner)


class FakeSpeaker:
    """Stands in for the voice (OmniVoice): 100 ms per word."""
    rate = 1000

    def __init__(self, broken=False):
        self.broken = broken

    def say_timed(self, text):
        if self.broken:
            raise RuntimeError("no voice model")
        n = len(text.split())
        return np.full(100 * n, 0.5, dtype=np.float32), [(100 * i, 100 * i + 80) for i in range(n)]

    def say(self, text):
        return self.say_timed(text)[0]


class LlmTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.client.__enter__()

    @classmethod
    def tearDownClass(cls):
        cls.client.__exit__(None, None, None)

    def setUp(self):
        worker.clear()
        self.fake = FakeModel()
        self.speaker = FakeSpeaker()
        self._saved = (jobs.ask_model, jobs.get_speaker, audio.AUDIO_DIR)
        jobs.ask_model = self.fake
        jobs.get_speaker = lambda: self.speaker
        audio.AUDIO_DIR = Path(tempfile.mkdtemp())     # story audio goes here, not to audio_cache/

    def tearDown(self):
        jobs.ask_model, jobs.get_speaker, audio.AUDIO_DIR = self._saved
        worker.clear()

    def approvals_for(self, group):
        ids = {c["id"] for c in group["learners"]}
        return [a for a in self.client.get("/api/approvals").json() if a["child_id"] in ids]

    def rows(self, sql, *args):
        with sqlite3.connect(db.DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            return conn.execute(sql, args).fetchall()

    def make_session(self, interests=("int_food", "int_toys"), group=None):
        if group is None:
            group = self.client.post("/api/groups", json={"tutor_name": "T", "learners": [
                {"name": "Ana", "picture": "cat", "profile": "low_emergent", "interests": list(interests)},
                {"name": "Ben", "picture": "dog", "profile": "high_emergent", "interests": ["int_food", "int_toys"]},
            ]}).json()
        ids = [c["id"] for c in group["learners"]]
        session = self.client.post("/api/sessions", json={"group_id": group["id"], "present": ids}).json()
        return group, session

    def play(self, sid, turns):
        """Answer `turns` items right on the first try (new learners are at support "show": prefill = answer)."""
        for _ in range(turns):
            turn = self.client.get(f"/api/sessions/{sid}/next").json()
            r = self.client.post(f"/api/sessions/{sid}/answer", json={
                "child_id": turn["child_id"], "item_id": turn["item"]["id"], "given": turn["prefill"],
                "hints_used": 0, "attempt": 1, "time_ms": 1000}).json()
            self.assertEqual(r["next_action"], "next")

    # ---------- harness ----------

    def test_prompts_and_checks_come_from_content_test_prompts(self):
        self.assertEqual(Path(tp.__file__).resolve(), (db.ROOT / "content" / "test_prompts.py").resolve())
        for kind in ("story", "words", "summary"):
            self.assertIn(kind, tp.TEMPLATES)
        self.assertEqual(jobs.model_name(), os.environ.get("OLLAMA_MODEL", "gemma4:e4b"))

    # ---------- groups ----------

    def test_groups_keep_interests_and_reject_unknown_ones(self):
        group, _ = self.make_session()
        self.assertEqual(group["learners"][0]["interests"], ["int_food", "int_toys"])
        r = self.client.post("/api/groups", json={"tutor_name": "T", "learners": [
            {"name": "X", "picture": "p", "profile": "low_emergent", "interests": ["int_nope"]}]})
        self.assertEqual(r.status_code, 422)
        too_many = [i.id for i in CONTENT.data.interests][:4]
        r = self.client.post("/api/groups", json={"tutor_name": "T", "learners": [
            {"name": "X", "picture": "p", "profile": "low_emergent", "interests": too_many}]})
        self.assertEqual(r.status_code, 422)
        # interests is optional
        r = self.client.post("/api/groups", json={"tutor_name": "T", "learners": [
            {"name": "X", "picture": "p", "profile": "low_emergent"}]})
        self.assertEqual(r.json()["learners"][0]["interests"], [])

    # ---------- queueing, never inside a turn ----------

    def end_session(self, session):
        """The summary phase: the summary, then each learner's story for the next session, get queued."""
        self.client.post(f"/api/sessions/{session['id']}/phase", json={"phase": "summary"})

    def test_session_queues_words_stories_come_at_the_end_and_turns_queue_nothing(self):
        _, session = self.make_session()
        kinds = sorted(j.kind for j in worker.pending() if j.kind != "story_audio")
        self.assertEqual(kinds, ["words", "words"])
        # Filled template stories get their audio in the background too.
        self.assertEqual({j.story_id for j in worker.pending() if j.kind == "story_audio"},
                         {i for i in session["story_ids"].values() if i.startswith("ts_")})
        before = len(worker.pending())
        self.play(session["id"], 2)
        self.assertEqual(len(worker.pending()), before)
        self.assertEqual(self.fake.calls, [])   # no model call during /next or /answer
        self.end_session(session)
        self.assertEqual([j.kind for j in worker.pending()][-2:], ["story", "story"])

    # ---------- stories ----------

    def test_story_goes_to_approvals_and_is_served_once_approved(self):
        group, session = self.make_session()
        self.end_session(session)
        worker.run_pending()
        approvals = self.client.get("/api/approvals").json()
        ana = group["learners"][0]["id"]
        story = next(a for a in approvals if a["kind"] == "story" and a["child_id"] == ana)
        p = story["payload"]
        for key in ("id", "title", "level", "skill_ids", "interests", "paragraphs", "questions", "source"):
            self.assertIn(key, p)
        self.assertEqual((p["source"], p["approved_by_tutor"], p["interests"]), ("model", False, ["int_food", "int_toys"]))
        self.assertEqual(self.client.get(f"/api/stories/{p['id']}").status_code, 404)   # not approved yet
        # Its audio was made before it reached the tutor.
        self.assertEqual(self.client.get(f"/api/audio/{p['id']}.wav").status_code, 200)

        self.assertEqual(self.client.post(f"/api/approvals/{story['id']}", json={"approve": True}).json(), {"ok": True})
        got = self.client.get(f"/api/stories/{p['id']}").json()
        self.assertEqual((got["title"], got["paragraphs"]), (p["title"], p["paragraphs"]))
        self.assertEqual((got["words"][1]["start_ms"], got["words"][1]["end_ms"]), (100, 180))   # real timings
        self.assertNotIn(story["id"], [a["id"] for a in self.client.get("/api/approvals").json()])

    def test_failed_check_is_retried_once_then_falls_back(self):
        self.fake.bad = 1                          # first output broken, retry passes
        group, _ = self.make_session()
        ana = group["learners"][0]["id"]
        jobs.run(jobs.Job("story", child_id=ana))
        self.assertEqual(self.fake.calls, ["story", "story"])
        self.assertEqual(len(self.rows("SELECT * FROM generated_items WHERE kind='story' AND child_id=?", ana)), 1)

        self.fake.calls.clear()
        self.fake.bad = 2                          # both broken: nothing saved, the library stories stay
        jobs.run(jobs.Job("story", child_id=group["learners"][1]["id"]))
        self.assertEqual(self.fake.calls, ["story", "story"])
        self.assertEqual(self.rows("SELECT * FROM generated_items WHERE kind='story' AND child_id=?",
                                   group["learners"][1]["id"]), [])

    def test_an_unreachable_model_is_not_retried(self):
        def off(*args):
            self.fake.calls.append("story")
            raise client.ModelError("Ollama at http://localhost:11434: refused")
        jobs.ask_model = off
        group, _ = self.make_session()
        jobs.run(jobs.Job("story", child_id=group["learners"][0]["id"]))
        self.assertEqual(self.fake.calls, ["story"])          # the retry is for failed checks only

    def test_no_story_without_a_usable_interest(self):
        group, _ = self.make_session(interests=["int_animals"])   # int_animals has no objects yet
        jobs.run(jobs.Job("story", child_id=group["learners"][0]["id"]))
        self.assertEqual(self.fake.calls, [])

    def test_a_learner_waiting_for_approval_gets_no_second_story(self):
        group, _ = self.make_session()
        ana = group["learners"][0]["id"]
        jobs.run(jobs.Job("story", child_id=ana))
        jobs.run(jobs.Job("story", child_id=ana))
        self.assertEqual(self.fake.calls, ["story"])

    # ---------- practice words ----------

    def test_approved_words_go_on_the_practice_sheet(self):
        group, _ = self.make_session()
        ana = group["learners"][0]["id"]
        jobs.run(jobs.Job("words", child_id=ana))
        item = next(a for a in self.client.get("/api/approvals").json() if a["kind"] == "words" and a["child_id"] == ana)
        chosen = [w["text"] for w in item["payload"]["words"]]
        self.client.post(f"/api/approvals/{item['id']}", json={"approve": True})
        sheet = self.client.get(f"/api/children/{ana}/sheet").json()
        self.assertEqual([w["text"] for w in sheet["words"]], chosen[:CONTENT.rules.practice_sheet.words])
        by_text = {w.text: w for w in CONTENT.data.words}
        self.assertEqual(sheet["words"][0]["syllables"], by_text[chosen[0]].syllables)

    # ---------- summary ----------

    def test_summary_phase_queues_the_model_summary_and_summary_uses_it(self):
        _, session = self.make_session()
        sid = session["id"]
        self.play(sid, 4)
        worker.clear()
        template = self.client.get(f"/api/sessions/{sid}/summary").json()
        self.client.post(f"/api/sessions/{sid}/phase", json={"phase": "summary"})
        self.assertIn("summary", [j.kind for j in worker.pending()])
        worker.run_pending()
        got = self.client.get(f"/api/sessions/{sid}/summary").json()
        self.assertNotEqual(got, template)
        self.assertEqual({x["child_id"] for x in got["learners"]}, {x["child_id"] for x in template["learners"]})
        for x in got["learners"]:
            self.assertIn(x["next_focus_skill"], CONTENT.skills_by_id)
            self.assertIn(x["next_method"], CONTENT.rules.methods)

        # A newer answer makes the model summary out of date: the template comes back, and a new one is queued.
        self.play(sid, 1)
        worker.clear()
        again = self.client.get(f"/api/sessions/{sid}/summary").json()
        self.assertTrue(again["learners"][0]["summary"].startswith("Ana: "))   # the code template
        self.assertNotEqual(again, got)
        self.assertIn("summary", [j.kind for j in worker.pending()])

    def test_summary_input_has_the_real_numbers(self):
        _, session = self.make_session()
        self.play(session["id"], 4)
        with db.connect() as conn:
            v = summary.prompt_values(summary.compute(conn, CONTENT, session["id"]), CONTENT)
        stats = v["_stats"]
        self.assertEqual(sum(s["total"] for s in stats.values()), 4)
        for child_id, s in stats.items():
            self.assertIn(f"{child_id} | ", v["learner_data"])
            self.assertIn(f"{s['correct']} of {s['total']} correct", v["learner_data"])
        _, unfilled = tp.fill(tp.TEMPLATES["summary"], {k: x for k, x in v.items() if not k.startswith("_")})
        self.assertEqual(unfilled, [])


    # ---------- audio before approval ----------

    def test_a_story_without_audio_never_reaches_the_tutor(self):
        self.speaker.broken = True
        group, _ = self.make_session()
        jobs.run(jobs.Job("story", child_id=group["learners"][0]["id"]))
        self.assertEqual(self.fake.calls, ["story"])
        self.assertEqual([a for a in self.approvals_for(group) if a["kind"] == "story"], [])

    # ---------- Ollama off ----------

    def test_nothing_breaks_when_ollama_is_off(self):
        jobs.ask_model = self._saved[0]                   # the real client...
        real_url = client.BASE_URL
        client.BASE_URL = "http://127.0.0.1:9"            # ...with nothing listening
        try:
            group, session = self.make_session()
            self.play(session["id"], 4)
            worker.run_pending()                          # story and words jobs fail quietly
            self.client.post(f"/api/sessions/{session['id']}/phase", json={"phase": "summary"})
            worker.run_pending()                          # summary job fails quietly
            self.assertEqual(self.approvals_for(group), [])
            got = self.client.get(f"/api/sessions/{session['id']}/summary").json()
            self.assertTrue(got["learners"][0]["summary"].startswith("Ana: "))      # the template
            for story_id in session["story_ids"].values():                          # template stories
                self.assertEqual(self.client.get(f"/api/stories/{story_id}").status_code, 200)
            sheet = self.client.get(f"/api/children/{group['learners'][0]['id']}/sheet")
            self.assertEqual(sheet.status_code, 200)
        finally:
            client.BASE_URL = real_url
            client._down_until = 0.0

    # ---------- which story each learner reads ----------

    def test_story_fallback_order_model_then_template_then_library(self):
        group, first = self.make_session()
        ana, ben = (c["id"] for c in group["learners"])
        # No approved model story yet: a filled template at the learner's level.
        tpl = self.client.get(f"/api/stories/{first['story_ids'][ana]}").json()
        self.assertIn("Ana", " ".join(tpl["paragraphs"]))
        self.assertNotIn("{", tpl["title"] + " ".join(tpl["paragraphs"]))

        self.end_session(first)
        worker.run_pending()
        item = next(a for a in self.client.get("/api/approvals").json()
                    if a["kind"] == "story" and a["child_id"] == ana)
        self.client.post(f"/api/approvals/{item['id']}", json={"approve": True})
        _, second = self.make_session(group=group)
        self.assertEqual(second["story_ids"][ana], item["payload"]["id"])      # the approved model story
        self.assertNotEqual(second["story_ids"][ben], item["payload"]["id"])   # never another learner's

        _, third = self.make_session(group=group)
        self.assertNotEqual(third["story_ids"][ana], item["payload"]["id"])    # a model story is read once

    def test_learner_without_interest_objects_gets_a_library_story_at_their_level(self):
        group, session = self.make_session(interests=["int_animals"])
        story_id = session["story_ids"][group["learners"][0]["id"]]
        self.assertIn(story_id, CONTENT.stories_by_id)
        self.assertEqual(CONTENT.stories_by_id[story_id].level, 1)

    def test_templates_are_not_repeated_within_two_sessions(self):
        group, s1 = self.make_session()
        ana = group["learners"][0]["id"]
        s2 = self.make_session(group=group)[1]
        templates = [json.loads(self.rows("SELECT payload FROM generated_items WHERE id = ?",
                                          s["story_ids"][ana])[0]["payload"])["template_id"] for s in (s1, s2)]
        self.assertEqual(len(set(templates)), 2)

    # ---------- alert ----------

    def test_alert_when_a_skill_stays_low_after_ten_attempts(self):
        group, session = self.make_session()
        ana = group["learners"][0]["id"]
        self.play(session["id"], 2)
        with db.connect() as conn:
            conn.execute("UPDATE skill_state SET score = 0.4, attempts = 12 WHERE child_id = ?", (ana,))
            stats = summary.compute(conn, CONTENT, session["id"])
        self.assertTrue(next(s for s in stats if s.child_id == ana).alert)
        self.assertIn("alert: yes", summary.prompt_values(stats, CONTENT)["learner_data"].splitlines()[0])
        got = self.client.get(f"/api/sessions/{session['id']}/summary").json()
        self.assertIn("Alert", got["learners"][0]["summary"])
        self.assertNotIn("Alert", got["learners"][1]["summary"])

    def test_summary_template_uses_skill_names_not_ids(self):
        _, session = self.make_session()
        self.play(session["id"], 2)
        got = self.client.get(f"/api/sessions/{session['id']}/summary").json()
        for x in got["learners"]:
            self.assertIn(CONTENT.skills_by_id[x["next_focus_skill"]].name_en, x["summary"])
            self.assertNotIn("sk_", x["summary"])


if __name__ == "__main__":
    unittest.main()
