"""Reading learner records from the database: skill states and what happened in a session.

Shared by the API (backend/main.py) and the background model jobs (backend/llm/jobs.py).
"""
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date
from typing import Optional

from backend.content import Content, Skill
from backend.engine.selector import weakest_unlocked_skill
from backend.engine.state import SkillState


def _date(value):
    return date.fromisoformat(value) if value else None


def load_states(conn, child_id: str) -> dict[str, SkillState]:
    rows = conn.execute("SELECT * FROM skill_state WHERE child_id = ?", (child_id,))
    return {r["skill_id"]: SkillState(
        skill_id=r["skill_id"], score=r["score"], support_level=r["support_level"], attempts=r["attempts"],
        correct_streak=r["correct_streak"], wrong_streak=r["wrong_streak"], review_step=r["review_step"],
        next_review_at=_date(r["next_review_at"]), mastered_at=_date(r["mastered_at"]),
    ) for r in rows}


@dataclass
class LearnerStats:
    child_id: str
    name: str
    correct: int                 # items right on the first try
    total: int                   # items seen this session
    skills: list[str]            # skill ids practiced, in order
    mistakes: Counter            # mistake code -> count
    main_mistake: Optional[str]
    skill: Skill                 # next focus: the weakest unlocked skill
    method: str                  # a key of rules.json methods
    support: str


def session_stats(conn, content: Content, session_id: str) -> list[LearnerStats]:
    """One entry per present learner, in the order of the session's present list."""
    rules = content.rules
    s = conn.execute("SELECT present FROM sessions WHERE id = ?", (session_id,)).fetchone()
    out = []
    for child_id in json.loads(s["present"]):
        child = conn.execute("SELECT name FROM children WHERE id = ?", (child_id,)).fetchone()
        events = conn.execute("SELECT * FROM events WHERE session_id = ? AND child_id = ? ORDER BY id",
                              (session_id, child_id)).fetchall()
        items = {e["item_id"] for e in events}
        first_try = {e["item_id"] for e in events if e["attempt"] == 1 and e["correct"]}
        mistakes = Counter(e["mistake_type"] for e in events if e["mistake_type"])
        states = load_states(conn, child_id)
        skill = weakest_unlocked_skill(content, states)
        main = mistakes.most_common(1)[0][0] if mistakes else None
        if main:
            method = rules.mistake_types[main].method
        elif skill.mistake_types:
            method = rules.mistake_types[skill.mistake_types[0]].method
        else:
            method = next(iter(rules.methods))
        support = events[-1]["support_level"] if events else (
            states[skill.id].support_level if skill.id in states else rules.support.start["new"])
        out.append(LearnerStats(
            child_id=child_id, name=child["name"], correct=len(first_try), total=len(items),
            skills=list(dict.fromkeys(e["skill_id"] for e in events if e["skill_id"])),
            mistakes=mistakes, main_mistake=main, skill=skill, method=method, support=support))
    return out


def event_count(conn, session_id: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM events WHERE session_id = ?", (session_id,)).fetchone()[0]
