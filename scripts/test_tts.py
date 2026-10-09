"""Synthesize the word "bahay" with facebook/mms-tts-tgl and save it as a wav.

Usage: python scripts/test_tts.py [output.wav]
The model downloads from Hugging Face on first run; after that it loads from cache.
"""
import sys
import wave

import torch
from transformers import AutoTokenizer, VitsModel

MODEL_ID = "facebook/mms-tts-tgl"
WORD = "bahay"


def main():
    out_path = sys.argv[1] if len(sys.argv) > 1 else "bahay.wav"
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID)
    model = VitsModel.from_pretrained(MODEL_ID)

    inputs = tokenizer(WORD, return_tensors="pt")
    with torch.no_grad():
        audio = model(**inputs).waveform[0]

    pcm = (audio.clamp(-1, 1) * 32767).to(torch.int16).numpy().tobytes()
    with wave.open(out_path, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(model.config.sampling_rate)
        f.writeframes(pcm)
    print(f"Wrote {out_path} ({len(audio) / model.config.sampling_rate:.2f}s)")


if __name__ == "__main__":
    main()
