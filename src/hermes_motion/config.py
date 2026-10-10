"""Layered configuration: defaults < user < project < --config < per-run overrides."""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import yaml

PACKAGE_DIR = Path(__file__).resolve().parent
# motion.config.yaml shipped next to the package (repo root or installed data)
_DEFAULT_CANDIDATES = [
    PACKAGE_DIR / "motion.config.yaml",
    PACKAGE_DIR.parent.parent / "motion.config.yaml",
]


def runtime_dir() -> Path:
    """Folder holding motion.js, templates and style presets."""
    for cand in (PACKAGE_DIR / "runtime", PACKAGE_DIR.parent.parent / "runtime"):
        if (cand / "motion.js").exists():
            return cand
    raise FileNotFoundError("hermes-motion runtime/ directory not found")


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _load_yaml(path: Path) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    if not isinstance(data, dict):
        raise ValueError(f"{path}: top level must be a mapping")
    return data


def parse_override(text: str) -> dict:
    """'tts.chain=[piper]' or 'video.fps=24' -> nested dict (value parsed as YAML)."""
    if "=" not in text:
        raise ValueError(f"override must look like key.sub=value, got {text!r}")
    key, _, raw = text.partition("=")
    value = yaml.safe_load(raw)
    node: dict = {}
    cur = node
    parts = key.strip().split(".")
    for p in parts[:-1]:
        cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value
    return node


def default_config() -> dict:
    for cand in _DEFAULT_CANDIDATES:
        if cand.exists():
            return _load_yaml(cand)
    raise FileNotFoundError("default motion.config.yaml not found")


def load_config(
    config_file: str | os.PathLike | None = None,
    overrides: list[str] | dict | None = None,
    project_dir: str | os.PathLike | None = None,
) -> dict:
    cfg = default_config()
    user = Path.home() / ".config" / "hermes-motion" / "config.yaml"
    if user.exists():
        cfg = deep_merge(cfg, _load_yaml(user))
    proj = Path(project_dir or Path.cwd()) / "motion.config.yaml"
    if proj.exists() and proj.resolve() not in {c.resolve() for c in _DEFAULT_CANDIDATES}:
        cfg = deep_merge(cfg, _load_yaml(proj))
    if config_file:
        cfg = deep_merge(cfg, _load_yaml(Path(config_file)))
    if isinstance(overrides, dict):
        cfg = deep_merge(cfg, overrides)
    else:
        for o in overrides or []:
            cfg = deep_merge(cfg, parse_override(o))
    return cfg


def cache_dir(cfg: dict) -> Path:
    p = cfg.get("cache_dir") or (Path.home() / ".cache" / "hermes-motion")
    p = Path(p).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    return p
