"""Tests for m11 (config-declared providers), m13 (renderer robustness), accent errors."""
import asyncio
import sys
import types

import pytest

from hermes_motion import storyboard
from hermes_motion.providers import base
from hermes_motion.providers.render import html_playwright as hp
from hermes_motion.providers.tts import voices


# ---- accents -------------------------------------------------------------------------------

def test_unknown_accent_is_an_error():
    with pytest.raises(ValueError, match="unknown accent"):
        voices.normalize_accent("klingon")


@pytest.mark.parametrize("a,exp", [("UK", "british"), ("en-gb", "british"), ("us", "american"), (None, "american")])
def test_known_accents(a, exp):
    assert voices.normalize_accent(a) == exp


def test_kokoro_non_english_voice_rejected():
    assert voices.kokoro_lang("bm_george") == "en-gb"
    assert voices.kokoro_lang("af_heart") == "en-us"
    with pytest.raises(ValueError):
        voices.kokoro_lang("jf_alpha")


def test_validate_reports_bad_accent():
    sb = {"voice": {"accent": "klingon"}, "scenes": [{"template": "title", "narration": "Hi.",
                                                       "data": {"title": "T"}}]}
    with pytest.raises(storyboard.StoryboardError, match="voice.accent"):
        storyboard.validate(sb)


# ---- providers from config (m11) -----------------------------------------------------------

def test_provider_declared_in_config():
    mod = types.ModuleType("fake_motion_prov")

    class Fake:
        def __init__(self, cfg):
            self.cfg = cfg
    mod.Fake = Fake
    sys.modules["fake_motion_prov"] = mod
    try:
        cfg = {"providers": {"tts": {"fakey": "fake_motion_prov:Fake"}}}
        assert isinstance(base.create("tts", "fakey", cfg), Fake)
    finally:
        del sys.modules["fake_motion_prov"]


def test_bad_provider_declaration_is_clear_error():
    with pytest.raises(base.ProviderUnavailable, match="pkg.mod:ClassName"):
        base.create("tts", "x", {"providers": {"tts": {"x": "nocolon"}}})
    with pytest.raises(base.ProviderUnavailable, match="must map names"):
        base.create("tts", "x", {"providers": {"tts": "oops"}})
    with pytest.raises(base.ProviderUnavailable, match="cannot load"):
        base.create("tts", "y", {"providers": {"tts": {"y": "no_such_module_xyz:C"}}})


# ---- renderer robustness (m13) -------------------------------------------------------------

def test_run_in_thread_propagates_value_and_error():
    assert hp._run_in_thread(lambda: 7) == 7
    with pytest.raises(KeyError):
        hp._run_in_thread(lambda: {}["x"])


def test_render_inside_running_loop_uses_thread(monkeypatch, tmp_path):
    r = hp.HtmlPlaywrightRenderer({})
    monkeypatch.setattr(r, "available", lambda: (True, ""))
    monkeypatch.setattr(r, "_render_sync", lambda *a: 5)

    async def inner():
        return r.render(tmp_path / "x.html", 1.0, 30, (1920, 1080), tmp_path / "f")
    assert asyncio.run(inner()) == 5


def test_available_is_cached(monkeypatch):
    r = hp.HtmlPlaywrightRenderer({})
    calls = []
    monkeypatch.setattr(r, "_check_available", lambda: calls.append(1) or (True, ""))
    r.available()
    r.available()
    assert len(calls) == 1


def test_disk_space_check(monkeypatch, tmp_path):
    r = hp.HtmlPlaywrightRenderer({"renderer": {"frame_format": "png"}})
    monkeypatch.setattr(hp.shutil, "disk_usage", lambda p: types.SimpleNamespace(free=1000))
    with pytest.raises(base.ProviderUnavailable, match="free disk space"):
        r._check_disk(tmp_path, 100)
    monkeypatch.setattr(hp.shutil, "disk_usage", lambda p: types.SimpleNamespace(free=10**12))
    r._check_disk(tmp_path, 100)


def test_no_will_change_in_runtime_css():
    # will-change promotes GPU layers and made frames differ between worker counts (m5)
    from pathlib import Path
    css = (Path(__file__).resolve().parent.parent / "runtime" / "base.css").read_text(encoding="utf-8")
    assert "will-change" not in css
