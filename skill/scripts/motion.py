#!/usr/bin/env python3
"""Bot-facing entry point: runs the hermes-motion CLI inside its uv-managed environment.

Locating the checkout (first match wins):
  1. $HERMES_MOTION_HOME
  2. the parent of this skill folder (when skill/ still lives inside the repo)
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
    cmd = [uv, "run", "--project", str(home), "--extra", "piper", "motion", *sys.argv[1:]]
    return subprocess.call(cmd)


if __name__ == "__main__":
    sys.exit(main())
