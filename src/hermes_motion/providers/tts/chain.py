"""TTS provider chain: try providers in configured order, first that works wins."""
from __future__ import annotations

import logging
from pathlib import Path

from .. import base
from ..base import ProviderUnavailable, TTSResult

log = logging.getLogger("hermes_motion")


def synthesize(text: str, voice_opts: dict, out_wav: Path, cfg: dict) -> TTSResult:
    """Honour voice_opts['provider'] (storyboard) first, then tts.chain from config.

    Set tts.strict=true to forbid falling back past the first provider. An explicit voice
    (``voice.name`` or ``voice.provider``) is also strict: a voice id belongs to one provider,
    so silently speaking with a different engine would be wrong. Any other fallback succeeds
    but is recorded in ``result.notes`` so the caller can warn.
    """
    chain = cfg["tts"].get("chain") or ["kokoro"]
    if isinstance(chain, str):
        chain = [chain]
    chain = list(chain)
    forced = voice_opts.get("provider")
    if forced:
        chain = [forced] + [c for c in chain if c != forced]
    explicit = bool(forced or voice_opts.get("name"))
    if cfg["tts"].get("strict") or explicit:
        chain = chain[:1]
    errors = []
    for name in chain:
        try:
            prov = base.create("tts", name, cfg)
            ok, why = prov.available()
            if not ok:
                errors.append(f"{name}: {why}")
                continue
            res = prov.synthesize(text, voice_opts, out_wav)
            if errors:
                res.notes.append(
                    f"tts fallback: {chain[0]} failed ({'; '.join(errors)}); used {name}:{res.voice} instead")
            return res
        except ProviderUnavailable as e:
            errors.append(f"{name}: {e}")
        except Exception as e:  # engine crashed; try next
            errors.append(f"{name}: {type(e).__name__}: {e}")
        log.warning("tts provider %s failed, trying next", name)
    raise ProviderUnavailable("no TTS provider worked:\n  - " + "\n  - ".join(errors))
