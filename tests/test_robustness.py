"""Daily-use robustness: UTF-8 console (M5), TTS fallback reporting (M4), storyboard shapes (M8),
resolution (M7), config validation, CLI exit codes."""
import io
import json
import subprocess
import sys

import pytest

from conftest import needs_chromium, needs_ffmpeg
from hermes_motion import cli, pipeline, storyboard
from hermes_motion import config as cfgmod
from hermes_motion.providers import base
from hermes_motion.providers.base import ProviderUnavailable
from hermes_motion.providers.tts import chain


# ---------------------------------------------------------------- M5
def test_utf8_streams_survive_cp1252_pipe(monkeypatch):
    raw_out, raw_err = io.BytesIO(), io.BytesIO()
    out = io.TextIOWrapper(raw_out, encoding="cp1252", errors="strict")
    err = io.TextIOWrapper(raw_err, encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stderr", err)
    with pytest.raises(UnicodeEncodeError):  # proves the failure mode exists without the fix
        print("Fast \u2192 free \u2014 ok")
        out.flush()
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", out)
    cli._utf8_streams()
    print("Fast \u2192 free \u2014 ok \U0001f680")
    out.flush()
    assert "\u2192" in out.buffer.getvalue().decode("utf-8")


def test_cli_validate_with_unicode_under_cp1252_env(tmp_path):
    sbp = tmp_path / "u.json"
    sbp.write_text(json.dumps({"scenes": [{"title": "Fast \u2192 free", "narration": "Fast \u2014 local \u2192 free."}]},
                              ensure_ascii=False), encoding="utf-8")
    env = {k: v for k, v in __import__("os").environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    env["PYTHONIOENCODING"] = "cp1252"  # what a Windows pipe defaults to
    r = subprocess.run([sys.executable, "-m", "hermes_motion.cli", "validate", str(sbp), "--print"],
                       capture_output=True, env=env)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert b"OK:" in r.stdout


@needs_ffmpeg
@needs_chromium
def test_render_unicode_narration_with_cp1252_stdout(cfg, tmp_path, monkeypatch):
    out = io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict")
    monkeypatch.setattr(sys, "stdout", out)
    cli._utf8_streams()
    sb = {"fps": 24, "scenes": [{"title": "Fast", "narration": "Fast \u2014 local \u2192 free."}]}
    res = pipeline.render(sb, tmp_path / "u.mp4", cfg, quiet=False)  # prints the timing report
    assert (tmp_path / "u.mp4").exists() and res["frames"] > 0


# ---------------------------------------------------------------- M4
class _Broken:
    name = "broken"

    def __init__(self, cfg):
        pass

    def available(self):
        return False, "model not installed"

    def synthesize(self, *a):
        raise AssertionError


def test_fallback_is_reported(cfg, tmp_path):
    base.register("tts", "broken", "test_robustness:_Broken")
    cfg["tts"]["chain"] = ["broken", "fake"]
    r = chain.synthesize("hello there", {}, tmp_path / "a.wav", cfg)
    assert r.provider == "fake"
    assert r.notes and "broken" in r.notes[0] and "model not installed" in r.notes[0] and "fake" in r.notes[0]


def test_no_fallback_note_when_first_provider_works(cfg, tmp_path):
    r = chain.synthesize("hello there", {}, tmp_path / "a.wav", cfg)
    assert r.notes == []


def test_explicit_voice_name_or_provider_is_strict(cfg, tmp_path):
    base.register("tts", "broken", "test_robustness:_Broken")
    cfg["tts"]["chain"] = ["broken", "fake"]
    with pytest.raises(ProviderUnavailable) as e:
        chain.synthesize("hello", {"name": "bm_nope"}, tmp_path / "a.wav", cfg)
    assert "broken" in str(e.value)
    with pytest.raises(ProviderUnavailable):
        chain.synthesize("hello", {"provider": "broken"}, tmp_path / "b.wav", cfg)


def test_chain_given_as_string_is_one_provider(cfg, tmp_path):
    cfg["tts"]["chain"] = "fake"
    assert chain.synthesize("hello", {}, tmp_path / "a.wav", cfg).provider == "fake"


@needs_ffmpeg
@needs_chromium
def test_render_surfaces_fallback_warning(cfg, tmp_path):
    base.register("tts", "broken", "test_robustness:_Broken")
    cfg["tts"]["chain"] = ["broken", "fake"]
    res = pipeline.render({"fps": 24, "scenes": [{"title": "Hi", "narration": "hello world"}]},
                          tmp_path / "w.mp4", cfg, quiet=True)
    assert any("tts fallback" in w for w in res["warnings"])


# ---------------------------------------------------------------- M8
BAD_SHAPES = [
    {"scenes": [{"template": "diagram", "data": {"nodes": [1, 2]}}]},
    {"scenes": [{"template": "diagram", "data": {"nodes": [{"label": 5}]}}]},
    {"scenes": [{"template": "diagram", "data": {"nodes": ["a", "b"], "edges": [5]}}]},
    {"scenes": [{"template": "diagram", "data": {"nodes": ["a", "b"], "edges": [[["x"], "b"]]}}]},
    {"scenes": [{"template": "bullets", "data": {"items": [["a"], None]}}]},
    {"scenes": [{"template": "bullets", "data": {"items": {"a": 1}}}]},
    {"scenes": [{"template": "title", "narration": 5, "data": {"title": "x"}}]},
    {"scenes": [{"template": "custom", "data": {"html": 5}}]},
    {"scenes": [{"template": "code", "data": {"code": "a", "highlight": ["a"]}}]},
    {"scenes": [{"template": "code", "data": {"code": "a\nb", "highlight": [9]}}]},
    {"scenes": [{"template": "chart", "data": {"labels": ["a"], "values": [float("nan")]}}]},
    {"scenes": [{"template": "chart", "data": {"labels": ["a"], "values": [-3]}}]},
    {"scenes": [{"template": "chart", "data": {"labels": ["a"], "values": ["x"]}}]},
    {"scenes": [{"template": "diagram", "data": {"nodes": ["A", "A"]}}]},
    {"scenes": [{"template": "comparison", "data": {"left": 5, "right": {"items": ["a"]}}}]},
    {"scenes": [{"template": "timeline", "data": {"events": 5}}]},
    {"scenes": [{"template": "callout", "data": {"points": 7}}]},
    {"fps": 24.5, "scenes": [{"title": "x"}]},
    {"fps": 29.97, "scenes": [{"title": "x"}]},
    {"bogus_key": 1, "scenes": [{"title": "x"}]},
    {"scenes": "nope"},
    {"scenes": [5]},
    {"scenes": [{"title": "x", "voice": 3}], "voice": 5},
    [1, 2],
    "scenes",
    None,
]


@pytest.mark.parametrize("raw", BAD_SHAPES, ids=range(len(BAD_SHAPES)))
def test_fuzz_shapes_raise_only_storyboard_error(raw):
    try:
        storyboard.validate(raw)
    except storyboard.StoryboardError as e:
        assert e.problems
    # no other exception type may escape; a pass-through (no error) is only valid for shapes we accept


def test_bad_shapes_give_actionable_messages():
    with pytest.raises(storyboard.StoryboardError) as e:
        storyboard.validate({"scenes": [{"template": "diagram", "data": {"nodes": [1, 2]}}]})
    assert "scenes[0]" in str(e.value) and "node" in str(e.value)
    with pytest.raises(storyboard.StoryboardError) as e:
        storyboard.validate({"fps": 29.97, "scenes": [{"title": "x"}]})
    assert "29.97" in str(e.value)
    with pytest.raises(storyboard.StoryboardError) as e:
        storyboard.validate({"scenes": [{"template": "code", "data": {"code": "a\nb", "highlight": [9]}}]})
    assert "between 1 and 2" in str(e.value)
    with pytest.raises(storyboard.StoryboardError) as e:
        storyboard.validate({"scenes": [{"template": "diagram", "data": {"nodes": ["A", "A"]}}]})
    assert "duplicate" in str(e.value)


def test_integer_valued_float_fps_ok_and_scalar_highlight():
    sb = storyboard.validate({"fps": 30.0, "scenes": [{"template": "code", "data": {"code": "a\nb", "highlight": 2}}]})
    assert sb["fps"] == 30 and sb["scenes"][0]["data"]["highlight"] == [2]


def test_utf8_bom_file_loads(tmp_path):
    p = tmp_path / "bom.json"
    p.write_bytes(b"\xef\xbb\xbf" + json.dumps({"scenes": [{"title": "hi"}]}).encode("utf-8"))
    assert storyboard.load(p)["scenes"][0]["template"] == "title"


def test_missing_and_directory_and_binary_files(tmp_path, capsys):
    with pytest.raises(storyboard.StoryboardError) as e:
        storyboard.load(tmp_path / "missing.json")
    assert "cannot read" in str(e.value)
    assert cli.main(["validate", str(tmp_path / "missing.json")]) == 2
    assert "cannot read" in capsys.readouterr().err
    assert cli.main(["render", str(tmp_path / "missing.json")]) == 2
    assert "Traceback" not in capsys.readouterr().err
    bad = tmp_path / "bin.json"
    bad.write_bytes(b"\xff\xfe\x00bad")
    assert cli.main(["validate", str(bad)]) == 2
    assert cli.main(["validate", str(tmp_path)]) == 2


def test_cli_returns_2_for_oserror(monkeypatch, capsys, tmp_path):
    def boom(*a, **k):
        raise PermissionError(13, "Permission denied", "x.json")
    monkeypatch.setattr(storyboard, "load", boom)
    assert cli.main(["validate", str(tmp_path / "x.json")]) == 2
    err = capsys.readouterr().err
    assert "Permission denied" in err and "Traceback" not in err


# ---------------------------------------------------------------- M7 + config
def test_non_1080p_is_rejected_clearly(cfg, tmp_path):
    cfg["video"]["width"], cfg["video"]["height"] = 1280, 720
    with pytest.raises(cfgmod.ConfigError) as e:
        pipeline.render({"scenes": [{"title": "x"}]}, tmp_path / "o.mp4", cfg, quiet=True)
    assert "1920x1080" in str(e.value)
    assert not (tmp_path / "o.mp4").exists()


def test_cli_render_non_1080p_exit_code(tmp_path, capsys):
    p = tmp_path / "s.json"
    p.write_text(json.dumps({"scenes": [{"title": "x"}]}))
    rc = cli.main(["render", str(p), "-o", str(tmp_path / "o.mp4"), "--set", "video.width=1280",
                   "--set", "video.height=720", "-q"])
    assert rc == 2 and "1920x1080" in capsys.readouterr().err


def test_config_validation():
    with pytest.raises(cfgmod.ConfigError) as e:
        cfgmod.load_config(overrides=["tts.chian=[kokoro]"], project_dir="/nonexistent")
    assert "tts.chian" in str(e.value)
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load_config(overrides=["tts.chain=[]"], project_dir="/nonexistent")
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load_config(overrides=["video.fps=25"], project_dir="/nonexistent")
    with pytest.raises(cfgmod.ConfigError):
        cfgmod.load_config(overrides=["pipeline.workers=0"], project_dir="/nonexistent")
    assert cfgmod.load_config(overrides=["tts.chain=piper"], project_dir="/nonexistent")["tts"]["chain"] == ["piper"]


def test_render_does_not_mutate_callers_config_and_accepts_partial(cfg, tmp_path):
    import copy
    before = copy.deepcopy(cfg)
    sb = {"fps": 24, "scenes": [{"title": "x"}]}
    try:
        pipeline.render(sb, tmp_path / "o.mp4", cfg, quiet=True)
    except Exception:
        pass
    assert cfg == before


def test_user_config_is_ignored_in_tests(tmp_path, monkeypatch):
    # conftest points HERMES_MOTION_USER_CONFIG at a missing file; a poisoned real home must not leak in
    home = tmp_path / "home"
    (home / ".config" / "hermes-motion").mkdir(parents=True)
    (home / ".config" / "hermes-motion" / "config.yaml").write_text("video:\n  fps: 24\n")
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    assert cfgmod.load_config(project_dir="/nonexistent")["video"]["fps"] == 30
    monkeypatch.delenv("HERMES_MOTION_USER_CONFIG")
    assert cfgmod.load_config(project_dir="/nonexistent")["video"]["fps"] == 24  # proves the poison works


@needs_ffmpeg
@needs_chromium
def test_missing_tmp_dir_is_created(cfg, tmp_path):
    cfg["pipeline"]["tmp_dir"] = str(tmp_path / "does" / "not" / "exist")
    res = pipeline.render({"fps": 24, "scenes": [{"title": "x", "narration": "hi there"}]},
                          tmp_path / "o.mp4", cfg, quiet=True)
    assert (tmp_path / "o.mp4").exists() and res["frames"] > 0
