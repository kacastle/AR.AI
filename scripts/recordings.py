"""Recorded syllables: what still needs recording, and importing recordings from any recorder.

The voice (OmniVoice) cannot say a lone syllable (it comes out as a thud), so every syllable is recorded by a
person: one file per syllable, syl_{syllable}.wav in content/recordings/ (or RECORDINGS_DIR). One recording
is used for syl_ma, the syllable item y_ma and every slow hint with "ma". Then run
python scripts/pregen_audio.py --short (copies them in, a few seconds).

Usage: python scripts/recordings.py --list            what still needs recording (> todo.txt to save it)
       python scripts/recordings.py --import FOLDER   WAVs named like ma.wav or syl_ma.wav, any rate, mono or
                                                      stereo -> 16 kHz mono 16-bit, edge silence trimmed
Phone recordings (m4a) must be exported as WAV first.
"""
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.content import load_content  # noqa: E402
from backend.tts import audio  # noqa: E402

RATE = 16000     # the rate of every clip in audio_cache/ (backend/tts/omni.py RATE)
PEAK = 0.7


def syllables(content) -> dict[str, str]:
    """Each syllable, lowercase, with one content word that uses it (to help the speaker)."""
    out: dict[str, str] = {}
    for w in content.data.words:
        for s in w.syllables:
            out.setdefault(s.lower(), w.text)
    return dict(sorted(out.items()))


def missing(content) -> list[str]:
    return [s for s in syllables(content) if not (audio.RECORDINGS_DIR / f"{audio.syllable_key(s)}.wav").is_file()]


def to_clip(path: Path) -> np.ndarray:
    """Any WAV -> 16 kHz mono float, edge silence trimmed, peak at PEAK."""
    import torch
    import torchaudio.functional as AF
    import wave
    with wave.open(str(path)) as f:
        rate, channels, width = f.getframerate(), f.getnchannels(), f.getsampwidth()
        raw = f.readframes(f.getnframes())
    if width != 2:
        raise ValueError(f"{path.name}: {8 * width}-bit; save it as 16-bit WAV")
    samples = np.frombuffer(raw, "<i2").astype(np.float32).reshape(-1, channels).mean(axis=1) / 32768
    if rate != RATE:
        samples = AF.resample(torch.from_numpy(samples), rate, RATE).numpy()
    samples, _ = audio.trim(samples, RATE)
    peak = float(np.abs(samples).max()) if len(samples) else 0.0
    if peak < audio.QUIET_PEAK:
        raise ValueError(f"{path.name}: nearly silent")
    return samples / peak * PEAK


def main():
    content = load_content()
    known = syllables(content)
    if "--import" in sys.argv:
        folder = Path(sys.argv[sys.argv.index("--import") + 1])
        audio.RECORDINGS_DIR.mkdir(parents=True, exist_ok=True)
        done, skipped = 0, []
        for path in sorted(folder.glob("*.wav")):
            name = path.stem.lower().removeprefix("syl_")
            if name not in known:
                skipped.append(path.name)
                continue
            try:
                audio.write_wav(audio.RECORDINGS_DIR / f"{audio.syllable_key(name)}.wav", to_clip(path), RATE)
                done += 1
            except ValueError as e:
                skipped.append(str(e))
        print(f"imported {done} into {audio.RECORDINGS_DIR}")
        for s in skipped:
            print(f"  skipped: {s} (not a syllable in content.json, or see the reason)")
    todo = missing(content)
    lines = [f"{audio.syllable_key(s)}.wav   say: {s}   (as in {known[s]})" for s in todo]
    if "--list" in sys.argv:
        print("\n".join(lines))
    print(f"{len(known) - len(todo)}/{len(known)} syllables recorded in {audio.RECORDINGS_DIR}")


if __name__ == "__main__":
    main()
