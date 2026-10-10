"""Model download + checksum. Models live in the cache dir, never in the repo.

Every download is pinned: a sha256 per file, and the Piper base URL is a Hugging Face commit
(not the moving ``main`` branch). A file without a digest is refused unless the caller opts in
with ``allow_unpinned`` (config ``tts.piper.allow_unpinned``).
"""
from __future__ import annotations

import hashlib
import re
import sys
import urllib.request
from pathlib import Path

from ..base import ProviderUnavailable

KOKORO_BASE = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0"
# rhasspy/piper-voices at a fixed commit, so a later upstream change cannot alter what we fetch.
PIPER_REV = "c10ece1aade47bb51c153c893d14e5bf8e5b7117"
PIPER_BASE = f"https://huggingface.co/rhasspy/piper-voices/resolve/{PIPER_REV}"

# Piper voice ids look like en_GB-alan-medium: <lang>_<REGION>-<name>-<quality>.
PIPER_VOICE_RE = re.compile(r"^[a-z]{2}_[A-Z]{2}-[A-Za-z0-9_]+-(x_low|low|medium|high)$")


def _piper_base(voice: str) -> str:
    lang, name, quality = voice.split("-")
    return f"{PIPER_BASE}/{lang.split('_')[0]}/{lang}/{name}/{quality}/{voice}"


def _piper(voice: str, onnx_sha: str, json_sha: str) -> dict[str, tuple[str, str | None]]:
    base = _piper_base(voice)
    return {f"{voice}.onnx": (f"{base}.onnx", onnx_sha), f"{voice}.onnx.json": (f"{base}.onnx.json", json_sha)}


# name -> (url, sha256). Digests were computed from the files at the pinned revisions above.
MODELS: dict[str, tuple[str, str | None]] = {
    "kokoro-v1.0.onnx": (f"{KOKORO_BASE}/kokoro-v1.0.onnx",
                         "7d5df8ecf7d4b1878015a32686053fd0eebe2bc377234608764cc0ef3636a6c5"),
    "voices-v1.0.bin": (f"{KOKORO_BASE}/voices-v1.0.bin",
                        "bca610b8308e8d99f32e6fe4197e7ec01679264efed0cac9140fe9c29f1fbf7d"),
    **_piper("en_GB-alan-medium",
             "0a309668932205e762801f1efc2736cd4b0120329622adf62be09e56339d3330",
             "c0f0d124e5895c00e7c03b35dcc8287f319a6998a365b182deb5c8e752ee8c1e"),
    **_piper("en_US-ryan-medium",
             "abf4c274862564ed647ba0d2c47f8ee7c9b717d27bdad9219100eb310db4047a",
             "44034c056cb15681b2ad494307c7f3f2e4499d1253c700c711fa0a4607ffe78d"),
    **_piper("en_US-amy-medium",
             "b3a6e47b57b8c7fbe6a0ce2518161a50f59a9cdd8a50835c02cb02bdd6206c18",
             "95a23eb4d42909d38df73bb9ac7f45f597dbfcde2d1bf9526fdeaf5466977d77"),
    **_piper("en_GB-jenny_dioco-medium",
             "469c630d209e139dd392a66bf4abde4ab86390a0269c1e47b4e5d7ce81526b01",
             "a9a7a93a317c9a3cb6563e37eb057df9ef09c06188a8a4341b0fcb58cba54dd4"),
}


def piper_urls(voice: str) -> dict[str, tuple[str, str | None]]:
    """URLs for a Piper voice id (digest None when the voice is not in the pinned table)."""
    if not isinstance(voice, str) or not PIPER_VOICE_RE.match(voice):
        raise ProviderUnavailable(
            f"invalid Piper voice name {voice!r}; expected something like en_GB-alan-medium "
            f"(<lang>_<REGION>-<name>-<x_low|low|medium|high>)")
    if f"{voice}.onnx" in MODELS:
        return {k: MODELS[k] for k in (f"{voice}.onnx", f"{voice}.onnx.json")}
    base = _piper_base(voice)
    return {f"{voice}.onnx": (f"{base}.onnx", None), f"{voice}.onnx.json": (f"{base}.onnx.json", None)}


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


def _progress(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def _fetch(url: str, tmp: Path, name: str) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "hermes-motion"})
    with urllib.request.urlopen(req, timeout=60) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or 0)
        done, next_mark = 0, 0.2
        _progress(f"[models] downloading {name}" + (f" ({total / 1e6:.0f} MB)" if total else ""))
        while True:
            chunk = r.read(1 << 20)
            if not chunk:
                break
            f.write(chunk)
            done += len(chunk)
            if total and done / total >= next_mark:
                _progress(f"[models] {name}: {int(done / total * 100)}%")
                next_mark += 0.2


def ensure(name: str, cache: Path, extra: dict | None = None, download: bool = True,
           allow_unpinned: bool = False) -> Path:
    table = {**MODELS, **(extra or {})}
    if name not in table:
        raise ProviderUnavailable(f"unknown model file {name!r}")
    if Path(name).name != name or name in (".", ".."):
        raise ProviderUnavailable(f"invalid model file name {name!r}")
    url, digest = table[name]
    mdir = models_dir(cache).resolve()
    dest = mdir / name
    if dest.resolve().parent != mdir:
        raise ProviderUnavailable(f"model path for {name!r} escapes the cache folder")
    if digest is None and not allow_unpinned:
        raise ProviderUnavailable(
            f"{name} has no pinned sha256, so it will not be downloaded or trusted; use a pinned voice "
            f"(see `motion voices`) or set tts.piper.allow_unpinned: true to accept it at your own risk")
    if dest.exists():
        if digest is None or sha256(dest) == digest:
            return dest
        dest.unlink()
    if not download:
        raise ProviderUnavailable(f"model {name} not in cache ({dest.parent})")
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        _fetch(url, tmp, name)
    except Exception as e:  # network, DNS, 404...
        tmp.unlink(missing_ok=True)
        raise ProviderUnavailable(f"could not download {name} from {url}: {e}") from e
    if digest and sha256(tmp) != digest:
        tmp.unlink(missing_ok=True)
        raise ProviderUnavailable(f"checksum mismatch for {name}; download corrupted or upstream changed")
    tmp.replace(dest)
    return dest
