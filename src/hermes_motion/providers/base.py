"""Provider interfaces and the registry that maps config names to implementations.

Each stage is a small class. Add your own by calling ``register(kind, name, "pkg.mod:Class")``

"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, runtime_checkable


class ProviderUnavailable(RuntimeError):
    """Raised when a provider cannot run here (missing model, binary, OS...). Message says how to fix."""


@dataclass
class Word:
    word: str
    start: float
    end: float


@dataclass
class TTSResult:
    wav_path: Path
    duration: float
    words: list[Word]
    provider: str
    voice: str
    sample_rate: int = 24000
    alignment: str = "estimated"  # "native" | "estimated"


@runtime_checkable
class TTSProvider(Protocol):
    name: str

    def available(self) -> tuple[bool, str]: ...
    def synthesize(self, text: str, voice_opts: dict, out_wav: Path) -> TTSResult: ...


@runtime_checkable
class Renderer(Protocol):
    name: str

    def available(self) -> tuple[bool, str]: ...
    def render(self, scene_html: Path, total_seconds: float, fps: int,
               size: tuple[int, int], frames_dir: Path) -> int: ...


@runtime_checkable
class Encoder(Protocol):
    name: str

    def available(self) -> tuple[bool, str]: ...
    def encode(self, frames_dir: Path, fps: int, audio: Path | None, out_mp4: Path,
               music: Path | None = None, duration: float | None = None) -> dict: ...


@runtime_checkable
class RefAnalyzer(Protocol):
    name: str

    def analyze(self, clips: list[str]) -> dict: ...


@runtime_checkable
class Planner(Protocol):
    """Planning is done by the calling bot's LLM; the library only validates the result."""

    def plan(self, prompt: str, refs: list[dict] | None = None) -> dict: ...


_REGISTRY: dict[str, dict[str, str]] = {
    "tts": {
        "kokoro": "hermes_motion.providers.tts.kokoro:KokoroTTS",
        "piper": "hermes_motion.providers.tts.piper:PiperTTS",
        "sapi": "hermes_motion.providers.tts.sapi:SapiTTS",
    },
    "renderer": {"html-playwright": "hermes_motion.providers.render.html_playwright:HtmlPlaywrightRenderer"},
    "encoder": {"ffmpeg": "hermes_motion.providers.encode.ffmpeg:FfmpegEncoder"},
    "refs": {"basic": "hermes_motion.providers.refs.basic:BasicRefAnalyzer"},
}


def register(kind: str, name: str, target: str) -> None:
    _REGISTRY.setdefault(kind, {})[name] = target


def names(kind: str) -> list[str]:
    return sorted(_REGISTRY.get(kind, {}))


def create(kind: str, name: str, cfg: dict):
    try:
        target = _REGISTRY[kind][name]
    except KeyError:
        raise ProviderUnavailable(
            f"unknown {kind} provider {name!r}; available: {names(kind)}") from None
    mod, _, cls = target.partition(":")
    return getattr(importlib.import_module(mod), cls)(cfg)
