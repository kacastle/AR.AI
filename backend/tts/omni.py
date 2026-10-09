"""Text to speech with k2-fsa/OmniVoice (Filipino, its default voice), from the local Hugging Face cache only.

Used by scripts/pregen_audio.py and the background worker, never inside a turn. Loading takes a few seconds;
a short clip takes about 8 s on the CPU, a story about 35 s.
Replaced facebook/mms-tts-tgl on 2026-10-10: that model has the letter "a" on the same id as its blank,
so short words and syllables lost their "a" ("bahay" sounded like "Dai").
"""
import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np  # noqa: E402
import torch  # noqa: E402
import torchaudio.functional as AF  # noqa: E402
from omnivoice import OmniVoice  # noqa: E402

from backend.tts import audio  # noqa: E402
from backend.tts.audio import best_take, estimate_word_spans, trim  # noqa: E402

MODEL_ID = "k2-fsa/OmniVoice"
LANGUAGE = "fil"
RATE = 16000         # the model makes 24 kHz; clips are saved at 16 kHz like the recordings in content/recordings/
MODEL_RATE = 24000
SEED = 0             # the same text sounds the same every run; a retry uses SEED + attempt

# Voice settings. Changing any of these makes scripts/pregen_audio.py remake every clip.
SPEED = 0.65         # about 2.6 words per second on a story: a normal talking pace (picked 2026-10-10)
NUM_STEP = 16        # generation steps; 32 is the model's default, 16 is about twice as fast
TRIES = 8            # the voice sometimes returns silence for a short text ("uod" needed seed 6); try another seed

INPUT_VERSION = 2    # 2: explicit duration from audio.speech_seconds (OmniVoice stretched short text into mumble)


def settings() -> dict:
    return {"model": MODEL_ID, "language": LANGUAGE, "speed": SPEED, "num_step": NUM_STEP, "seed": SEED,
            "rate": RATE, "seconds_per_weight": audio.SECONDS_PER_WEIGHT,
            "min_speech_seconds": audio.MIN_SPEECH_SECONDS, "input_version": INPUT_VERSION}


class Speaker:
    def __init__(self):
        self.model = OmniVoice.from_pretrained(MODEL_ID, device_map="cpu", dtype=torch.float32)
        self.rate = RATE
        self._cache: dict[str, tuple[np.ndarray, list[tuple[int, int]]]] = {}

    def _generate(self, text: str, seed: int) -> np.ndarray:
        torch.manual_seed(seed)
        wav = self.model.generate(text=text, language=LANGUAGE, duration=audio.speech_seconds(text, SPEED),
                                  num_step=NUM_STEP)[0]
        wav = torch.as_tensor(np.asarray(wav, dtype=np.float32))
        return AF.resample(wav, MODEL_RATE, RATE).numpy().astype(np.float32)

    def say_timed(self, text: str) -> tuple[np.ndarray, list[tuple[int, int]]]:
        """Float samples in [-1, 1] and (start_ms, end_ms) of each word. The voice gives no timings, so they
        are estimated from each word's letters. Text with no letters is silence."""
        text = " ".join(text.split())
        if text not in self._cache:
            if not any(ch.isalpha() for ch in text):
                self._cache[text] = (np.zeros(0, dtype=np.float32), [(0, 0)] * len(text.split()))
            else:
                samples, _ = best_take(lambda attempt: self._generate(text, SEED + attempt), TRIES,
                                       score=lambda samples: 1.0, good=1.0)   # any take with real sound
                samples, _ = trim(samples, self.rate)
                spans = estimate_word_spans(text.split(), round(len(samples) * 1000 / self.rate))
                self._cache[text] = (samples, spans)
        return self._cache[text]

    def say(self, text: str) -> np.ndarray:
        return self.say_timed(text)[0]
