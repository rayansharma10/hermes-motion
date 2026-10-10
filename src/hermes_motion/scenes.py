"""Scene HTML builders. One function per template; all are driven by style tokens (CSS vars)
and by narration cues, so a storyboard plus word timings fully determines the picture.

To add a template: write ``def tpl_x(data, ctx) -> str`` and add it to ``BUILDERS``.
Elements animate through ``data-anim`` attributes understood by runtime/motion.js.
"""
from __future__ import annotations

import html
import json
import re
from pathlib import Path

from . import config as cfgmod
from .timeline import caption_chunks, cue_times

W, H = 1920, 1080
CONTENT_W = 1680


def esc(x) -> str:
    return html.escape(str(x), quote=True)


def A(kind: str, t: float, d: float = 0.6) -> str:
    return f'data-anim="{kind}" data-t="{t:.3f}" data-d="{d:.3f}"'


class Ctx:
    """Per-scene helper passed to template builders."""

    def __init__(self, scene: dict, base_dir: Path | None):
        self.scene = scene
        self.words = scene["words"]
        self.start = scene["start"]
        self.length = scene["length"]
        self.base_dir = base_dir

    def cues(self, labels: list[str], explicit: list | None = None) -> list[float]:
        return cue_times(labels, self.words, self.start, self.length, explicit=explicit)

    @property
    def t0(self) -> float:
        """Scene-local time of the first spoken word (or a small default)."""
        return max(0.2, (self.scene["narration_start"] - self.start)) if self.words else 0.3

    @property
    def tend(self) -> float:
        return (self.scene["narration_end"] - self.start) if self.words else self.length * 0.7


# ----------------------------------------------------------------------------- title
def tpl_title(d, c: Ctx) -> str:
    t = 0.2
    sub = f'<div class="sub" {A("rise", t + 0.55)}>{esc(d["subtitle"])}</div>' if d.get("subtitle") else ""
    kick = f'<div class="kicker" {A("fade", t)}>{esc(d["kicker"])}</div>' if d.get("kicker") else ""
    return (f'<div class="stage tpl-title">{kick}<div class="bar" {A("grow-x", t, 0.6)}></div>'
            f'<h1 {A("rise", t + 0.2, 0.7)}>{esc(d["title"])}</h1>{sub}</div>')


# ----------------------------------------------------------------------------- bullets
def _heading(d, t=0.15) -> str:
    return f'<h2 class="heading" {A("rise", t)}>{esc(d["heading"])}</h2>' if d.get("heading") else ""


def tpl_bullets(d, c: Ctx) -> str:
    items = d["items"]
    cues = c.cues(items)
    li = "".join(f'<li {A("rise", t, 0.55)}><span>{esc(i)}</span></li>' for i, t in zip(items, cues))
    return f'<div class="stage tpl-bullets">{_heading(d)}<ul>{li}</ul></div>'


# ----------------------------------------------------------------------------- diagram
def _ranks(nodes, edges, back_ok=True) -> dict[str, int]:
    ids = [n["id"] for n in nodes]
    rank = {i: 0 for i in ids}
    for _ in range(len(ids)):  # longest-path relaxation, bounded so cycles cannot loop
        changed = False
        for e in edges:
            if e["from"] in rank and e["to"] in rank and rank[e["to"]] < rank[e["from"]] + 1 \
                    and rank[e["from"]] + 1 < len(ids):
                rank[e["to"]] = rank[e["from"]] + 1
                changed = True
        if not changed:
            break
    return rank


def tpl_diagram(d, c: Ctx) -> str:
    nodes, edges = d["nodes"], d["edges"]
    horizontal = d.get("layout", "lr") != "tb"
    has_head = bool(d.get("heading"))
    cw, ch = CONTENT_W, 790 - (120 if has_head else 0)
    rank = _ranks(nodes, edges)
    n_ranks = max(rank.values()) + 1
    layers: list[list[dict]] = [[] for _ in range(n_ranks)]
    for n in nodes:
        layers[rank[n["id"]]].append(n)
    # layout box sizes
    along, across = (cw, ch) if horizontal else (ch, cw)
    max_in_layer = max(len(l) for l in layers)
    if horizontal:
        nw = min(440, (along - 120 * (n_ranks - 1)) / n_ranks) if n_ranks > 1 else 420
        nh = min(150, (across - 26 * (max_in_layer - 1)) / max_in_layer)
    else:
        nw = min(380, (across - 40 * (max_in_layer - 1)) / max_in_layer)
        nh = min(130, (along - 70 * (n_ranks - 1)) / n_ranks)
    nw, nh = max(nw, 160), max(nh, 70)
    pos: dict[str, tuple[float, float]] = {}
    for r, layer in enumerate(layers):
        for k, n in enumerate(layer):
            if horizontal:
                x = 0 if n_ranks == 1 else r * (cw - nw) / (n_ranks - 1)
                y = (ch - nh) / 2 if len(layer) == 1 else k * (ch - nh) / (len(layer) - 1)
                if len(layer) > 1:  # keep columns compact and centred rather than full-height
                    span = min(ch - nh, (len(layer) - 1) * (nh + 34))
                    y = (ch - span - nh) / 2 + k * span / (len(layer) - 1)
            else:
                y = 0 if n_ranks == 1 else r * (ch - nh) / (n_ranks - 1)
                x = (cw - nw) / 2 if len(layer) == 1 else k * (cw - nw) / (len(layer) - 1)
            pos[n["id"]] = (x, y)
    order = [n for layer in layers for n in layer]
    labels = [n["label"] for n in order]
    cues = dict(zip([n["id"] for n in order], c.cues(labels, [n.get("cue") for n in order])))
    html_nodes = []
    for n in order:
        x, y = pos[n["id"]]
        kind = n.get("kind", "")
        sub = f'<div class="ns">{esc(n["sub"])}</div>' if n.get("sub") else ""
        html_nodes.append(
            f'<div class="node {esc(kind)}" style="left:{x:.1f}px;top:{y:.1f}px;width:{nw:.1f}px;height:{nh:.1f}px" '
            f'{A("pop", cues[n["id"]], 0.45)}><div class="nl">{esc(n["label"])}</div>{sub}</div>')
    svg, lab = [], []
    out_n = {n["id"]: [e for e in edges if e["from"] == n["id"]] for n in nodes}
    in_n = {n["id"]: [e for e in edges if e["to"] == n["id"]] for n in nodes}

    def spread(group, e, span):
        k = len(group)
        return (group.index(e) - (k - 1) / 2) * min(span / max(k, 1), 30) if k > 1 else 0.0

    for e in edges:
        (x1, y1), (x2, y2) = pos[e["from"]], pos[e["to"]]
        so, si = spread(out_n[e["from"]], e, nh * 0.6), spread(in_n[e["to"]], e, nh * 0.6)
        if horizontal:
            sx, sy, tx, ty = x1 + nw, y1 + nh / 2 + so, x2, y2 + nh / 2 + si
            if tx <= sx:  # same-rank or back edge: route below
                sx, tx = x1 + nw / 2, x2 + nw / 2
                sy, ty = y1 + nh, y2 + nh
            m = (sx + tx) / 2
            path = f"M{sx:.1f},{sy:.1f} C{m:.1f},{sy:.1f} {m:.1f},{ty:.1f} {tx - 14:.1f},{ty:.1f}"
        else:
            sx, sy, tx, ty = x1 + nw / 2 + so, y1 + nh, x2 + nw / 2 + si, y2
            m = (sy + ty) / 2
            path = f"M{sx:.1f},{sy:.1f} C{sx:.1f},{m:.1f} {tx:.1f},{m:.1f} {tx:.1f},{ty - 14:.1f}"
        t_draw = max(0.2, cues[e["to"]] - 0.45)
        svg.append(f'<path class="edge" d="{path}" {A("draw", t_draw, 0.5)}/>')
        svg.append(f'<path class="flow" d="{path}" {A("flow", t_draw + 0.5)}/>')
        ang = "M-16,-9 L2,0 L-16,9 Z"
        if horizontal:
            svg.append(f'<path d="{ang}" fill="var(--fg)" transform="translate({tx:.1f},{ty:.1f})" {A("fade", t_draw + 0.4, 0.15)}/>')
        else:
            svg.append(f'<path d="{ang}" fill="var(--fg)" transform="translate({tx:.1f},{ty:.1f}) rotate(90)" {A("fade", t_draw + 0.4, 0.15)}/>')
        if e.get("label"):
            lab.append(f'<div class="elabel" style="left:{(sx + tx) / 2:.1f}px;top:{(sy + ty) / 2:.1f}px" '
                       f'{A("fade", t_draw + 0.3)}>{esc(e["label"])}</div>')
    return (f'<div class="stage tpl-diagram">{_heading(d)}<div class="canvas">'
            f'<svg class="edges" width="{cw}" height="{ch}" viewBox="0 0 {cw} {ch}">{"".join(svg)}</svg>'
            f'{"".join(lab)}{"".join(html_nodes)}</div></div>')


# ----------------------------------------------------------------------------- code
_KW = r"\b(def|class|return|if|else|elif|for|while|import|from|as|in|not|and|or|const|let|var|function|async|await|new|try|except|catch|fn|pub|use|struct|impl|true|false|None|null|True|False)\b"


def _hilite(line: str) -> str:
    out, i = [], 0
    pat = re.compile(r"(#.*|//.*)|(\"(?:[^\"\\]|\\.)*\"|'(?:[^'\\]|\\.)*')|(\b\d+(?:\.\d+)?\b)|" + _KW)
    for m in pat.finditer(line):
        out.append(esc(line[i:m.start()]))
        cls = "tk-c" if m.group(1) else "tk-s" if m.group(2) else "tk-n" if m.group(3) else "tk-k"
        out.append(f'<span class="{cls}">{esc(m.group(0))}</span>')
        i = m.end()
    out.append(esc(line[i:]))
    return "".join(out)


def tpl_code(d, c: Ctx) -> str:
    lines = d["code"].rstrip("\n").split("\n")
    hl = [int(x) for x in d.get("highlight", [])]
    cues = c.cues([f"line{i}" for i in hl]) if hl else []
    cue_of = dict(zip(hl, cues))
    # reveal lines progressively across the first ~60% of narration
    n = len(lines)
    t_a, t_b = 0.3, max(0.8, c.tend * 0.6)
    rows = []
    for i, line in enumerate(lines, 1):
        t_line = t_a + (t_b - t_a) * (i - 1) / max(n, 1)
        inner = f'<div class="cl" {A("hl", cue_of[i], 0.5) if i in cue_of else ""}>' \
                f'<span class="ln">{i}</span><span class="tx">{_hilite(line) or "&nbsp;"}</span></div>'
        rows.append(f'<div {A("fade", t_line, 0.35)}>{inner}</div>')
    lang = f'<div class="lang" {A("fade", 0.2)}>{esc(d["language"])}</div>' if d.get("language") else ""
    return f'<div class="stage tpl-code">{_heading(d)}{lang}<div class="win">{"".join(rows)}</div></div>'


# ----------------------------------------------------------------------------- chart
def tpl_chart(d, c: Ctx) -> str:
    labels, values = d["labels"], [float(v) for v in d["values"]]
    unit = d.get("unit", "")
    has_head = bool(d.get("heading"))
    cw, chh = CONTENT_W, 790 - (120 if has_head else 0)
    base_y, top_y, left = chh - 70, 50, 20
    vmax = max(values) if max(values) > 0 else 1
    scale = (base_y - top_y) / vmax
    n = len(values)
    slot = (cw - left * 2) / n
    cues = c.cues(labels)
    parts = [f'<line class="chart-axis" x1="0" y1="{base_y}" x2="{cw}" y2="{base_y}"/>']
    dec = 0 if all(v == int(v) for v in values) else 1
    kind = d.get("type", "bar")
    pts = []
    for i, (lab, v) in enumerate(zip(labels, values)):
        cx = left + slot * (i + 0.5)
        y = base_y - v * scale
        t = cues[i]
        parts.append(f'<text x="{cx:.1f}" y="{base_y + 48}" font-size="34" text-anchor="middle" fill="var(--muted)" {A("fade", t)}>{esc(lab)}</text>')
        if kind == "bar":
            bw = min(slot * 0.55, 240)
            parts.append(f'<rect x="{cx - bw / 2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{base_y - y:.1f}" rx="6" fill="var(--accent)" {A("grow-y", t, 0.7)}/>')
        else:
            pts.append((cx, y))
            parts.append(f'<circle cx="{cx:.1f}" cy="{y:.1f}" r="11" fill="var(--accent)" {A("pop", t, 0.35)}/>')
        parts.append(f'<text x="{cx:.1f}" y="{y - 20:.1f}" font-size="40" font-weight="700" text-anchor="middle" '
                     f'{A("count", t + 0.1, 0.8)} data-to="{v}" data-dec="{dec}" data-unit="{esc(unit)}">0</text>')
    if kind != "bar" and len(pts) > 1:
        dpath = "M" + " L".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        parts.insert(1, f'<path d="{dpath}" fill="none" stroke="var(--accent)" stroke-width="7" stroke-linejoin="round" '
                        f'{A("draw", cues[0], max(0.6, cues[-1] - cues[0] + 0.3))}/>')
    return (f'<div class="stage tpl-chart">{_heading(d)}'
            f'<svg viewBox="0 0 {cw} {chh}" width="{cw}" height="{chh}">{"".join(parts)}</svg></div>')


# ----------------------------------------------------------------------------- comparison
def tpl_comparison(d, c: Ctx) -> str:
    cols = []
    all_items = d["left"]["items"] + d["right"]["items"]
    cues = c.cues(all_items)
    k = 0
    for side, cls in (("left", "l"), ("right", "r")):
        s = d[side]
        lis = []
        for it in s["items"]:
            lis.append(f'<li {A("rise", cues[k], 0.5)}>{esc(it)}</li>')
            k += 1
        cols.append(f'<div class="col {cls}" {A("rise", 0.2 if cls == "l" else 0.35, 0.6)}>'
                    f'<h3>{esc(s.get("title", ""))}</h3><ul>{"".join(lis)}</ul></div>')
    return f'<div class="stage tpl-comparison">{_heading(d)}<div class="cols">{"".join(cols)}</div></div>'


# ----------------------------------------------------------------------------- timeline
def tpl_timeline(d, c: Ctx) -> str:
    ev = d["events"]
    n = len(ev)
    cues = c.cues([e.get("label", "") for e in ev])
    cw = CONTENT_W
    parts = [f'<div class="tl-line"></div>',
             f'<div class="tl-fill" {A("wipe", 0.2, max(0.8, c.tend))}></div>']
    for i, e in enumerate(ev):
        x = cw * (i + 0.5) / n
        up = i % 2 == 0
        side = "bottom:calc(50% + 44px)" if up else "top:calc(50% + 44px)"
        det = f'<div class="d">{esc(e["detail"])}</div>' if e.get("detail") else ""
        parts.append(f'<div class="tl-dot" style="left:{x:.1f}px" {A("pop", cues[i], 0.4)}></div>')
        parts.append(f'<div class="tl-ev" style="left:{x:.1f}px;{side}" {A("rise", cues[i] + 0.1, 0.5)}>'
                     f'<div class="l">{esc(e.get("label", ""))}</div>{det}</div>')
    return f'<div class="stage tpl-timeline">{_heading(d)}<div class="tl">{"".join(parts)}</div></div>'


# ----------------------------------------------------------------------------- callout
def tpl_callout(d, c: Ctx) -> str:
    pts = d.get("points", [])
    cues = c.cues([f'{p.get("title", "")} {p.get("text", "")}' for p in pts]) if pts else []
    head = f'<div class="kicker" {A("fade", 0.2)}>{esc(d["heading"])}</div>' if d.get("heading") else ""
    stmt = f'<div class="statement" {A("rise", 0.3, 0.7)}>{esc(d["text"])}</div>' if d.get("text") else ""
    cards = []
    for i, p in enumerate(pts):
        t = f'<div class="pt-t">{esc(p["title"])}</div>' if p.get("title") else ""
        x = f'<div class="pt-x">{esc(p["text"])}</div>' if p.get("text") else ""
        cards.append(f'<div class="pt" {A("rise", cues[i], 0.55)}><div class="pn">{i + 1:02d}</div>{t}{x}</div>')
    return (f'<div class="stage tpl-callout">{head}{stmt}'
            f'<div class="points">{"".join(cards)}</div></div>')


# ----------------------------------------------------------------------------- custom
def tpl_custom(d, c: Ctx) -> str:
    p = Path(d["html"])
    if not p.is_absolute() and c.base_dir:
        p = c.base_dir / p
    return f'<div class="stage tpl-custom" style="inset:0;left:0;right:0;top:0;bottom:0">{p.read_text(encoding="utf-8")}</div>'


BUILDERS = {
    "title": tpl_title, "bullets": tpl_bullets, "diagram": tpl_diagram, "code": tpl_code,
    "chart": tpl_chart, "comparison": tpl_comparison, "timeline": tpl_timeline,
    "callout": tpl_callout, "custom": tpl_custom,
}


# ----------------------------------------------------------------------------- tokens & page
def load_tokens(sb: dict, cfg: dict, base_dir: Path | None) -> dict:
    """preset < config style.tokens < reference style.json < storyboard style.tokens."""
    rt = cfgmod.runtime_dir()
    style = {**(cfg.get("style") or {}), **(sb.get("style") or {})}
    preset = style.get("preset") or "clean"
    if preset == "custom":
        preset = "clean"
    tokens = json.loads((rt / "styles" / f"{preset}.json").read_text(encoding="utf-8"))
    tokens.update((cfg.get("style") or {}).get("tokens") or {})
    ref = style.get("from_reference") or (cfg.get("style") or {}).get("from_reference")
    if ref:
        rp = Path(ref)
        if not rp.is_absolute() and base_dir:
            rp = base_dir / rp
        tokens.update(json.loads(rp.read_text(encoding="utf-8")).get("tokens", {}))
    tokens.update((sb.get("style") or {}).get("tokens") or {})
    return tokens


def _font_faces(fonts_dir: str | None) -> str:
    if not fonts_dir:
        return ""
    out = []
    for f in sorted(Path(fonts_dir).expanduser().glob("*")):
        if f.suffix.lower() in (".ttf", ".otf", ".woff", ".woff2"):
            out.append(f'@font-face{{font-family:"{f.stem}";src:url("{f.resolve().as_uri()}")}}')
    return "\n".join(out)


def build_page(sb: dict, timeline: dict, tokens: dict, cfg: dict, base_dir: Path | None) -> str:
    rt = cfgmod.runtime_dir()
    size = (cfg["video"]["width"], cfg["video"]["height"])
    css_vars = {
        "--W": f"{size[0]}px", "--H": f"{size[1]}px",
        "--bg": tokens["bg"], "--fg": tokens["fg"], "--muted": tokens["muted"],
        "--accent": tokens["accent"], "--accent2": tokens.get("accent2", tokens["fg"]),
        "--surface": tokens["surface"], "--line": tokens["line"], "--on-accent": tokens["on_accent"],
        "--font-head": tokens["font_head"], "--font-body": tokens["font_body"], "--font-mono": tokens["font_mono"],
        "--weight-head": str(tokens["weight_head"]), "--radius": f'{tokens["radius"]}px',
        "--caption-bg": tokens["caption_bg"], "--caption-fg": tokens["caption_fg"],
    }
    root = ";".join(f"{k}:{v}" for k, v in css_vars.items())
    scenes_html = []
    all_words = []
    for sc, tl in zip(sb["scenes"], timeline["scenes"]):
        ctx = Ctx(tl, base_dir)
        body = BUILDERS[sc["template"]](sc["data"], ctx)
        scenes_html.append(
            f'<section class="scene" id="sc-{esc(sc["id"])}" data-start="{tl["start"]}" data-end="{tl["end"]}" '
            f'data-transition="{esc(sc["transition"])}">{body}</section>')
        all_words += tl["words"]
    caps_html = ""
    capcfg = cfg.get("captions", {})
    show_caps = sb.get("captions", capcfg.get("enabled", True))
    if show_caps:
        chunks = caption_chunks(all_words)
        hl = " hl" if capcfg.get("highlight_words", True) else ""
        for ch in chunks:
            ws = "".join(f'<span class="w" data-s="{w["start"]}" data-e="{w["end"]}">{esc(w["word"])}</span> '
                         for w in ch["words"])
            caps_html += f'<div class="cap{hl}" data-start="{ch["start"]:.3f}" data-end="{ch["end"]:.3f}">{ws}</div>'
    pos = "top" if capcfg.get("position") == "top" else ""
    runtime_cfg = json.dumps({"easing": tokens.get("easing", "smooth"), "intensity": tokens.get("intensity", 1.0)})
    css = (rt / "base.css").read_text(encoding="utf-8")
    js = (rt / "motion.js").read_text(encoding="utf-8")
    fonts = _font_faces(cfg.get("renderer", {}).get("fonts_dir"))
    title = esc(sb.get("title", "hermes-motion"))
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{title}</title>'
            f'<style>:root{{{root}}}\n{fonts}\n{css}</style></head><body>'
            f'<div id="frame">{"".join(scenes_html)}<div id="captions" class="{pos}">{caps_html}</div></div>'
            f'<script>window.__CFG__={runtime_cfg};</script><script>{js}</script></body></html>')
