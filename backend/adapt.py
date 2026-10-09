"""Adapting to one learner across items: the diagnostic, pace, re-teaching with a method that works for this
learner, stars, and the learner profile for parents. All numbers come from content/rules.json.

- Diagnostic (placement, rules.md 5): a learner created with "diagnostic": true gets 2 short items per skill in
  rules.json placement.skills first. When it ends, passed skills count as mastered and the profile is set.
- Pace: the median time of the learner's last first tries (timing.pace_window) -> fast / steady / slow.
  A first try slower than timing.slow_seconds makes the next item easy (the SLOW rule).
- Re-teach (rules.md 6.7): when the same mistake comes back (reteach.after_same_mistake within
  reteach.within_last_items), the next items.items_after items use a method (reteach.effects: task type,
  difficulty, some support). Each run is remembered: did it work (reteach.worked_at)? Next time the same mistake
  comes back, a method that worked comes first and one that did not is skipped ("learns the child").
"""
import json
from statistics import median
from typing import Optional

from backend.content import Content
from backend.engine import review
from backend.engine.selector import skill_items, weakest_unlocked_skill
from backend.records import learner_info, load_states


# ---------- diagnostic (placement) ----------

def _testable(content: Content, skill_id: str) -> bool:
    skill = next((s for s in content.data.skills if s.id == skill_id), None)
    return skill is not None and bool(skill_items(content, skill))


def placement_answers(conn, content: Content, child_id: str) -> dict[str, list[bool]]:
    """skill_id -> first-try results of the learner's diagnostic items. Skills with no tile items (for example
    the comprehension skill, which the story quiz scores) count as passed so the diagnostic can finish."""
    out: dict[str, list[bool]] = {}
    for r in conn.execute("SELECT skill_id, correct FROM events WHERE child_id = ? AND placement = 1 "
                          "AND attempt = 1 ORDER BY id", (child_id,)):
        out.setdefault(r["skill_id"], []).append(bool(r["correct"]))
    n = content.rules.placement.items_per_skill
    for skill_id in content.rules.placement.skills:
        if not _testable(content, skill_id):
            out[skill_id] = [True] * n
    return out


def placement_skill(conn, content: Content, child) -> Optional[str]:
    """The skill for the learner's next diagnostic item; None without a diagnostic or when it is finished."""
    if child["placement"] != "pending":
        return None
    return review.next_placement_skill(placement_answers(conn, content, child["id"]), content.rules)


def finish_placement(conn, content: Content, child_id: str, today, save_state) -> Optional[review.PlacementResult]:
    """When every diagnostic item is answered: save the passed skills (mastered) and the profile."""
    result = review.placement_status(placement_answers(conn, content, child_id), content.rules)
    if not result.done:
        return None
    result.passed = [s for s in result.passed if _testable(content, s)]
    for state in review.placement_states(result, content.rules, today):
        save_state(conn, child_id, state)
    conn.execute("UPDATE children SET placement = 'done', profile = ? WHERE id = ?", (result.profile, child_id))
    return result


# ---------- pace ----------

def pace(conn, child_id: str, rules) -> Optional[str]:
    t = rules.timing
    rows = conn.execute("SELECT time_ms FROM events WHERE child_id = ? AND attempt = 1 ORDER BY id DESC LIMIT ?",
                        (child_id, t.pace_window)).fetchall()
    if not rows:
        return None
    seconds = median(r["time_ms"] for r in rows) / 1000
    return "fast" if seconds < t.fast_seconds else "slow" if seconds > t.slow_seconds else "steady"


def last_was_slow(conn, child_id: str, rules) -> bool:
    r = conn.execute("SELECT time_ms FROM events WHERE child_id = ? AND attempt = 1 AND placement = 0 "
                     "ORDER BY id DESC LIMIT 1", (child_id,)).fetchone()
    return r is not None and r["time_ms"] > rules.timing.slow_seconds * 1000


# ---------- re-teach with a method that works for this learner ----------

def active_method(conn, child_id: str):
    return conn.execute("SELECT * FROM method_runs WHERE child_id = ? AND worked IS NULL ORDER BY id DESC LIMIT 1",
                        (child_id,)).fetchone()


def method_for_pick(rules, run) -> Optional[dict]:
    """The running method as selector.pick_next wants it."""
    if run is None:
        return None
    return {"skill_id": run["skill_id"], "effect": rules.reteach["effects"].get(run["method"], {}),
            "support": rules.reteach["support"]}


def choose_method(conn, rules, child_id: str, mistake: str) -> Optional[str]:
    """A method that worked for this learner comes first; then one not tried yet; a method that did not work
    is skipped while another is left. When every method failed, the list starts again."""
    order = rules.reteach["method_order"].get(mistake)
    if not order:
        return None
    past: dict[str, int] = {}
    for r in conn.execute("SELECT method, worked FROM method_runs WHERE child_id = ? AND mistake_type = ? "
                          "AND worked IS NOT NULL ORDER BY id", (child_id, mistake)):
        past[r["method"]] = r["worked"]                       # the latest result counts
    return (next((m for m in order if past.get(m) == 1), None)
            or next((m for m in order if m not in past), None)
            or order[0])


def after_item(conn, rules, child_id: str, skill_id: str, first_try_correct: bool) -> Optional[str]:
    """Call when an item ends (its events are saved). Moves a running method on, or starts one when the same
    first-try mistake came back. Returns the method that started, if any."""
    run = active_method(conn, child_id)
    if run is not None:
        left, total = run["items_left"] - 1, run["total"] + 1
        correct = run["correct"] + int(first_try_correct)
        worked = int(correct / total >= rules.reteach["worked_at"]) if left <= 0 else None
        conn.execute("UPDATE method_runs SET items_left = ?, correct = ?, total = ?, worked = ? WHERE id = ?",
                     (left, correct, total, worked, run["id"]))
        return None
    if first_try_correct:
        return None
    rt = rules.reteach
    recent = [r["mistake_type"] for r in conn.execute(
        "SELECT mistake_type FROM events WHERE child_id = ? AND skill_id = ? AND attempt = 1 AND placement = 0 "
        "ORDER BY id DESC LIMIT ?", (child_id, skill_id, rt["within_last_items"]))]
    mistake = recent[0] if recent else None
    if not mistake or recent.count(mistake) < rt["after_same_mistake"]:
        return None
    method = choose_method(conn, rules, child_id, mistake)
    if method is None:
        return None
    conn.execute("INSERT INTO method_runs (child_id, skill_id, mistake_type, method, items_left) VALUES (?, ?, ?, ?, ?)",
                 (child_id, skill_id, mistake, method, rules.methods[method].items_after))
    return method


# ---------- motivation ----------

def stars(conn, child_id: str) -> int:
    """One star for every item right on the first try and every story question right on the first answer."""
    tiles = conn.execute("SELECT COUNT(*) FROM events WHERE child_id = ? AND attempt = 1 AND correct = 1",
                         (child_id,)).fetchone()[0]
    quiz = conn.execute("SELECT COUNT(*) FROM story_answers WHERE child_id = ? AND first = 1 AND correct = 1",
                        (child_id,)).fetchone()[0]
    return tiles + quiz


def streak(conn, child_id: str) -> int:
    """Items right on the first try in a row, up to now."""
    n = 0
    for r in conn.execute("SELECT correct FROM events WHERE child_id = ? AND attempt = 1 ORDER BY id DESC",
                          (child_id,)):
        if not r["correct"]:
            break
        n += 1
    return n


# ---------- profile (tutor and parents) ----------

def profile(conn, content: Content, child_id: str) -> dict:
    rules = content.rules
    child = conn.execute("SELECT * FROM children WHERE id = ?", (child_id,)).fetchone()
    states = load_states(conn, child_id)
    skills = {s.id: s for s in content.data.skills}
    interests = {i.id: i for i in content.data.interests}
    reteach_below = rules.thresholds.reteach_below

    def skill_out(s):
        st = states.get(s.id)
        return {"id": s.id, "name": skills[s.id].name_en, "score": round(st.score, 2) if st else 0.0}

    mastered = [skill_out(skills[k]) for k, st in states.items() if st.mastered and k in skills]
    practiced = [skill_out(skills[k]) for k, st in states.items() if not st.mastered and st.attempts and k in skills]
    current = weakest_unlocked_skill(content, states)
    sessions = [{"session_id": r["session_id"], "date": r["day"], "correct": r["correct"], "total": r["total"]}
                for r in conn.execute(
                    "SELECT session_id, MIN(substr(created_at, 1, 10)) AS day, SUM(correct) AS correct, "
                    "COUNT(*) AS total FROM events WHERE child_id = ? AND attempt = 1 GROUP BY session_id "
                    "ORDER BY MIN(id)", (child_id,))]
    methods = [{"mistake_type": r["mistake_type"], "mistake": rules.mistake_types[r["mistake_type"]].description_en,
                "method": r["method"], "method_description": rules.methods[r["method"]].description_en,
                "correct": r["correct"], "total": r["total"],
                "worked": None if r["worked"] is None else bool(r["worked"])}
               for r in conn.execute("SELECT * FROM method_runs WHERE child_id = ? ORDER BY id", (child_id,))]
    return {
        "child_id": child_id, "name": child["name"], "profile": child["profile"],
        "interests": [{"id": i, "label": interests[i].label_en, "icon": interests[i].icon}
                      for i in json.loads(child["interests"]) if i in interests],
        "diagnostic": child["placement"],
        "story_level": learner_info(conn, content, child_id)["level"],
        "pace": pace(conn, child_id, rules),
        "current_skill": skill_out(current),
        "mastered": mastered,
        "strengths": sorted([p for p in practiced if p["score"] >= reteach_below], key=lambda p: -p["score"]),
        "needs_work": sorted([p for p in practiced if p["score"] < reteach_below], key=lambda p: p["score"]),
        "methods": methods,
        "stars": stars(conn, child_id),
        "streak": streak(conn, child_id),
        "sessions": sessions,
    }
