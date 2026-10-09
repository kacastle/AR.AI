"""Audio file names, the list of clips to pregenerate, clip building and story word timings.

No TTS model here (see omni.py), so the server and the tests can import this without loading torch.
Files live in audio_cache/ (gitignored) and are served by GET /api/audio/{key}.wav.

Keys:
  {word_id}              a word or syllable item (prompt_audio)
  {word_id}_slow         the same word, syllable by syllable with short gaps (hint replay_by_syllable)
  syl_{syllable}         one syllable tile
  {sentence_id}          a sentence; {sentence_id}_slow is word by word
  {story_id}             the whole story read naturally, paragraph by paragraph; {story_id}.json has word timings
  {story_id}_p{n}        one story paragraph, n from 1
  fb_{CODE}_{i}          a fixed feedback line (message_fil[i]); fb_{CODE}_hint is hint_fil.
                         Lines with placeholders ({name}, {syllables_hyphen}, ...) are not pregenerated.

A person's recording in RECORDINGS_DIR/{key}.wav replaces the model for that key (not for whole stories,
which need word timings). Recorded syllables are also used inside the slow versions.
"""
import hashlib
import json
import os
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np

from backend.db import ROOT

AUDIO_DIR = ROOT / "audio_cache"
RECORDINGS_DIR = Path(os.environ.get("RECORDINGS_DIR", ROOT / "content" / "recordings"))
SLOW_GAP_MS = 250
SENTENCE_GAP_MS = 300
PARAGRAPH_GAP_MS = 500
EDGE_KEEP_MS = 40    # silence kept at each end of a spoken piece before pieces are joined
MAX_WORD_MS = 1500   # a story word longer than this is a voice glitch; the check reports it
QUIET_PEAK = 0.05    # a clip quieter than this has no real speech (the voice sometimes returns silence)
SECONDS_PER_WEIGHT = 1.0 / 14.1   # OmniVoice: its reference "Nice to meet you." (weight 14.1) is 25 frames = 1 s
MIN_SPEECH_SECONDS = 0.5          # floor for one short syllable or word (0.35 sounded clipped; picked 2026-10-10)


@dataclass
class Job:
    key: str
    parts: list[str]                         # one part = one synthesis; several are joined with gap_ms of silence
    gap_ms: Optional[int] = None
    part_keys: Optional[list[str]] = None    # a recording under one of these keys replaces that part
    words: Optional[list[str]] = None        # stories: save each word's start_ms and end_ms in {key}.json


def fingerprint(job: Job) -> str:
    """Changes when the clip's text or how it is joined changes, so edited content gets new audio."""
    data = json.dumps([job.parts, job.gap_ms, job.part_keys, job.words], ensure_ascii=False)
    return hashlib.sha1(data.encode("utf-8")).hexdigest()[:16]


def clip_stamp(job: Job, settings: dict) -> str:
    """What a clip was made from: its text and the voice settings. A clip whose saved stamp differs is out of date."""
    data = json.dumps(settings, sort_keys=True).encode("utf-8")
    return f"{fingerprint(job)}/{hashlib.sha1(data).hexdigest()[:12]}"


def is_short(job: Job) -> bool:
    """One word or syllable per part: words, syllables, syllable items and the slow versions.
    Sentences, stories and feedback lines are not short."""
    return job.words is None and all(" " not in p.strip() for p in job.parts)


def slow_key(item_id: str) -> str:
    return f"{item_id}_slow"


def syllable_key(syllable: str) -> str:
    return f"syl_{syllable}"


def paragraph_key(story_id: str, n: int) -> str:
    return f"{story_id}_p{n + 1}"


def story_words(story) -> list[str]:
    """The story's words in reading order, as GET /api/stories shows them."""
    return " ".join(story.paragraphs).split()


def wav_path(key: str) -> Path:
    return AUDIO_DIR / f"{key}.wav"


def timings_path(key: str) -> Path:
    return AUDIO_DIR / f"{key}.json"


def plan(content) -> list[Job]:
    """Every clip to pregenerate, in a stable order, without duplicate keys."""
    jobs: dict[str, Job] = {}

    def add(job: Job):
        jobs.setdefault(job.key, job)

    for w in content.data.words:
        add(Job(w.id, [w.tts_text]))
        add(Job(slow_key(w.id), list(w.syllables), gap_ms=SLOW_GAP_MS,
                part_keys=[syllable_key(s) for s in w.syllables]))
    for w in content.data.words:
        for syl in w.syllables:
            add(Job(syllable_key(syl), [syl]))
    for s in content.sentences:
        add(Job(s.id, [s.text]))
        add(Job(slow_key(s.id), list(s.word_tiles), gap_ms=SLOW_GAP_MS))
    for story in content.data.stories:
        add(Job(story.id, list(story.paragraphs), gap_ms=PARAGRAPH_GAP_MS, words=story_words(story)))
        for n, paragraph in enumerate(story.paragraphs):
            add(Job(paragraph_key(story.id, n), [paragraph]))
    for code, t in content.rules.feedback_templates.items():
        for i, line in enumerate(t.message_fil):
            if "{" not in line:
                add(Job(f"fb_{code}_{i}", [line]))
        if t.hint_fil and "{" not in t.hint_fil:
            add(Job(f"fb_{code}_hint", [t.hint_fil]))
    return list(jobs.values())


# ---------- timings ----------

def estimate_word_spans(words: list[str], total_ms: int) -> list[tuple[int, int]]:
    """(start_ms, end_ms) per word for a voice that gives no timings: the time is shared by letter count.
    A word with no letters (a dash) gets an empty span."""
    letters = [sum(ch.isalpha() for ch in w) for w in words]
    total = sum(letters)
    if not total:
        return [(0, 0)] * len(words)
    spans, done = [], 0
    for n in letters:
        start = round(total_ms * done / total)
        done += n
        spans.append((start, round(total_ms * done / total)))
    return spans


def speech_seconds(text: str, speed: float) -> float:
    """A natural length for the text, given to the voice as its duration. OmniVoice's own estimate stretches
    anything shorter than ~2 s (a 2-letter syllable got ~0.8 s, 1.3 s at our speed) and the voice fills the
    extra time with mumble. Same Latin weights as OmniVoice, without that stretch, floored for one syllable."""
    weight = sum(1.0 if ch.isalpha() else 0.2 if ch.isspace() else 0.5 for ch in text.strip())
    return max(MIN_SPEECH_SECONDS, weight * SECONDS_PER_WEIGHT / speed)


def best_take(make, tries: int, score, good: float, quiet: float = QUIET_PEAK) -> tuple[np.ndarray, float]:
    """make(attempt) -> samples, or raises ValueError when the voice returned nothing; score(samples) -> 0..1.
    Tries up to `tries` times and returns (samples, score) of the first take scoring at least `good`, else of
    the best one. A take with no real sound scores 0; among those the loudest is kept (empty if all failed)."""
    best, best_key = np.zeros(0, dtype=np.float32), (-1.0, -1.0)
    for attempt in range(tries):
        try:
            samples = make(attempt)
        except ValueError:
            continue
        peak = float(np.abs(samples).max()) if len(samples) else 0.0
        value = score(samples) if peak >= quiet else 0.0
        if value >= good:
            return samples, value
        if (value, peak) > best_key:
            best, best_key = samples, (value, peak)
    return best, max(best_key[0], 0.0)


def split_sentences(text: str) -> list[str]:
    """Sentences of a text, every word kept. A sentence ends at . ! or ? (maybe followed by a closing quote)
    when the next word starts with a capital letter or a quote. The voice is steadier one sentence at a time."""
    sentences, current = [], []
    words = text.split()
    for i, word in enumerate(words):
        current.append(word)
        nxt = words[i + 1] if i + 1 < len(words) else None
        ends = word.rstrip('"”\'').endswith((".", "!", "?"))
        if nxt is None or (ends and (nxt[0].isupper() or nxt[0] in '"“\'')):
            sentences.append(" ".join(current))
            current = []
    return sentences


def join_clips(clips: list[np.ndarray], rate: int, gap_ms: int) -> tuple[np.ndarray, list[tuple[int, int]]]:
    """Join clips with gap_ms of silence between them. Returns the samples and each clip's (start_ms, end_ms)."""
    gap = np.zeros(int(rate * gap_ms / 1000), dtype=np.float32)
    pieces, spans, pos = [], [], 0
    for k, clip in enumerate(clips):
        if k:
            pieces.append(gap)
            pos += len(gap)
        pieces.append(clip.astype(np.float32))
        spans.append((round(pos * 1000 / rate), round((pos + len(clip)) * 1000 / rate)))
        pos += len(clip)
    return (np.concatenate(pieces) if pieces else np.zeros(0, dtype=np.float32)), spans


# ---------- building one clip ----------

def _recording(recordings_dir: Path, key: Optional[str], rate: Optional[int] = None) -> Optional[np.ndarray]:
    """A person's recording for this key, or None. With rate, only a recording at that rate counts."""
    if key is None or not (recordings_dir / f"{key}.wav").is_file():
        return None
    samples, got = read_wav(recordings_dir / f"{key}.wav")
    if rate is not None and got != rate:
        print(f"  recording {key}.wav is {got} Hz, needs {rate} Hz mono to join with others; using the model")
        return None
    return samples


def trim(samples: np.ndarray, rate: int, spans: Optional[list[tuple[int, int]]] = None,
         threshold: float = 0.02, keep_ms: int = EDGE_KEEP_MS):
    """Cut the silence the model puts at both ends, keeping keep_ms. Word spans move with the audio.
    Returns (samples, spans). A clip with no sound is left as it is."""
    loud = np.flatnonzero(np.abs(samples) > threshold)
    if not len(loud):
        return samples, spans
    keep = int(rate * keep_ms / 1000)
    start, end = max(0, loud[0] - keep), min(len(samples), loud[-1] + keep + 1)
    if spans is not None:
        shift, length = round(start * 1000 / rate), round((end - start) * 1000 / rate)
        spans = [(min(max(a - shift, 0), length), min(max(b - shift, 0), length)) for a, b in spans]
    return samples[start:end], spans


def _join_timed(pieces: list[tuple[np.ndarray, list[tuple[int, int]]]], rate: int, gap_ms: int):
    """Join (samples, word spans) pieces with gap_ms between; word spans move with their piece."""
    joined, offsets = join_clips([samples for samples, _ in pieces], rate, gap_ms)
    return joined, [(start + a, start + b) for (start, _), (_, spans) in zip(offsets, pieces) for a, b in spans]


def speak(text: str, speaker, key: str = "") -> tuple[np.ndarray, list[tuple[int, int]]]:
    """The text one sentence at a time, joined with SENTENCE_GAP_MS. Returns samples and each word's span."""
    pieces = []
    for sentence in split_sentences(text):
        samples, spans = speaker.say_timed(sentence)
        samples, spans = trim(samples, speaker.rate, spans)
        if len(spans) != len(sentence.split()):
            raise ValueError(f"{key}: {len(spans)} word timings for {len(sentence.split())} words in: {sentence}")
        pieces.append((samples, spans))
    return _join_timed(pieces, speaker.rate, SENTENCE_GAP_MS)


def build(job: Job, speaker, recordings_dir: Path = None) -> tuple[np.ndarray, int, Optional[list[dict]]]:
    """(samples, rate, word timings or None) for one job.

    speaker: has .rate, .say(text) -> samples and .say_timed(text) -> (samples, [(start_ms, end_ms)] per word).
    """
    recordings_dir = RECORDINGS_DIR if recordings_dir is None else recordings_dir
    rate = speaker.rate

    if job.words is not None:
        joined, times = _join_timed([speak(p, speaker, job.key) for p in job.parts], rate, job.gap_ms)
        if len(times) != len(job.words):
            raise ValueError(f"{job.key}: {len(times)} word timings for {len(job.words)} words")
        return joined, rate, [{"text": t, "start_ms": a, "end_ms": b} for t, (a, b) in zip(job.words, times)]

    whole = _recording(recordings_dir, job.key)
    if whole is not None:
        _, got = read_wav(recordings_dir / f"{job.key}.wav")
        return whole, got, None

    if job.gap_ms is None:
        return speak(job.parts[0], speaker, job.key)[0], rate, None
    keys = job.part_keys or [None] * len(job.parts)
    clips = []
    for part, key in zip(job.parts, keys):
        recorded = _recording(recordings_dir, key, rate)
        clips.append(trim(recorded if recorded is not None else speaker.say(part), rate)[0])
    return join_clips(clips, rate, job.gap_ms)[0], rate, None


# ---------- files ----------

def write_wav(path: Path, samples: np.ndarray, rate: int) -> None:
    """16-bit mono wav. Writes to a temp file first so a stopped run never leaves half a file."""
    pcm = (np.clip(samples, -1, 1) * 32767).astype("<i2").tobytes()
    tmp = path.with_suffix(".tmp")
    with wave.open(str(tmp), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(pcm)
    tmp.replace(path)


def read_wav(path: Path) -> tuple[np.ndarray, int]:
    """Samples in [-1, 1] and the sample rate. 16-bit wav; stereo is mixed down to mono."""
    with wave.open(str(path)) as f:
        if f.getsampwidth() != 2:
            raise ValueError(f"{path.name}: needs 16-bit wav")
        data = np.frombuffer(f.readframes(f.getnframes()), "<i2").astype(np.float32) / 32767
        if f.getnchannels() > 1:
            data = data.reshape(-1, f.getnchannels()).mean(axis=1)
        return data, f.getframerate()


def load_timings(story_id: str) -> Optional[list[dict]]:
    """Word timings saved by scripts/pregen_audio.py, or None if the story has no audio yet."""
    path = timings_path(story_id)
    if not (path.is_file() and wav_path(story_id).is_file()):
        return None
    return json.loads(path.read_text(encoding="utf-8"))["words"]
