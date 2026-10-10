import pytest

from hermes_motion import config as c


def test_defaults_load():
    cfg = c.load_config(project_dir="/nonexistent")
    assert cfg["video"]["width"] == 1920 and cfg["video"]["height"] == 1080
    assert cfg["video"]["fps"] == 30
    assert cfg["tts"]["chain"][0] == "kokoro"


def test_parse_override_nested_and_yaml_values():
    assert c.parse_override("video.fps=24") == {"video": {"fps": 24}}
    assert c.parse_override("tts.chain=[piper]") == {"tts": {"chain": ["piper"]}}
    assert c.parse_override("encoder.hw_encode=true") == {"encoder": {"hw_encode": True}}


def test_layering_order(tmp_path):
    f = tmp_path / "extra.yaml"
    f.write_text("video:\n  fps: 24\ncaptions:\n  enabled: false\n")
    cfg = c.load_config(f, ["video.fps=30"], project_dir="/nonexistent")
    assert cfg["video"]["fps"] == 30            # per-run override beats file
    assert cfg["captions"]["enabled"] is False  # file beats defaults
    assert cfg["video"]["width"] == 1920        # untouched keys survive


def test_deep_merge_does_not_mutate():
    a = {"x": {"y": 1}}
    b = c.deep_merge(a, {"x": {"z": 2}})
    assert a == {"x": {"y": 1}} and b == {"x": {"y": 1, "z": 2}}


def test_bad_override():
    with pytest.raises(ValueError):
        c.parse_override("nokeyvalue")
