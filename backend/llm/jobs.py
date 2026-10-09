"""Model jobs, run by the background worker (never inside /next or /answer).

- story:       a personal story for one learner (content/prompts.md section 1). Its audio is made before
               it goes to GET /api/approvals; learners only see it after the tutor approves it.
- words:       practice words for one learner (section 2) -> approvals; approved ones go on the sheet
- summary:     the tutor summary for one session (section 4) -> GET /summary while it is current
- story_audio: audio for a filled template story (no model call)
- warmup:      load the model and the voice when the app starts, so the first real call is not slow

Every model and voice call is timed: one console line each ("... 12.3 s, ok") and an entry in CALL_TIMES.
A failed check is retried once; then nothing is saved and the fallback stays (backend/llm/fallbacks.py,
the sheet's content words, summary.template()). When Ollama is off, every job just falls back.
"""
import json
import os
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from backend import db, summary
from backend.content import Content, Word, load_content
from backend.llm import checks, client, prompts
from backend.records import event_count, learner_info
from backend.tts import audio

DEFAULT_MODEL = "gemma4:e4b"


@dataclass(frozen=True)
class Job:
    kind: str                         # warmup, story_audio, summary, words or story
    child_id: Optional[str] = None
    session_id: Optional[str] = None
    story_id: Optional[str] = None


def model_name() -> str:
    return os.environ.get("OLLAMA_MODEL", DEFAULT_MODEL)


def log(message: str) -> None:
    print(f"[llm] {datetime.now():%H:%M:%S} {message}", flush=True)


CALL_TIMES: list[dict] = []     # every timed call since startup: {"what", "label", "seconds", "result"}


def timed(what: str, label: str, result: str, start: float) -> None:
    seconds = time.perf_counter() - start
    CALL_TIMES.append({"what": what, "label": label, "seconds": round(seconds, 1), "result": result})
    log(f"{label}: {seconds:.1f} s, {result}")


_content: Optional[Content] = None
_speaker = None


def get_content() -> Content:
    global _content
    if _content is None:
        _content = load_content()
    return _content


def get_speaker():
    """MMS-TTS, loaded once in the worker thread on first use. Replaced by a fake in tests."""
    global _speaker
    if _speaker is None:
        from backend.tts.mms import Speaker   # torch; only when a story needs audio
        _speaker = Speaker()
    return _speaker


# ---------- model call with checks ----------

def ask_model(kind: str, user: str, v: dict, learner: Optional[dict]) -> str:
    """One call to the local model. Replaced by a fake in tests."""
    system, _, _ = prompts.build(kind, v)
    temperature, num_predict = prompts.SETTINGS[kind]
    text, finish = client.chat(model_name(), system, user, temperature, num_predict, schema=v.get("_schema"))
    return "" if finish == "length" else text     # cut off: treat as broken output


def generate(kind: str, v: dict, learner: Optional[dict], label: str) -> Optional[dict]:
    """The checked model output, or None after one retry (the caller then keeps its fallback)."""
    _, user, unfilled = prompts.build(kind, v)
    if unfilled:
        log(f"{label}: prompt has unfilled placeholders {unfilled}; skipped")
        return None
    for attempt in (1, 2):
        start = time.perf_counter()
        try:
            out = ask_model(kind, user, v, learner)
        except client.ModelError as e:              # the retry is for failed checks, not a missing model
            timed(kind, f"{label}, attempt {attempt}", f"no model ({e}); using the fallback", start)
            return None
        fails, parsed = checks.check(kind, out, v, learner)
        if not fails:
            timed(kind, f"{label}, attempt {attempt}", "ok", start)
            return parsed
        timed(kind, f"{label}, attempt {attempt}", f"failed checks {fails}", start)
    log(f"{label}: using the fallback")
    return None


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


def make_story_audio(story_id: str, paragraphs: list[str]) -> None:
    """audio_cache/{story_id}.wav read naturally, and {story_id}.json with each word's timing."""
    job = audio.Job(story_id, list(paragraphs), gap_ms=audio.PARAGRAPH_GAP_MS,
                    words=" ".join(paragraphs).split())
    start = time.perf_counter()
    try:
        samples, rate, words = audio.build(job, get_speaker())
    except Exception as e:
        timed("story audio", f"story audio {story_id}", f"failed ({e!r})", start)
        raise
    timed("story audio", f"story audio {story_id}", "ok", start)
    audio.AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    audio.timings_path(story_id).write_text(json.dumps({"words": words}, ensure_ascii=False), encoding="utf-8")
    audio.write_wav(audio.wav_path(story_id), samples, rate)


# ---------- jobs ----------

def run_story(job: Job, content: Content) -> None:
    label = f"story for {job.child_id}"
    with db.connect() as conn:
        if _waiting(conn, "story", job.child_id):
            log(f"{label}: one is already waiting for the tutor; skipped")
            return
        learner = learner_info(conn, content, job.child_id)
    if not learner["interests"]:
        log(f"{label}: the learner has no interests; skipped (fallback stories are used)")
        return
    try:
        v = prompts.story_case(learner, random.Random())
    except (IndexError, ValueError, KeyError) as e:   # no plot fits the learner's interest objects
        log(f"{label}: no story plot fits interests {learner['interests']} ({e!r}); skipped")
        return
    parsed = generate("story", v, learner, label)
    if parsed is None:
        return
    story_id = db.new_id("gs")
    try:
        make_story_audio(story_id, parsed["paragraphs"])
    except Exception as e:                            # no voice model: the tutor never sees a silent story
        log(f"{label}: audio failed ({e!r}); story dropped, fallback stories are used")
        return
    text = " ".join(parsed["paragraphs"])
    words = {w.text: w.id for w in content.data.words}
    payload = {   # the same fields as content.json stories, plus where it came from
        "id": story_id, "title": parsed["title"], "level": learner["level"], "skill_ids": [learner["weakest"]],
        "target_word_ids": [words[w] for w in v["_optional"] if w in words and w in text.split()],
        "interests": learner["interests"], "word_count": len(text.split()),
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
        learner = learner_info(conn, content, job.child_id)
    v = prompts.words_case(learner, random.Random())
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
        v = summary.prompt_values(summary.compute(conn, content, job.session_id), content)
        events = event_count(conn, job.session_id)
    parsed = generate("summary", v, None, label)
    if parsed is None:
        return
    with db.connect() as conn:   # keep only the newest summary for the session
        conn.execute("DELETE FROM generated_items WHERE kind = 'summary' AND session_id = ?", (job.session_id,))
    _save("summary", {**parsed, "event_count": events, "model": model_name()},
          session_id=job.session_id, approval=False)


def run_story_audio(job: Job, content: Content) -> None:
    if audio.wav_path(job.story_id).is_file():
        return
    with db.connect() as conn:
        row = conn.execute("SELECT payload FROM generated_items WHERE id = ?", (job.story_id,)).fetchone()
    if row:
        make_story_audio(job.story_id, json.loads(row["payload"])["paragraphs"])


def run_warmup(job: Job, content: Content) -> None:
    """Load the model (Ollama keeps it for keep_alive) and the voice before the first session needs them."""
    start = time.perf_counter()
    try:
        client.warm(model_name())
        timed("warm-up model", f"warm-up model {model_name()}", "ok", start)
    except client.ModelError as e:
        timed("warm-up model", f"warm-up model {model_name()}", f"failed ({e}); stories and summaries fall back", start)
    start = time.perf_counter()
    try:
        get_speaker()
        timed("warm-up voice", "warm-up voice facebook/mms-tts-tgl", "ok", start)
    except Exception as e:
        timed("warm-up voice", "warm-up voice facebook/mms-tts-tgl", f"failed ({e!r})", start)


RUNNERS = {"story": run_story, "words": run_words, "summary": run_summary, "story_audio": run_story_audio,
           "warmup": run_warmup}

# The worker runs lower numbers first: the summary must never wait behind next session's stories.
PRIORITY = {"warmup": 0, "story_audio": 1, "summary": 2, "words": 3, "story": 4}


def run(job: Job, content: Optional[Content] = None) -> None:
    """Run one job. Never raises: a broken job must not stop the worker."""
    try:
        RUNNERS[job.kind](job, content or get_content())
    except Exception as e:
        log(f"{job}: error {e!r}")
