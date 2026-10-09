"""The tutor summary (content/prompts.md section 4). Code computes every number; the model only words it.

compute()        -> per learner: correct of total, skills practiced, weakest skill, main mistakes,
                    support level, alert (rules.json alert)
prompt_values()  -> the summary prompt's values, in the {learner_data} line format of prompts.md
template()       -> the fixed fallback, with skill names (never ids)
current()        -> the model's summary if it was written from the events there are now
The model call itself runs in the background (backend/llm/jobs.py); GET /summary never waits for it.
"""
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from backend.content import Content, Skill
from backend.engine.selector import weakest_unlocked_skill
from backend.records import load_states
from backend.schemas import LearnerSummary, SummaryOut


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
    alert: bool
    alert_skill: Optional[Skill]


def _alert(conn, content: Content, child_id: str, states) -> Optional[Skill]:
    """rules.md section 3: score below alert.below after alert.min_attempts attempts, or for alert.days days."""
    a = content.rules.alert
    low = [s for s in states.values() if s.score < a["below"] and not s.mastered and s.skill_id in content.skills_by_id]
    for s in sorted(low, key=lambda s: s.score):
        if s.attempts >= a["min_attempts"]:
            return content.skills_by_id[s.skill_id]
        first = conn.execute("SELECT MIN(created_at) FROM events WHERE child_id = ? AND skill_id = ?",
                             (child_id, s.skill_id)).fetchone()[0]
        if first and datetime.fromisoformat(first).date() <= date.today() - timedelta(days=a["days"]):
            return content.skills_by_id[s.skill_id]
    return None


def compute(conn, content: Content, session_id: str) -> list[LearnerStats]:
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
        alert_skill = _alert(conn, content, child_id, states)
        out.append(LearnerStats(
            child_id=child_id, name=child["name"], correct=len(first_try), total=len(items),
            skills=list(dict.fromkeys(e["skill_id"] for e in events if e["skill_id"])),
            mistakes=mistakes, main_mistake=main, skill=skill, method=method, support=support,
            alert=alert_skill is not None, alert_skill=alert_skill))
    return out


def prompt_values(stats: list[LearnerStats], content: Content) -> dict:
    """Values for the summary prompt. _stats and _shared_mistake are for check_summary."""
    rules, skills = content.rules, content.skills_by_id

    def skill_text(skill_id):
        return f"{skill_id} ({skills[skill_id].name_en})"

    lines = []
    for s in stats:
        mistakes = ", ".join(f"{code} ({rules.mistake_types[code].description_en}) x{n}"
                             for code, n in s.mistakes.most_common()) or "none"
        lines.append(f"{s.child_id} | {s.name} | {s.correct} of {s.total} correct | "
                     f"skills: {', '.join(skill_text(k) for k in s.skills) or 'none'} | "
                     f"weakest: {skill_text(s.skill.id)} | mistakes: {mistakes} | support: {s.support} | "
                     f"alert: {'yes' if s.alert else 'no'}")
    mains = [s.main_mistake for s in stats if s.main_mistake]
    return {"date": date.today().isoformat(), "present_count": len(stats), "learner_data": "\n".join(lines),
            "method_list": ", ".join(rules.methods),
            "skill_list": ", ".join(skill_text(s.id) for s in content.skills),
            "_stats": {s.child_id: {"correct": s.correct, "total": s.total} for s in stats},
            "_shared_mistake": len(set(mains)) < len(mains)}


def method_name(method_id: str) -> str:
    return method_id.replace("_", " ")


def template(stats: list[LearnerStats], content: Content) -> SummaryOut:
    """prompts.md section 4 fixed template, plus the alert (rules.md section 3: add it to the tutor summary)."""
    rules = content.rules
    learners, main_mistakes = [], {}
    for s in stats:
        if s.main_mistake:
            main_mistakes.setdefault(s.main_mistake, []).append(s.name)
        text = f"{s.name}: {s.correct} of {s.total} correct. Next: {s.skill.name_en} with {method_name(s.method)}."
        if s.alert:
            text += f" Alert: {s.alert_skill.name_en} is still below {rules.alert['below']:.2f}."
        learners.append(LearnerSummary(child_id=s.child_id, summary=text,
                                       next_focus_skill=s.skill.id, next_method=s.method))
    shared = [(code, names) for code, names in main_mistakes.items() if len(names) >= 2]
    note = ""
    if shared:
        code, names = shared[0]
        note = f"{' and '.join(names)} need more work on {rules.mistake_types[code].description_en.lower()}."
    return SummaryOut(learners=learners, group_note=note)


def current(conn, session_id: str, stats: list[LearnerStats], events: int) -> Optional[SummaryOut]:
    """The model's summary if it was written from the events there are now, else None."""
    row = conn.execute("SELECT payload FROM generated_items WHERE kind = 'summary' AND session_id = ? "
                       "ORDER BY created_at DESC LIMIT 1", (session_id,)).fetchone()
    if row is None:
        return None
    payload = json.loads(row["payload"])
    if payload.get("event_count") != events:
        return None
    try:
        out = SummaryOut(learners=payload["learners"], group_note=payload.get("group_note", ""))
    except (KeyError, ValueError):
        return None
    return out if [x.child_id for x in out.learners] == [s.child_id for s in stats] else None
