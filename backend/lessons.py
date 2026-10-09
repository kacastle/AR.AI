"""The lesson player: teach a skill before the learner practises it, and teach it again, another way, when the
learner is stuck (a re-teach method starts). Numbers and styles come from rules.json lessons.

Explanation styles:
- visual: one example word as tiles, the skill's letters lit up, its syllables underneath
- steps:  the example word built syllable by syllable (ba -> ba + hay -> bahay)
- story:  a very short story with the learner's name and interest that uses words of the skill. Written by the
          model in the background (prompts.md section 7, kind "lesson"), approved like the personal story;
          until one is ready, a content.json sentence of the skill.

Every lesson is remembered with the learner's first tries on the next lessons.check_items items of that skill:
did it work (lessons.worked_at)? The next lesson for the learner prefers a style that worked, and a re-teach
lesson always uses a different style than the last one for that skill.
"""
import json
import re
from typing import Optional

from backend.content import Content, Sentence, Word
from backend.engine.selector import skill_items

TILE = re.compile(r"ng|.")
VOWELS = set("aeiou")


def due(conn, child_id: str, turn: dict, states: dict) -> Optional[str]:
    """'new' before the learner's first item of a skill, 'reteach' when a re-teach method just started.
    None when no lesson is due (diagnostic items and easy items never get one)."""
    mode = turn.get("mode")
    if mode == "reteach":
        run_id = turn.get("method_run_id")
        seen = conn.execute("SELECT 1 FROM lesson_views WHERE child_id = ? AND method_run_id = ?",
                            (child_id, run_id)).fetchone()
        return None if seen else "reteach"
    if mode == "practice":
        state = states.get(turn["skill_id"])
        if state is not None and state.attempts > 0:
            return None
        seen = conn.execute("SELECT 1 FROM lesson_views WHERE child_id = ? AND skill_id = ?",
                            (child_id, turn["skill_id"])).fetchone()
        return None if seen else "new"
    return None


def _story(conn, content: Content, child_id: str, skill) -> Optional[dict]:
    """The learner's newest approved model lesson story for the skill, else a content.json sentence of it."""
    rows = conn.execute(
        "SELECT g.payload FROM generated_items g JOIN approvals a ON a.generated_item_id = g.id "
        "WHERE g.kind = 'lesson' AND g.child_id = ? AND a.status = 'approved' ORDER BY g.created_at DESC",
        (child_id,)).fetchall()
    for r in rows:
        p = json.loads(r["payload"])
        if p.get("skill_id") == skill.id:
            return {"sentences": p["sentences"], "words": p["words"], "source": "model"}
    words = {w.text for w in skill_items(content, skill) if isinstance(w, Word)}
    for sn in content.sentences:
        tokens = {t.strip(".,!?").lower() for t in sn.text.split()}
        if skill.id in sn.skill_ids or tokens & words:
            return {"sentences": [sn.text], "words": sorted(tokens & words), "source": "content"}
    return None


def choose_style(conn, rules, child_id: str, skill_id: str, reason: str, story_ok: bool) -> str:
    styles = [s for s in rules.lessons["styles"] if s != "story" or story_ok]
    if reason == "reteach":
        last = conn.execute("SELECT style FROM lesson_views WHERE child_id = ? AND skill_id = ? ORDER BY id DESC "
                            "LIMIT 1", (child_id, skill_id)).fetchone()
        if last is not None and len(styles) > 1:
            styles = [s for s in styles if s != last["style"]]
    worked = [r["style"] for r in conn.execute(
        "SELECT style FROM lesson_views WHERE child_id = ? AND worked = 1 ORDER BY id DESC", (child_id,))]
    failed = {r["style"] for r in conn.execute(
        "SELECT style FROM lesson_views WHERE child_id = ? AND worked = 0", (child_id,))} - set(worked)
    return (next((s for s in worked if s in styles), None)
            or next((s for s in styles if s not in failed), None)
            or styles[0])


def _highlight(skill, tiles: list[str], syllables: list[str]) -> list[int]:
    """Tiles to light up: the skill's letters; else the part of the word the skill is about."""
    if skill.letters:
        return [i for i, t in enumerate(tiles) if t in skill.letters]
    if skill.id == "sk_cvc_final":
        return [len(tiles) - 1]
    if skill.id == "sk_cvc_mid" and syllables:
        return [len(TILE.findall(syllables[0])) - 1]
    if skill.id == "sk_clusters":
        pair = next((i for i in range(len(tiles) - 1) if tiles[i] not in VOWELS and tiles[i + 1] not in VOWELS), None)
        return [] if pair is None else [pair, pair + 1]
    return []


def build(conn, content: Content, child, skill_id: str, item_id: str, reason: str, prefer: list[str]) -> Optional[dict]:
    """The lesson for one turn, or None when the skill has nothing to show (for example a comprehension skill)."""
    skill = next(s for s in content.data.skills if s.id == skill_id)
    items = [i for i in skill_items(content, skill) if i.id != item_id] or skill_items(content, skill)
    if not items:
        return None
    liked = [i for i in items if getattr(i, "text", None) in set(prefer)]
    example = (liked or items)[0]
    if isinstance(example, Sentence):
        tiles, syllables = list(example.word_tiles), []
        steps = [" ".join(example.word_tiles[:k]) for k in range(1, len(example.word_tiles) + 1)]
        highlight = [0]                            # the capital letter starts the sentence
    else:
        tiles, syllables = list(example.tiles), list(example.syllables)
        steps = ["".join(syllables[:k]) for k in range(1, len(syllables) + 1)]
        highlight = _highlight(skill, tiles, syllables)
    more = [{"text": w.text, "syllables": w.syllables} for w in items if isinstance(w, Word) and w.id != example.id][:3]
    story = _story(conn, content, child["id"], skill)
    style = choose_style(conn, content.rules, child["id"], skill_id, reason, story is not None)
    return {"skill_id": skill_id, "skill_name_fil": skill.name_fil, "skill_name_en": skill.name_en,
            "reason": reason, "style": style, "example": {"text": getattr(example, "text", ""), "tiles": tiles,
                                                          "syllables": syllables, "highlight": highlight},
            "steps": steps, "more_words": more, "story": story if style == "story" else None}


def record(conn, child_id: str, session_id: str, lesson: dict, method_run_id: Optional[int]) -> None:
    conn.execute("INSERT INTO lesson_views (child_id, skill_id, style, reason, method_run_id, session_id) "
                 "VALUES (?, ?, ?, ?, ?, ?)", (child_id, lesson["skill_id"], lesson["style"], lesson["reason"],
                                               method_run_id, session_id))


def after_item(conn, rules, child_id: str, skill_id: str, first_try_correct: bool) -> None:
    """Counts the items after a lesson; after lessons.check_items, the lesson is judged."""
    view = conn.execute("SELECT * FROM lesson_views WHERE child_id = ? AND skill_id = ? AND worked IS NULL "
                        "ORDER BY id DESC LIMIT 1", (child_id, skill_id)).fetchone()
    if view is None:
        return
    total, correct = view["total"] + 1, view["correct"] + int(first_try_correct)
    worked = int(correct / total >= rules.lessons["worked_at"]) if total >= rules.lessons["check_items"] else None
    conn.execute("UPDATE lesson_views SET total = ?, correct = ?, worked = ? WHERE id = ?",
                 (total, correct, worked, view["id"]))
