import json
import os
import random
import re
from collections import Counter
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from backend import db
from backend.content import Content, format_problems, load_content
from backend.engine.selector import focus_skill, pick_word, skill_words
from backend.schemas import (
    AnswerIn, ApprovalIn, ApprovalItem, Feedback, Group, GroupIn, Hint, Item, Learner,
    LearnerSummary, LoginIn, NextTurn, OkOut, PhaseIn, PhaseOut, Result, Session, SessionIn,
    SheetOut, SheetWord, StoryOut, StoryWord, SummaryOut,
)

AUDIO_DIR = db.ROOT / "audio_cache"
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


def mastered_skills(conn, child_id: str) -> set[str]:
    rows = conn.execute(
        "SELECT skill_id FROM skill_state WHERE child_id = ? AND mastered_at IS NOT NULL", (child_id,))
    return {r["skill_id"] for r in rows}


def support_level(conn, child_id: str, skill_id: str) -> str:
    row = conn.execute("SELECT support_level FROM skill_state WHERE child_id = ? AND skill_id = ?",
                       (child_id, skill_id)).fetchone()
    return row["support_level"] if row else content.rules.support.start["new"]


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
    # Estimated timings until scripts/pregen_audio.py writes real ones.
    words, t = [], 0
    for text in " ".join(story.paragraphs).split():
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
        if s["current_item_id"] is None:
            present = json.loads(s["present"])
            child_id = present[(s["turn_number"] - 1) % len(present)]
            used = {r["item_id"] for r in conn.execute(
                "SELECT DISTINCT item_id FROM events WHERE session_id = ? AND child_id = ?", (session_id, child_id))}
            skill, word = pick_word(content, mastered_skills(conn, child_id), used)
            tiles = word.tiles + word.distractor_tiles[:rules.difficulty.distractor_tiles["normal"]]
            random.shuffle(tiles)
            conn.execute(
                "UPDATE sessions SET current_child_id = ?, current_item_id = ?, current_task_type = ?, "
                "current_skill_id = ?, current_tiles = ? WHERE id = ?",
                (child_id, word.id, "dictation_letters", skill.id, json.dumps(tiles), session_id))
            s = get_row(conn, "sessions", session_id)

        child = get_row(conn, "children", s["current_child_id"])
        word = content.words_by_id[s["current_item_id"]]
        level = support_level(conn, child["id"], s["current_skill_id"])

    prefill = {"show": list(word.tiles), "guide": word.tiles[:1], "alone": []}[level]
    return NextTurn(
        child_id=child["id"],
        child_name=child["name"],
        turn_number=s["turn_number"],
        task_type=s["current_task_type"],
        item=Item(id=word.id, prompt_audio=f"/api/audio/{word.id}.wav", slots=len(word.tiles),
                  tiles=json.loads(s["current_tiles"]), syllables=word.syllables),
        support_level=level,
        prefill=prefill,
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
        word = content.words_by_id[body.item_id]
        expected = word.tiles
        correct = body.given == expected
        ladder = rules.hints.ladder
        templates = rules.feedback_templates
        hint = None
        answer_tiles = None

        if correct:
            next_action = "next"
            n_correct = conn.execute("SELECT COUNT(*) FROM events WHERE child_id = ? AND correct = 1",
                                     (child["id"],)).fetchone()[0]
            lines = templates["CORRECT"].message_fil
            feedback = Feedback(message_fil=lines[n_correct % len(lines)].format(name=child["name"]),
                                hint_fil=templates["CORRECT"].hint_fil)
        elif body.attempt <= len(ladder):
            next_action = "retry"
            kind = ladder[body.attempt - 1]
            diff = next((i for i, t in enumerate(expected) if i >= len(body.given) or body.given[i] != t),
                        len(expected) - 1)
            hint = Hint(
                kind=kind,
                audio=f"/api/audio/{word.id}_slow.wav" if kind == "replay_by_syllable" else None,
                highlight_slot={"highlight_slot": diff, "first_tile": 0}.get(kind),
            )
            # Stub until the classifier lands: no mistake type, so no mistake feedback text.
            feedback = Feedback(message_fil=None, hint_fil=None)
        else:
            next_action = "show_answer"
            show = templates["SHOW_ANSWER"]
            feedback = Feedback(message_fil=show.message_fil[0].format(name=child["name"]), hint_fil=show.hint_fil)
            answer_tiles = list(expected)

        level = support_level(conn, child["id"], s["current_skill_id"])
        conn.execute(
            "INSERT INTO events (session_id, child_id, item_id, task_type, skill_id, given, correct, mistake_type, "
            "hints_used, attempt, time_ms, support_level, next_action) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, child["id"], word.id, s["current_task_type"], s["current_skill_id"], json.dumps(body.given),
             int(correct), None, body.hints_used, body.attempt, body.time_ms, level, next_action))
        if next_action == "next":
            conn.execute(
                "UPDATE sessions SET turn_number = turn_number + 1, current_child_id = NULL, current_item_id = NULL, "
                "current_task_type = NULL, current_skill_id = NULL, current_tiles = NULL WHERE id = ?",
                (session_id,))

    return Result(correct=correct, mistake_type=None, feedback=feedback, hint=hint,
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
            skill = focus_skill(content, mastered_skills(conn, child_id))
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
        skill = focus_skill(content, mastered_skills(conn, child_id))
    words = skill_words(content, skill.id)[:ps.words]
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
    path = AUDIO_DIR / f"{key}.wav"
    if not path.is_file():
        raise HTTPException(404, f"audio '{key}' not generated yet")
    return FileResponse(path, media_type="audio/wav")
