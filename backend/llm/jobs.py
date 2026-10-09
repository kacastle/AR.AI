"""Model jobs, run by the background worker (never inside /next or /answer).

- story:   a personal story for one learner (content/prompts.md section 1) -> approvals
- words:   practice words for one learner (section 2) -> approvals; approved ones go on the sheet
- summary: the tutor summary for one session (section 4) -> used by GET /summary while it is current

Prompts, model call, case builders and checks come from content/test_prompts.py (harness.tp).
A failed check is retried once; then nothing is saved and the library story / code template is used.
"""
import json
import os
import random
from dataclasses import dataclass
from datetime import date
from typing import Optional

from backend import db
from backend.content import Content, Word, load_content
from backend.engine.selector import weakest_unlocked_skill
from backend.llm.harness import tp
from backend.records import event_count, load_states, session_stats

DEFAULT_MODEL = "gemma4:e4b"


@dataclass(frozen=True)
class Job:
    kind: str                         # story, words or summary
    child_id: Optional[str] = None
    session_id: Optional[str] = None


def model_name() -> str:
    return os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)


def log(message: str) -> None:
    print(f"[llm] {message}", flush=True)


_content: Optional[Content] = None


def get_content() -> Content:
    global _content
    if _content is None:
        _content = load_content()
    return _content


# ---------- model call with checks ----------

def ask_model(kind: str, prompt: str, v: dict, learner: Optional[dict]) -> str:
    """One call to the local Ollama model. Replaced by a fake in tests."""
    temperature, num_predict = tp.SETTINGS_BY_KIND[kind]
    out, _, finish = tp.call_model(model_name(), prompt, temperature, num_predict,
                                   system=tp.SYSTEM if kind == "story" else tp.GENERIC_SYSTEM,
                                   backend="ollama", schema=v.get("_schema"))
    return "" if finish == "length" else out     # cut off: treat as broken output


def _check(kind: str, out: str, v: dict, learner: Optional[dict]):
    if kind == "story":
        return tp.check_story(out, v, learner)
    if kind == "words":
        return tp.check_words(out, v)
    return tp.check_summary(out, v)


def generate(kind: str, v: dict, learner: Optional[dict], label: str) -> Optional[dict]:
    """The checked model output, or None after one retry (the caller then keeps its fallback)."""
    prompt, unfilled = tp.fill(tp.TEMPLATES[kind], {k: x for k, x in v.items() if not k.startswith("_")})
    if unfilled:
        log(f"{label}: prompt has unfilled placeholders {unfilled}; skipped")
        return None
    for attempt in (1, 2):
        try:
            out = ask_model(kind, prompt, v, learner)
        except Exception as e:                     # Ollama not running, timeout, ...
            log(f"{label}: model call failed ({e})")
            continue
        fails, parsed = _check(kind, out, v, learner)
        if not fails:
            log(f"{label}: ok (attempt {attempt})")
            return parsed
        log(f"{label}: failed checks {fails} (attempt {attempt})")
    log(f"{label}: using the fallback")
    return None


# ---------- inputs from the database ----------

def learner_for(conn, content: Content, child_id: str) -> dict:
    """The learner dict the harness case builders expect."""
    child = conn.execute("SELECT * FROM children WHERE id = ?", (child_id,)).fetchone()
    skill = weakest_unlocked_skill(content, load_states(conn, child_id), words_only=True)
    levels = sorted(int(k) for k in content.rules.story_levels)
    level = min(max(skill.level, levels[0]), levels[-1])
    return {"child_id": child_id, "name": child["name"], "level": level,
            "interests": json.loads(child["interests"]), "weakest": skill.id}


def summary_values(conn, content: Content, session_id: str) -> dict:
    """The summary prompt's values from the session's real events (prompts.md section 4 format)."""
    rules, skills = content.rules, content.skills_by_id

    def skill_text(skill_id):
        return f"{skill_id} ({skills[skill_id].name_en})"

    stats = session_stats(conn, content, session_id)
    lines = []
    for s in stats:
        mistakes = ", ".join(f"{code} ({rules.mistake_types[code].description_en}) x{n}"
                             for code, n in s.mistakes.most_common()) or "none"
        lines.append(f"{s.child_id} | {s.name} | {s.correct} of {s.total} correct | "
                     f"skills: {', '.join(skill_text(k) for k in s.skills) or 'none'} | "
                     f"weakest: {skill_text(s.skill.id)} | mistakes: {mistakes} | support: {s.support} | alert: no")
    mains = [s.main_mistake for s in stats if s.main_mistake]
    return {"date": date.today().isoformat(), "present_count": len(stats), "learner_data": "\n".join(lines),
            "method_list": ", ".join(rules.methods),
            "skill_list": ", ".join(skill_text(s.id) for s in content.skills),
            "_stats": {s.child_id: {"correct": s.correct, "total": s.total} for s in stats},
            "_shared_mistake": len(set(mains)) < len(mains)}


# ---------- saving ----------

def _waiting(conn, kind: str, child_id: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM generated_items g JOIN approvals a ON a.generated_item_id = g.id "
        "WHERE g.kind = ? AND g.child_id = ? AND a.status = 'pending'", (kind, child_id)).fetchone() is not None


def _save(kind: str, payload: dict, child_id: Optional[str] = None, session_id: Optional[str] = None,
          item_id: Optional[str] = None, approval: bool = True) -> str:
    item_id = item_id or db.new_id("gen")
    with db.connect() as conn:
        conn.execute("INSERT INTO generated_items (id, kind, child_id, session_id, payload) VALUES (?, ?, ?, ?, ?)",
                     (item_id, kind, child_id, session_id, json.dumps(payload, ensure_ascii=False)))
        if approval:
            conn.execute("INSERT INTO approvals (id, generated_item_id) VALUES (?, ?)", (db.new_id("a"), item_id))
    return item_id


# ---------- jobs ----------

def run_story(job: Job, content: Content) -> None:
    label = f"story for {job.child_id}"
    with db.connect() as conn:
        if _waiting(conn, "story", job.child_id):
            log(f"{label}: one is already waiting for the tutor; skipped")
            return
        learner = learner_for(conn, content, job.child_id)
    if not learner["interests"]:
        log(f"{label}: the learner has no interests; skipped (library stories are used)")
        return
    try:
        v = tp.story_case(learner, random.Random())
    except (IndexError, ValueError, KeyError) as e:   # no plot fits the learner's interest objects
        log(f"{label}: no story plot fits interests {learner['interests']} ({e!r}); skipped")
        return
    parsed = generate("story", v, learner, label)
    if parsed is None:
        return
    story_id = db.new_id("gs")
    text = " ".join(parsed["paragraphs"])
    words = {w.text: w.id for w in content.data.words}
    payload = {   # the same fields as content.json stories, plus where it came from
        "id": story_id, "title": parsed["title"], "level": learner["level"], "skill_ids": [learner["weakest"]],
        "target_word_ids": [words[w] for w in v["_optional"] if w in words and w in tp.words_in(text)],
        "interests": learner["interests"], "word_count": len(tp.words_in(text)),
        "paragraphs": parsed["paragraphs"], "questions": parsed["questions"],
        "source": "model", "reviewed": False, "approved_by_tutor": False,
        "model": model_name(), "plot_id": v["_plot_id"], "object": v["object"],
    }
    _save("story", payload, child_id=job.child_id, item_id=story_id)


def run_words(job: Job, content: Content) -> None:
    label = f"words for {job.child_id}"
    with db.connect() as conn:
        if _waiting(conn, "words", job.child_id):
            log(f"{label}: a list is already waiting for the tutor; skipped")
            return
        learner = learner_for(conn, content, job.child_id)
    v = tp.words_case(learner, random.Random())
    parsed = generate("words", v, learner, label)
    if parsed is None:
        return
    by_text = {w.text: w for w in content.data.words if isinstance(w, Word)}
    # The model only chooses; code adds the syllables from content.json.
    chosen = [{"text": w["text"], "word_id": by_text[w["text"]].id, "syllables": by_text[w["text"]].syllables,
               "meaning_en": w.get("meaning_en", "")} for w in parsed["words"] if w["text"] in by_text]
    _save("words", {"skill_id": learner["weakest"], "words": chosen, "model": model_name()}, child_id=job.child_id)


def run_summary(job: Job, content: Content) -> None:
    label = f"summary for {job.session_id}"
    with db.connect() as conn:
        v = summary_values(conn, content, job.session_id)
        events = event_count(conn, job.session_id)
    parsed = generate("summary", v, None, label)
    if parsed is None:
        return
    with db.connect() as conn:   # keep only the newest summary for the session
        conn.execute("DELETE FROM generated_items WHERE kind = 'summary' AND session_id = ?", (job.session_id,))
    _save("summary", {**parsed, "event_count": events, "model": model_name()},
          session_id=job.session_id, approval=False)


RUNNERS = {"story": run_story, "words": run_words, "summary": run_summary}


def run(job: Job, content: Optional[Content] = None) -> None:
    """Run one job. Never raises: a broken job must not stop the worker."""
    try:
        RUNNERS[job.kind](job, content or get_content())
    except Exception as e:
        log(f"{job}: error {e!r}")
