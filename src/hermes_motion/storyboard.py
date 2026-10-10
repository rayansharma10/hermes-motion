"""Storyboard schema, forgiving normalisation and validation with self-correctable errors.

The calling bot (often a small local model) writes storyboard.json. We are lenient about
shape (aliases, strings instead of objects) and strict about meaning, and every error names
the exact path and what is expected.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import jsonschema

TEMPLATES = [
    "title", "bullets", "diagram", "code", "chart",
    "comparison", "timeline", "callout", "custom",
]
PRESETS = ["clean", "broadcast", "terminal", "editorial", "custom"]
TRANSITIONS = ["fade", "slide", "cut"]

STORYBOARD_SCHEMA: dict = {
    "$schema": "http://json-schema.org/draft-07/schema#",
    "title": "hermes-motion storyboard",
    "type": "object",
    "required": ["scenes"],
    "properties": {
        "title": {"type": "string"},
        "fps": {"enum": [24, 30]},
        "target_seconds": {"type": "number", "exclusiveMinimum": 0},
        "style": {
            "type": "object",
            "properties": {
                "preset": {"enum": PRESETS},
                "tokens": {"type": "object"},
                "from_reference": {"type": ["string", "null"]},
            },
        },
        "voice": {
            "type": "object",
            "properties": {
                "provider": {"type": "string"},
                "name": {"type": "string"},
                "accent": {"type": "string"},
                "gender": {"type": "string"},
                "speed": {"type": "number", "minimum": 0.5, "maximum": 2.0},
                "tone": {"type": "string"},
            },
        },
        "captions": {"type": "boolean"},
        "music": {"type": ["string", "null"]},
        "scenes": {
            "type": "array",
            "minItems": 1,
            "items": {
                "type": "object",
                "required": ["template"],
                "properties": {
                    "id": {"type": "string"},
                    "narration": {"type": "string"},
                    "template": {"enum": TEMPLATES},
                    "data": {"type": "object"},
                    "min_seconds": {"type": "number", "minimum": 0},
                    "transition": {"enum": TRANSITIONS},
                },
            },
        },
    },
}

_TEMPLATE_HINTS = {
    "title": ["title", "subtitle", "kicker"],
    "bullets": ["heading", "items"],
    "diagram": ["heading", "nodes", "edges", "layout"],
    "code": ["heading", "language", "code", "highlight"],
    "chart": ["heading", "type", "labels", "values", "unit"],
    "comparison": ["heading", "left", "right"],
    "timeline": ["heading", "events"],
    "callout": ["heading", "text", "points"],
    "custom": ["html"],
}


class StoryboardError(ValueError):
    """Raised with a list of human/bot readable problems."""

    def __init__(self, problems: list[str]):
        self.problems = problems
        super().__init__("Invalid storyboard:\n  - " + "\n  - ".join(problems))


def _infer_template(data: dict) -> str | None:
    if "nodes" in data:
        return "diagram"
    if "code" in data:
        return "code"
    if "values" in data:
        return "chart"
    if "events" in data:
        return "timeline"
    if "left" in data and "right" in data:
        return "comparison"
    if "html" in data:
        return "custom"
    if "items" in data:
        return "bullets"
    if "text" in data or "points" in data:
        return "callout"
    if "title" in data:
        return "title"
    return None


def _as_list(v: Any) -> list:
    if v is None:
        return []
    if isinstance(v, str):
        return [s.strip(" -*\u2022") for s in v.splitlines() if s.strip()]
    return list(v)


def _norm_scene_data(template: str, d: dict) -> dict:
    d = dict(d)
    if template == "bullets":
        d["items"] = [i if isinstance(i, str) else (i.get("text") or i.get("label") or str(i))
                      for i in _as_list(d.get("items"))]
    elif template == "diagram":
        nodes = []
        for n in _as_list(d.get("nodes")):
            if isinstance(n, str):
                n = {"id": re.sub(r"\W+", "_", n.lower()).strip("_") or n, "label": n}
            n = dict(n)
            n.setdefault("label", n.get("id", ""))
            n.setdefault("id", re.sub(r"\W+", "_", str(n["label"]).lower()).strip("_"))
            nodes.append(n)
        ids = {n["id"] for n in nodes}
        by_label = {n["label"].lower(): n["id"] for n in nodes}
        edges = []
        for e in _as_list(d.get("edges")):
            if isinstance(e, str):
                m = re.split(r"\s*(?:->|=>|\u2192)\s*", e)
                if len(m) != 2:
                    raise StoryboardError([f"diagram edge {e!r} must look like 'a -> b'"])
                e = {"from": m[0], "to": m[1]}
            elif isinstance(e, (list, tuple)) and len(e) >= 2:
                e = {"from": e[0], "to": e[1], **({"label": e[2]} if len(e) > 2 else {})}
            e = dict(e)
            if "source" in e:
                e["from"] = e.pop("source")
            if "target" in e:
                e["to"] = e.pop("target")
            for end in ("from", "to"):
                v = e.get(end)
                if v not in ids and isinstance(v, str) and v.lower() in by_label:
                    e[end] = by_label[v.lower()]
            edges.append(e)
        d["nodes"], d["edges"] = nodes, edges
    elif template == "timeline":
        d["events"] = [e if isinstance(e, dict) else {"label": str(e)} for e in _as_list(d.get("events"))]
    elif template == "callout":
        pts = []
        for p in _as_list(d.get("points")):
            pts.append(p if isinstance(p, dict) else {"title": "", "text": str(p)})
        d["points"] = pts
    elif template == "comparison":
        for side in ("left", "right"):
            s = d.get(side)
            if isinstance(s, dict):
                s = dict(s)
                s["items"] = _as_list(s.get("items"))
                d[side] = s
    elif template == "chart":
        d["labels"] = [str(x) for x in _as_list(d.get("labels"))]
        d["values"] = _as_list(d.get("values"))
    return d


def normalize(raw: dict, base_dir: Path | None = None) -> dict:
    """Return a cleaned copy (aliases resolved, ids assigned). Raises StoryboardError."""
    if not isinstance(raw, dict):
        raise StoryboardError(["top level must be a JSON object with a 'scenes' array"])
    sb = json.loads(json.dumps(raw))
    scenes_in = sb.get("scenes")
    if not isinstance(scenes_in, list) or not scenes_in:
        raise StoryboardError(["'scenes' must be a non-empty array of scene objects"])
    problems: list[str] = []
    scenes = []
    for i, sc in enumerate(scenes_in):
        where = f"scenes[{i}]"
        if not isinstance(sc, dict):
            problems.append(f"{where} must be an object")
            continue
        sc = dict(sc)
        if "type" in sc and "template" not in sc:
            sc["template"] = sc.pop("type")
        if "text" in sc and "narration" not in sc:
            sc["narration"] = sc.pop("text")
        data = sc.get("data")
        if data is None:  # allow fields at scene level
            data = {k: v for k, v in sc.items()
                    if k not in ("id", "narration", "template", "min_seconds", "transition", "data")}
            for k in list(data):
                sc.pop(k)
        if not isinstance(data, dict):
            problems.append(f"{where}.data must be an object")
            continue
        if "template" not in sc:
            guess = _infer_template(data)
            if guess:
                sc["template"] = guess
        if sc.get("template") not in TEMPLATES:
            problems.append(
                f"{where}.template is {sc.get('template')!r}; must be one of {TEMPLATES}")
            continue
        try:
            sc["data"] = _norm_scene_data(sc["template"], data)
        except StoryboardError as e:
            problems.extend(f"{where}: {p}" for p in e.problems)
            continue
        sc.setdefault("id", f"s{i + 1}")
        sc["narration"] = (sc.get("narration") or "").strip()
        sc.setdefault("transition", "fade")
        if not sc["narration"] and not sc.get("min_seconds"):
            sc["min_seconds"] = 3.0
        scenes.append(sc)
    sb["scenes"] = scenes
    if "fps" in sb and isinstance(sb["fps"], (int, float)):
        sb["fps"] = int(sb["fps"])
    if problems:
        raise StoryboardError(problems)
    return sb


def _semantic_checks(sb: dict, base_dir: Path | None) -> list[str]:
    problems = []
    seen = set()
    for i, sc in enumerate(sb["scenes"]):
        w = f"scenes[{i}]"
        if sc["id"] in seen:
            problems.append(f"{w}.id {sc['id']!r} is duplicated; ids must be unique")
        seen.add(sc["id"])
        d, t = sc["data"], sc["template"]
        if t == "title" and not d.get("title"):
            problems.append(f"{w}.data.title is required for template 'title'")
        if t == "bullets" and not d.get("items"):
            problems.append(f"{w}.data.items must be a non-empty list of strings")
        if t == "diagram":
            ids = {n["id"] for n in d["nodes"]}
            if not d["nodes"]:
                problems.append(f"{w}.data.nodes must list at least one node ({{id,label}})")
            for j, e in enumerate(d["edges"]):
                for end in ("from", "to"):
                    if e.get(end) not in ids:
                        problems.append(
                            f"{w}.data.edges[{j}].{end}={e.get(end)!r} is not a node id; "
                            f"node ids are {sorted(ids)}")
        if t == "code" and not d.get("code"):
            problems.append(f"{w}.data.code must be a non-empty string")
        if t == "chart":
            if len(d["labels"]) != len(d["values"]) or not d["values"]:
                problems.append(f"{w}.data.labels and values must be equal-length, non-empty lists")
            elif not all(isinstance(v, (int, float)) for v in d["values"]):
                problems.append(f"{w}.data.values must all be numbers")
        if t == "comparison":
            for side in ("left", "right"):
                if not isinstance(d.get(side), dict) or not d[side].get("items"):
                    problems.append(f"{w}.data.{side} must be {{title, items:[...]}}")
        if t == "timeline" and not d["events"]:
            problems.append(f"{w}.data.events must be a non-empty list")
        if t == "callout" and not (d.get("text") or d.get("points")):
            problems.append(f"{w}.data needs 'text' and/or 'points'")
        if t == "custom":
            html = d.get("html")
            if not html:
                problems.append(f"{w}.data.html must be a path to an HTML file")
            elif base_dir is not None and not (Path(base_dir) / html).exists():
                problems.append(f"{w}.data.html file not found: {html} (relative to the storyboard)")
    return problems


def validate(raw: dict, base_dir: Path | None = None) -> dict:
    """Normalise then validate. Returns the clean storyboard or raises StoryboardError."""
    sb = normalize(raw, base_dir)
    validator = jsonschema.Draft7Validator(STORYBOARD_SCHEMA)
    problems = []
    for err in sorted(validator.iter_errors(sb), key=lambda e: list(e.absolute_path)):
        path = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
        problems.append(f"${path}: {err.message}")
    problems += _semantic_checks(sb, base_dir)
    if problems:
        raise StoryboardError(problems)
    return sb


def load(path: str | Path) -> dict:
    p = Path(path)
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise StoryboardError([f"{p.name} is not valid JSON: {e}"]) from e
    return validate(raw, p.parent)
