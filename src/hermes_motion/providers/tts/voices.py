"""Voice registry: maps descriptive attributes (accent, gender) to concrete voices per provider."""
from __future__ import annotations

# (accent, gender) -> voice id.
KOKORO = {
    ("british", "male"): "bm_george", ("british", "female"): "bf_emma",
    ("american", "male"): "am_michael", ("american", "female"): "af_heart",
}
PIPER = {  # downloaded on first use from the rhasspy/piper-voices collection (all pinned, see models.py)
    ("british", "male"): "en_GB-alan-medium", ("british", "female"): "en_GB-jenny_dioco-medium",
    ("american", "male"): "en_US-ryan-medium", ("american", "female"): "en_US-amy-medium",
}
SAPI = {  # substring match against installed voice names
    ("british", "male"): "George", ("british", "female"): "Hazel",
    ("american", "male"): "David", ("american", "female"): "Zira",
}

BRITISH = ("british", "uk", "gb", "english", "en-gb")
AMERICAN = ("american", "us", "usa", "en-us")


def normalize_accent(accent) -> str:
    """'british' or 'american'; anything else is an error (it used to silently become American)."""
    a = str(accent or "american").lower()
    if a in BRITISH:
        return "british"
    if a in AMERICAN:
        return "american"
    raise ValueError(f"unknown accent {accent!r}; use one of {list(BRITISH + AMERICAN)}")


def normalize_gender(gender) -> str:
    return "female" if str(gender or "male").lower().startswith("f") else "male"


def kokoro_lang(voice: str) -> str:
    """Kokoro voice ids start with a language letter: a* American English, b* British English."""
    if voice[:1] == "b":
        return "en-gb"
    if voice[:1] == "a":
        return "en-us"
    raise ValueError(f"kokoro voice {voice!r} is not an English voice (a*/b*); only English is supported")


def pick(table: dict, opts: dict, default: str) -> str:
    return table.get((normalize_accent(opts.get("accent")), normalize_gender(opts.get("gender"))), default)
