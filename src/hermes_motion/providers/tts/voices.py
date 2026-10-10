"""Voice registry: maps descriptive attributes (accent, gender) to concrete voices per provider."""
from __future__ import annotations

# (accent, gender) -> voice id. 'american' is the fallback accent.
KOKORO = {
    ("british", "male"): "bm_george", ("british", "female"): "bf_emma",
    ("american", "male"): "am_michael", ("american", "female"): "af_heart",
}
KOKORO_LANG = {"british": "en-gb", "american": "en-us"}
PIPER = {  # downloaded on first use from the rhasspy/piper-voices collection
    ("british", "male"): "en_GB-alan-medium", ("british", "female"): "en_GB-jenny_dioco-medium",
    ("american", "male"): "en_US-ryan-medium", ("american", "female"): "en_US-amy-medium",
}
SAPI = {  # substring match against installed voice names
    ("british", "male"): "George", ("british", "female"): "Hazel",
    ("american", "male"): "David", ("american", "female"): "Zira",
}


def pick(table: dict, opts: dict, default: str) -> str:
    accent = (opts.get("accent") or "american").lower()
    accent = "british" if accent in ("british", "uk", "gb", "english", "en-gb") else "american"
    gender = (opts.get("gender") or "male").lower()
    gender = "female" if gender.startswith("f") else "male"
    return table.get((accent, gender), default)


def accent_of(opts: dict) -> str:
    a = (opts.get("accent") or "american").lower()
    return "british" if a in ("british", "uk", "gb", "english", "en-gb") else "american"
