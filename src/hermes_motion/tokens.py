"""Style-token validation. Tokens end up inside a ``<style>`` block and a ``<script>`` block,
so every value from a storyboard, config or reference file is checked before use."""
from __future__ import annotations

import math
import re

EASINGS = ("linear", "smooth", "snappy", "bounce", "inout")
DENSITIES = ("low", "medium", "high")
COLOR_KEYS = ("bg", "fg", "muted", "accent", "accent2", "surface", "line", "on_accent",
              "caption_bg", "caption_fg")
FONT_KEYS = ("font_head", "font_body", "font_mono")
NUMBER_KEYS = {"weight_head": (100, 1000), "radius": (0, 200), "intensity": (0.0, 3.0)}
TEXT_KEYS = ("name",)
KNOWN_KEYS = (set(COLOR_KEYS) | set(FONT_KEYS) | set(NUMBER_KEYS) | {"easing", "density"} | set(TEXT_KEYS))

# Anything that could end a CSS declaration/rule, a <style>/<script> element, or fetch a resource.
_FORBIDDEN = re.compile(r"[;{}<>\\\x00-\x1f]|/\*|\*/|@|url\s*\(|expression\s*\(|javascript:", re.I)


def safe_css(value, where: str = "style token") -> str:
    s = str(value)
    if _FORBIDDEN.search(s) or len(s) > 400 or s.count('"') % 2 or s.count("'") % 2:
        raise ValueError(f"{where} value {s[:60]!r} contains forbidden characters, unbalanced quotes "
                         f"or is too long (forbidden: ; {{ }} < > \\ /* @ url( )")
    return s


def sanitize(tokens, where: str = "style.tokens") -> dict:
    """Return a clean copy of ``tokens`` or raise ValueError naming the first bad key."""
    if tokens is None:
        return {}
    if not isinstance(tokens, dict):
        raise ValueError(f"{where} must be an object of token: value pairs")
    out: dict = {}
    for k, v in tokens.items():
        w = f"{where}.{k}"
        if k not in KNOWN_KEYS:
            raise ValueError(f"{w}: unknown token; allowed: {sorted(KNOWN_KEYS)}")
        if k in NUMBER_KEYS:
            lo, hi = NUMBER_KEYS[k]
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or not lo <= v <= hi:
                raise ValueError(f"{w} must be a number between {lo} and {hi}, got {v!r}")
            out[k] = v
        elif k == "easing":
            if v not in EASINGS:
                raise ValueError(f"{w} must be one of {list(EASINGS)}, got {v!r}")
            out[k] = v
        elif k == "density":
            if v not in DENSITIES:
                raise ValueError(f"{w} must be one of {list(DENSITIES)}, got {v!r}")
            out[k] = v
        else:
            if not isinstance(v, str):
                raise ValueError(f"{w} must be a string, got {type(v).__name__}")
            out[k] = safe_css(v, w)
    return out
