"""`motion doctor`: check every dependency and print the exact fix for anything missing."""
from __future__ import annotations

import shutil
import subprocess
import sys
from dataclasses import dataclass

from . import config as cfgmod
from .providers import base
from .providers.encode import ffmpeg as ff
from .providers.tts import models


@dataclass
class Check:
    name: str
    status: str  # ok | warn | fail
    detail: str
    fix: str = ""


def run_checks(cfg: dict, fetch: bool = False, deep: bool = True) -> list[Check]:
    out: list[Check] = []
    v = sys.version_info
    out.append(Check("python", "ok", f"{v.major}.{v.minor}.{v.micro}"))

    exe = shutil.which("ffmpeg")
    if not exe:
        out.append(Check("ffmpeg", "fail", "not found on PATH",
                         "install ffmpeg (https://ffmpeg.org/download.html) and add it to PATH"))
    else:
        ver = subprocess.run([exe, "-version"], capture_output=True, text=True).stdout.splitlines()[0]
        enc = ff.list_encoders()
        miss = [c for c in ("libx264", "aac") if c not in enc]
        out.append(Check("ffmpeg", "fail" if miss else "ok",
                         ver if not miss else f"missing encoders: {miss}",
                         "use an ffmpeg build with libx264 and aac" if miss else ""))
    if not shutil.which("ffprobe"):
        out.append(Check("ffprobe", "warn", "not found (needed for reference analysis and verification)",
                         "ships with ffmpeg; add its folder to PATH"))

    r_ok, r_why = base.create("renderer", cfg["renderer"]["provider"], cfg).available()
    out.append(Check(f"renderer:{cfg['renderer']['provider']}", "ok" if r_ok else "fail", r_why,
                     "uv sync && uv run playwright install chromium" if not r_ok else ""))

    cache = cfgmod.cache_dir(cfg)
    out.append(Check("cache dir", "ok", str(cache)))

    for name in cfg["tts"].get("chain", []):
        prov = base.create("tts", name, cfg)
        ok, why = prov.available()
        status = "ok" if ok else "warn"
        fix = ""
        if name == "piper" and not ok:
            fix = "uv sync --extra piper"
        if name == "sapi" and not ok:
            fix = "Windows only; ignore on other platforms"
        out.append(Check(f"tts:{name}", status, why, fix))

    if fetch:
        for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin", "en_GB-alan-medium.onnx", "en_GB-alan-medium.onnx.json"):
            try:
                models.ensure(f, cache)
                out.append(Check(f"model:{f}", "ok", "present and checksum verified"))
            except base.ProviderUnavailable as e:
                out.append(Check(f"model:{f}", "fail", str(e), "check your network connection and retry"))

    if deep and "kokoro" in cfg["tts"].get("chain", []):
        try:
            models.ensure("kokoro-v1.0.onnx", cache, download=False)
            out.append(Check("model:kokoro", "ok", "cached"))
        except base.ProviderUnavailable:
            out.append(Check("model:kokoro", "warn", "not cached yet (downloads ~350 MB on first render)",
                             "uv run motion doctor --fetch"))

    hw_ok, hw_why = ff.hw_encoder_works(cfg["encoder"].get("hw_codec", "h264_amf"))
    out.append(Check("gpu encoder", "ok" if hw_ok else "warn",
                     f"{cfg['encoder'].get('hw_codec', 'h264_amf')}: {hw_why}"
                     + ("" if hw_ok else " (optional; libx264 on CPU is always used as fallback)"),
                     "set encoder.hw_encode: true to use it" if hw_ok and not cfg["encoder"].get("hw_encode") else ""))
    return out


def format_report(checks: list[Check]) -> str:
    sym = {"ok": "[ OK ]", "warn": "[WARN]", "fail": "[FAIL]"}
    lines = []
    for c in checks:
        lines.append(f"{sym[c.status]} {c.name}: {c.detail}")
        if c.fix and c.status != "ok":
            lines.append(f"         fix: {c.fix}")
        elif c.fix:
            lines.append(f"         tip: {c.fix}")
    fails = sum(c.status == "fail" for c in checks)
    lines.append("")
    lines.append("doctor: all required checks passed" if not fails else f"doctor: {fails} required check(s) failed")
    return "\n".join(lines)
