"""Basic RefAnalyzer: abstract style traits from reference clips via ffmpeg/ffprobe + numpy.

Only aggregate traits are extracted (pacing, palette, loudness, aspect). No footage, frames
or text from the reference are stored or copied.
"""
from __future__ import annotations

import colorsys
import json
import re
import shutil
import subprocess
from pathlib import Path

import numpy as np

from ..base import ProviderUnavailable


def _hex(rgb) -> str:
    r, g, b = (int(max(0, min(255, round(float(x))))) for x in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def _lum(rgb) -> float:
    r, g, b = (x / 255.0 for x in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _mix(a, b, t):
    return [x * (1 - t) + y * t for x, y in zip(a, b)]


def kmeans(px: np.ndarray, k: int = 6, iters: int = 15, seed: int = 0):
    rng = np.random.default_rng(seed)
    px = px.astype(np.float32)
    centers = px[rng.choice(len(px), size=min(k, len(px)), replace=False)]
    for _ in range(iters):
        d = ((px[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        lab = d.argmin(axis=1)
        for i in range(len(centers)):
            m = lab == i
            if m.any():
                centers[i] = px[m].mean(axis=0)
    counts = np.bincount(lab, minlength=len(centers))
    order = np.argsort(-counts)
    return centers[order], counts[order] / counts.sum()


def tokens_from_traits(palette: list[tuple], weights: list[float], avg_shot: float | None) -> dict:
    """Map palette + pacing to style tokens (merged over a preset by the renderer)."""
    cols = [np.array(p, dtype=float) for p in palette]
    bg = cols[0]
    fg = np.array([20, 22, 26.0]) if _lum(bg) > 0.5 else np.array([240, 242, 246.0])

    def sat(c):
        h, s, v = colorsys.rgb_to_hsv(*(x / 255 for x in c))
        return s * v

    cand = [(sat(c), c) for c, w in zip(cols, weights) if w > 0.02 and _lum(c) not in (0.0, 1.0)]
    cand = [x for x in cand if x[0] > 0.25]
    accent = max(cand, key=lambda x: x[0])[1] if cand else np.array([217, 72, 15.0])
    on_acc = np.array([255, 255, 255.0]) if _lum(accent) < 0.6 else np.array([20, 22, 26.0])
    tokens = {
        "bg": _hex(bg), "fg": _hex(fg), "muted": _hex(_mix(fg, bg, 0.45)), "accent": _hex(accent),
        "surface": _hex(_mix(bg, np.array([255.0] * 3), 0.55 if _lum(bg) > 0.5 else 0.06)),
        "line": _hex(_mix(fg, bg, 0.82)), "on_accent": _hex(on_acc),
        "caption_bg": "rgba(0,0,0,0.78)", "caption_fg": "#ffffff",
    }
    if avg_shot is not None:
        if avg_shot < 2.0:
            tokens.update(easing="snappy", intensity=1.3, density="high")
        elif avg_shot < 5.0:
            tokens.update(easing="smooth", intensity=1.0, density="medium")
        else:
            tokens.update(easing="inout", intensity=0.8, density="low")
    return tokens


class BasicRefAnalyzer:
    name = "basic"

    def __init__(self, cfg: dict):
        self.cfg = cfg.get("refs", {})

    def _probe(self, clip: str) -> dict:
        r = subprocess.run(["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", clip],
                           capture_output=True, text=True)
        if r.returncode != 0:
            raise ProviderUnavailable(f"ffprobe could not read {clip}: {r.stderr.strip()[-200:]}")
        return json.loads(r.stdout)

    def _cuts(self, clip: str, duration: float) -> list[float]:
        thr = float(self.cfg.get("scene_threshold", 0.3))
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", clip, "-an",
                            "-vf", f"select='gt(scene,{thr})',showinfo", "-f", "null", "-"],
                           capture_output=True, text=True)
        return [float(m) for m in re.findall(r"pts_time:([0-9.]+)", r.stderr)]

    def _frames(self, clip: str, duration: float, n: int) -> np.ndarray:
        rate = max(n / max(duration, 0.1), 0.01)
        r = subprocess.run(["ffmpeg", "-v", "error", "-i", clip, "-an", "-vf", f"fps={rate:.5f},scale=64:36",
                            "-f", "rawvideo", "-pix_fmt", "rgb24", "-"], capture_output=True)
        buf = np.frombuffer(r.stdout, dtype=np.uint8)
        return buf[: (len(buf) // 3) * 3].reshape(-1, 3)

    def _volume(self, clip: str) -> float | None:
        r = subprocess.run(["ffmpeg", "-hide_banner", "-i", clip, "-vn", "-af", "volumedetect", "-f", "null", "-"],
                           capture_output=True, text=True)
        m = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", r.stderr)
        return float(m.group(1)) if m else None

    def analyze(self, clips: list[str]) -> dict:
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise ProviderUnavailable("ffmpeg/ffprobe not on PATH")
        all_px, shots, per_clip = [], [], []
        total_dur = 0.0
        for clip in clips:
            info = self._probe(clip)
            v = next((s for s in info["streams"] if s["codec_type"] == "video"), None)
            if not v:
                raise ProviderUnavailable(f"{clip} has no video stream")
            dur = float(info["format"].get("duration") or v.get("duration") or 0)
            num, _, den = v.get("r_frame_rate", "30/1").partition("/")
            fps = float(num) / float(den or 1)
            cuts = self._cuts(clip, dur)
            bounds = [0.0] + cuts + [dur]
            shots += [b - a for a, b in zip(bounds, bounds[1:]) if b - a > 0.05]
            total_dur += dur
            all_px.append(self._frames(clip, dur, int(self.cfg.get("sample_frames", 24))))
            per_clip.append({"width": v["width"], "height": v["height"], "fps": round(fps, 2),
                             "duration": round(dur, 2), "cuts": len(cuts), "loudness_mean_db": self._volume(clip),
                             "has_audio": any(s["codec_type"] == "audio" for s in info["streams"])})
        px = np.concatenate(all_px)
        centers, weights = kmeans(px, 6)
        avg_shot = float(np.mean(shots)) if shots else None
        tokens = tokens_from_traits([tuple(c) for c in centers], list(weights), avg_shot)
        return {
            "source": "hermes-motion basic RefAnalyzer (abstract traits only)",
            "clips": len(clips),
            "palette": [{"hex": _hex(c), "weight": round(float(w), 3)} for c, w in zip(centers, weights)],
            "pacing": {"avg_shot_seconds": round(avg_shot, 2) if avg_shot else None,
                       "cuts_per_min": round(len(shots) / (total_dur / 60), 1) if total_dur else None},
            "motion_intensity": tokens.get("intensity"),
            "density": tokens.get("density"),
            "easing_family": tokens.get("easing"),
            "caption_style": "unknown (OCR not enabled in the basic analyzer)",
            "font_category": "sans (open fonts only: system stack or fonts under OFL)",
            "per_clip": per_clip,
            "tokens": tokens,
        }
