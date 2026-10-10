# hermes-motion — SPEC

Prompt-in, MP4-out explainer videos for Hermes Agent. Public, MIT-licensed, usable by any Hermes setup.
Inspired by Claude Motion: the video is CODE (editable scenes), never a video-generation model.

## Goals
- A Hermes skill (bot-callable) that turns a prompt (+ optional reference clips) into a narrated 1080p MP4.
- Modular: every stage is a swappable provider behind a small interface; all knobs in one config file.
- Free and local by default. No API keys required. CPU-safe (AMD GPU optional, never required).
- Terminal CLI is a later phase; design the core as a library with a thin CLI shim from day one.

## Fixed design decisions
- Output: 1920x1080, 16:9, fps 24 or 30 (default 30, configurable). Other aspect ratios are out of scope.
- Use cases: uni concept explainers, hackathon project videos, project presentations.
- Style ADAPTS to the prompt and can be learned from reference clips (see Reference ingestion).
- Voice (TTS) is prompt-controllable: voice, accent, gender, speed, tone.
- Captions and music: decided per prompt. Default = captions on, music off.
- TTS applies to the video pipeline only (do NOT touch Hermes' own `tts` toolset).
- Narration drives timing: generate audio first, get word timestamps, then time scenes to the words.
- Public repo, so: no secrets, no personal paths, no author-specific assumptions in code. Examples may use generic content.

## Architecture
```
prompt (+ refs) -> [Planner] -> storyboard.json -> [Narration/TTS] -> audio + word timings
                                   |                                   |
                                   +--> [Scene authoring: HTML/CSS/JS] <+  (scenes timed to words)
                                              |
                                        [Renderer] -> frames -> [Encoder (ffmpeg)] -> out.mp4
```
Provider interfaces (Python Protocols or JSON-RPC-free plain classes, one file each, registered via config):
- `Planner`  : prompt/refs -> storyboard (the calling bot's LLM does this; the library only defines + validates the schema).
- `TTSProvider`: `synthesize(text, voice_opts) -> wav + word_timings`.
- `Renderer`  : `render(scene_dir, timeline, fps, size) -> frames/` .
- `Encoder`   : frames + audio (+captions/music) -> mp4.
- `RefAnalyzer`: clip -> style.json.

## Rendering (default provider: html-playwright)
- Scenes are plain HTML/CSS/JS + a tiny runtime `motion.js` exposing a deterministic timeline: `window.__seek(tSeconds)` sets every animation to that time. NO real-time recording; capture frame-by-frame so output is exact and reproducible.
- Prefer Web Animations API / CSS vars driven by `__seek`; optionally allow GSAP-style libs if bundled locally (check licence; keep default dependency-free).
- Headless Chromium via Playwright (MIT/Apache). Do not use Remotion (source-available licence is a problem for a public tool) — but keep the Renderer interface clean so someone could add a Remotion provider.
- Built-in scene primitives/templates: title, bullet-reveal, diagram (nodes+arrows with animated flow), code block with line highlight, chart (bar/line draw-on), comparison, timeline, callout, lower-third caption. Primitives are style-token driven (colours, fonts, easing, spacing) so a style.json restyles everything.
- Escape hatch: the planner/bot may author a fully custom scene HTML file.

## Encoding
- ffmpeg: libx264 by default (always works). Optional `h264_amf` (AMD hardware encode; machine has RX 9070) selectable in config with automatic fallback to libx264. yuv420p, faststart, AAC audio.
- Never depend on GPU for correctness. Detect and report.

## TTS (default provider chain)
1. Kokoro-82M via ONNX runtime on CPU (Apache-2.0). Primary: best naturalness for cost. Has multiple voices incl. British/American, male/female.
2. Piper (MIT) fallback: faster, lighter.
3. Windows SAPI via PowerShell as last-resort zero-install fallback (Windows only, robotic).
- Word-level timestamps: use provider alignment if available, else forced-alignment fallback (e.g. estimate from phoneme/char durations, or a tiny local aligner). Must produce `[{word,start,end}]`.
- Voice selection from prompt: storyboard carries `voice: {name|accent|gender, speed}`; a voice registry maps descriptive attributes to concrete voices per provider.
- Models download on first use into a configurable cache dir (default ~/.cache/hermes-motion). Pin versions + checksums.
- Python env managed with `uv` (project has pyproject.toml; `uv run`). No global pip.

## Reference ingestion (RefAnalyzer)
Input: one or more local clips/URLs the user supplies (respect copyright: analysis only extracts abstract style traits, never copies footage).
Extract with ffmpeg/ffprobe: scene-cut detection -> avg shot length/pacing; dominant palette (k-means over sampled frames); aspect/fps; loudness; caption presence (optional OCR if cheap). Optionally pass sampled keyframes to a vision model (via the calling bot) for qualitative style notes (typography feel, motion feel, density).
Output `style.json`: palette, font category suggestions (use open fonts only, e.g. bundled/Google Fonts under OFL), easing curve family, pacing (cuts/min, avg scene length), motion intensity, density, caption style. This is merged with defaults and feeds the primitives' style tokens.
No reference given -> style is derived from the prompt (storyboard `style` block) with sane defaults.

## Config (single file, `motion.config.yaml`, layered: defaults < user < project < per-run overrides)
Resolution/fps, renderer, encoder + hw-encode toggle, tts provider chain, voice defaults, cache dir, captions on/off + style, music on/off + folder, style defaults, paths for fonts/assets, parallelism (workers), tmp dir. Every key documented in docs/CONFIG.md. Per-run overrides via function args / CLI flags.

## Hermes integration
- A skill (`SKILL.md` + scripts/) installable by copying into any Hermes skills dir, plus `hermes skills`-compatible metadata. The skill tells the calling bot how to: (1) write a storyboard.json from the user's prompt per schema, (2) call `motion render storyboard.json`, (3) deliver the MP4 via `MEDIA:/abs/path.mp4`.
- Skill must work with a small local model: the storyboard schema should be forgiving, validated with clear error messages the bot can self-correct from, with `motion validate`.
- Provide a `motion doctor` command: checks ffmpeg, chromium, python, models, GPU encoder availability, prints fixes.
- The bot-facing entry point can be a script (`scripts/motion.py` or `uv run motion ...`) — a CLI shim over the library is therefore needed in Phase 1 even though end-user CLI polish is Phase 3.

## Storyboard schema (sketch; finalise in code with JSON Schema + examples)
```json
{
 "title": "...", "fps": 30,
 "style": {"preset": "clean|broadcast|terminal|editorial|custom", "tokens": {}, "from_reference": "refs/style.json"},
 "voice": {"provider": "kokoro", "accent": "british", "gender": "male", "speed": 1.0},
 "captions": true, "music": null,
 "scenes": [
   {"id": "s1", "narration": "text spoken over this scene", "template": "diagram",
    "data": {"nodes": [...], "edges": [...]}, "min_seconds": 2.0, "transition": "fade"}
 ]
}
```
Scene duration = narration duration (from TTS) + padding, unless `min_seconds` larger. Total length reported; warn if it exceeds an optional `target_seconds`.

## Repo layout
```
hermes-motion/
  pyproject.toml  (uv)   motion.config.yaml (defaults)   LICENSE (MIT)   README.md   SPEC.md   AGENTS.md
  src/hermes_motion/ {cli.py, config.py, storyboard.py, pipeline.py, providers/{tts,render,encode,refs}/ ...}
  runtime/ (motion.js + scene templates + style tokens)   skill/ (SKILL.md, scripts/)
  examples/ (storyboards)   docs/ (CONFIG.md, PROVIDERS.md, STYLE.md, SKILL-INSTALL.md)   tests/
```

## Phases and gates
- P1 (this build): library + minimal CLI shim, html-playwright renderer, Kokoro+Piper+SAPI TTS, ffmpeg encoder, primitives, config, `doctor`, `validate`, skill, tests, and the acceptance clip.
- P2: RefAnalyzer (reference clips -> style.json) fully working + docs. (Implement a working basic version in P1 if time permits; otherwise stub with clear TODO and interface.)
- P3: polished end-user CLI, more primitives, music mixing, alternate renderer providers.

## Acceptance (P1 done = ALL true, with real tool output shown)
1. `motion doctor` passes on this Windows machine.
2. Acceptance clip: a ~15 second 1080p 30fps narrated explainer (examples/agent-team.json), burned-in captions, British male voice, MP4 at out/agent-team.mp4 (repo-relative, gitignored). Verify with ffprobe: 1920x1080, ~15s (14-16.5s), 30fps, h264+aac, audio not silent (measure mean volume with ffmpeg volumedetect), and extract >=3 frames at different times and look at them (use the vision tool) to confirm scenes are legible and not blank/overlapping.
3. Narration timing: scene boundaries land on the narration (check word timings vs scene starts in a log).
4. Swapping a provider via config alone (e.g. tts: piper instead of kokoro) works, proven by a second short render.
5. Unit tests pass (`uv run pytest`). Fresh-clone install instructions in README actually work (test in a temp clone).
6. Repo hygiene for a PUBLIC repo: no secrets, no absolute personal paths in code/docs (except the acceptance output path in this task, keep it out of the repo), MIT LICENSE, third-party model/font licences listed in NOTICE.md.
