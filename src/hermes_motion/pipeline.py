"""End-to-end pipeline: storyboard -> narration -> timeline -> scene page -> frames -> MP4."""
from __future__ import annotations

import json
import logging
import shutil
import tempfile
import time
from pathlib import Path

from . import config as cfgmod
from . import paths, scenes, storyboard, timeline
from .providers import base
from .providers.tts import chain

log = logging.getLogger("hermes_motion")


def _say(msg: str, quiet: bool) -> None:
    if not quiet:
        print(msg, flush=True)


def _find_music(sb: dict, cfg: dict, base_dir: Path | None) -> Path | None:
    m = sb.get("music")
    allow_abs = bool(cfg.get("security", {}).get("allow_absolute_paths"))
    if m:
        try:
            return paths.resolve_inside(base_dir, m, storyboard.AUDIO_SUFFIXES, "music", allow_absolute=allow_abs)
        except paths.PathError as e:
            raise storyboard.StoryboardError([str(e)]) from None
    mc = cfg.get("music", {})
    if mc.get("enabled") and mc.get("folder"):
        files = sorted(p for p in Path(mc["folder"]).expanduser().glob("*")
                       if p.suffix.lower() in (".mp3", ".wav", ".ogg", ".m4a", ".flac"))
        return files[0] if files else None
    return None


def render(storyboard_path: str | Path | dict, out_mp4: str | Path, cfg: dict | None = None,
           quiet: bool = False) -> dict:
    """Render a storyboard to MP4. Returns a dict with paths, timings and the timing report."""
    t_start = time.time()
    cfg = cfgmod.load_config() if cfg is None else cfgmod.deep_merge(cfgmod.default_config(), cfg)  # copy, never mutate
    allow_abs = bool(cfg.get("security", {}).get("allow_absolute_paths"))
    base_dir = None
    if isinstance(storyboard_path, dict):
        sb = storyboard.validate(storyboard_path, allow_absolute=allow_abs)
    else:
        base_dir = Path(storyboard_path).resolve().parent
        sb = storyboard.load(storyboard_path, allow_absolute=allow_abs)
    fps = int(sb.get("fps") or cfg["video"]["fps"])
    cfg["video"]["fps"] = fps
    v = cfg["video"]
    if (v.get("width"), v.get("height")) != (1920, 1080):
        raise cfgmod.ConfigError(
            f"video.width/height is {v.get('width')}x{v.get('height')}, but only 1920x1080 is supported "
            f"(the scene layouts are fixed for 1080p); remove those keys or set 1920x1080")
    out_mp4 = Path(out_mp4)
    out_mp4.parent.mkdir(parents=True, exist_ok=True)
    warnings: list[str] = []

    tmp_root = cfg["pipeline"].get("tmp_dir")
    if tmp_root:
        tmp_root = str(Path(tmp_root).expanduser())
        Path(tmp_root).mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="hm-", dir=tmp_root or None))
    try:
        # 1. narration first: audio + word timings drive everything else
        voice = {**cfg["tts"].get("voice", {}), **(sb.get("voice") or {})}
        results = {}
        for sc in sb["scenes"]:
            if not sc["narration"]:
                results[sc["id"]] = None
                continue
            _say(f"[tts] {sc['id']}: {len(sc['narration'].split())} words", quiet)
            results[sc["id"]] = chain.synthesize(sc["narration"], voice, work / f"{sc['id']}.wav", cfg)
        used = sorted({r.provider + ":" + r.voice for r in results.values() if r})
        _say(f"[tts] voice(s): {', '.join(used) or 'none (silent)'}", quiet)
        for r in results.values():
            for note in (r.notes if r else []):
                if note not in warnings:
                    warnings.append(note)

        # 2. timeline from word timings
        v = cfg["video"]
        tl = timeline.build(sb, results, fps, float(v.get("scene_lead", 0.15)), float(v.get("scene_tail", 0.25)))
        audio_wav = None
        if any(results.values()):
            audio_wav = work / "narration.wav"
            timeline.mix_audio(tl, results, audio_wav)
        report = timeline.timing_report(tl)
        _say(report, quiet)
        _say(f"[timeline] {tl['total_seconds']:.2f}s, {tl['total_frames']} frames @ {fps}fps", quiet)
        target = sb.get("target_seconds")
        if target and tl["total_seconds"] > float(target) * 1.05:
            warnings.append(f"video is {tl['total_seconds']:.1f}s, over target_seconds={target}; shorten narration")
        (work / "timeline.json").write_text(json.dumps(tl, indent=2), encoding="utf-8")

        # 3. scene page
        tokens = scenes.load_tokens(sb, cfg, base_dir)
        page = scenes.build_page(sb, tl, tokens, cfg, base_dir)
        page_path = work / "index.html"
        page_path.write_text(page, encoding="utf-8")

        # 4. render frames
        renderer = base.create("renderer", cfg["renderer"]["provider"], cfg)
        frames = work / "frames"
        _say(f"[render] {cfg['renderer']['provider']} -> {tl['total_frames']} frames", quiet)
        t_r = time.time()
        n = renderer.render(page_path, tl["total_seconds"], fps, (v["width"], v["height"]), frames)
        _say(f"[render] {n} frames in {time.time() - t_r:.1f}s", quiet)

        # 5. encode
        encoder = base.create("encoder", cfg["encoder"]["provider"], cfg)
        info = encoder.encode(frames, fps, audio_wav, out_mp4,
                              music=_find_music(sb, cfg, base_dir), duration=tl["total_seconds"])
        _say(f"[encode] {info['codec']} -> {out_mp4}", quiet)
        for err in info.get("fallback_errors", []):
            warnings.append(f"encoder fallback: {err}")

        # sidecars next to the video (handy for review; out/ is gitignored)
        out_mp4.with_suffix(".timing.txt").write_text(report + "\n", encoding="utf-8")
        shutil.copyfile(work / "timeline.json", out_mp4.with_suffix(".timeline.json"))
        if cfg["pipeline"].get("keep_workdir"):
            shutil.copytree(work, out_mp4.with_suffix(".work"), dirs_exist_ok=True)
        for w in warnings:
            _say(f"[warn] {w}", quiet)
        return {"output": str(out_mp4.resolve()), "seconds": tl["total_seconds"], "frames": n,
                "fps": fps, "encoder": info["codec"], "tts": used, "warnings": warnings,
                "timing_report": report, "elapsed": round(time.time() - t_start, 1)}
    finally:
        shutil.rmtree(work, ignore_errors=True)
