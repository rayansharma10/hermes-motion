"""Storyboard schema, forgiving normalisation and validation with self-correctable errors.

The calling bot (often a small local model) writes storyboard.json. We are lenient about
shape (aliases, strings instead of objects) and strict about meaning, and every error names
the exact path and what is expected.
"""
from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

import jsonschema

from . import paths, tokens as tokenmod

TEMPLATES = [
    "title", "bullets", "diagram", "code", "chart",
    "comparison", "timeline", "callout", "custom",
]
PRESETS = ["clean", "broadcast", "terminal", "editorial", "custom"]
TRANSITIONS = ["fade", "slide", "cut"]
AUDIO_SUFFIXES = (".mp3", ".wav", ".ogg", ".m4a", ".flac")

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
    if isinstance(v, (list, tuple)):
        return list(v)
    raise StoryboardError([f"expected a list (or a newline-separated string), got {type(v).__name__}"])


def _text_of(i: Any) -> str:
    if isinstance(i, str):
        return i
    if isinstance(i, dict):
        t = i.get("text") or i.get("label")
        if isinstance(t, str):
            return t
    raise StoryboardError([f"bullet item {i!r} must be a string (or {{\"text\": \"...\"}})"])


def _norm_scene_data(template: str, d: dict) -> dict:
    d = dict(d)
    if template == "bullets":
        d["items"] = [_text_of(i) for i in _as_list(d.get("items"))]
    elif template == "diagram":
        nodes = []
        for n in _as_list(d.get("nodes")):
            if isinstance(n, str):
                n = {"id": re.sub(r"\W+", "_", n.lower()).strip("_") or n, "label": n}
            if not isinstance(n, dict):
                raise StoryboardError([f"diagram node {n!r} must be a string or {{id, label}} object"])
            n = dict(n)
            n.setdefault("label", n.get("id", ""))
            n["label"] = str(n["label"])
            n.setdefault("id", re.sub(r"\W+", "_", n["label"].lower()).strip("_"))
            n["id"] = str(n["id"])
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
            if not isinstance(e, dict):
                raise StoryboardError([f"diagram edge {e!r} must be 'a -> b', [a, b] or {{from, to}}"])
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
                s["items"] = [str(x) for x in _as_list(s.get("items"))]
                d[side] = s
    elif template == "chart":
        d["labels"] = [str(x) for x in _as_list(d.get("labels"))]
        d["values"] = _as_list(d.get("values"))
    elif template == "code":
        hl = d.get("highlight")
        if isinstance(hl, (int, float)) and not isinstance(hl, bool):
            d["highlight"] = [hl]
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
        except (TypeError, AttributeError, ValueError, KeyError) as e:
            problems.append(f"{where}.data: {type(e).__name__}: {e}; "
                            f"check the shape of data for template {sc['template']!r}")
            continue
        sc.setdefault("id", f"s{i + 1}")
        narr = sc.get("narration")
        if narr is not None and not isinstance(narr, str):
            problems.append(f"{where}.narration must be a string, got {type(narr).__name__}")
            continue
        sc["narration"] = (narr or "").strip()
        sc.setdefault("transition", "fade")
        if not sc["narration"] and not sc.get("min_seconds"):
            sc["min_seconds"] = 3.0
        scenes.append(sc)
    sb["scenes"] = scenes
    if "fps" in sb and isinstance(sb["fps"], (int, float)) and not isinstance(sb["fps"], bool):
        if float(sb["fps"]).is_integer():
            sb["fps"] = int(sb["fps"])
        else:
            problems.append(f"$.fps: {sb['fps']} is not one of [24, 30]")
    unknown = sorted(set(sb) - set(STORYBOARD_SCHEMA["properties"]) - {"$schema"})
    if unknown:
        problems.append(f"unknown top-level key(s) {unknown}; allowed: {sorted(STORYBOARD_SCHEMA['properties'])}")
    if problems:
        raise StoryboardError(problems)
    return sb


def _semantic_checks(sb: dict, base_dir: Path | None, allow_absolute: bool = False) -> list[str]:
    problems = []
    style = sb.get("style")
    if isinstance(style, dict):
        try:
            tokenmod.sanitize(style.get("tokens"), "style.tokens")
        except ValueError as e:
            problems.append(str(e))
        if style.get("from_reference"):
            try:
                paths.resolve_inside(base_dir, style["from_reference"], (".json",), "style.from_reference",
                                     allow_absolute=allow_absolute)
            except paths.PathError as e:
                problems.append(str(e))
    if sb.get("music"):
        try:
            paths.resolve_inside(base_dir, sb["music"], AUDIO_SUFFIXES, "music", allow_absolute=allow_absolute)
        except paths.PathError as e:
            problems.append(str(e))
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
            if len(ids) != len(d["nodes"]):
                problems.append(f"{w}.data.nodes has duplicate ids; every node id must be unique "
                                f"(got {[n['id'] for n in d['nodes']]})")
            for j, e in enumerate(d["edges"]):
                for end in ("from", "to"):
                    v = e.get(end)
                    if not isinstance(v, str) or v not in ids:
                        problems.append(
                            f"{w}.data.edges[{j}].{end}={v!r} is not a node id; "
                            f"node ids are {sorted(ids)}")
        if t == "code":
            if not isinstance(d.get("code"), str) or not d.get("code"):
                problems.append(f"{w}.data.code must be a non-empty string")
            else:
                n_lines = len(d["code"].rstrip("\n").split("\n"))
                hl = d.get("highlight", [])
                if not isinstance(hl, list) or not all(
                        isinstance(x, (int, float)) and not isinstance(x, bool)
                        and float(x).is_integer() and 1 <= x <= n_lines for x in hl):
                    problems.append(f"{w}.data.highlight must be a list of line numbers between 1 and {n_lines}")
                else:
                    d["highlight"] = [int(x) for x in hl]
        if t == "chart":
            if len(d["labels"]) != len(d["values"]) or not d["values"]:
                problems.append(f"{w}.data.labels and values must be equal-length, non-empty lists")
            elif not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                         for v in d["values"]):
                problems.append(f"{w}.data.values must all be finite numbers")
            elif any(v < 0 for v in d["values"]):
                problems.append(f"{w}.data.values must not be negative")
            elif d.get("type", "bar") not in ("bar", "line"):
                problems.append(f"{w}.data.type must be 'bar' or 'line'")
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
            if not html or not isinstance(html, str):
                problems.append(f"{w}.data.html must be a path (string) to an HTML file")
            else:
                try:
                    paths.resolve_inside(base_dir, html, (".html", ".htm"), what=f"{w}.data.html",
                                         allow_absolute=allow_absolute)
                except paths.PathError as e:
                    problems.append(str(e))
    return problems


def validate(raw: dict, base_dir: Path | None = None, allow_absolute: bool = False) -> dict:
    """Normalise then validate. Returns the clean storyboard or raises StoryboardError."""
    sb = normalize(raw, base_dir)
    validator = jsonschema.Draft7Validator(STORYBOARD_SCHEMA)
    problems = []
    for err in sorted(validator.iter_errors(sb), key=lambda e: list(e.absolute_path)):
        path = "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in err.absolute_path)
        problems.append(f"${path}: {err.message}")
    try:
        problems += _semantic_checks(sb, base_dir, allow_absolute)
    except (TypeError, AttributeError, KeyError, ValueError) as e:
        if not problems:  # otherwise the schema errors above already explain it
            problems.append(f"{type(e).__name__}: {e}; check the shape of the storyboard")
    if problems:
        raise StoryboardError(problems)
    return sb


def load(path: str | Path, allow_absolute: bool = False) -> dict:
    p = Path(path)
    try:
        text = p.read_text(encoding="utf-8-sig")  # tolerate the BOM PowerShell writes
    except FileNotFoundError:
        raise StoryboardError([f"cannot read {p}: file not found"]) from None
    except (OSError, UnicodeDecodeError) as e:
        raise StoryboardError([f"cannot read {p}: {e}"]) from e
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as e:
        raise StoryboardError([f"{p.name} is not valid JSON: {e}"]) from e
    return validate(raw, p.resolve().parent, allow_absolute)
