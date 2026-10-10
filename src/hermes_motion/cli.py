"""Thin CLI over the library: motion {doctor,validate,render,schema,voices,analyze-ref}."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from . import config as cfgmod
from . import doctor as doctor_mod
from . import pipeline, storyboard
from .providers import base


def _cfg(args) -> dict:
    ov = list(args.set or [])
    if getattr(args, "tts", None):
        ov.append(f"tts.chain=[{args.tts}]")
    if getattr(args, "fps", None):
        ov.append(f"video.fps={args.fps}")
    if getattr(args, "hw", False):
        ov.append("encoder.hw_encode=true")
    return cfgmod.load_config(args.config, ov)


def cmd_doctor(args) -> int:
    checks = doctor_mod.run_checks(_cfg(args), fetch=args.fetch)
    print(doctor_mod.format_report(checks))
    return 1 if any(c.status == "fail" for c in checks) else 0


def cmd_validate(args) -> int:
    try:
        sb = storyboard.load(args.storyboard)
    except storyboard.StoryboardError as e:
        print(str(e), file=sys.stderr)
        return 2
    n = len(sb["scenes"])
    words = sum(len(s["narration"].split()) for s in sb["scenes"])
    print(f"OK: {n} scenes, {words} narration words (~{words / 2.7:.0f}s at normal speed)")
    if args.print:
        print(json.dumps(sb, indent=2))
    return 0


def cmd_render(args) -> int:
    cfg = _cfg(args)
    out = args.output or str(Path("out") / (Path(args.storyboard).stem + ".mp4"))
    try:
        res = pipeline.render(args.storyboard, out, cfg, quiet=args.quiet)
    except storyboard.StoryboardError as e:
        print(str(e), file=sys.stderr)
        return 2
    except base.ProviderUnavailable as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    print(json.dumps({k: v for k, v in res.items() if k != "timing_report"}, indent=2))
    return 0


def cmd_schema(args) -> int:
    print(json.dumps(storyboard.STORYBOARD_SCHEMA, indent=2))
    return 0


def cmd_voices(args) -> int:
    from .providers.tts import voices
    print("kokoro:", json.dumps({f"{a}/{g}": v for (a, g), v in voices.KOKORO.items()}))
    print("piper: ", json.dumps({f"{a}/{g}": v for (a, g), v in voices.PIPER.items()}))
    print("sapi:  ", json.dumps({f"{a}/{g}": v for (a, g), v in voices.SAPI.items()}))
    print("Set storyboard voice: {accent, gender, speed} or {name: '<exact voice id>'}.")
    return 0


def cmd_analyze(args) -> int:
    cfg = _cfg(args)
    try:
        prov = base.create("refs", cfg["refs"]["provider"], cfg)
        style = prov.analyze(args.clips)
    except base.ProviderUnavailable as e:
        print(f"error: {e}", file=sys.stderr)
        return 3
    Path(args.output).write_text(json.dumps(style, indent=2), encoding="utf-8")
    print(f"wrote {args.output}  (reference it with style.from_reference in your storyboard)")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="motion", description="Narrated explainer videos from a storyboard.")
    ap.add_argument("--version", action="version", version=f"hermes-motion {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", help="extra config YAML (layered over defaults)")
    common.add_argument("--set", action="append", metavar="KEY=VALUE", help="override a config key, e.g. video.fps=24")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("doctor", parents=[common], help="check dependencies and print fixes")
    p.add_argument("--fetch", action="store_true", help="download and verify TTS models now")
    p.set_defaults(fn=cmd_doctor)

    p = sub.add_parser("validate", parents=[common], help="validate a storyboard.json")
    p.add_argument("storyboard")
    p.add_argument("--print", action="store_true", help="print the normalised storyboard")
    p.set_defaults(fn=cmd_validate)

    p = sub.add_parser("render", parents=[common], help="render storyboard.json to MP4")
    p.add_argument("storyboard")
    p.add_argument("-o", "--output")
    p.add_argument("--tts", help="shortcut for --set tts.chain=[NAME]")
    p.add_argument("--fps", type=int, choices=[24, 30])
    p.add_argument("--hw", action="store_true", help="try hardware encoder first")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(fn=cmd_render)

    p = sub.add_parser("schema", help="print the storyboard JSON Schema")
    p.set_defaults(fn=cmd_schema)
    p = sub.add_parser("voices", help="list the voice registry")
    p.set_defaults(fn=cmd_voices)

    p = sub.add_parser("analyze-ref", parents=[common], help="reference clips -> style.json")
    p.add_argument("clips", nargs="+")
    p.add_argument("-o", "--output", default="style.json")
    p.set_defaults(fn=cmd_analyze)

    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == "__main__":
    sys.exit(main())
