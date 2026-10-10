import shutil
import wave

import numpy as np
import pytest

from hermes_motion import config as cfgmod
from hermes_motion.providers import base
from hermes_motion.providers.base import TTSResult, Word


class FakeTTS:
    """Deterministic offline TTS: a sine tone, ~0.35 s per word. Lets tests run with no models."""
    name = "fake"

    def __init__(self, cfg):
        pass

    def available(self):
        return True, "ok"

    def synthesize(self, text, voice_opts, out_wav):
        words = text.split()
        sr = 24000
        dur = 0.35 * len(words)
        t = np.arange(int(sr * dur)) / sr
        audio = (0.3 * np.sin(2 * np.pi * 220 * t)).astype(np.float32)
        out_wav.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(out_wav), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(sr)
            w.writeframes((audio * 32767).astype("<i2").tobytes())
        ws = [Word(x, i * 0.35, (i + 1) * 0.35) for i, x in enumerate(words)]
        return TTSResult(out_wav, dur, ws, "fake", "sine", sr, "estimated")


@pytest.fixture(autouse=True)
def _register_fake():
    base.register("tts", "fake", "conftest:FakeTTS")
    yield


@pytest.fixture
def cfg():
    c = cfgmod.load_config(project_dir="/nonexistent")
    c["tts"]["chain"] = ["fake"]
    c["pipeline"]["workers"] = 2
    return c


needs_ffmpeg = pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not on PATH")


def chromium_ok() -> bool:
    try:
        return base.create("renderer", "html-playwright", {}).available()[0]
    except Exception:
        return False


needs_chromium = pytest.mark.skipif(not chromium_ok(), reason="Playwright Chromium not installed")
