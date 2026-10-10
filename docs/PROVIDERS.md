# Providers

Every stage of the pipeline is a small class behind a Protocol, selected by name via config.
The registry maps `(kind, name)` to `"package.module:ClassName"`.

## Interfaces (`src/hermes_motion/providers/base.py`)

All providers expose `name` and, except `Planner`, an `available() -> (bool, str)` method whose
string explains, when false, the exact fix.

```python
class TTSProvider(Protocol):
    name: str
    def available(self) -> tuple[bool, str]: ...
    def synthesize(self, text: str, voice_opts: dict, out_wav: Path) -> TTSResult: ...

class Renderer(Protocol):
    name: str
    def available(self) -> tuple[bool, str]: ...
    def render(self, scene_html: Path, total_seconds: float, fps: int,
               size: tuple[int, int], frames_dir: Path) -> int: ...   # returns frame count

class Encoder(Protocol):
    name: str
    def available(self) -> tuple[bool, str]: ...
    def encode(self, frames_dir: Path, fps: int, audio: Path | None, out_mp4: Path,
               music: Path | None = None, duration: float | None = None) -> dict: ...

class RefAnalyzer(Protocol):
    name: str
    def analyze(self, clips: list[str]) -> dict: ...                  # -> style.json

class Planner(Protocol):
    def plan(self, prompt: str, refs: list[dict] | None = None) -> dict: ...
```

The `Planner` interface is not implemented in-process: the calling bot's LLM writes the
storyboard, and the library only validates it (`storyboard.validate`).

Shared result types:

```python
@dataclass
class Word:      word: str; start: float; end: float          # seconds

@dataclass
class TTSResult:
    wav_path: Path; duration: float; words: list[Word]
    provider: str; voice: str
    sample_rate: int = 24000
    alignment: str = "estimated"    # "native" | "estimated"
```

`ProviderUnavailable` is raised when a provider cannot run here; its message says how to fix it.

## Registry

The built-ins live in `_REGISTRY`:

| kind | names |
|------|-------|
| `tts` | `kokoro`, `piper`, `sapi` |
| `renderer` | `html-playwright` |
| `encoder` | `ffmpeg` |
| `refs` | `basic` |

```python
from hermes_motion.providers import base

base.register("tts", "mytts", "mypkg.tts:MyTTS")   # add/replace an entry
base.names("tts")                                   # -> sorted names
prov = base.create("tts", "mytts", cfg)             # constructs Class(cfg)
```

`create()` imports the module and calls `Class(cfg)` with the whole config dict. Unknown names
raise `ProviderUnavailable` listing the available ones.

> Note: there is no entry-point mechanism. Providers come from the built-in registry or from the
> `providers` config key, e.g. `providers: {tts: {mytts: "pkg.mod:Class"}}` (registered before the
> pipeline runs). From Python you can also call `base.register()` yourself.

## Adding a TTS provider (worked example)

```python
# mypkg/tts.py
from pathlib import Path
from hermes_motion.providers.base import TTSResult
from hermes_motion.providers.tts import voices
from hermes_motion.providers.tts.common import synth_clauses

class MyTTS:
    name = "mytts"

    def __init__(self, cfg: dict):
        self.cfg = cfg

    def available(self) -> tuple[bool, str]:
        try:
            import my_engine  # noqa: F401
        except Exception as e:
            return False, f"my-engine not installed: {e}"
        return True, "ok"

    def synthesize(self, text: str, voice_opts: dict, out_wav: Path) -> TTSResult:
        voice = voice_opts.get("name") or voices.pick(MY_VOICES, voice_opts, "default-voice")

        def clause(txt):
            audio, sr = my_engine.say(txt, voice, speed=float(voice_opts.get("speed", 1.0)))
            return audio, sr          # float32 mono ndarray + sample rate

        return synth_clauses(text, clause, out_wav, self.name, voice)
```

Then register it and select it:

```python
base.register("tts", "mytts", "mypkg.tts:MyTTS")
```

```
motion render sb.json --set tts.chain=[mytts]
```

`synth_clauses` handles clause splitting, resampling to 24 kHz, silence trimming, pause
insertion, WAV writing and word-time estimation, so a provider only needs to turn one clause of
text into mono audio.

## The TTS fallback chain

`providers/tts/chain.py::synthesize` is the pipeline entry point:

1. `tts.chain` from config (default `[kokoro, piper, sapi]`).
2. If the storyboard sets `voice.provider`, move it to the front.
3. If `tts.strict` is truthy, keep only the first entry.
4. Try each in order: construct, call `available()`, then `synthesize()`. The first success
   returns. A provider that is unavailable, or raises `ProviderUnavailable`, or crashes, is
   logged and skipped.
5. If none work, raise `ProviderUnavailable` listing every failure.

Providers, in default order:

- **kokoro** — Kokoro-82M via `kokoro-onnx` on CPU. Voices `bm_george`/`bf_emma` (British),
  `am_michael`/`af_heart` (American).
- **piper** — Piper via the optional `piper` extra. Faster, lighter. Voice ids like
  `en_GB-alan-medium`.
- **sapi** — Windows SAPI through PowerShell. Zero-install, Windows-only, robotic. Matches the
  requested voice by substring against installed voices; falls back to `SelectVoiceByHints`
  by gender. Voices `George`/`Hazel`/`David`/`Zira`.

## Word timing (clause-level synthesis + weighted estimation)

No engine used here exposes native word timings, so `TTSResult.alignment` is `"estimated"`.

`synth_clauses` (in `providers/tts/common.py`) splits the text into clauses at `.`/`!`/`?`/`;`/`:`
(`align.split_clauses`), synthesises one clause at a time, and stitches the audio with short
pauses (0.16 s after sentence punctuation, 0.12 s otherwise). Clause boundaries are therefore
exact.

`align.estimate_words` distributes the words of each clause across the silence-trimmed voiced
span, weighted by a speech-effort score per word:

```
weight = 1.0 + 0.55*letters + 1.1*vowel_groups + 1.5*digits
```

with a ×1.25 penalty for a trailing `,;:` and ×1.4 for `.!?`. Cumulative normalised weights give
each word a `[start, end)` slot inside the clause, offset by the clause's position in the audio
stream. This tracks real speech rhythm closely enough to time reveals and captions. There is no
forced aligner; if a provider ever produced native timings, it would report `alignment="native"`.

## Model cache and sha256 pinning

Models are downloaded on first use by `providers/tts/models.py` into
`<cache_dir>/models/` (`cache_dir` from config, default `~/.cache/hermes-motion`). No model file
is committed to the repo. `motion doctor --fetch` pre-downloads and verifies them.

- Kokoro: `kokoro-v1.0.onnx` and `voices-v1.0.bin` from the kokoro-onnx release, both pinned to a
  sha256.
- Piper: voice files are derived from the `rhasspy/piper-voices` collection. The bundled default
  `en_GB-alan-medium` (`.onnx` + `.onnx.json`) is pinned; other voice ids are derived
  unpinned (`piper_urls`).

`models.ensure(name, cache, extra=None, download=True)`:

- returns the cached file if it exists and (has no digest or) its sha256 matches;
- deletes and re-downloads a file whose digest mismatches;
- with `download=False`, raises `ProviderUnavailable` when the file is absent (used by
  `available()` and `doctor`);
- downloads to a `.part` file, verifies the sha256, then atomically renames into place; a
  checksum mismatch or network error leaves no partial file.

## Encoder: h264_amf fallback

`providers/encode/ffmpeg.py::FfmpegEncoder.encode` builds an ordered list of codecs to try:

- if `encoder.hw_encode` is true, `encoder.hw_codec` (`h264_amf`) goes first;
- then `encoder.codec` (default `libx264`);
- `libx264` is appended last if it is not already present.

Each codec is attempted with a full ffmpeg invocation; the first that exits 0 wins and is
returned as `{"codec": <name>, "fallback_errors": [...]}`. Failures are collected (last stderr
line each) and surfaced in the pipeline warnings; if all fail, `ProviderUnavailable` is raised
with the list. So enabling hardware encode never breaks a render — it silently falls back to
libx264 on CPU.

`hw_encoder_works(codec)` (used by `doctor`) is stricter than a codec listing check: it actually
encodes three synthetic frames, because a listed hardware encoder can still fail without a
driver or GPU.

Software path: `-c:v libx264 -preset <preset> -crf <crf>`. Hardware path:
`-quality quality -rc cqp -qp_i/-qp_p/-qp_b <min(crf+2,30)>`. Both use `-pix_fmt yuv420p
-movflags +faststart`; audio is AAC at `audio_bitrate`, 48 kHz; `-t <seconds>` trims to the
timeline length. When music is mixed, `[2:a]` is volume-scaled and `amix`-ed with narration
(`duration=first:normalize=0`).

ffmpeg is invoked as an external program (found on `PATH`) and is not bundled.

## RefAnalyzer

`providers/refs/basic.py::BasicRefAnalyzer.analyze(clips)` uses ffprobe/ffmpeg plus numpy:
scene-cut detection (`scene_threshold`), dominant palette via k-means over sampled frames
(`sample_frames`), shot-length pacing, aspect/fps and mean loudness. It extracts abstract traits
only — no footage, frames or text from the reference are stored. Output is a style.json dict
(documented in [STYLE.md](STYLE.md)). Requires `ffmpeg` and `ffprobe` on `PATH`.
