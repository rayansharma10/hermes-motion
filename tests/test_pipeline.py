"""Pipeline-level tests: provider chain/swap, every template builds, full render with an offline fake TTS."""
import json
import shutil
import subprocess

import pytest

from conftest import needs_chromium, needs_ffmpeg
from hermes_motion import pipeline, scenes, storyboard, timeline
from hermes_motion.providers import base
from hermes_motion.providers.base import ProviderUnavailable
from hermes_motion.providers.tts import chain

ALL_TEMPLATES = {"scenes": [
    {"narration": "A title about cats.", "template": "title", "data": {"title": "Cats", "subtitle": "Sub", "kicker": "K"}},
    {"narration": "dogs and cats and birds", "template": "bullets", "data": {"heading": "H", "items": ["dogs", "cats", "birds"]}},
    {"narration": "a goes to b", "template": "diagram", "data": {"nodes": ["a", "b", "c"], "edges": ["a -> b", "b -> c"]}},
    {"narration": "look at this code", "template": "code", "data": {"language": "python", "code": "def f(x):\n    return x  # hi", "highlight": [2]}},
    {"narration": "sales grew", "template": "chart", "data": {"labels": ["Q1", "Q2"], "values": [3, 5], "type": "bar"}},
    {"narration": "sales grew", "template": "chart", "data": {"labels": ["Q1", "Q2", "Q3"], "values": [3, 5, 4], "type": "line"}},
    {"narration": "left versus right", "template": "comparison", "data": {"left": {"title": "L", "items": ["x"]}, "right": {"title": "R", "items": ["y"]}}},
    {"narration": "first then second", "template": "timeline", "data": {"events": [{"label": "first"}, {"label": "second", "detail": "d"}]}},
    {"narration": "big idea", "template": "callout", "data": {"text": "Big idea", "points": ["one", "two"]}},
]}


def _fake_results(sb, tmp_path, cfg):
    return {s["id"]: chain.synthesize(s["narration"], {}, tmp_path / f"{s['id']}.wav", cfg) if s["narration"] else None
            for s in sb["scenes"]}


def test_every_template_builds_a_page(cfg, tmp_path):
    sb = storyboard.validate(ALL_TEMPLATES)
    res = _fake_results(sb, tmp_path, cfg)
    tl = timeline.build(sb, res, 30, 0.15, 0.25)
    page = scenes.build_page(sb, tl, scenes.load_tokens(sb, cfg, None), cfg, None)
    assert page.count('class="scene"') == len(sb["scenes"])
    for cls in ("tpl-title", "tpl-bullets", "tpl-diagram", "tpl-code", "tpl-chart",
                "tpl-comparison", "tpl-timeline", "tpl-callout"):
        assert cls in page
    assert "window.__seek" in page and 'id="captions"' in page


def test_tts_chain_falls_back_and_reports(cfg, tmp_path):
    cfg["tts"]["chain"] = ["nonexistent", "fake"]
    r = chain.synthesize("hello world", {}, tmp_path / "a.wav", cfg)
    assert r.provider == "fake"
    cfg["tts"]["strict"] = True
    with pytest.raises(ProviderUnavailable) as e:
        chain.synthesize("hello", {}, tmp_path / "b.wav", cfg)
    assert "nonexistent" in str(e.value)


def test_unknown_provider_error_lists_choices():
    with pytest.raises(ProviderUnavailable) as e:
        base.create("tts", "nope", {})
    assert "kokoro" in str(e.value)


def test_storyboard_voice_provider_overrides_chain(cfg, tmp_path):
    cfg["tts"]["chain"] = ["nonexistent"]
    r = chain.synthesize("hello", {"provider": "fake"}, tmp_path / "c.wav", cfg)
    assert r.provider == "fake"


@needs_ffmpeg
@needs_chromium
def test_full_render_with_fake_tts(cfg, tmp_path):
    sb = {"title": "t", "fps": 24, "scenes": [
        {"narration": "hello there world", "template": "title", "data": {"title": "Hello"}},
        {"narration": "two things", "template": "bullets", "data": {"items": ["two", "things"]}},
    ]}
    out = tmp_path / "o.mp4"
    res = pipeline.render(sb, out, cfg, quiet=True)
    assert out.exists() and res["encoder"] == "libx264"
    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_streams", "-show_format", str(out)],
        capture_output=True, text=True).stdout)
    v = next(s for s in probe["streams"] if s["codec_type"] == "video")
    a = next(s for s in probe["streams"] if s["codec_type"] == "audio")
    assert (v["width"], v["height"], v["r_frame_rate"], v["codec_name"]) == (1920, 1080, "24/1", "h264")
    assert a["codec_name"] == "aac"
    assert abs(float(probe["format"]["duration"]) - res["seconds"]) < 0.15
    assert (tmp_path / "o.timing.txt").exists()
    vol = subprocess.run(["ffmpeg", "-i", str(out), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    assert "mean_volume" in vol and "-91" not in vol  # not silent


@needs_ffmpeg
def test_encoder_falls_back_when_hw_codec_fails(cfg, tmp_path):
    frames = tmp_path / "f"
    frames.mkdir()
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=320x240:r=10", "-frames:v", "10",
                    str(frames / "%06d.png")], check=True)
    cfg["encoder"]["hw_encode"] = True
    cfg["encoder"]["hw_codec"] = "h264_does_not_exist"
    enc = base.create("encoder", "ffmpeg", cfg)
    info = enc.encode(frames, 10, None, tmp_path / "x.mp4")
    assert info["codec"] == "libx264" and info["fallback_errors"]
    assert (tmp_path / "x.mp4").stat().st_size > 0
