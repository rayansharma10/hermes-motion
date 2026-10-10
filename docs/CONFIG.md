# Configuration

Every knob lives in `motion.config.yaml`. The file shipped with the package (repo root,
or `hermes_motion/motion.config.yaml` when installed) holds the built-in defaults.

## Layering

Later layers win. For dict values the merge is deep (missing keys fall through); any other
value is replaced outright.

| # | Layer | Source |
|---|-------|--------|
| 1 | built-in defaults | the `motion.config.yaml` shipped with the package |
| 2 | user | `~/.config/hermes-motion/config.yaml` |
| 3 | project | `./motion.config.yaml` (current working directory) |
| 4 | explicit file | `--config FILE` (or `config_file=` argument) |
| 5 | per-run | `--set key=value` flags, CLI shortcuts, or a dict of function overrides |

The project layer is skipped when it resolves to the same file as a built-in default, so
running from the repo root does not double-apply the shipped defaults.

### Overrides

`--set KEY=VALUE` splits on the first `=`, treats `KEY` as a dotted path, and parses
`VALUE` as YAML (so `[piper]`, `24`, `true`, `1.0` all work):

```
motion render sb.json --set video.fps=24
motion render sb.json --set tts.chain=[piper]
motion render sb.json --set encoder.hw_encode=true --set encoder.crf=20
motion render sb.json --set 'tts.voice={accent: american, gender: female}'
```

Inline shortcuts on `render` (equivalent to the shown `--set`):

| Flag | Equivalent |
|------|-----------|
| `--tts NAME` | `--set tts.chain=[NAME]` |
| `--fps N` | `--set video.fps=N` |
| `--hw` | `--set encoder.hw_encode=true` |

### Swapping the TTS provider

`tts.chain` is tried in order; the first provider that reports available and succeeds wins.
To use Piper only (instead of the default `[kokoro, piper, sapi]`):

```
motion render sb.json --set tts.chain=[piper]
# or the shorthand:
motion render sb.json --tts piper
```

A storyboard's `voice.provider` is moved to the front of the chain for that render.

## Keys

### `video`

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `width` | int | `1920` | Output width in pixels. |
| `height` | int | `1080` | Output height in pixels. |
| `fps` | int | `30` | Frame rate; `24` or `30`. A storyboard's `fps` overrides this. |
| `scene_lead` | float (s) | `0.15` | Picture before a scene's first spoken word. |
| `scene_tail` | float (s) | `0.25` | Picture after a scene's last spoken word. |

### `pipeline`

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `tmp_dir` | path / null | `null` | Working-directory root; `null` = system temp. |
| `keep_workdir` | bool | `false` | If true, copy the work dir (frames, `index.html`, `timeline.json`) next to the output as `<out>.work/`. |
| `workers` | int | `3` | Parallel Chromium pages used by the renderer. |

### top-level

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `cache_dir` | path / null | `null` | Where TTS models are downloaded; `null` = `~/.cache/hermes-motion`. |

### `tts`

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `chain` | list[str] | `[kokoro, piper, sapi]` | Providers tried in order. |
| `strict` | bool | *unset* | If true, only the first provider in the (possibly reordered) chain is tried; no fallback. Not present in the shipped config; read by the chain. |
| `voice.accent` | str | `british` | `british`/`american` (aliases: `uk`, `gb`, `english` → british; anything else → american). |
| `voice.gender` | str | `male` | `male`/`female` (a value starting with `f` → female). |
| `voice.speed` | float | `1.0` | Speaking rate; per-provider mapping (see below). |
| `kokoro` | map | `{}` | Reserved for per-provider options. |
| `piper` | map | `{}` | Reserved. |
| `sapi` | map | `{}` | Reserved. |

A storyboard `voice` object is merged over `tts.voice` for that render. `voice.name` (an exact
provider voice id) overrides accent/gender selection; `voice.provider` forces that provider to
the front of the chain. `speed` maps to Kokoro/Piper directly and to SAPI rate as
`clamp(round((speed-1)*10), -10, 10)`.

### `renderer`

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `provider` | str | `html-playwright` | Renderer registry name. |
| `frame_format` | str | `jpeg` | `jpeg` (fast) or `png` (lossless). |
| `jpeg_quality` | int | `95` | JPEG quality when `frame_format` is `jpeg`. |
| `fonts_dir` | path / null | `null` | Folder of `.ttf/.otf/.woff/.woff2` files loaded as `@font-face`. User supplies and licenses these. |

### `encoder`

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `provider` | str | `ffmpeg` | Encoder registry name. |
| `codec` | str | `libx264` | Software codec (always available). |
| `hw_encode` | bool | `false` | Try `hw_codec` first, fall back to `codec`/`libx264`. |
| `hw_codec` | str | `h264_amf` | Hardware codec name (AMD AMF). |
| `crf` | int | `18` | libx264 CRF. For the hardware path this becomes a constant quantiser `min(crf+2, 30)` applied to I/P/B. |
| `preset` | str | `medium` | libx264 `-preset`. |
| `audio_bitrate` | str | `192k` | AAC bitrate (48 kHz). |

### `captions`

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `enabled` | bool | `true` | Burn in captions. A storyboard `captions` boolean overrides this. |
| `position` | str | `bottom` | `bottom` or `top`. |
| `highlight_words` | bool | `true` | Highlight the currently spoken word (adds the `hl` class). |

### `music`

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `enabled` | bool | `false` | Mix background music when no storyboard `music` is set. |
| `folder` | path / null | `null` | Folder scanned for the first audio file (`.mp3/.wav/.ogg/.m4a/.flac`). |
| `volume` | float | `0.12` | Music gain when mixing. |

A storyboard `music` string takes precedence over the folder; it is resolved relative to the
storyboard, trimmed to the video length, looped (`-stream_loop -1`), mixed with narration.

### `style`

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `preset` | str | `clean` | `clean`, `broadcast`, `terminal`, `editorial`, or `custom` (`custom` acts as `clean`). |
| `tokens` | map | `{}` | Token overrides merged over the preset. |
| `from_reference` | path / null | `null` | style.json to merge tokens from. |

Merge order and the full token set: see [STYLE.md](STYLE.md).

### `refs`

| Key | Type | Default | Meaning |
|-----|------|---------|---------|
| `provider` | str | `basic` | RefAnalyzer registry name. |
| `sample_frames` | int | `24` | Frames sampled per clip for the palette. |
| `scene_threshold` | float | `0.3` | ffmpeg scene-change threshold for cut detection. |

## Reading the config in code

```python
from hermes_motion import config
cfg = config.load_config(config_file=None, overrides=["video.fps=24"], project_dir=None)
cfg["video"]["fps"]          # -> 24
```

`config.load_config(config_file=None, overrides=None, project_dir=None)` mirrors the CLI.
`config.cache_dir(cfg)` resolves and creates the model cache directory.
