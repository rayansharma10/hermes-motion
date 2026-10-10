# Installing the Hermes skill

The skill turns a prompt into a narrated MP4 using the `motion` library. It is a normal Hermes
skill folder: a `SKILL.md` plus a `scripts/` directory (including `scripts/motion.py`, the
bot-facing entry point wrapper). Copy it into any Hermes skills directory — no packaging step
required.

## Install

1. Clone or locate the hermes-motion repo checkout.
2. Copy the `skill/` folder to your Hermes skills directory as `hermes-motion/`:

   ```
   <hermes skills dir>/hermes-motion/SKILL.md
   <hermes skills dir>/hermes-motion/scripts/motion.py
   ```

   The exact skills directory is the one your Hermes profile uses (the same place other skills
   live; see the Hermes docs). Copying the folder in is the whole install.

3. Point the skill at the checkout. Either:

   - **Set `HERMES_MOTION_HOME`** to the repo checkout, so the skill can find the library,
     `runtime/`, and `motion.config.yaml` regardless of where it is invoked:

     ```
     HERMES_MOTION_HOME=/path/to/hermes-motion
     ```

     (Windows: set it as an environment variable for the Hermes process.)

   - **Or run from inside the checkout** — the CLI and library resolve `runtime/` and
     `motion.config.yaml` relative to the package and the current working directory, so invoking
     the skill with the repo as the working directory also works.

The Python environment is managed with `uv`. From the checkout:

```
uv sync                          # core deps (Playwright, Kokoro, ffmpeg wrapper deps)
uv sync --extra piper            # optional Piper TTS (piper-tts is GPL-3.0-or-later; see NOTICE.md)
uv run playwright install chromium
```

`ffmpeg` and `ffprobe` must be on `PATH` (they are external programs, not bundled).

## Bot workflow

The calling bot drives the pipeline in four steps.

1. **Write `storyboard.json`** from the user's prompt, per the schema. The schema is forgiving:
   `motion schema` prints the JSON Schema, and templates accept strings where objects would be
   verbose (see [STYLE.md](STYLE.md) for every template's data shape). A minimal storyboard:

   ```json
   {
     "title": "How it works",
     "fps": 30,
     "style": {"preset": "clean"},
     "voice": {"accent": "british", "gender": "male", "speed": 1.0},
     "captions": true,
     "scenes": [
       {"id": "hook", "template": "title",
        "narration": "One PC. One assistant.",
        "data": {"title": "One PC. One assistant."}},
       {"id": "flow", "template": "diagram",
        "narration": "Concierge posts jobs to the board.",
        "data": {"nodes": [{"id": "concierge", "label": "Concierge"}, {"id": "board", "label": "Board"}],
                 "edges": ["concierge -> board"]}}
     ]
   }
   ```

2. **Validate:** `motion validate storyboard.json` (add `--print` to see the normalised
   storyboard). Errors name the exact path and expectation so a small model can self-correct.
   On success it reports the scene and word counts.

3. **Render:** `motion render storyboard.json [-o out/video.mp4]`. This synthesises narration,
   builds the timeline from word timings, renders frames through headless Chromium, and encodes
   with ffmpeg. It prints a JSON result (output path, seconds, frames, fps, encoder, TTS voices,
   warnings). Useful flags: `--tts NAME`, `--fps 24|30`, `--hw`, `--set key=value`, `-q`.

4. **Deliver** the MP4 to the user with a media directive naming the absolute path:

   ```
   MEDIA:/abs/path/to/out/video.mp4
   ```

   Use the absolute path from the render result (`"output"`).

Outputs land in `out/` by default (`out/<storyboard-stem>.mp4`), alongside sidecars
`<name>.timing.txt` and `<name>.timeline.json`.

## `motion doctor`

`motion doctor` checks every dependency and prints the exact fix for anything missing:

- Python version;
- `ffmpeg` present and built with `libx264` + `aac`; `ffprobe` present;
- the configured renderer (Chromium installed via Playwright);
- the cache directory;
- each provider in `tts.chain` (availability, with the right fix: `uv sync --extra piper` for
  Piper, "Windows only" for SAPI);
- Kokoro model cache status (warns if it will download ~350 MB on first render);
- GPU encoder availability (it actually encodes test frames; optional — CPU libx264 is always
  the fallback).

`motion doctor --fetch` downloads and checksum-verifies the TTS models up front. The command
exits non-zero if any required check fails.

## Related docs

- [CONFIG.md](CONFIG.md) — every config key and the layering order.
- [PROVIDERS.md](PROVIDERS.md) — provider interfaces, adding a provider, the TTS chain.
- [STYLE.md](STYLE.md) — style tokens, presets, template data shapes, the runtime contract.
