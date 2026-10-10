---
name: hermes-motion
description: Use when the user asks for an explainer, concept, project or presentation video. Turns a prompt into a narrated 1080p MP4 (scenes, voice-over, captions) with no API keys.
version: 0.1.0
license: MIT
metadata:
  hermes:
    tags: [video, explainer, tts, presentation, ffmpeg]
---

# hermes-motion

You write a `storyboard.json`; the tool narrates it, animates it and encodes an MP4. Everything runs
locally (Kokoro TTS, headless Chromium, ffmpeg). The video is code, never a video-generation model.

## Workflow

1. Plan 3-6 scenes from the user's request. Write ONE short narration per scene (about 6-10 words
   per scene for a 15 s clip; about 2.3 words/second overall). Pick a template per scene.
2. Save the storyboard (schema below) to a file, for example `work/storyboard.json`.
3. Validate and self-correct until it prints `OK`:
   `python <skill>/scripts/motion.py validate work/storyboard.json`
   Every error names the exact path and the allowed values; fix and re-run.
4. Render: `python <skill>/scripts/motion.py render work/storyboard.json -o out/video.mp4`
   It prints a timing table (scene starts vs. spoken words) and a JSON summary with the final length.
5. Check the summary: `seconds` near what the user asked, `warnings` empty. If too long, cut narration words.
6. Deliver the file with `MEDIA:/absolute/path/to/out/video.mp4`.

First run downloads TTS models (~350 MB) into `~/.cache/hermes-motion`. If anything fails, run
`python <skill>/scripts/motion.py doctor` and follow the `fix:` lines.

## Storyboard

```json
{
  "title": "Short title",
  "fps": 30,
  "target_seconds": 15,
  "style": {"preset": "clean"},
  "voice": {"accent": "british", "gender": "male", "speed": 1.2},
  "captions": true,
  "scenes": [
    {"id": "hook", "template": "title", "narration": "Words spoken over this scene.",
     "data": {"kicker": "Topic", "title": "Big headline"}}
  ]
}
```

- `style.preset`: `clean` (light, default), `broadcast` (dark, fast), `terminal`, `editorial`.
  Override colours with `style.tokens` (`bg, fg, accent, muted, surface, line`). To match a reference
  clip: `motion.py analyze-ref clip.mp4 -o style.json`, then `"style": {"from_reference": "style.json"}`.
- `voice`: `accent` british|american, `gender` male|female, `speed` 0.5-2 (1.2-1.3 suits short clips),
  or an exact `name` (see `motion.py voices`).
- `captions`: true by default. `music`: path to an audio file or null.
- Scene length follows the narration automatically. `min_seconds` forces a longer scene.
  `transition`: fade (default) | slide | cut.

### Templates and their `data`

| template   | data |
|------------|------|
| title      | `title` (required), `subtitle`, `kicker` |
| bullets    | `heading`, `items`: ["..."] |
| diagram    | `heading`, `nodes`: [{id,label,sub?,kind?: accent/muted}] or ["A","B"], `edges`: ["a -> b"], `layout`: lr (default) or tb |
| code       | `heading`, `language`, `code`, `highlight`: [line numbers] |
| chart      | `heading`, `type`: bar/line, `labels`: [...], `values`: [numbers], `unit` |
| comparison | `heading`, `left`: {title, items}, `right`: {title, items} |
| timeline   | `heading`, `events`: [{label, detail?}] |
| callout    | `heading`, `text`, `points`: [{title,text}] or ["..."] |
| custom     | `html`: path to your own HTML fragment (see docs/STYLE.md) |

Items appear when their keyword is spoken, so use the same words in `narration` and in labels
(for example narration "Dev, uni and hardware bots" with nodes labelled dev, uni, hardware).
Keep labels short (under 24 characters); at most 5 nodes per diagram column, 6 bullets, 3-4 callout points.

## Rules

- Do not touch Hermes' own `tts` tool; this skill has its own voice pipeline.
- No secrets or personal data in storyboards.
- Output is always 1920x1080, 16:9. Other aspect ratios are not supported.
- Switch voice engine without editing code: add `--tts piper` (or `sapi`) to `render`.
