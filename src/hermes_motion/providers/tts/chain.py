"""TTS provider chain: try providers in configured order, first that works wins."""
from __future__ import annotations

import logging
from pathlib import Path

from .. import base
from ..base import ProviderUnavailable, TTSResult

log = logging.getLogger("hermes_motion")


def synthesize(text: str, voice_opts: dict, out_wav: Path, cfg: dict) -> TTSResult:
    """Honour voice_opts['provider'] (storyboard) first, then tts.chain from config.

    Set tts.strict=true to forbid falling back past the first provider.
    """
    chain = list(cfg["tts"].get("chain") or ["kokoro"])
    forced = voice_opts.get("provider")
    if forced:
        chain = [forced] + [c for c in chain if c != forced]
    if cfg["tts"].get("strict"):
        chain = chain[:1]
    errors = []
    for name in chain:
        try:
            prov = base.create("tts", name, cfg)
            ok, why = prov.available()
            if not ok:
                errors.append(f"{name}: {why}")
                continue
            return prov.synthesize(text, voice_opts, out_wav)
        except ProviderUnavailable as e:
            errors.append(f"{name}: {e}")
        except Exception as e:  # engine crashed; try next
            errors.append(f"{name}: {type(e).__name__}: {e}")
        log.warning("tts provider %s failed, trying next", name)
    raise ProviderUnavailable("no TTS provider worked:\n  - " + "\n  - ".join(errors))
