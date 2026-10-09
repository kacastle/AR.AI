"""Text to speech with facebook/mms-tts-tgl, from the local Hugging Face cache only.

Used by scripts/pregen_audio.py, never inside a turn. Loading takes a few seconds.
"""
import os

os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")

import numpy as np  # noqa: E402
import torch  # noqa: E402
from transformers import AutoTokenizer, VitsModel  # noqa: E402

from backend.tts.audio import mms_ids, word_spans  # noqa: E402

MODEL_ID = "facebook/mms-tts-tgl"
SEED = 0  # MMS adds random noise; a fixed seed makes the same text sound the same every run

# Voice settings. The model's own defaults are 0.667, 0.8 and 1.0.
# Changing any of these makes scripts/pregen_audio.py remake every clip.
NOISE_SCALE = 0.667          # variation in the voice; lower = cleaner, flatter
NOISE_SCALE_DURATION = 0.8   # variation in sound lengths; lower = steadier timing
SPEAKING_RATE = 1.0          # below 1 = slower

INPUT_VERSION = 4            # 2: model input built by audio.mms_ids, not the Hugging Face tokenizer
                             # 3: one sentence at a time (audio.speak)
                             # 4: edge silence trimmed before joining (audio.trim)


def settings() -> dict:
    return {"model": MODEL_ID, "seed": SEED, "noise_scale": NOISE_SCALE,
            "noise_scale_duration": NOISE_SCALE_DURATION, "speaking_rate": SPEAKING_RATE,
            "input_version": INPUT_VERSION}


class Speaker:
    def __init__(self):
        self.vocab = AutoTokenizer.from_pretrained(MODEL_ID).get_vocab()
        self.model = VitsModel.from_pretrained(MODEL_ID)
        self.model.eval()
        self.model.noise_scale = NOISE_SCALE
        self.model.noise_scale_duration = NOISE_SCALE_DURATION
        self.model.speaking_rate = SPEAKING_RATE
        self.rate = self.model.config.sampling_rate
        self._log_duration = None
        self.model.duration_predictor.register_forward_hook(self._keep_durations)
        self._cache: dict[str, tuple[np.ndarray, list[tuple[int, int]]]] = {}

    def _keep_durations(self, module, inputs, output):
        self._log_duration = output

    def say_timed(self, text: str) -> tuple[np.ndarray, list[tuple[int, int]]]:
        """Float samples in [-1, 1] and (start_ms, end_ms) of each word. Text with no letters is silence."""
        text = " ".join(text.split())
        if text not in self._cache:
            ids, chars = mms_ids(text, self.vocab)
            if not any(ch.isalpha() for ch in chars):
                self._cache[text] = (np.zeros(0, dtype=np.float32), [(0, 0)] * len(text.split()))
            else:
                torch.manual_seed(SEED)
                with torch.no_grad():
                    wav = self.model(input_ids=torch.tensor([ids])).waveform[0].numpy().astype(np.float32)
                # The same rounding the model uses to turn predicted lengths into frames.
                frames = torch.ceil(torch.exp(self._log_duration[0, 0]) / self.model.speaking_rate).int().tolist()
                spans = word_spans(chars, frames, len(wav) / sum(frames), self.rate)
                self._cache[text] = (wav, spans)
        return self._cache[text]

    def say(self, text: str) -> np.ndarray:
        return self.say_timed(text)[0]
