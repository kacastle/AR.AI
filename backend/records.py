"""Reading learner records from the database: skill states, events and the learner's story inputs.

Shared by the API (backend/main.py), the summary (backend/summary.py) and the model jobs (backend/llm/).
"""
import json
from datetime import date

from backend.content import Content
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


def event_count(conn, session_id: str) -> int:
    return conn.execute("SELECT COUNT(*) FROM events WHERE session_id = ?", (session_id,)).fetchone()[0]


def learner_info(conn, content: Content, child_id: str) -> dict:
    """The learner dict the story and words prompts use: name, story level, interests, weakest words skill."""
    child = conn.execute("SELECT * FROM children WHERE id = ?", (child_id,)).fetchone()
    skill = weakest_unlocked_skill(content, load_states(conn, child_id), words_only=True)
    levels = sorted(int(k) for k in content.rules.story_levels)
    # The story quiz sets story_level (rules.json story_quiz); before the first quiz, the tile skill decides.
    level = child["story_level"] if child["story_level"] is not None else skill.level
    return {"child_id": child_id, "name": child["name"], "level": min(max(level, levels[0]), levels[-1]),
            "interests": json.loads(child["interests"]), "weakest": skill.id}
