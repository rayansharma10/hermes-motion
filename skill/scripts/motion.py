#!/usr/bin/env python3
"""Bot-facing entry point: runs the hermes-motion CLI inside its uv-managed environment.

Locating the checkout (first match wins):
  1. $HERMES_MOTION_HOME
  2. the parent of this skill folder (when skill/ still lives inside the repo)
Optional extras: set HERMES_MOTION_EXTRAS=piper to also install the Piper TTS fallback.
Usage: python motion.py <doctor|validate|render|voices|schema|analyze-ref> [args...]
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path


def find_home() -> Path:
    env = os.environ.get("HERMES_MOTION_HOME")
    candidates = [Path(env)] if env else []
    candidates.append(Path(__file__).resolve().parents[2])
    for c in candidates:
        if (c / "pyproject.toml").exists() and (c / "src" / "hermes_motion").exists():
            return c
    sys.exit("hermes-motion checkout not found. Set HERMES_MOTION_HOME to the repository folder.")


def main() -> int:
    home = find_home()
    uv = shutil.which("uv")
    if not uv:
        sys.exit("uv is required (https://docs.astral.sh/uv/). Install it, then retry.")
    cmd = [uv, "run", "--project", str(home)]
    # Optional extras (e.g. "piper", which is GPL-3.0+) are opt-in: HERMES_MOTION_EXTRAS=piper
    for extra in filter(None, (x.strip() for x in os.environ.get("HERMES_MOTION_EXTRAS", "").split(","))):
        cmd += ["--extra", extra]
    cmd += ["motion", *sys.argv[1:]]
    # UTF-8 so narration with arrows/emoji cannot crash a cp1252 pipe on Windows
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    return subprocess.call(cmd, env=env)


if __name__ == "__main__":
    sys.exit(main())
