"""ffmpeg encoder: libx264 by default, optional AMD h264_amf with automatic fallback."""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path

from ..base import ProviderUnavailable

log = logging.getLogger("hermes_motion")


def find_ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


def list_encoders() -> str:
    exe = find_ffmpeg()
    if not exe:
        return ""
    return subprocess.run([exe, "-hide_banner", "-encoders"], capture_output=True, text=True).stdout


def hw_encoder_works(codec: str = "h264_amf") -> tuple[bool, str]:
    """Actually try to encode 3 frames; a listed encoder may still lack a GPU/driver."""
    exe = find_ffmpeg()
    if not exe:
        return False, "ffmpeg not found"
    if codec not in list_encoders():
        return False, f"{codec} not compiled into this ffmpeg"
    r = subprocess.run(
        [exe, "-hide_banner", "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=1280x720:r=30",
         "-frames:v", "3", "-c:v", codec, "-pix_fmt", "yuv420p", "-f", "null", "-"],
        capture_output=True, text=True)
    if r.returncode == 0:
        return True, "ok"
    return False, (r.stderr.strip().splitlines() or ["failed"])[-1]


class FfmpegEncoder:
    name = "ffmpeg"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.used_codec: str | None = None

    def available(self) -> tuple[bool, str]:
        exe = find_ffmpeg()
        if not exe:
            return False, "ffmpeg not on PATH (install from https://ffmpeg.org/download.html)"
        if "libx264" not in list_encoders():
            return False, "this ffmpeg build lacks libx264; use a build that includes it"
        return True, f"ok ({exe})"

    def _cmd(self, frames_dir: Path, fps: int, audio: Path | None, out: Path, codec: str,
             music: Path | None, duration: float | None) -> list[str]:
        e = self.cfg["encoder"]
        ext = "jpg" if next(frames_dir.glob("*.jpg"), None) else "png"
        cmd = [find_ffmpeg() or "ffmpeg", "-y", "-hide_banner", "-v", "error", "-framerate", str(fps),
               "-i", str(frames_dir / f"%06d.{ext}")]
        n_audio = 0
        if audio:
            cmd += ["-i", str(audio)]
            n_audio += 1
        if music:
            cmd += ["-stream_loop", "-1", "-i", str(music)]
            n_audio += 1
        if codec == "libx264":
            cmd += ["-c:v", "libx264", "-preset", str(e.get("preset", "medium")), "-crf", str(e.get("crf", 18))]
        else:  # hardware encoder: constant quantiser keeps quality predictable
            qp = str(min(int(e.get("crf", 18)) + 2, 30))
            cmd += ["-c:v", codec, "-quality", "quality", "-rc", "cqp", "-qp_i", qp, "-qp_p", qp, "-qp_b", qp]
        cmd += ["-vf", "scale=in_range=full:out_range=limited,format=yuv420p", "-pix_fmt", "yuv420p",
                "-color_range", "tv", "-r", str(fps), "-movflags", "+faststart"]
        if n_audio == 2:
            vol = float(self.cfg.get("music", {}).get("volume", 0.12))
            cmd += ["-filter_complex", f"[2:a]volume={vol}[m];[1:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "0:v", "-map", "[a]"]
        elif n_audio == 1:
            cmd += ["-map", "0:v", "-map", "1:a"]
        if n_audio:
            cmd += ["-c:a", "aac", "-b:a", str(e.get("audio_bitrate", "192k")), "-ar", "48000"]
        if duration:
            cmd += ["-t", f"{duration:.3f}"]
        cmd.append(str(out))
        return cmd

    def encode(self, frames_dir: Path, fps: int, audio: Path | None, out_mp4: Path,
               music: Path | None = None, duration: float | None = None) -> dict:
        ok, why = self.available()
        if not ok:
            raise ProviderUnavailable(why)
        out_mp4.parent.mkdir(parents=True, exist_ok=True)
        e = self.cfg["encoder"]
        tries = []
        if e.get("hw_encode"):
            tries.append(e.get("hw_codec", "h264_amf"))
        tries.append(e.get("codec", "libx264"))
        if tries[-1] != "libx264":
            tries.append("libx264")
        errors = []
        for codec in tries:
            r = subprocess.run(self._cmd(frames_dir, fps, audio, out_mp4, codec, music, duration),
                               capture_output=True, text=True)
            if r.returncode == 0:
                self.used_codec = codec
                return {"codec": codec, "fallback_errors": errors}
            msg = (r.stderr.strip().splitlines() or ["unknown ffmpeg error"])[-1]
            errors.append(f"{codec}: {msg}")
            log.warning("encoder %s failed (%s); trying next", codec, msg)
        raise ProviderUnavailable("ffmpeg encode failed:\n  - " + "\n  - ".join(errors))
