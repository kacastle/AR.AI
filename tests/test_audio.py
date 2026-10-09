"""Audio planning, model input, clip joining and story timings. No TTS model needed."""
import json
import os
import re
import tempfile
import wave
from pathlib import Path

import numpy as np
import pytest

os.environ.setdefault("DB_PATH", str(Path(tempfile.mkdtemp()) / "test.db"))

from fastapi.testclient import TestClient  # noqa: E402

from backend.content import load_content  # noqa: E402
from backend.main import app  # noqa: E402
from backend.tts import audio  # noqa: E402

CONTENT = load_content()
KEY = re.compile(r"^[A-Za-z0-9_-]+$")


class FakeSpeaker:
    """10 samples per character; each word 'spoken' at 100 ms steps."""
    rate = 1000

    def say(self, text):
        return np.full(10 * len(text), 0.5, dtype=np.float32)

    def say_timed(self, text):
        words = text.split()
        return np.full(100 * len(words), 0.5, dtype=np.float32), [(100 * i, 100 * i + 80) for i in range(len(words))]


# ---------- model input ----------

def test_join_clips_puts_silence_between_and_returns_ms():
    rate = 16000
    clips = [np.ones(1600, dtype=np.float32), np.ones(800, dtype=np.float32)]
    joined, spans = audio.join_clips(clips, rate, gap_ms=120)
    assert spans == [(0, 100), (220, 270)]
    assert len(joined) == 1600 + 1920 + 800
    assert not joined[1600:1600 + 1920].any()


def test_wav_roundtrip(tmp_path):
    path = tmp_path / "x.wav"
    audio.write_wav(path, np.linspace(-1, 1, 1600, dtype=np.float32), 16000)
    with wave.open(str(path)) as f:
        assert (f.getframerate(), f.getnchannels(), f.getnframes()) == (16000, 1, 1600)
    samples, rate = audio.read_wav(path)
    assert rate == 16000 and len(samples) == 1600 and abs(samples[-1] - 1) < 1e-3


# ---------- plan ----------

def test_plan_covers_every_word_syllable_sentence_story_and_fixed_line():
    jobs = {j.key: j for j in audio.plan(CONTENT)}
    assert all(KEY.match(k) for k in jobs)
    for w in CONTENT.data.words:
        assert jobs[w.id].parts == [w.tts_text]
        slow = jobs[audio.slow_key(w.id)]
        assert slow.parts == w.syllables and slow.gap_ms == audio.SLOW_GAP_MS
        assert slow.part_keys == [audio.syllable_key(s) for s in w.syllables]
        for syl in w.syllables:
            assert jobs[audio.syllable_key(syl)].parts == [syl]
    for s in CONTENT.sentences:
        assert jobs[s.id].parts == [s.text]
    for story in CONTENT.data.stories:
        job = jobs[story.id]
        assert job.parts == story.paragraphs and job.gap_ms == audio.PARAGRAPH_GAP_MS
        assert job.words == audio.story_words(story)
        for n, p in enumerate(story.paragraphs):
            assert jobs[audio.paragraph_key(story.id, n)].parts == [p]
    fixed = [j for k, j in jobs.items() if k.startswith("fb_")]
    assert fixed and all("{" not in j.parts[0] for j in fixed)
    assert jobs["fb_SHOW_ANSWER_0"].parts == CONTENT.rules.feedback_templates["SHOW_ANSWER"].message_fil


def test_syllables_are_said_as_written():
    # OmniVoice says a lone vowel as it is, so syllables need no special spelling.
    jobs = {j.key: j for j in audio.plan(CONTENT)}
    assert jobs["syl_a"].parts == ["a"]
    aso = jobs[audio.slow_key("w_aso")]
    assert aso.parts == ["a", "so"] and aso.part_keys == ["syl_a", "syl_so"]


# ---------- voice output ----------

def test_estimate_word_spans_shares_the_time_by_letters():
    spans = audio.estimate_word_spans(["Si", "Ana", "ay", "masaya."], 1300)
    assert spans == [(0, 200), (200, 500), (500, 700), (700, 1300)]   # 2, 3, 2, 6 letters of 13
    assert audio.estimate_word_spans(["a", "—", "b"], 200) == [(0, 100), (100, 100), (100, 200)]
    assert audio.estimate_word_spans(["—"], 300) == [(0, 0)]


def test_speech_seconds_is_a_natural_length_without_omnivoice_short_text_stretch():
    # letters 1.0, spaces 0.2, punctuation 0.5; OmniVoice's own Latin weights, divided by the speed
    assert audio.speech_seconds("Si Ana ay masaya.", 1.0) == pytest.approx(14.1 * audio.SECONDS_PER_WEIGHT)   # 13 letters, 3 spaces, 1 period
    assert audio.speech_seconds("Si Ana ay masaya.", 0.5) == pytest.approx(2 * 14.1 * audio.SECONDS_PER_WEIGHT)
    # OmniVoice itself would give a 2-letter syllable ~0.8 s (1.3 s at speed 0.65); we give the floor
    assert audio.speech_seconds("ma", 0.65) == audio.MIN_SPEECH_SECONDS
    assert audio.speech_seconds("sapatos", 0.65) > audio.speech_seconds("aso", 0.65)


def test_is_short_means_one_word_or_syllable_per_part():
    jobs = {j.key: j for j in audio.plan(CONTENT)}
    short = {k for k, j in jobs.items() if audio.is_short(j)}
    assert {"syl_ma", "w_aso", audio.slow_key("w_aso"), "y_ma"} <= short    # y_ = a syllable item
    assert audio.slow_key(CONTENT.sentences[0].id) in short           # a sentence word by word
    assert CONTENT.sentences[0].id not in short                       # the whole sentence
    assert not any(k.startswith(("st_", "fb_")) for k in short)       # stories and feedback lines


def test_clip_stamp_changes_with_text_or_voice_settings():
    job = audio.Job("w_x", ["bahay"])
    s1, s2 = {"speed": 0.65}, {"speed": 0.7}
    assert audio.clip_stamp(job, s1) == audio.clip_stamp(audio.Job("w_x", ["bahay"]), dict(s1))
    assert audio.clip_stamp(job, s1) != audio.clip_stamp(job, s2)
    assert audio.clip_stamp(job, s1) != audio.clip_stamp(audio.Job("w_x", ["baha"]), s1)


def _takes(outputs, tried):
    def make(attempt):
        tried.append(attempt)
        out = outputs[attempt]
        if isinstance(out, Exception):
            raise out
        return out
    return make


def test_best_take_retries_errors_silence_and_low_scores():
    loud_bad, loud_good = (np.full(10, 0.5, dtype=np.float32) for _ in range(2))
    quiet = np.full(10, 0.01, dtype=np.float32)
    tried = []
    scores = {id(loud_bad): 0.4, id(loud_good): 0.9}
    samples, score = audio.best_take(_takes([ValueError("empty"), quiet, loud_bad, loud_good, loud_bad], tried),
                                     tries=5, score=lambda s: scores[id(s)], good=0.8)
    assert samples is loud_good and score == 0.9
    assert tried == [0, 1, 2, 3]                                # stops at the first good take


def test_best_take_keeps_the_best_when_no_take_is_good():
    a, b = np.full(4, 0.5, dtype=np.float32), np.full(4, 0.6, dtype=np.float32)
    scores = {id(a): 0.5, id(b): 0.7}
    samples, score = audio.best_take(_takes([a, b], []), tries=2, score=lambda s: scores[id(s)], good=0.8)
    assert samples is b and score == 0.7
    # every take quiet: the loudest one, score 0 (pregen_audio --check reports it)
    outs = [np.full(4, p, dtype=np.float32) for p in (0.01, 0.03, 0.02)]
    samples, score = audio.best_take(_takes(outs, []), tries=3, score=lambda s: 1.0, good=0.8)
    assert samples is outs[1] and score == 0.0
    samples, score = audio.best_take(_takes([ValueError("x")] * 2, []), tries=2, score=lambda s: 1.0, good=0.8)
    assert len(samples) == 0 and score == 0.0


# ---------- build ----------

def test_build_text_and_slow(tmp_path):
    samples, rate, words = audio.build(audio.Job("w_x", ["bahay"]), FakeSpeaker(), tmp_path)
    assert (len(samples), rate, words) == (100, 1000, None)
    samples, _, _ = audio.build(audio.Job("w_x_slow", ["ba", "hay"], gap_ms=100, part_keys=["syl_ba", "syl_hay"]),
                                FakeSpeaker(), tmp_path)
    assert len(samples) == 20 + 100 + 30


def test_build_uses_a_recording_when_there_is_one(tmp_path):
    audio.write_wav(tmp_path / "w_x.wav", np.zeros(7, dtype=np.float32), 1000)
    audio.write_wav(tmp_path / "syl_ba.wav", np.zeros(4, dtype=np.float32), 1000)
    samples, _, _ = audio.build(audio.Job("w_x", ["bahay"]), FakeSpeaker(), tmp_path)
    assert len(samples) == 7
    # A recorded syllable is used inside the slow version too.
    samples, _, _ = audio.build(audio.Job("w_x_slow", ["ba", "hay"], gap_ms=100, part_keys=["syl_ba", "syl_hay"]),
                                FakeSpeaker(), tmp_path)
    assert len(samples) == 4 + 100 + 30


def test_a_syllable_item_uses_the_syllable_recording(tmp_path):
    jobs = {j.key: j for j in audio.plan(CONTENT)}
    assert jobs["y_ma"].part_keys == ["syl_ma"]             # one recording: syl_ma, y_ma and the slow hints
    assert jobs["y_ma"].word_gap_ms is None                    # one syllable: the recording as it is
    audio.write_wav(tmp_path / "syl_ma.wav", np.zeros(9, dtype=np.float32), 1000)
    samples, rate, _ = audio.build(jobs["y_ma"], FakeSpeaker(), tmp_path)
    assert (len(samples), rate) == (9, 1000)


def test_a_word_is_its_recorded_syllables_with_pauses(tmp_path):
    jobs = {j.key: j for j in audio.plan(CONTENT)}
    aso = jobs["w_aso"]
    assert aso.part_keys == ["syl_a", "syl_so"] and aso.word_gap_ms == audio.WORD_GAP_MS
    audio.write_wav(tmp_path / "syl_a.wav", np.full(200, 0.5, dtype=np.float32), 1000)
    audio.write_wav(tmp_path / "syl_so.wav", np.full(300, 0.5, dtype=np.float32), 1000)
    samples, rate, _ = audio.build(audio.Job("w_aso", ["aso"], part_keys=["syl_a", "syl_so"], word_gap_ms=80),
                                   FakeSpeaker(), tmp_path)
    assert (len(samples), rate) == (200 + 80 + 300, 1000)          # whole recordings, 80 ms pause
    assert samples[0] == 0 and samples[100] == pytest.approx(0.5, abs=1e-3)                # faded edge, recording kept whole
    # a syllable without a recording: the voice says the whole word
    samples, _, _ = audio.build(audio.Job("w_x", ["bahay"], part_keys=["syl_ba", "syl_hay"], word_gap_ms=80),
                                FakeSpeaker(), tmp_path)
    assert len(samples) == 100                                     # FakeSpeaker: 100 samples per word


def test_split_sentences_keeps_every_word():
    assert audio.split_sentences("Si Ana. May aso si Ben.") == ["Si Ana.", "May aso si Ben."]
    # A quote ending in ! followed by a lowercase word is one sentence.
    assert audio.split_sentences('"Ang ganda ng langit!" sabi ni Ben.') == ['"Ang ganda ng langit!" sabi ni Ben.']
    text = 'Pero naputol ang tali! Nalungkot si Paolo. "Gagawa tayo bukas," sabi ni Kuya Jun.'
    assert audio.split_sentences(text) == ["Pero naputol ang tali!", "Nalungkot si Paolo.",
                                           '"Gagawa tayo bukas," sabi ni Kuya Jun.']
    assert audio.split_sentences("bahay") == ["bahay"]


def test_build_speaks_one_sentence_at_a_time(tmp_path):
    samples, _, _ = audio.build(audio.Job("p", ["Si Ana. May aso."]), FakeSpeaker(), tmp_path)
    assert len(samples) == 200 + audio.SENTENCE_GAP_MS + 200


def test_build_story_joins_sentences_and_paragraphs_and_offsets_word_times(tmp_path):
    job = audio.Job("st_x", ["Si Ana. May aso.", "Ben."], gap_ms=500, words=["Si", "Ana.", "May", "aso.", "Ben."])
    samples, rate, words = audio.build(job, FakeSpeaker(), tmp_path)
    gap = audio.SENTENCE_GAP_MS
    assert len(samples) == 200 + gap + 200 + 500 + 100
    assert [w["text"] for w in words] == job.words
    p2 = 200 + gap + 200 + 500
    assert [(w["start_ms"], w["end_ms"]) for w in words] == [
        (0, 80), (100, 180), (200 + gap, 280 + gap), (300 + gap, 380 + gap), (p2, p2 + 80)]


def test_build_story_refuses_timings_that_do_not_match_the_words(tmp_path):
    job = audio.Job("st_x", ["Si Ana."], gap_ms=500, words=["Si", "Ana.", "extra"])
    with pytest.raises(ValueError):
        audio.build(job, FakeSpeaker(), tmp_path)


# ---------- API ----------

def test_story_uses_saved_timings_and_audio_is_served(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "AUDIO_DIR", tmp_path)
    story = CONTENT.data.stories[0]
    words = audio.story_words(story)
    spans = [{"text": w, "start_ms": 500 * i, "end_ms": 500 * i + 400} for i, w in enumerate(words)]
    (tmp_path / f"{story.id}.json").write_text(json.dumps({"words": spans}), encoding="utf-8")
    audio.write_wav(tmp_path / f"{story.id}.wav", np.zeros(160, dtype=np.float32), 16000)

    with TestClient(app) as client:
        got = client.get(f"/api/stories/{story.id}").json()
        assert got["words"] == spans
        assert got["audio_url"] == f"/api/audio/{story.id}.wav"
        r = client.get(got["audio_url"])
        assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"


def test_story_without_audio_still_has_estimated_timings(monkeypatch, tmp_path):
    monkeypatch.setattr(audio, "AUDIO_DIR", tmp_path)
    story = CONTENT.data.stories[0]
    with TestClient(app) as client:
        words = client.get(f"/api/stories/{story.id}").json()["words"]
    assert [w["text"] for w in words] == audio.story_words(story)
    assert all(w["end_ms"] > w["start_ms"] for w in words)


@pytest.mark.parametrize("bad", ["../x", "a.b"])
def test_bad_audio_key_rejected(bad):
    with TestClient(app) as client:
        assert client.get(f"/api/audio/{bad}.wav").status_code in (400, 404)


def test_trim_cuts_edge_silence_and_moves_word_spans():
    rate = 1000
    x = np.concatenate([np.zeros(100), np.full(50, 0.5), np.zeros(30), np.full(20, 0.5), np.zeros(100)]).astype(np.float32)
    trimmed, spans = audio.trim(x, rate, [(100, 150), (180, 200)], keep_ms=10)
    assert len(trimmed) == 10 + 100 + 10
    assert spans == [(10, 60), (90, 110)]
    silent = np.zeros(50, dtype=np.float32)
    assert len(audio.trim(silent, rate)[0]) == 50     # nothing to keep: leave it alone


def test_fingerprint_changes_when_the_text_or_joining_changes():
    base = audio.Job("w_x", ["bahay"])
    assert audio.fingerprint(base) == audio.fingerprint(audio.Job("w_x", ["bahay"]))
    assert audio.fingerprint(base) != audio.fingerprint(audio.Job("w_x", ["bahay!"]))
    slow = audio.Job("w_x_slow", ["ba", "hay"], gap_ms=250)
    assert audio.fingerprint(slow) != audio.fingerprint(audio.Job("w_x_slow", ["ba", "hay"], gap_ms=300))
