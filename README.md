# hermes-motion

Prompt-in, MP4-out narrated explainer videos. The video is **code**: deterministic HTML/CSS/JS scenes
captured frame by frame with headless Chromium, narrated by local text-to-speech, encoded with ffmpeg.
No video-generation model, no API keys, no GPU required.

- 1920x1080, 16:9, 30 fps (24 optional), H.264 + AAC, burned-in captions
- Narration first: audio and word timings are generated before anything is drawn, so scene length and
  on-screen reveals follow the spoken words
- Every stage (TTS, renderer, encoder, reference analyser) is a swappable provider chosen in `motion.config.yaml`
- Built as a [Hermes Agent](https://hermes-agent.nousresearch.com) skill, but usable on its own as a library and CLI
- MIT licensed. Third-party components: see [NOTICE.md](NOTICE.md)

## Requirements

- [uv](https://docs.astral.sh/uv/) (it installs Python 3.12 for you)
- [ffmpeg](https://ffmpeg.org/download.html) with libx264 and aac, on `PATH`
- About 600 MB of disk for models and Chromium (downloaded outside the repo)

Windows, macOS and Linux work. Windows is the primary dev machine; a Windows-only SAPI voice is the last-resort TTS fallback.

## Quickstart

```bash
git clone <this repo> hermes-motion
cd hermes-motion
uv sync --extra piper                    # Python deps (piper is the optional fallback voice)
uv run playwright install chromium       # headless browser, one-off
uv run motion doctor --fetch             # checks everything and downloads TTS models (~420 MB)
uv run motion render examples/quickstart.json -o out/quickstart.mp4
```

`doctor` prints a `fix:` line under anything that is missing. Models are cached in
`~/.cache/hermes-motion` (change with `cache_dir`) and verified by SHA-256.

## Make your own video

1. Write a storyboard (JSON). Start from `examples/quickstart.json`; the schema is `uv run motion schema`.
2. `uv run motion validate my.json` gives errors that say exactly what to fix.
3. `uv run motion render my.json -o out/my.mp4` prints a timing table showing each scene boundary against the spoken words.

```json
{
  "voice": {"accent": "british", "gender": "male", "speed": 1.15},
  "scenes": [
    {"template": "title", "narration": "Videos are code.", "data": {"title": "Prompt in, video out"}},
    {"template": "bullets", "narration": "Fast, local, and free.",
     "data": {"items": ["Fast", "Local", "Free"]}}
  ]
}
```

Templates: `title`, `bullets`, `diagram`, `code`, `chart`, `comparison`, `timeline`, `callout`, `custom` (your own HTML).
See [docs/STYLE.md](docs/STYLE.md).

## Swap providers with config alone

```bash
uv run motion render my.json --config examples/piper.config.yaml     # Piper instead of Kokoro
uv run motion render my.json --set video.fps=24 --set encoder.hw_encode=true
```

Config layers: defaults < `~/.config/hermes-motion/config.yaml` < `./motion.config.yaml` < `--config` < `--set`.
Keys: [docs/CONFIG.md](docs/CONFIG.md). Writing a provider: [docs/PROVIDERS.md](docs/PROVIDERS.md).

## Match a reference clip's style

```bash
uv run motion analyze-ref my-reference.mp4 -o style.json    # pacing, palette, loudness -> style tokens
```

Then set `"style": {"from_reference": "style.json"}` in the storyboard. Only abstract traits are extracted; no footage is copied.

## Use it from a Hermes agent

Copy `skill/` into your Hermes skills folder as `hermes-motion/` and point `HERMES_MOTION_HOME` at this checkout.
See [docs/SKILL-INSTALL.md](docs/SKILL-INSTALL.md).

## Commands

| command | purpose |
|---|---|
| `motion doctor [--fetch]` | check ffmpeg, Chromium, TTS, models, GPU encoder; print fixes |
| `motion validate FILE` | validate and normalise a storyboard |
| `motion render FILE -o OUT.mp4` | render (`--tts`, `--fps`, `--hw`, `--config`, `--set`) |
| `motion analyze-ref CLIPS... -o style.json` | reference clips to style tokens |
| `motion voices` | voice registry per provider |
| `motion schema` | storyboard JSON Schema |

## Development

```bash
uv sync --extra piper
uv run pytest          # tests use a fake offline TTS; render tests need ffmpeg and Chromium
```

## Notes and limits

- Word timestamps are estimated per sentence (the engines expose no alignment), accurate to roughly 100-150 ms.
- Hardware encoding (`encoder.hw_encode: true`, AMD `h264_amf`) is optional and falls back to libx264 automatically.
- Phase 1 scope: see [SPEC.md](SPEC.md) for what is planned next (polished CLI, music mixing, more renderers).
