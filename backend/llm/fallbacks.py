"""Which story each learner reads, without the model (rules.md section 9, "Fallback order"):

1. an approved model story for that learner that the learner has not read yet
2. a filled template from content.json story_templates at the learner's level, not used in the
   learner's last 2 sessions ({name}, {object} from the learner's interests, {other_object_1/2} from others)
3. a library story from content.json stories at the learner's level

Runs when a session is created: database reads and string filling only, no model, well under a second.
The other model fallbacks are simpler and live where they are used: practice words fall back to the
skill's content.json words (the sheet), the summary to summary.template().
"""
import json
import random
import re
from typing import Optional, Sequence

from backend import db
from backend.content import Content
from backend.records import learner_info

RECENT_SESSIONS = 2


def _recent_story_ids(conn, child_id: str, sessions: Optional[int] = None) -> list[str]:
    """Story ids this learner got, newest session first (all sessions, or only the last few)."""
    rows = conn.execute("SELECT story_ids FROM sessions WHERE story_ids LIKE ? ORDER BY rowid DESC",
                        (f'%"{child_id}"%',)).fetchall()
    ids = [json.loads(r["story_ids"]).get(child_id) for r in rows]
    ids = [i for i in ids if i]
    return ids if sessions is None else ids[:sessions]


def _model_story(conn, child_id: str) -> Optional[str]:
    read = set(_recent_story_ids(conn, child_id))
    rows = conn.execute(
        "SELECT g.id FROM generated_items g JOIN approvals a ON a.generated_item_id = g.id "
        "WHERE g.kind = 'story' AND g.child_id = ? AND a.status = 'approved' ORDER BY g.created_at",
        (child_id,)).fetchall()
    return next((r["id"] for r in rows if r["id"] not in read), None)


def _fill(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


def fill_template(template, learner: dict, obj: str, others: list[str]) -> dict:
    """A content.json story_templates entry with the learner's name and objects filled in."""
    values = {"name": learner["name"], "object": obj, "other_object_1": others[0], "other_object_2": others[1]}
    paragraphs = [_fill(p, values) for p in template.paragraphs]
    questions = [{"type": q.type, "skill_id": q.skill_id, "prompt": _fill(q.prompt, values),
                  "choices": [_fill(c, values) for c in q.choices], "answer": _fill(q.answer, values)}
                 for q in template.questions]
    return {"title": _fill(template.title, values), "level": template.level, "skill_ids": template.skill_ids,
            "target_word_ids": [], "interests": learner["interests"],
            "word_count": len(" ".join(paragraphs).split()), "paragraphs": paragraphs, "questions": questions,
            "source": "template", "template_id": template.id, "object": obj,
            "reviewed": True, "approved_by_tutor": True}     # Person 3's reviewed text; no model involved


def _template_story(conn, content: Content, learner: dict, rnd: random.Random) -> Optional[str]:
    objects = {i.id: i.objects for i in content.data.interests}
    mine = [i for i in learner["interests"] if objects.get(i)]
    if not mine:
        return None
    recent = _recent_story_ids(conn, learner["child_id"], RECENT_SESSIONS)
    used = set()
    for story_id in recent:
        row = conn.execute("SELECT payload FROM generated_items WHERE id = ?", (story_id,)).fetchone()
        if row:
            used.add(json.loads(row["payload"]).get("template_id"))
    templates = [t for t in content.data.story_templates if t.level == learner["level"] and t.id not in used]
    if not templates:
        return None
    # Rotate the interests between sessions.
    interest = mine[len(_recent_story_ids(conn, learner["child_id"])) % len(mine)]
    obj = rnd.choice(objects[interest])
    others = [o for i, objs in objects.items() if i not in learner["interests"] for o in objs if o != obj]
    payload = fill_template(rnd.choice(templates), learner, obj, rnd.sample(others, 2))
    story_id = db.new_id("ts")
    payload["id"] = story_id
    conn.execute("INSERT INTO generated_items (id, kind, child_id, payload) VALUES (?, 'template_story', ?, ?)",
                 (story_id, learner["child_id"], json.dumps(payload, ensure_ascii=False)))
    return story_id


def iid(interest: str) -> str:
    """content.json stories tag interests without the prefix ("animals"); learners have "int_animals"."""
    return interest.removeprefix("int_")


def split_sentences(paragraph: str) -> list[str]:
    """A paragraph's sentences, each with its end mark (content text only, nothing made up)."""
    return [m.strip() for m in re.findall(r"[^.!?]+[.!?]", paragraph) if m.strip()]


def library_story(conn, content: Content, child_id: str, level: int, interests: Sequence[str] = (),
                  rnd: Optional[random.Random] = None) -> str:
    """A content.json story at the level: the most of the learner's interests first, then not one from the
    learner's last sessions; at random among equals (deterministic without rnd)."""
    recent = set(_recent_story_ids(conn, child_id, RECENT_SESSIONS))
    at_level = [s for s in content.data.stories if s.level == level] or content.data.stories
    mine = {iid(i) for i in interests}

    def rank(s):
        return (len(mine & {iid(t) for t in s.interests}), s.id not in recent)

    best = max(rank(s) for s in at_level)
    tier = [s for s in at_level if rank(s) == best]
    return (rnd.choice(tier) if rnd else tier[0]).id


def read_along_story(content: Content, learners: list[dict], rnd: random.Random) -> str:
    """The group read-along: a library story at the group's lowest level that fits the most interests."""
    level = min(l["level"] for l in learners) if learners else min(content.data.levels)
    at_level = [s for s in content.data.stories if s.level == level] or content.data.stories
    wanted = [iid(i) for l in learners for i in l["interests"]]

    def score(s):
        tags = {iid(t) for t in s.interests}
        return sum(1 for w in wanted if w in tags)

    best = max(score(s) for s in at_level)
    return rnd.choice([s for s in at_level if score(s) == best]).id


def choose_story(conn, content: Content, child_id: str, rnd: random.Random) -> str:
    """The story this learner reads in a new session (see the module docstring for the order)."""
    learner = learner_info(conn, content, child_id)
    return (_model_story(conn, child_id)
            or _template_story(conn, content, learner, rnd)
            or library_story(conn, content, child_id, learner["level"], learner["interests"], rnd))
