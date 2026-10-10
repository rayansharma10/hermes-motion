"""Model download + checksum. Models live in the cache dir, never in the repo."""
from __future__ import annotations

import hashlib
import shutil
import urllib.request
from pathlib import Path

from ..base import ProviderUnavailable

KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
PIPER_BASE = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

# name -> (url, sha256 or None). Pinned where the file has been verified.
MODELS: dict[str, tuple[str, str | None]] = {
    "kokoro-v1.0.onnx": (f"{KOKORO_BASE}/kokoro-v1.0.onnx",
                         "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5"),
    "voices-v1.0.bin": (f"{KOKORO_BASE}/voices-v1.0.bin",
                        "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
    "en_GB-alan-medium.onnx": (f"{PIPER_BASE}/en/en_GB/alan/medium/en_GB-alan-medium.onnx?download=true",
                               "0a309668932205e762801f1efc2736cd4b0120329622adf62be09e56339d3330"),
    "en_GB-alan-medium.onnx.json": (f"{PIPER_BASE}/en/en_GB/alan/medium/en_GB-alan-medium.onnx.json",
                                    "c0f0d124e5895c00e7c03b35dcc8287f319a6998a365b182deb5c8e752ee8c1e"),
}


def piper_urls(voice: str) -> dict[str, tuple[str, str | None]]:
    """Derive Hugging Face URLs for any piper voice id like en_GB-alan-medium (unpinned)."""
    lang, name, quality = voice.split("-")
    base = f"{PIPER_BASE}/{lang.split('_')[0]}/{lang}/{name}/{quality}/{voice}.onnx"
    return {f"{voice}.onnx": (base + "?download=true", None), f"{voice}.onnx.json": (base + ".json", None)}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def models_dir(cache: Path) -> Path:
    d = Path(cache) / "models"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ensure(name: str, cache: Path, extra: dict | None = None, download: bool = True) -> Path:
    table = {**MODELS, **(extra or {})}
    if name not in table:
        raise ProviderUnavailable(f"unknown model file {name!r}")
    url, digest = table[name]
    dest = models_dir(cache) / name
    if dest.exists():
        if digest is None or sha256(dest) == digest:
            return dest
        dest.unlink()
    if not download:
        raise ProviderUnavailable(f"model {name} not in cache ({dest.parent})")
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "hermes-motion"})
        with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
            shutil.copyfileobj(r, f)
    except Exception as e:  # network, DNS, 404...
        tmp.unlink(missing_ok=True)
        raise ProviderUnavailable(f"could not download {name} from {url}: {e}") from e
    if digest and sha256(tmp) != digest:
        tmp.unlink(missing_ok=True)
        raise ProviderUnavailable(f"checksum mismatch for {name}; download corrupted or upstream changed")
    tmp.replace(dest)
    return dest
