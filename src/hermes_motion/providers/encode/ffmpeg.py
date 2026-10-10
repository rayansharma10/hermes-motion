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


def codec_args(codec: str, e: dict) -> list[str]:
    """Per-codec rate-control arguments. Only libx264 and h264_amf have been run on real hardware
    by the authors; the others follow each encoder's documented options (UNTESTED here)."""
    crf = int(e.get("crf", 18))
    qp = str(min(crf + 2, 30))
    if codec == "libx264":
        return ["-c:v", "libx264", "-preset", str(e.get("preset", "medium")), "-crf", str(crf)]
    if codec == "libx265":
        return ["-c:v", "libx265", "-preset", str(e.get("preset", "medium")), "-crf", str(crf), "-tag:v", "hvc1"]
    if codec == "h264_amf":
        return ["-c:v", codec, "-quality", "quality", "-rc", "cqp", "-qp_i", qp, "-qp_p", qp, "-qp_b", qp]
    if codec in ("h264_nvenc", "hevc_nvenc"):
        return ["-c:v", codec, "-preset", "p5", "-rc", "constqp", "-qp", qp]
    if codec in ("h264_qsv", "hevc_qsv"):
        return ["-c:v", codec, "-global_quality", qp]
    if codec in ("h264_videotoolbox", "hevc_videotoolbox"):
        return ["-c:v", codec, "-q:v", str(max(1, min(100, 100 - crf * 2)))]
    return ["-c:v", codec]  # unknown encoder: let ffmpeg use its defaults


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
        cmd += codec_args(codec, e)
        # Frames are full-range sRGB (PNG) or BT.601 JPEG; convert to limited-range BT.709 and tag
        # it explicitly so every player decodes the same colours for both frame formats.
        cmd += ["-vf", "scale=in_range=full:in_color_matrix=bt601:out_range=limited:out_color_matrix=bt709,"
                       "format=yuv420p,setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709:range=tv",
                "-pix_fmt", "yuv420p", "-color_range", "tv", "-colorspace", "bt709",
                "-color_primaries", "bt709", "-color_trc", "bt709", "-r", str(fps), "-movflags", "+faststart"]
        vol = float(self.cfg.get("music", {}).get("volume", 0.12))
        if n_audio == 2:
            cmd += ["-filter_complex", f"[2:a]volume={vol}[m];[1:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "0:v", "-map", "[a]"]
        elif n_audio == 1 and music and not audio:  # music only: still honour music.volume
            cmd += ["-filter_complex", f"[1:a]volume={vol}[a]", "-map", "0:v", "-map", "[a]"]
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
        timeout = float(e.get("timeout_seconds", 3600)) or None
        tries = []
        if e.get("hw_encode"):
            tries.append(e.get("hw_codec", "h264_amf"))
        tries.append(e.get("codec", "libx264"))
        if tries[-1] != "libx264":
            tries.append("libx264")
        errors = []
        for codec in tries:
            try:
                r = subprocess.run(self._cmd(frames_dir, fps, audio, out_mp4, codec, music, duration),
                                   capture_output=True, text=True, timeout=timeout)
                rc, stderr = r.returncode, r.stderr
            except subprocess.TimeoutExpired:
                rc, stderr = -1, f"timed out after {timeout:.0f}s (encoder.timeout_seconds)"
            if rc == 0:
                self.used_codec = codec
                return {"codec": codec, "fallback_errors": errors}
            msg = (stderr.strip().splitlines() or ["unknown ffmpeg error"])[-1]
            errors.append(f"{codec}: {msg}")
            log.warning("encoder %s failed (%s); trying next", codec, msg)
        raise ProviderUnavailable("ffmpeg encode failed:\n  - " + "\n  - ".join(errors))
