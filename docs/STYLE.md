# Style

Style is a flat map of tokens (colours, fonts, spacing, motion) that drives every scene through
CSS variables and a small runtime config. A preset is just a named token file in
`runtime/styles/`.

## Merge order

Later layers win (`scenes.load_tokens`):

1. **preset** tokens — `runtime/styles/<preset>.json`
2. **config** `style.tokens`
3. **reference** tokens — the `tokens` object of the style.json named by
   `style.from_reference` (storyboard first, else config)
4. **storyboard** `style.tokens`

The preset is chosen by the storyboard's `style.preset`, else config `style.preset`, else
`clean`. The value `custom` is treated as `clean` (there is no separate custom token file).

## Presets

| Preset | Look |
|--------|------|
| `clean` | Light warm-neutral (`#f6f4ef`), orange accent, sans headings, `smooth` easing, radius 14. |
| `broadcast` | Dark navy, amber accent, heavy headings, `snappy` easing, high motion intensity, radius 8. |
| `terminal` | Near-black green, mono everywhere, `linear` easing, low intensity, radius 4. |
| `editorial` | Cream/paper, serif headings, red accent, `inout` easing, low density, radius 2. |
| `custom` | Alias for `clean`. Use `style.tokens` for a bespoke look. |

## Tokens (`runtime/styles/clean.json`)

Keys present in every preset file and what each controls:

| Token | Type | Applied as | Controls |
|-------|------|-----------|----------|
| `name` | str | — | Informational preset label; not consumed by the renderer. |
| `bg` | colour | `--bg` | Page/scene background. |
| `fg` | colour | `--fg` | Primary text and diagram edge strokes. |
| `muted` | colour | `--muted` | Secondary text, labels, axis. |
| `accent` | colour | `--accent` | Bars, bullets, dots, highlighted flows, chart fills. |
| `accent2` | colour | `--accent2` | Second accent (available to templates via `var(--accent2)`). |
| `surface` | colour | `--surface` | Card, node and comparison-panel fill. |
| `line` | colour | `--line` | Borders, chart axis, timeline track. |
| `on_accent` | colour | `--on-accent` | Text drawn on accent-filled elements. |
| `font_head` | font stack | `--font-head` | Headings, node labels, statements, timeline labels. |
| `font_body` | font stack | `--font-body` | Body text, captions, chart text. |
| `font_mono` | font stack | `--font-mono` | Code window and language label. |
| `weight_head` | int | `--weight-head` | Heading font weight. |
| `radius` | int (px) | `--radius` | Corner radius of cards, nodes, code window. |
| `easing` | str | `window.__CFG__.easing` | Runtime easing: `linear`, `smooth`, `snappy`, `bounce`, `inout`. |
| `intensity` | float | `window.__CFG__.intensity` | Multiplier on transform distances (rise/slide). |
| `density` | str | — | Pacing hint (`low`/`medium`/`high`); informational, not read by the renderer. |
| `caption_bg` | colour | `--caption-bg` | Caption background. |
| `caption_fg` | colour | `--caption-fg` | Caption text. |

Notes:

- `--radius` is set with a `px` suffix from the numeric token.
- `--cap-hl` (the colour of the currently spoken word in highlight mode) is read by the CSS with
  a built-in fallback of `#ffd9a8`; it is **not** wired to a token in this version — to change it
  supply a token that maps to it only if you extend `scenes.build_page`.
- The code-block palette (`.tk-*` colours) is hard-coded in `runtime/base.css`, not tokenised.

## style.json (reference analysis)

`motion analyze-ref CLIP... [-o style.json]` runs the RefAnalyzer and writes a model-independent
style file. Reference it from a storyboard with `style.from_reference` (path relative to the
storyboard) or set `style.from_reference` in config. Only the `tokens` object is consumed.

```json
{
  "source": "hermes-motion basic RefAnalyzer (abstract traits only)",
  "clips": 2,
  "palette": [{"hex": "#101623", "weight": 0.42}, {"hex": "#ffb000", "weight": 0.09}],
  "pacing": {"avg_shot_seconds": 2.4, "cuts_per_min": 25.0},
  "motion_intensity": 1.3,
  "density": "high",
  "easing_family": "snappy",
  "caption_style": "unknown (OCR not enabled in the basic analyzer)",
  "font_category": "sans (open fonts only: system stack or fonts under OFL)",
  "per_clip": [
    {"width": 1920, "height": 1080, "fps": 30.0, "duration": 42.5,
     "cuts": 18, "loudness_mean_db": -21.3, "has_audio": true}
  ],
  "tokens": {
    "bg": "#101623", "fg": "#f1f4f9", "muted": "#9aa6bb", "accent": "#ffb000",
    "surface": "#1a2335", "line": "#2c3a55", "on_accent": "#101623",
    "caption_bg": "rgba(0,0,0,0.78)", "caption_fg": "#ffffff",
    "easing": "snappy", "intensity": 1.3, "density": "high"
  }
}
```

`tokens_from_traits` derives `bg` from the dominant palette colour, `fg` from its luminance,
`accent` from the most saturated colour, plus muted/surface/line/on_accent; `easing`, `intensity`
and `density` come from average shot length (<2 s → snappy/high, <5 s → smooth/medium, else
inout/low).

## Templates and their data shapes

Set with the scene's `template`. The scene's `data` object is normalised by
`storyboard._norm_scene_data` (lenient: a bare string can stand in for many list items). All
templates accept an optional `heading`.

| Template | `data` shape |
|----------|--------------|
| `title` | `{title (required), subtitle?, kicker?}` |
| `bullets` | `{heading?, items: [str, ...] (non-empty)}` |
| `diagram` | `{heading?, layout?: "lr"\|"tb", nodes: [{id, label, sub?, kind?, cue?}], edges: [{from, to, label?}]}` |
| `code` | `{heading?, language?, code (required str), highlight?: [line numbers]}` |
| `chart` | `{heading?, type?: "bar"\|"line", labels: [str], values: [num], unit?}` |
| `comparison` | `{heading?, left: {title?, items: [...]}, right: {title?, items: [...]}}` |
| `timeline` | `{heading?, events: [{label, detail?}, ...]}` |
| `callout` | `{heading?, text?, points?: [{title?, text?}]}` (needs `text` and/or `points`) |
| `custom` | `{html: "path/to/file.html"}` (resolved relative to the storyboard) |

Normalisation details:

- **bullets** items may be strings or objects with `text`/`label`.
- **diagram** nodes may be strings (id derived from the slug of the label). Edges may be strings
  `"a -> b"` (also `=>` or `→`), or objects with `from`/`to` (aliases `source`/`target`) and an
  optional `label`. Node `kind` is `accent` (accent fill) or `muted` (dashed); anything else is
  the default node. Node `cue` overrides the words used to time its reveal. `layout` defaults to
  left-to-right.
- **chart** `type` defaults to `bar`; any non-`bar` value draws a line (dots + connecting path).
- **comparison** each side normalises `items`; `title` on the left is neutral, the right is
  accent-coloured.
- **timeline** events may be strings (become `{label}`); dots alternate above/below the line.
- **callout** points may be strings (become `{title:"", text}`).
- **code** `highlight` lists 1-based line numbers that get the highlight animation.

Scene-level conveniences: `type` is accepted for `template`; a scene `text` becomes `narration`;
fields placed at the scene top level (not under `data`) are lifted into `data`; if `template` is
omitted it is inferred from the data keys (`nodes`→diagram, `code`→code, `values`→chart,
`events`→timeline, `left`+`right`→comparison, `html`→custom, `items`→bullets, `text`/`points`→
callout, `title`→title). A scene with no narration and no `min_seconds` gets `min_seconds: 3`.

## Runtime contract (`runtime/motion.js`)

Rendering is deterministic: the renderer calls `window.__seek(t)` for each frame time and every
visual is a pure function of `t`. The runtime exposes:

- `window.__seek(t)` — set the whole page to absolute time `t` (seconds).
- `window.__ready` — a promise resolving when fonts are loaded; the renderer awaits it after
  navigation.
- `window.__duration` — end time of the last scene.
- `window.__hooks` — custom scenes may `push(function (t, scenes) {...})`; each hook is called on
  every seek.
- `window.__CFG__` — `{easing, intensity}` injected from the tokens.

### Scene DOM

```
<section class="scene" data-start="0.0" data-end="4.2" data-transition="fade"> ... </section>
```

The runtime shows a scene while `start <= t < end` (the last scene holds to `end`). Transitions:
`fade` (in over 0.35 s, out over 0.3 s), `slide` (same fade plus a horizontal translate scaled by
`intensity`), `cut` (instant). Non-visible scenes get `visibility:hidden`.

### `data-anim` elements

Any element under a scene may carry:

```
data-anim="TYPE"  data-t="DELAY"  data-d="DURATION"
```

- `data-t` — delay in **scene-local** seconds (default `0`).
- `data-d` — duration in seconds (default `0.6`).
- Progress `p = clamp((local - data-t) / data-d, 0, 1)`, eased by the token easing.

Types:

| Type | Effect |
|------|--------|
| `fade` | opacity 0→1 |
| `rise` | fade + translateY from `36*intensity` px |
| `pop` | fade + scale 0.82→1 |
| `draw` | SVG path: stroke-dashoffset from full length to 0 |
| `flow` | SVG path: travelling dashes (`stroke-dashoffset = -(t-t0)*70`) |
| `grow-y` | scaleY 0→1 from the bottom |
| `grow-x` | scaleX 0→1 from the left |
| `wipe` | clip-path reveal left→right |
| `count` | text counts up to `data-to`, `data-dec` decimals, suffix `data-unit` |
| `hl` | sets CSS var `--hl` (0→1), used to highlight a code line |

SVG animated elements pivot on their own box (`transform-box:fill-box`).

### Custom scenes

`template: "custom"` injects the file at `data.html` into the stage. It can use the same
`data-anim` contract and may register arbitrary JS via `window.__hooks`, keeping everything a
function of `t`.

## Cue timing

Templates that reveal items progressively (bullets, diagram nodes, comparison items, timeline
events, callout points, chart labels, code highlight lines) time each reveal to the narration via
`timeline.cue_times`:

- For each label, scan the scene's spoken words in order for the first word matching a keyword
  token of that label. A match is exact equality, or — for label tokens longer than 3 chars and
  spoken words longer than 3 chars — a 4-char prefix match. Stop words are ignored.
- On a match, the reveal time is `max(0.25, word.start - scene_start - 0.1)` (scene-local),
  so the item appears just before the word is spoken.
- Labels with no match are interpolated evenly between their matched neighbours, so reveals
  follow narration order and never bunch or overlap; the sequence is forced non-decreasing.
- A node's `cue` field (or the explicit labels some templates pass) overrides the search text.

Diagram edges animate relative to their target node: the edge draws starting ~0.45 s before the
target appears, its flow dashes follow 0.5 s later, and the arrowhead fades at
`t_draw + 0.4`.

Captions are grouped from the global word list (`timeline.caption_chunks`, ≤ 6 words / 38 chars,
breaking on punctuation) and shown while `start <= t < end`; each word is toggled `on`/`done` by
its own timings when `captions.highlight_words` is set.
