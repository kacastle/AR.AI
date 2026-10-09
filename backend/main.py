import json
from typing import Optional
import os
import random
import re
from contextlib import asynccontextmanager
from dataclasses import asdict, replace
from datetime import date, datetime, timedelta
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend import adapt, db
from backend.content import Content, Word, format_problems, load_content
from backend.engine import review, rotation, scoring
from backend.engine.feedback import feedback_for, mistake_code
from backend.engine.selector import build_pick, choose_item, pick_next, skill_items, weakest_unlocked_skill
from backend.engine.state import SkillState, new_state
from backend.llm.jobs import Job
from backend.llm.worker import worker
from backend import summary
from backend.llm.fallbacks import choose_story
from backend.records import event_count, learner_info, load_states
from backend.schemas import (
    AnswerIn, ApprovalIn, ApprovalItem, Feedback, Group, GroupIn, Hint, Item, Learner,
    LearnerSummary, LoginIn, NextTurn, OkOut, PhaseIn, PhaseOut, ProfileOut, QuizResult, Result, Session,
    SessionIn, SheetOut, SheetWord, StoryAnswerIn, StoryAnswerOut, StoryOut, StoryQuestion, StoryTurn,
    StoryTurnQuestion, StoryWord, SummaryOut,
)
from backend.tts import audio as tts_audio

AUDIO_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
DEMO_FAST = os.environ.get("DEMO_FAST") == "1"

content: Content


@asynccontextmanager
async def lifespan(app: FastAPI):
    global content
    content = load_content()
    if content.problems:
        print(f"Content loaded with {len(content.problems)} problem(s):")
        print(format_problems(content.problems))
    db.init_db()
    worker.start()
    yield
    worker.stop()


app = FastAPI(title="ReadingTutor PH", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------- helpers ----------

def get_row(conn, table: str, row_id: str):
    row = conn.execute(f"SELECT * FROM {table} WHERE id = ?", (row_id,)).fetchone()
    if row is None:
        raise HTTPException(404, f"{table} '{row_id}' not found")
    return row


def save_state(conn, child_id: str, s: SkillState) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO skill_state (child_id, skill_id, score, attempts, correct_streak, wrong_streak, "
        "support_level, review_step, next_review_at, mastered_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (child_id, s.skill_id, s.score, s.attempts, s.correct_streak, s.wrong_streak, s.support_level,
         s.review_step, s.next_review_at and s.next_review_at.isoformat(),
         s.mastered_at and s.mastered_at.isoformat()))


def first_try_results(conn, child_id: str) -> list[bool]:
    """The learner's items, oldest first: True = right on the first attempt."""
    rows = conn.execute("SELECT correct FROM events WHERE child_id = ? AND attempt = 1 ORDER BY id", (child_id,))
    return [bool(r["correct"]) for r in rows]


def used_items(conn, session_id: str, child_id: str) -> list[str]:
    """Items this learner saw in this session and in the last N sessions (rules.selection), oldest first."""
    n = content.rules.selection.avoid_items_seen_in_last_sessions
    sessions = [r["session_id"] for r in conn.execute(
        "SELECT session_id FROM events WHERE child_id = ? AND session_id != ? "
        "GROUP BY session_id ORDER BY MAX(id) DESC LIMIT ?", (child_id, session_id, n))]
    sessions.append(session_id)
    marks = ",".join("?" * len(sessions))
    rows = conn.execute(f"SELECT item_id FROM events WHERE child_id = ? AND session_id IN ({marks}) "
                        "GROUP BY item_id ORDER BY MAX(id)", (child_id, *sessions))
    return [r["item_id"] for r in rows]


def interest_words(child) -> list[str]:
    """Word texts from the learner's interests (content.json interests[].words): tile items prefer them."""
    mine = set(json.loads(child["interests"]))
    return [w for i in content.data.interests if i.id in mine for w in i.words]


def pick_for(conn, session_id: str, child) -> dict:
    """The learner's next turn: a diagnostic item first (rules.json placement), else practice with a running
    re-teach method, an easy item after wrong or slow answers, or the normal choice. Returns the stored turn."""
    rules = content.rules
    child_id = child["id"]
    used = used_items(conn, session_id, child_id)
    prefer = interest_words(child)
    skill_id = adapt.placement_skill(conn, content, child)
    if skill_id is not None:
        skill = next(sk for sk in content.data.skills if sk.id == skill_id)
        state = replace(new_state(skill.id, rules), support_level="alone")     # no help: see what the child knows
        item = choose_item(skill_items(content, skill), used, "easy", prefer)
        pick = build_pick(content, skill, state, item, "easy", False, False, random.Random())
        return {**asdict(pick), "mode": "placement", "method": None}
    results = first_try_results(conn, child_id)
    run = adapt.active_method(conn, child_id)
    easy = rotation.needs_easy_item(results, rules) or adapt.last_was_slow(conn, child_id, rules)
    pick = pick_next(content, load_states(conn, child_id), date.today(), used, results, easy=easy and run is None,
                     prefer=prefer, method=adapt.method_for_pick(rules, run))
    mode = "reteach" if run is not None else "easy" if pick.is_easy else "practice"
    return {**asdict(pick), "mode": mode, "method": run["method"] if run is not None else None}


def group_out(conn, group_id: str) -> Group:
    g = get_row(conn, "groups", group_id)
    kids = conn.execute("SELECT * FROM children WHERE group_id = ? ORDER BY rowid", (group_id,))
    return Group(id=g["id"], tutor_name=g["tutor_name"],
                 learners=[Learner(id=k["id"], name=k["name"], picture=k["picture"], profile=k["profile"],
                                   interests=json.loads(k["interests"])) for k in kids])


def session_out(s) -> Session:
    return Session(id=s["id"], group_id=s["group_id"], present=json.loads(s["present"]),
                   phase=s["phase"], read_along_story_id=s["read_along_story_id"],
                   story_ids=json.loads(s["story_ids"]))


# ---------- endpoints ----------

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/tutor/login", response_model=OkOut)
def login(body: LoginIn):
    # Demo stub: one tutor, one laptop. Any PIN is accepted.
    return OkOut(ok=True)


@app.post("/api/groups", response_model=Group)
def create_group(body: GroupIn):
    profiles = content.rules.placement.profiles
    known = {i.id for i in content.data.interests}
    most = content.rules.personalization["max_interests_per_learner"]
    for learner in body.learners:
        if learner.profile not in profiles:
            raise HTTPException(422, f"profile must be one of {profiles}")
        unknown = [i for i in learner.interests if i not in known]
        if unknown or len(learner.interests) > most:
            raise HTTPException(422, f"interests: up to {most} ids from content.json interests (unknown: {unknown})")
    with db.connect() as conn:
        group_id = db.new_id("g")
        conn.execute("INSERT INTO groups (id, tutor_name) VALUES (?, ?)", (group_id, body.tutor_name))
        for learner in body.learners:
            conn.execute("INSERT INTO children (id, group_id, name, picture, profile, interests, placement) "
                         "VALUES (?, ?, ?, ?, ?, ?, ?)", (db.new_id("c"), group_id, learner.name, learner.picture,
                                                          learner.profile, json.dumps(learner.interests),
                                                          "pending" if learner.diagnostic else None))
        return group_out(conn, group_id)


@app.get("/api/groups/{group_id}", response_model=Group)
def get_group(group_id: str):
    with db.connect() as conn:
        return group_out(conn, group_id)


@app.post("/api/sessions", response_model=Session)
def create_session(body: SessionIn):
    if not body.present:
        raise HTTPException(422, "present must list at least one child id")
    with db.connect() as conn:
        get_row(conn, "groups", body.group_id)
        kids = {r["id"] for r in conn.execute("SELECT id FROM children WHERE group_id = ?", (body.group_id,))}
        missing = [c for c in body.present if c not in kids]
        if missing:
            raise HTTPException(422, f"not in this group: {missing}")
        level = min(content.data.levels)
        story = next(s for s in content.data.stories if s.level == level)
        session_id = db.new_id("s")
        # Each learner's story turn: approved model story -> filled template -> library story (no model).
        rnd = random.Random()
        story_ids = {child_id: choose_story(conn, content, child_id, rnd) for child_id in body.present}
        conn.execute("INSERT INTO sessions (id, group_id, present, phase, read_along_story_id, story_ids) "
                     "VALUES (?, ?, ?, ?, ?, ?)", (session_id, body.group_id, json.dumps(body.present), "tiles",
                                                   story.id, json.dumps(story_ids)))
        out = session_out(get_row(conn, "sessions", session_id))
    # Background work: audio for filled templates now, practice words for the sheet. Personal stories for
    # the next session are written at the end of this one (prompts.md section 0), after the summary.
    for story_id in story_ids.values():
        if story_id.startswith("ts_"):
            worker.submit(Job("story_audio", story_id=story_id))
    for child_id in body.present:
        worker.submit(Job("words", child_id=child_id))
    return out


@app.get("/api/stories/{story_id}", response_model=StoryOut)
def get_story(story_id: str):
    story = content.stories_by_id.get(story_id) or generated_story(story_id)
    if story is None:
        raise HTTPException(404, f"story '{story_id}' not found")
    saved = tts_audio.load_timings(story.id)
    if saved is not None:
        words = [StoryWord(**w) for w in saved]
    else:
        # Estimated timings until scripts/pregen_audio.py writes real ones.
        words, t = [], 0
        for text in tts_audio.story_words(story):
            length = 150 + 80 * len(text)
            words.append(StoryWord(text=text, start_ms=t, end_ms=t + length))
            t += length + 150
    return StoryOut(title=story.title, paragraphs=story.paragraphs, words=words,
                    audio_url=f"/api/audio/{story.id}.wav",
                    questions=[StoryQuestion(type=q["type"], prompt=q["prompt"], choices=q["choices"])
                               for q in story_questions(story)])


def story_questions(story) -> list[dict]:
    """A story's questions as dicts (content.json stories hold models, generated stories hold dicts)."""
    return [q if isinstance(q, dict) else q.model_dump() for q in (getattr(story, "questions", None) or [])]


def _quiz_story(conn, session_row, child_id: str):
    story_id = json.loads(session_row["story_ids"]).get(child_id)
    story = (content.stories_by_id.get(story_id) or generated_story(story_id)) if story_id else None
    return story_id, (story_questions(story) if story else [])


def _question_done(conn, session_id: str, child_id: str, story_id: str, index: int) -> bool:
    """A question ends when it is answered right, or after its second wrong answer (the answer is shown)."""
    rows = conn.execute("SELECT correct FROM story_answers WHERE session_id = ? AND child_id = ? AND story_id = ? "
                        "AND question_index = ?", (session_id, child_id, story_id, index)).fetchall()
    return any(r["correct"] for r in rows) or len(rows) >= 2


@app.get("/api/sessions/{session_id}/story_turn", response_model=Optional[StoryTurn])
def story_turn(session_id: str):
    """The story phase, learner by learner: each learner answers the questions of their own story
    (session story_ids), in turn order. null when every learner is done."""
    with db.connect() as conn:
        s = get_row(conn, "sessions", session_id)
        for child_id in json.loads(s["present"]):
            story_id, questions = _quiz_story(conn, s, child_id)
            for index, q in enumerate(questions):
                if not _question_done(conn, session_id, child_id, story_id, index):
                    child = get_row(conn, "children", child_id)
                    return StoryTurn(
                        child_id=child_id, child_name=child["name"], story_id=story_id,
                        turn_number=index + 1, questions_total=len(questions),
                        question=StoryTurnQuestion(id=f"{story_id}:{index}", type=q["type"], prompt=q["prompt"],
                                                   choices=q["choices"], prompt_audio=None))
    return None


@app.post("/api/sessions/{session_id}/story_answer", response_model=StoryAnswerOut)
def story_answer(session_id: str, body: StoryAnswerIn):
    """One answer in a learner's story quiz. The first answer to each question counts: it scores the question's
    comprehension skill, and when every question has one, the next story's level moves (rules.json story_quiz)
    and that story is written right away in the background. A second wrong answer shows the right choice."""
    rules = content.rules
    quiz_rules = rules.story_quiz
    story_id, _, index_text = body.question_id.rpartition(":")
    with db.connect() as conn:
        s = get_row(conn, "sessions", session_id)
        own_story, questions = _quiz_story(conn, s, body.child_id)
        if story_id != own_story or not index_text.isdigit() or int(index_text) >= len(questions):
            raise HTTPException(422, "question_id is not a question of this learner's story in this session")
        index = int(index_text)
        if _question_done(conn, session_id, body.child_id, story_id, index):
            raise HTTPException(409, "this question is already done; call /story_turn")
        child = get_row(conn, "children", body.child_id)
        q = questions[index]
        correct = body.choice == q["answer"]
        key = (session_id, body.child_id, story_id)
        first = conn.execute("SELECT 1 FROM story_answers WHERE session_id = ? AND child_id = ? AND story_id = ? "
                             "AND question_index = ?", (*key, index)).fetchone() is None
        conn.execute("INSERT INTO story_answers (session_id, child_id, story_id, question_index, question_type, "
                     "choice, correct, first) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                     (*key, index, q["type"], body.choice, int(correct), int(first)))
        code = None if correct else quiz_rules["mistake_by_type"].get(q["type"])
        feedback = feedback_for(rules, "CORRECT" if correct else code, name=child["name"], syllables=[], slots=0,
                                turn=index)
        done = correct or not first
        quiz = None
        if first:
            skill_id = quiz_rules["skill_by_type"].get(q["type"])
            if skill_id:
                state = load_states(conn, child["id"]).get(skill_id) or new_state(skill_id, rules)
                result = scoring.item_result(rules, "alone", 1, correct)
                save_state(conn, child["id"], scoring.apply_item(rules, state, result, correct, date.today()))
            firsts = conn.execute("SELECT correct FROM story_answers WHERE session_id = ? AND child_id = ? "
                                  "AND story_id = ? AND first = 1", key).fetchall()
            if len(firsts) == len(questions):
                right = sum(r["correct"] for r in firsts)
                before = learner_info(conn, content, child["id"])["level"]
                levels = sorted(int(k) for k in rules.story_levels)
                step = (1 if right >= quiz_rules["harder_at_correct"]
                        else -1 if right <= quiz_rules["easier_at_most_correct"] else 0)
                after = min(max(before + step, levels[0]), levels[-1])
                conn.execute("UPDATE children SET story_level = ? WHERE id = ?", (after, child["id"]))
                quiz = QuizResult(correct=right, total=len(questions), story_level_before=before, story_level=after)
    if quiz:
        worker.submit(Job("story", child_id=body.child_id))     # the adapted story, written right after the quiz
    return StoryAnswerOut(correct=correct, mistake_type=code, feedback=feedback,
                          next_action="next" if done else "retry",
                          answer=q["answer"] if done and not correct else None, quiz=quiz)


@app.get("/api/children/{child_id}/profile", response_model=ProfileOut)
def child_profile(child_id: str):
    """The learner profile for the tutor and parents: skills, level, pace, interests, methods that worked."""
    with db.connect() as conn:
        get_row(conn, "children", child_id)
        return ProfileOut(**adapt.profile(conn, content, child_id))


@app.post("/api/sessions/{session_id}/phase", response_model=PhaseOut)
def set_phase(session_id: str, body: PhaseIn):
    s = content.rules.session
    minutes = s.demo_fast.phase_minutes if DEMO_FAST else {
        "tiles": s.tile_turn_minutes, "stories": s.story_turn_minutes, "summary": s.summary_minutes,
    }[body.phase]
    ends_at = (datetime.now().astimezone() + timedelta(minutes=minutes)).isoformat(timespec="seconds")
    with db.connect() as conn:
        present = json.loads(get_row(conn, "sessions", session_id)["present"])
        conn.execute("UPDATE sessions SET phase = ?, phase_ends_at = ? WHERE id = ?",
                     (body.phase, ends_at, session_id))
    if body.phase == "summary":
        # The summary first; then each learner's personal story for the next session (end of session).
        worker.submit(Job("summary", session_id=session_id))
        for child_id in present:
            worker.submit(Job("story", child_id=child_id))
    return PhaseOut(phase=body.phase, ends_at=ends_at)


@app.get("/api/sessions/{session_id}/next", response_model=NextTurn)
def next_turn(session_id: str):
    rules = content.rules
    with db.connect() as conn:
        s = get_row(conn, "sessions", session_id)
        if s["current_turn"] is None:
            group_order = [r["id"] for r in conn.execute(
                "SELECT id FROM children WHERE group_id = ? ORDER BY rowid", (s["group_id"],))]
            order = rotation.turn_order(group_order, json.loads(s["present"]), rules)
            child_id = rotation.child_for_turn(order, s["turn_number"])
            pick = pick_for(conn, session_id, get_row(conn, "children", child_id))
            conn.execute("UPDATE sessions SET current_child_id = ?, current_item_id = ?, current_turn = ? WHERE id = ?",
                         (child_id, pick["item_id"], json.dumps(pick), session_id))
            s = get_row(conn, "sessions", session_id)
        child = get_row(conn, "children", s["current_child_id"])
        stars, streak = adapt.stars(conn, child["id"]), adapt.streak(conn, child["id"])
    turn = json.loads(s["current_turn"])
    method = turn.get("method")

    return NextTurn(
        child_id=child["id"],
        child_name=child["name"],
        turn_number=s["turn_number"],
        task_type=turn["task_type"],
        item=Item(id=turn["item_id"], prompt_audio=f"/api/audio/{turn['item_id']}.wav", slots=len(turn["answer"]),
                  tiles=turn["tiles"], syllables=turn["syllables"]),
        support_level=turn["support_level"],
        prefill=turn["prefill"],
        gap_slot=turn.get("gap_slot"),   # turns stored before this field have none
        seconds=rules.session.demo_fast.item_seconds if DEMO_FAST else rules.timing.item_seconds,
        mode=turn.get("mode", "practice"),
        method=method,
        method_note=rules.methods[method].description_en if method else None,
        stars=stars,
        streak=streak,
    )


@app.post("/api/sessions/{session_id}/answer", response_model=Result)
def answer(session_id: str, body: AnswerIn):
    rules = content.rules
    with db.connect() as conn:
        s = get_row(conn, "sessions", session_id)
        if s["current_item_id"] != body.item_id or s["current_child_id"] != body.child_id:
            raise HTTPException(409, "this is not the current turn; call /next first")
        child = get_row(conn, "children", body.child_id)
        turn = json.loads(s["current_turn"])
        item_id = turn["item_id"]
        expected = turn["answer"]
        correct = body.given == expected
        mistake = mistake_code(turn["task_type"], expected, body.given)
        ladder = rules.hints.ladder
        hint = None
        answer_tiles = None

        def text(code: str, rotate: int = 0, with_hint: bool = True) -> Feedback:
            return feedback_for(rules, code, name=child["name"], syllables=turn["syllables"],
                                slots=len(expected), turn=rotate, with_hint=with_hint)

        placement = turn.get("mode") == "placement"
        # Correction steps: hints from the ladder, then show the answer, then the rebuild ends the item.
        # A diagnostic item has one try only: encouragement, no hints, then the next item.
        if placement:
            next_action = "next"
            feedback = text("CORRECT") if correct else text("SLOW", with_hint=False)
        elif correct:
            next_action = "next"
            n_correct = conn.execute("SELECT COUNT(*) FROM events WHERE child_id = ? AND correct = 1",
                                     (child["id"],)).fetchone()[0]
            feedback = text("CORRECT", rotate=n_correct)
        elif body.attempt <= len(ladder):
            next_action = "retry"
            kind = ladder[body.attempt - 1]
            diff = next((i for i, t in enumerate(expected) if i >= len(body.given) or body.given[i] != t),
                        len(expected) - 1)
            hint = Hint(
                kind=kind,
                audio=f"/api/audio/{item_id}_slow.wav" if kind == "replay_by_syllable" else None,
                highlight_slot={"highlight_slot": diff, "first_tile": 0}.get(kind),
            )
            feedback = text(mistake, rotate=body.attempt - 1)
        elif body.attempt == len(ladder) + 1:
            next_action = "show_answer"
            feedback = text("SHOW_ANSWER")
            answer_tiles = list(expected)
        else:
            # Wrong rebuild after the answer was shown: move on, no hint.
            next_action = "next"
            feedback = text(mistake, with_hint=False)

        conn.execute(
            "INSERT INTO events (session_id, turn_number, child_id, item_id, task_type, skill_id, given, correct, "
            "mistake_type, hints_used, attempt, time_ms, support_level, next_action, placement) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, s["turn_number"], child["id"], item_id, turn["task_type"], turn["skill_id"],
             json.dumps(body.given), int(correct), mistake, body.hints_used, body.attempt, body.time_ms,
             turn["support_level"], next_action, int(placement)))
        method_started = None
        if placement:
            adapt.finish_placement(conn, content, child["id"], date.today(), save_state)
            conn.execute(
                "UPDATE sessions SET turn_number = turn_number + 1, current_child_id = NULL, current_item_id = NULL, "
                "current_turn = NULL WHERE id = ?", (session_id,))
        elif next_action == "next":
            # The item has ended: update the skill once.
            today = date.today()
            first_try = body.attempt == 1 and correct
            state = load_states(conn, child["id"]).get(turn["skill_id"]) or new_state(turn["skill_id"], rules)
            result = scoring.item_result(rules, turn["support_level"], body.attempt, correct=correct)
            state = scoring.apply_item(rules, state, result, first_try, today)
            if turn["is_review"]:
                state = review.apply_review(state, first_try, rules, today)
            save_state(conn, child["id"], state)
            method_started = adapt.after_item(conn, rules, child["id"], turn["skill_id"], first_try)
            conn.execute(
                "UPDATE sessions SET turn_number = turn_number + 1, current_child_id = NULL, current_item_id = NULL, "
                "current_turn = NULL WHERE id = ?", (session_id,))
        stars, streak = adapt.stars(conn, child["id"]), adapt.streak(conn, child["id"])

    return Result(correct=correct, mistake_type=mistake, feedback=feedback, hint=hint,
                  next_action=next_action, answer=answer_tiles, stars=stars, streak=streak,
                  method_started=method_started)


@app.get("/api/sessions/{session_id}/summary", response_model=SummaryOut)
def get_summary(session_id: str):
    with db.connect() as conn:
        s = get_row(conn, "sessions", session_id)
        stats = summary.compute(conn, content, session_id)
        events = event_count(conn, session_id)
        model = summary.current(conn, session_id, stats, events)
    if model is not None:
        return model
    if s["phase"] == "summary" and events:
        worker.submit(Job("summary", session_id=session_id))   # ready on a later call; never waited for
    return summary.template(stats, content)


@app.get("/api/children/{child_id}/sheet", response_model=SheetOut)
def sheet(child_id: str):
    ps = content.rules.practice_sheet
    with db.connect() as conn:
        child = get_row(conn, "children", child_id)
        skill = weakest_unlocked_skill(content, load_states(conn, child_id), words_only=True)
        approved = conn.execute(
            "SELECT g.payload FROM generated_items g JOIN approvals a ON a.generated_item_id = g.id "
            "WHERE g.kind = 'words' AND g.child_id = ? AND a.status = 'approved' "
            "ORDER BY a.decided_at DESC, g.created_at DESC LIMIT 1", (child_id,)).fetchone()
    words = [i for i in skill_items(content, skill) if isinstance(i, Word)][:ps.words]
    if approved:
        chosen = json.loads(approved["payload"])
        # Practice words the tutor approved, while the learner is still on that skill.
        picked = [content.words_by_id[w["word_id"]] for w in chosen["words"] if w["word_id"] in content.words_by_id]
        if chosen.get("skill_id") == skill.id and picked:
            words = picked[:ps.words]
    sentence = next((sn for sn in content.sentences if sn.level == skill.level), content.sentences[0])
    return SheetOut(name=child["name"], date=date.today().isoformat(),
                    words=[SheetWord(text=w.text, syllables=w.syllables) for w in words],
                    sentence=sentence.text, home_line_fil=ps.home_line_fil)


@app.get("/api/approvals", response_model=list[ApprovalItem])
def list_approvals():
    with db.connect() as conn:
        rows = conn.execute(
            "SELECT a.id, g.kind, g.child_id, g.payload FROM approvals a "
            "JOIN generated_items g ON g.id = a.generated_item_id WHERE a.status = 'pending' ORDER BY g.created_at")
        return [ApprovalItem(id=r["id"], kind=r["kind"], child_id=r["child_id"], payload=json.loads(r["payload"]))
                for r in rows]


@app.post("/api/approvals/{approval_id}", response_model=OkOut)
def decide_approval(approval_id: str, body: ApprovalIn):
    with db.connect() as conn:
        approval = get_row(conn, "approvals", approval_id)
        conn.execute("UPDATE approvals SET status = ?, decided_at = datetime('now') WHERE id = ?",
                     ("approved" if body.approve else "rejected", approval_id))
        item = get_row(conn, "generated_items", approval["generated_item_id"])
        payload = json.loads(item["payload"])
        if "approved_by_tutor" in payload:
            payload["approved_by_tutor"] = body.approve
            conn.execute("UPDATE generated_items SET payload = ? WHERE id = ?",
                         (json.dumps(payload, ensure_ascii=False), item["id"]))
    return OkOut(ok=True)


def generated_story(story_id: str):
    """A filled template story, or a model story the tutor approved, shaped like a content.json story.
    None for anything else: a model story stays hidden from learners until it is approved."""
    with db.connect() as conn:
        row = conn.execute(
            "SELECT g.payload FROM generated_items g LEFT JOIN approvals a ON a.generated_item_id = g.id "
            "WHERE g.id = ? AND (g.kind = 'template_story' OR (g.kind = 'story' AND a.status = 'approved'))",
            (story_id,)).fetchone()
    return SimpleNamespace(**json.loads(row["payload"])) if row else None


@app.get("/api/audio/{key}.wav")
def audio(key: str):
    if not AUDIO_KEY.match(key):
        raise HTTPException(400, "bad audio key")
    path = tts_audio.wav_path(key)
    if not path.is_file():
        raise HTTPException(404, f"audio '{key}' not generated yet")
    return FileResponse(path, media_type="audio/wav")
