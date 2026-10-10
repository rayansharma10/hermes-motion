"""Kokoro-82M via ONNX Runtime on CPU (Apache-2.0)."""
from __future__ import annotations

from pathlib import Path

from ... import config as cfgmod
from ..base import ProviderUnavailable, TTSResult
from . import models, voices
from .common import synth_clauses


class KokoroTTS:
    name = "kokoro"

    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.cache = cfgmod.cache_dir(cfg)
        self._engine = None

    def available(self) -> tuple[bool, str]:
        try:
            import kokoro_onnx  # noqa: F401
        except Exception as e:
            return False, f"kokoro-onnx not importable: {e}"
        missing = []
        for f in ("kokoro-v1.0.onnx", "voices-v1.0.bin"):
            try:
                models.ensure(f, self.cache, download=False)
            except ProviderUnavailable:
                missing.append(f)
        if missing:
            return True, f"ok (models {missing} download on first use, ~350 MB)"
        return True, "ok"

    def _load(self):
        if self._engine is None:
            from kokoro_onnx import Kokoro
            m = models.ensure("kokoro-v1.0.onnx", self.cache)
            v = models.ensure("voices-v1.0.bin", self.cache)
            self._engine = Kokoro(str(m), str(v))
        return self._engine

    def synthesize(self, text: str, voice_opts: dict, out_wav: Path) -> TTSResult:
        eng = self._load()
        voice = voice_opts.get("name") or voices.pick(voices.KOKORO, voice_opts, "bm_george")
        known = eng.get_voices()
        if voice not in known:
            raise ProviderUnavailable(f"kokoro has no voice {voice!r}; examples: {sorted(known)[:8]}")
        try:
            lang = voices.kokoro_lang(voice)
        except ValueError as e:
            raise ProviderUnavailable(str(e)) from None
        speed = float(voice_opts.get("speed", 1.0))

        def clause(txt):
            return eng.create(txt, voice=voice, speed=speed, lang=lang)

        return synth_clauses(text, clause, out_wav, self.name, voice)
