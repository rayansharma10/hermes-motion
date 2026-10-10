"""Windows SAPI via PowerShell: zero-install last-resort fallback (Windows only, robotic)."""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

import soundfile as sf

from ..base import TTSResult
from . import voices
from .common import synth_clauses

_PS = r"""
Add-Type -AssemblyName System.Speech
$s = New-Object System.Speech.Synthesis.SpeechSynthesizer
$want = $env:HM_VOICE
$gender = $env:HM_GENDER
$picked = $false
if ($want) {
  foreach ($v in $s.GetInstalledVoices()) {
    if ($v.VoiceInfo.Name -like "*$want*") { $s.SelectVoice($v.VoiceInfo.Name); $picked = $true; break }
  }
}
if (-not $picked -and $gender) {
  try { $s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::$gender) } catch {}
}
$s.Rate = [int]$env:HM_RATE
$s.SetOutputToWaveFile($env:HM_OUT)
$s.Speak([System.IO.File]::ReadAllText($env:HM_TEXT))
$s.Dispose()
"""


class SapiTTS:
    name = "sapi"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def available(self) -> tuple[bool, str]:
        if sys.platform != "win32":
            return False, "SAPI is Windows-only"
        return True, "ok"

    def synthesize(self, text: str, voice_opts: dict, out_wav: Path) -> TTSResult:
        import os
        voice = voice_opts.get("name") or voices.pick(voices.SAPI, voice_opts, "")
        gender = "Female" if str(voice_opts.get("gender", "")).lower().startswith("f") else "Male"
        rate = max(-10, min(10, round((float(voice_opts.get("speed", 1.0)) - 1.0) * 10)))

        def clause(txt):
            with tempfile.TemporaryDirectory() as d:
                tf, wf = Path(d, "t.txt"), Path(d, "o.wav")
                tf.write_text(txt, encoding="utf-8")
                env = {**os.environ, "HM_VOICE": voice, "HM_GENDER": gender,
                       "HM_RATE": str(rate), "HM_TEXT": str(tf), "HM_OUT": str(wf)}
                subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _PS],
                               env=env, check=True, capture_output=True, timeout=120)
                audio, sr = sf.read(str(wf), dtype="float32")
                if audio.ndim > 1:
                    audio = audio.mean(axis=1)
                return audio, sr

        return synth_clauses(text, clause, out_wav, self.name, voice or f"system-{gender.lower()}")
