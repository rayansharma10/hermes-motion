"""Shared clause-by-clause synthesis used by engines without native word alignment."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import soundfile as sf

from ..base import TTSResult, Word
from .align import estimate_words, split_clauses, trim_silence

OUT_SR = 24000


def resample(audio: np.ndarray, sr: int, target: int = OUT_SR) -> np.ndarray:
    if sr == target or audio.size == 0:
        return audio
    n = int(round(len(audio) * target / sr))
    x_old = np.linspace(0.0, 1.0, num=len(audio), endpoint=False)
    x_new = np.linspace(0.0, 1.0, num=n, endpoint=False)
    return np.interp(x_new, x_old, audio).astype(np.float32)


def synth_clauses(text: str, clause_fn, out_wav: Path, provider: str, voice: str,
                  sample_rate: int = OUT_SR) -> TTSResult:
    """clause_fn(clause_text) -> (float32 mono audio, sr). Stitches clauses with natural pauses."""
    chunks: list[np.ndarray] = []
    words: list[Word] = []
    t = 0.0
    clauses = split_clauses(text)
    for i, clause in enumerate(clauses):
        audio, sr = clause_fn(clause)
        audio = resample(np.asarray(audio, dtype=np.float32).reshape(-1), sr, sample_rate)
        a, b = trim_silence(audio, sample_rate, 0.004)
        margin = int(0.02 * sample_rate)
        audio = audio[max(0, a - margin): b + margin]
        words += estimate_words(clause, audio, sample_rate, offset=t)
        chunks.append(audio)
        t += len(audio) / sample_rate
        if i < len(clauses) - 1:
            pause = 0.16 if clause.rstrip()[-1:] in ".!?" else 0.12
            chunks.append(np.zeros(int(pause * sample_rate), dtype=np.float32))
            t += pause
    wav = np.concatenate(chunks) if chunks else np.zeros(1, dtype=np.float32)
    out_wav.parent.mkdir(parents=True, exist_ok=True)
    sf.write(str(out_wav), wav, sample_rate, subtype="PCM_16")
    return TTSResult(out_wav, len(wav) / sample_rate, words, provider, voice, sample_rate, "estimated")
