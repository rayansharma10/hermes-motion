import json
import subprocess

from conftest import needs_ffmpeg
from hermes_motion import cli
from hermes_motion.providers.refs.basic import BasicRefAnalyzer, tokens_from_traits
import numpy as np


@needs_ffmpeg
def test_basic_ref_analyzer_on_synthetic_clip(tmp_path):
    clip = tmp_path / "ref.mp4"
    # two hard cuts: red -> blue -> red, 6 s total, with a tone
    subprocess.run([
        "ffmpeg", "-v", "error", "-y",
        "-f", "lavfi", "-i", "color=c=0xd9480f:s=320x180:r=15:d=2",
        "-f", "lavfi", "-i", "color=c=0x1e2a44:s=320x180:r=15:d=2",
        "-f", "lavfi", "-i", "color=c=0xd9480f:s=320x180:r=15:d=2",
        "-f", "lavfi", "-i", "sine=frequency=300:duration=6",
        "-filter_complex", "[0:v][1:v][2:v]concat=n=3:v=1:a=0[v]", "-map", "[v]", "-map", "3:a",
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest", str(clip)], check=True)
    style = BasicRefAnalyzer({"refs": {"sample_frames": 12}}).analyze([str(clip)])
    assert style["clips"] == 1
    assert style["pacing"]["avg_shot_seconds"] is not None and 1.5 < style["pacing"]["avg_shot_seconds"] < 2.5
    assert style["per_clip"][0]["width"] == 320 and style["per_clip"][0]["has_audio"]
    hexes = {p["hex"] for p in style["palette"]}
    assert any(h.startswith("#d") for h in hexes) or any(h.startswith("#1") for h in hexes)
    t = style["tokens"]
    assert all(k in t for k in ("bg", "fg", "accent", "muted", "surface", "line", "on_accent"))
    json.dumps(style)


def test_tokens_from_traits_picks_saturated_accent_and_contrast():
    pal = [(250, 248, 240), (217, 72, 15), (120, 120, 120)]
    t = tokens_from_traits(pal, [0.7, 0.2, 0.1], avg_shot=1.0)
    assert t["accent"] == "#d9480f" and t["easing"] == "snappy"
    assert t["fg"] == "#14161a"  # dark text on a light background
    dark = tokens_from_traits([(10, 12, 20), (0, 200, 120)], [0.9, 0.1], avg_shot=8)
    assert dark["fg"] == "#f0f2f6" and dark["easing"] == "inout"


def test_style_json_feeds_page_tokens(cfg, tmp_path):
    from hermes_motion import scenes
    style = tmp_path / "style.json"
    style.write_text(json.dumps({"tokens": {"accent": "#00aa55", "bg": "#101010"}}))
    sb = {"style": {"preset": "clean", "from_reference": "style.json", "tokens": {"bg": "#202020"}}}
    tok = scenes.load_tokens(sb, cfg, tmp_path)
    assert tok["accent"] == "#00aa55"   # reference beats preset
    assert tok["bg"] == "#202020"       # storyboard tokens beat reference
    assert tok["fg"]                    # preset values remain


def test_cli_validate_codes(tmp_path, capsys):
    good = tmp_path / "g.json"
    good.write_text(json.dumps({"scenes": [{"title": "hi", "narration": "hello there"}]}))
    bad = tmp_path / "b.json"
    bad.write_text(json.dumps({"scenes": [{"template": "bullets", "data": {}}]}))
    assert cli.main(["validate", str(good)]) == 0
    assert cli.main(["validate", str(bad)]) == 2
    assert "items" in capsys.readouterr().err


def test_cli_schema_and_voices(capsys):
    assert cli.main(["schema"]) == 0
    assert '"scenes"' in capsys.readouterr().out
    assert cli.main(["voices"]) == 0
    assert "bm_george" in capsys.readouterr().out
