"""Confine file paths named by a storyboard to the storyboard's own folder.

A storyboard is untrusted input (usually written by an LLM from a user prompt), so
``custom`` HTML, ``style.from_reference`` and ``music`` may only name files inside the
folder that holds the storyboard, unless the operator opts in with
``security.allow_absolute_paths: true`` in the config.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable


class PathError(ValueError):
    """A storyboard path is outside the allowed folder, the wrong type, or missing."""


def resolve_inside(base_dir: str | Path | None, rel: str, suffixes: Iterable[str], what: str,
                   allow_absolute: bool = False, must_exist: bool = True) -> Path:
    """Return the resolved file path for ``rel``, or raise PathError with a fix hint."""
    if not isinstance(rel, str) or not rel.strip():
        raise PathError(f"{what} must be a non-empty path string")
    base = Path(base_dir if base_dir is not None else Path.cwd()).resolve()
    raw = Path(rel).expanduser() if allow_absolute else Path(rel)
    if raw.is_absolute() and not allow_absolute:
        raise PathError(f"{what}: absolute paths are not allowed ({rel!r}); use a path relative to the "
                        f"storyboard folder (or set security.allow_absolute_paths: true in the config)")
    p = (raw if raw.is_absolute() else base / raw).resolve()
    if not allow_absolute and p != base and base not in p.parents:
        raise PathError(f"{what}: {rel!r} is outside the storyboard folder; put the file next to the "
                        f"storyboard and use a relative path")
    sfx = tuple(s.lower() for s in suffixes)
    if p.suffix.lower() not in sfx:
        raise PathError(f"{what}: {rel!r} must be a {'/'.join(sfx)} file")
    if must_exist and not p.is_file():
        raise PathError(f"{what}: file not found: {rel!r} (relative to the storyboard folder)")
    return p
