"""Narration-driven timeline: scene durations and element cues come from word timings."""
from __future__ import annotations

import math
import re
from dataclasses import asdict

import numpy as np
import soundfile as sf

from .providers.base import TTSResult, Word

_STOP = {"the", "and", "for", "with", "that", "this", "from", "into", "her", "his", "its",
         "are", "you", "your", "our", "only", "when", "then", "than", "but", "not", "all"}


def _tokens(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) >= 2 and t not in _STOP]


def build(sb: dict, results: dict[str, TTSResult | None], fps: int,
          lead: float, tail: float) -> dict:
    """Compute absolute scene windows (frame-aligned) and global word times."""
    frame = 1.0 / fps
    t = 0.0
    scenes = []
    for sc in sb["scenes"]:
        r = results.get(sc["id"])
        narr = r.duration if r else 0.0
        length = lead + narr + tail if r else 0.0
        length = max(length, float(sc.get("min_seconds") or 0.0))
        length = max(math.ceil(length / frame - 1e-9) * frame, frame * 15)
        words = []
        if r:
            words = [{"word": w.word, "start": round(t + lead + w.start, 3),
                      "end": round(t + lead + w.end, 3)} for w in r.words]
        scenes.append({
            "id": sc["id"], "template": sc["template"], "transition": sc["transition"],
            "start": round(t, 4), "end": round(t + length, 4), "length": round(length, 4),
            "audio_offset": round(t + lead, 4) if r else None,
            "narration": sc["narration"], "words": words,
            "narration_start": words[0]["start"] if words else None,
            "narration_end": words[-1]["end"] if words else None,
        })
        t += length
    return {"fps": fps, "total_seconds": round(t, 4), "total_frames": round(t * fps), "scenes": scenes}


def caption_chunks(words: list[dict], max_words: int = 6, max_chars: int = 38) -> list[dict]:
    """Group words into caption lines, breaking at punctuation or length."""
    chunks, cur = [], []
    for w in words:
        cur.append(w)
        text = " ".join(x["word"] for x in cur)
        end_punct = w["word"][-1:] in ".!?;:,"
        if len(cur) >= max_words or len(text) >= max_chars or (end_punct and len(cur) >= 3) \
                or w["word"][-1:] in ".!?":
            chunks.append(cur)
            cur = []
    if cur:
        if chunks and len(cur) == 1:
            chunks[-1].extend(cur)
        else:
            chunks.append(cur)
    out = []
    for i, c in enumerate(chunks):
        nxt = chunks[i + 1][0]["start"] if i + 1 < len(chunks) else c[-1]["end"] + 0.4
        out.append({"start": c[0]["start"], "end": min(nxt, c[-1]["end"] + 0.6), "words": c})
    return out


def cue_times(labels: list[str], words: list[dict], scene_start: float, scene_len: float,
              lead: float = 0.1, explicit: list[str | None] | None = None,
              min_t: float = 0.25) -> list[float]:
    """Scene-local reveal time for each label: when a keyword of it is spoken, else interpolated.

    Unmatched labels are spread evenly between their matched neighbours, so reveals always
    follow narration order and never bunch up.
    """
    n = len(labels)
    if n == 0:
        return []
    found: list[float | None] = [None] * n
    cursor = 0
    for i, label in enumerate(labels):
        toks = _tokens(explicit[i] if explicit and explicit[i] else label)
        for j in range(cursor, len(words)):
            wt = _tokens(words[j]["word"])
            if wt and any(w == tk or (len(tk) > 3 and w.startswith(tk[:4]) and len(w) > 3)
                          for w in wt for tk in toks):
                found[i] = max(min_t, words[j]["start"] - scene_start - lead)
                cursor = j + 1
                break
    if words:
        span_a = max(min_t, words[0]["start"] - scene_start)
        span_b = max(span_a + 0.1, words[-1]["start"] - scene_start)
    else:
        span_a, span_b = min_t, max(min_t + 0.5, scene_len * 0.6)
    out: list[float] = []
    i = 0
    while i < n:
        if found[i] is not None:
            out.append(found[i])  # type: ignore[arg-type]
            i += 1
            continue
        j = i
        while j < n and found[j] is None:
            j += 1
        a = out[-1] if out else span_a - (span_b - span_a) / max(n, 1)
        b = found[j] if j < n else span_b
        if j >= n and out:
            b = max(b, a + 0.3 * (j - i))
        gap = j - i
        for k in range(gap):
            out.append(max(min_t, a + (b - a) * (k + 1) / (gap + (1 if j < n else 0))))
        i = j
    # enforce non-decreasing
    for k in range(1, n):
        out[k] = max(out[k], out[k - 1])
    return [round(x, 3) for x in out]


def mix_audio(timeline: dict, results: dict[str, TTSResult | None], out_wav, sr: int = 24000) -> float:
    """Place each scene's narration at its audio_offset; returns total audio seconds."""
    total = int(math.ceil(timeline["total_seconds"] * sr))
    buf = np.zeros(total, dtype=np.float32)
    for sc in timeline["scenes"]:
        r = results.get(sc["id"])
        if not r:
            continue
        audio, file_sr = sf.read(str(r.wav_path), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if file_sr != sr:
            from .providers.tts.common import resample
            audio = resample(audio, file_sr, sr)
        a = int(round(sc["audio_offset"] * sr))
        seg = audio[: max(0, total - a)]
        buf[a:a + len(seg)] += seg
    peak = float(np.max(np.abs(buf))) if buf.size else 0.0
    if peak > 0.98:
        buf *= 0.98 / peak
    sf.write(str(out_wav), buf, sr, subtype="PCM_16")
    return total / sr


def timing_report(timeline: dict) -> str:
    """Table proving scene boundaries sit on the narration."""
    rows = ["scene  start   end    first-word  last-word  lead(s)  tail(s)  first words"]
    for sc in timeline["scenes"]:
        ns, ne = sc["narration_start"], sc["narration_end"]
        if ns is None:
            rows.append(f"{sc['id']:<6} {sc['start']:6.2f} {sc['end']:6.2f}   (silent scene)")
            continue
        first = " ".join(w["word"] for w in sc["words"][:4])
        rows.append(f"{sc['id']:<6} {sc['start']:6.2f} {sc['end']:6.2f}   {ns:8.2f}   {ne:8.2f}  "
                    f"{ns - sc['start']:6.2f}  {sc['end'] - ne:7.2f}  {first}")
    return "\n".join(rows)
