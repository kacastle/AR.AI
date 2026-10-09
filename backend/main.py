import json
import os
import re
from collections import Counter
from contextlib import asynccontextmanager
from dataclasses import asdict
from datetime import date, datetime, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend import db
from backend.content import Content, Word, format_problems, load_content
from backend.engine import review, rotation, scoring
from backend.engine.feedback import feedback_for, mistake_code
from backend.engine.selector import pick_next, skill_items, weakest_unlocked_skill
from backend.engine.state import SkillState, new_state
from backend.schemas import (
    AnswerIn, ApprovalIn, ApprovalItem, Feedback, Group, GroupIn, Hint, Item, Learner,
    LearnerSummary, LoginIn, NextTurn, OkOut, PhaseIn, PhaseOut, Result, Session, SessionIn,
    SheetOut, SheetWord, StoryOut, StoryWord, SummaryOut,
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
    yield


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


def _date(value):
    return date.fromisoformat(value) if value else None


def load_states(conn, child_id: str) -> dict[str, SkillState]:
    rows = conn.execute("SELECT * FROM skill_state WHERE child_id = ?", (child_id,))
    return {r["skill_id"]: SkillState(
        skill_id=r["skill_id"], score=r["score"], support_level=r["support_level"], attempts=r["attempts"],
        correct_streak=r["correct_streak"], wrong_streak=r["wrong_streak"], review_step=r["review_step"],
        next_review_at=_date(r["next_review_at"]), mastered_at=_date(r["mastered_at"]),
    ) for r in rows}


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


def group_out(conn, group_id: str) -> Group:
    g = get_row(conn, "groups", group_id)
    kids = conn.execute("SELECT * FROM children WHERE group_id = ? ORDER BY rowid", (group_id,))
    return Group(id=g["id"], tutor_name=g["tutor_name"],
                 learners=[Learner(id=k["id"], name=k["name"], picture=k["picture"], profile=k["profile"])
                           for k in kids])


def session_out(s) -> Session:
    return Session(id=s["id"], group_id=s["group_id"], present=json.loads(s["present"]),
                   phase=s["phase"], read_along_story_id=s["read_along_story_id"])


def method_name(method_id: str) -> str:
    return method_id.replace("_", " ")


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
    for learner in body.learners:
        if learner.profile not in profiles:
            raise HTTPException(422, f"profile must be one of {profiles}")
    with db.connect() as conn:
        group_id = db.new_id("g")
        conn.execute("INSERT INTO groups (id, tutor_name) VALUES (?, ?)", (group_id, body.tutor_name))
        for learner in body.learners:
            conn.execute("INSERT INTO children (id, group_id, name, picture, profile) VALUES (?, ?, ?, ?, ?)",
                         (db.new_id("c"), group_id, learner.name, learner.picture, learner.profile))
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
        conn.execute("INSERT INTO sessions (id, group_id, present, phase, read_along_story_id) VALUES (?, ?, ?, ?, ?)",
                     (session_id, body.group_id, json.dumps(body.present), "tiles", story.id))
        return session_out(get_row(conn, "sessions", session_id))


@app.get("/api/stories/{story_id}", response_model=StoryOut)
def get_story(story_id: str):
    story = content.stories_by_id.get(story_id)
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
                    audio_url=f"/api/audio/{story.id}.wav")


@app.post("/api/sessions/{session_id}/phase", response_model=PhaseOut)
def set_phase(session_id: str, body: PhaseIn):
    s = content.rules.session
    minutes = s.demo_fast.phase_minutes if DEMO_FAST else {
        "tiles": s.tile_turn_minutes, "stories": s.story_turn_minutes, "summary": s.summary_minutes,
    }[body.phase]
    ends_at = (datetime.now().astimezone() + timedelta(minutes=minutes)).isoformat(timespec="seconds")
    with db.connect() as conn:
        get_row(conn, "sessions", session_id)
        conn.execute("UPDATE sessions SET phase = ?, phase_ends_at = ? WHERE id = ?",
                     (body.phase, ends_at, session_id))
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
            results = first_try_results(conn, child_id)
            pick = pick_next(content, load_states(conn, child_id), date.today(),
                             used_items(conn, session_id, child_id), results,
                             easy=rotation.needs_easy_item(results, rules))
            conn.execute("UPDATE sessions SET current_child_id = ?, current_item_id = ?, current_turn = ? WHERE id = ?",
                         (child_id, pick.item_id, json.dumps(asdict(pick)), session_id))
            s = get_row(conn, "sessions", session_id)
        child = get_row(conn, "children", s["current_child_id"])
    turn = json.loads(s["current_turn"])

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

        # Correction steps: hints from the ladder, then show the answer, then the rebuild ends the item.
        if correct:
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
            "mistake_type, hints_used, attempt, time_ms, support_level, next_action) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, s["turn_number"], child["id"], item_id, turn["task_type"], turn["skill_id"],
             json.dumps(body.given), int(correct), mistake, body.hints_used, body.attempt, body.time_ms,
             turn["support_level"], next_action))
        if next_action == "next":
            # The item has ended: update the skill once.
            today = date.today()
            first_try = body.attempt == 1 and correct
            state = load_states(conn, child["id"]).get(turn["skill_id"]) or new_state(turn["skill_id"], rules)
            result = scoring.item_result(rules, turn["support_level"], body.attempt, correct=correct)
            state = scoring.apply_item(rules, state, result, first_try, today)
            if turn["is_review"]:
                state = review.apply_review(state, first_try, rules, today)
            save_state(conn, child["id"], state)
            conn.execute(
                "UPDATE sessions SET turn_number = turn_number + 1, current_child_id = NULL, current_item_id = NULL, "
                "current_turn = NULL WHERE id = ?", (session_id,))

    return Result(correct=correct, mistake_type=mistake, feedback=feedback, hint=hint,
                  next_action=next_action, answer=answer_tiles)


@app.get("/api/sessions/{session_id}/summary", response_model=SummaryOut)
def summary(session_id: str):
    rules = content.rules
    learners, main_mistakes = [], {}
    with db.connect() as conn:
        s = get_row(conn, "sessions", session_id)
        for child_id in json.loads(s["present"]):
            child = get_row(conn, "children", child_id)
            events = conn.execute("SELECT * FROM events WHERE session_id = ? AND child_id = ?",
                                  (session_id, child_id)).fetchall()
            items = {e["item_id"] for e in events}
            first_try = {e["item_id"] for e in events if e["attempt"] == 1 and e["correct"]}
            mistakes = Counter(e["mistake_type"] for e in events if e["mistake_type"])
            skill = weakest_unlocked_skill(content, load_states(conn, child_id))
            if mistakes:
                main = mistakes.most_common(1)[0][0]
                main_mistakes.setdefault(main, []).append(child["name"])
                method = rules.mistake_types[main].method
            elif skill.mistake_types:
                method = rules.mistake_types[skill.mistake_types[0]].method
            else:
                method = next(iter(rules.methods))
            learners.append(LearnerSummary(
                child_id=child_id,
                summary=f"{child['name']}: {len(first_try)} of {len(items)} correct. "
                        f"Next: {skill.name_en} with {method_name(method)}.",
                next_focus_skill=skill.id,
                next_method=method,
            ))
    shared = [(code, names) for code, names in main_mistakes.items() if len(names) >= 2]
    group_note = ""
    if shared:
        code, names = shared[0]
        group_note = f"{' and '.join(names)} need more work on {rules.mistake_types[code].description_en.lower()}."
    return SummaryOut(learners=learners, group_note=group_note)


@app.get("/api/children/{child_id}/sheet", response_model=SheetOut)
def sheet(child_id: str):
    ps = content.rules.practice_sheet
    with db.connect() as conn:
        child = get_row(conn, "children", child_id)
        skill = weakest_unlocked_skill(content, load_states(conn, child_id), words_only=True)
    words = [i for i in skill_items(content, skill) if isinstance(i, Word)][:ps.words]
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
        get_row(conn, "approvals", approval_id)
        conn.execute("UPDATE approvals SET status = ?, decided_at = datetime('now') WHERE id = ?",
                     ("approved" if body.approve else "rejected", approval_id))
    return OkOut(ok=True)


@app.get("/api/audio/{key}.wav")
def audio(key: str):
    if not AUDIO_KEY.match(key):
        raise HTTPException(400, "bad audio key")
    path = tts_audio.wav_path(key)
    if not path.is_file():
        raise HTTPException(404, f"audio '{key}' not generated yet")
    return FileResponse(path, media_type="audio/wav")
