"""Piper (MIT) fallback. Needs the optional extra: ``uv sync --extra piper``."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from ... import config as cfgmod
from ..base import TTSResult
from . import models, voices
from .common import synth_clauses


class PiperTTS:
    name = "piper"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.cache = cfgmod.cache_dir(cfg)
        self._voices: dict = {}

    def available(self) -> tuple[bool, str]:
        try:
            import piper  # noqa: F401
        except Exception as e:
            return False, f"piper-tts not installed (uv sync --extra piper): {e}"
        return True, "ok (voice model downloads on first use, ~60 MB)"

    def _load(self, voice: str):
        if voice not in self._voices:
            from piper import PiperVoice
            extra = models.piper_urls(voice)  # validates the voice id
            unpinned = bool((self.cfg.get("tts", {}).get("piper") or {}).get("allow_unpinned"))
            onnx = models.ensure(f"{voice}.onnx", self.cache, extra, allow_unpinned=unpinned)
            models.ensure(f"{voice}.onnx.json", self.cache, extra, allow_unpinned=unpinned)
            self._voices[voice] = PiperVoice.load(str(onnx))
        return self._voices[voice]

    def synthesize(self, text: str, voice_opts: dict, out_wav: Path) -> TTSResult:
        voice = voice_opts.get("name") or voices.pick(voices.PIPER, voice_opts, "en_US-ryan-medium")
        v = self._load(voice)
        speed = float(voice_opts.get("speed", 1.0))
        from piper import SynthesisConfig
        syn = SynthesisConfig(length_scale=1.0 / max(speed, 0.1))

        def clause(txt):
            parts = [np.asarray(c.audio_float_array, dtype=np.float32).reshape(-1)
                     for c in v.synthesize(txt, syn_config=syn)]
            audio = np.concatenate(parts) if parts else np.zeros(1, np.float32)
            return audio, v.config.sample_rate

        return synth_clauses(text, clause, out_wav, self.name, voice)
