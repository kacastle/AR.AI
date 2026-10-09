"""Pregenerate every audio clip into audio_cache/ with facebook/mms-tts-tgl, fully offline.

Words, syllables, sentences, story paragraphs, fixed feedback lines, a slow syllable-by-syllable
version of each word, and each whole story read naturally with its word timings.
Files that already exist are skipped, unless their text in content/ or the voice settings in
backend/tts/mms.py changed.
A recording in content/recordings/{key}.wav (or RECORDINGS_DIR) is used instead of the model.
See backend/tts/audio.py for the file names.

Usage: python scripts/pregen_audio.py          generate what is missing, then check
       python scripts/pregen_audio.py --force  remake every clip
       python scripts/pregen_audio.py --check  only check that every word and story has a file that plays
"""
import json
import os
import shutil
import sys
import time
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

from backend.content import load_content  # noqa: E402
from backend.tts import audio  # noqa: E402

# The voice settings the files in audio_cache/ were made with, and each clip's text fingerprint.
STAMP = audio.AUDIO_DIR / "_settings.json"


def read_stamp() -> tuple[dict | None, dict]:
    if not STAMP.is_file():
        return None, {}
    data = json.loads(STAMP.read_text(encoding="utf-8"))
    if "settings" not in data:      # older stamp: settings only, no fingerprints
        return data, {}
    return data["settings"], data["clips"]


def done(job: audio.Job) -> bool:
    return audio.wav_path(job.key).is_file() and (job.words is None or audio.timings_path(job.key).is_file())


def recorded(job: audio.Job) -> bool:
    """The clip, or one of its parts, has a person's recording."""
    keys = [job.key] + (job.part_keys or [])
    return job.words is None and any((audio.RECORDINGS_DIR / f"{k}.wav").is_file() for k in keys)


def generate(jobs: list[audio.Job], force: bool) -> None:
    from backend.tts import mms   # loads torch; only when generating
    settings = mms.settings()
    old, made = read_stamp()
    if old != settings and any(audio.wav_path(j.key).is_file() for j in jobs):
        print(f"Voice settings changed ({old} -> {settings}); remaking every clip.")
        force = True
    changed = [j for j in jobs if done(j) and made.get(j.key) != audio.fingerprint(j)]
    if changed and not force:
        print("No text fingerprints saved yet; remaking every clip once." if not made else
              f"{len(changed)} clips have new text in content/ (for example {changed[0].key}); remaking them.")
    # Recordings are cheap to copy, so they are always refreshed.
    todo = [j for j in jobs if force or not done(j) or recorded(j) or j in changed]
    print(f"{len(jobs)} clips, {len(jobs) - len(todo)} up to date in {audio.AUDIO_DIR}, {len(todo)} to make")
    if todo:
        speaker = mms.Speaker()
        start = time.perf_counter()
        for n, job in enumerate(todo, 1):
            if job.words is None and (audio.RECORDINGS_DIR / f"{job.key}.wav").is_file():
                shutil.copyfile(audio.RECORDINGS_DIR / f"{job.key}.wav", audio.wav_path(job.key))
            else:
                samples, rate, words = audio.build(job, speaker)
                if words is not None:
                    audio.timings_path(job.key).write_text(
                        json.dumps({"words": words}, ensure_ascii=False, indent=1), encoding="utf-8")
                audio.write_wav(audio.wav_path(job.key), samples, rate)
            if n % 50 == 0 or n == len(todo):
                print(f"  {n}/{len(todo)}  ({time.perf_counter() - start:.0f}s)", flush=True)
    STAMP.write_text(json.dumps({"settings": settings, "clips": {j.key: audio.fingerprint(j) for j in jobs}},
                                indent=1), encoding="utf-8")


def plays(key: str) -> bool:
    try:
        with wave.open(str(audio.wav_path(key))) as f:
            return f.getnframes() > 0
    except (OSError, wave.Error, EOFError):
        return False


def _peak(key: str) -> float:
    samples, _ = audio.read_wav(audio.wav_path(key))
    return float(abs(samples).max()) if len(samples) else 0.0


def check(content, jobs: list[audio.Job]) -> int:
    """Every word and story must have a wav with sound in it. Returns the number of problems."""
    must = [w.id for w in content.data.words] + [s.id for s in content.data.stories]
    bad = [k for k in must if not plays(k)]
    missing = [j.key for j in jobs if not done(j)]
    for k in bad:
        print(f"  no playable audio: {k}")
    quiet = [j.key for j in jobs if done(j) and not recorded(j) and _peak(j.key) < audio.QUIET_PEAK]
    for k in quiet:
        users = [j.key for j in jobs if k in (j.part_keys or [])]
        print(f"  warning: {k} is nearly silent (the voice cannot say it); record content/recordings/{k}.wav"
              + (f" (also used in {', '.join(users)})" if users else ""))
    for story in content.data.stories:
        if audio.timings_path(story.id).is_file():
            for w in json.loads(audio.timings_path(story.id).read_text(encoding="utf-8"))["words"]:
                if w["end_ms"] - w["start_ms"] > audio.MAX_WORD_MS:
                    print(f"  warning: {story.id} word {w['text']!r} lasts {w['end_ms'] - w['start_ms']} ms; "
                          "listen to it, the voice may have glitched")
    print(f"check: {len(must) - len(bad)}/{len(must)} words and stories play; "
          f"{len(jobs) - len(missing)}/{len(jobs)} clips present")
    return len(bad) + len(missing)


def main():
    content = load_content()
    if content.problems:
        print(f"Content has {len(content.problems)} problem(s); run python -m backend.content")
    audio.AUDIO_DIR.mkdir(exist_ok=True)
    jobs = audio.plan(content)
    if "--check" not in sys.argv:
        generate(jobs, force="--force" in sys.argv)
    sys.exit(1 if check(content, jobs) else 0)


if __name__ == "__main__":
    main()
