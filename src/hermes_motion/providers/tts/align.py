"""Word timing estimation for engines without native alignment.

Strategy: the caller synthesises one *sentence/clause* at a time, so clause boundaries are
exact. Inside a clause we spread the (silence-trimmed) audio over words proportional to a
speech-effort weight (letters + vowel groups), which tracks real speech rhythm closely.
"""
from __future__ import annotations

import re

import numpy as np

from ..base import Word

_SPLIT = re.compile(r"(?<=[.!?;:])\s+")


def split_clauses(text: str) -> list[str]:
    parts = [p.strip() for p in _SPLIT.split(text.strip()) if p.strip()]
    return parts or [text.strip()]


def _weight(word: str) -> float:
    letters = re.sub(r"[^A-Za-z0-9]", "", word)
    if not letters:
        return 0.5
    vowels = len(re.findall(r"[aeiouy]+", letters.lower()))
    digits = sum(c.isdigit() for c in letters)
    return 1.0 + 0.55 * len(letters) + 1.1 * vowels + 1.5 * digits


def trim_silence(audio: np.ndarray, sr: int, thresh: float = 0.01) -> tuple[int, int]:
    """Return (first, last) sample indices of non-silent audio."""
    if audio.size == 0:
        return 0, 0
    mask = np.abs(audio) > thresh
    if not mask.any():
        return 0, len(audio)
    idx = np.flatnonzero(mask)
    return int(idx[0]), int(idx[-1]) + 1


def estimate_words(text: str, audio: np.ndarray, sr: int, offset: float = 0.0) -> list[Word]:
    """Distribute words across the voiced part of ``audio`` (one clause)."""
    tokens = text.split()
    if not tokens:
        return []
    a, b = trim_silence(audio, sr)
    t0, t1 = a / sr, b / sr
    weights = np.array([_weight(t) for t in tokens])
    # trailing punctuation lengthens the gap after a word (reflected as a slightly longer slot)
    for i, tok in enumerate(tokens[:-1]):
        if tok[-1:] in ",;:":
            weights[i] *= 1.25
        elif tok[-1:] in ".!?":
            weights[i] *= 1.4
    cum = np.concatenate([[0.0], np.cumsum(weights)])
    cum /= cum[-1]
    words = []
    span = max(t1 - t0, 1e-3)
    for i, tok in enumerate(tokens):
        words.append(Word(tok, float(offset + t0 + cum[i] * span),
                          float(offset + t0 + cum[i + 1] * span)))
    return words
