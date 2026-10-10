"""Untrusted-input handling: token injection (M1), path traversal and network isolation (M2),
Piper voice names and download pinning (M3, M9)."""
import hashlib
import json

import pytest

from hermes_motion import paths, scenes, storyboard, timeline, tokens
from hermes_motion.providers.base import ProviderUnavailable
from hermes_motion.providers.render.html_playwright import request_allowed
from hermes_motion.providers.tts import chain, models

SCRIPT_PAYLOAD = "red;}</style><script>window.PWN=1</script><style>a{"


def _page(cfg, tmp_path, sb_raw, base_dir=None):
    sb = storyboard.validate(sb_raw, base_dir)
    res = {s["id"]: chain.synthesize(s["narration"], {}, tmp_path / f"{s['id']}.wav", cfg) if s["narration"] else None
           for s in sb["scenes"]}
    tl = timeline.build(sb, res, 30, 0.15, 0.25)
    return scenes.build_page(sb, tl, scenes.load_tokens(sb, cfg, base_dir), cfg, base_dir)


# ---------------------------------------------------------------- M1 tokens
@pytest.mark.parametrize("bad", [
    {"accent": SCRIPT_PAYLOAD},
    {"font_head": "x</style><script>1</script>"},
    {"bg": "red; background:url(http://evil/x)"},
    {"easing": "</script><script>window.PWN2=1</script>"},
    {"intensity": "1</script>"},
    {"intensity": float("nan")},
    {"nonsense_key": "x"},
    {"accent": {"nested": "obj"}},
    {"accent": "url(http://evil)"},
])
def test_hostile_tokens_rejected_at_validation(bad):
    with pytest.raises(storyboard.StoryboardError) as e:
        storyboard.validate({"style": {"tokens": bad}, "scenes": [{"title": "hi"}]})
    assert "style.tokens" in str(e.value)


def test_hostile_tokens_never_reach_the_page(cfg, tmp_path):
    # even if validation were bypassed, load_tokens sanitises every layer
    sb = {"style": {"tokens": {"accent": SCRIPT_PAYLOAD}}, "scenes": [{"title": "hi", "narration": "hi there"}]}
    with pytest.raises(storyboard.StoryboardError):
        scenes.load_tokens(sb, cfg, None)


def test_config_and_reference_tokens_are_sanitised(cfg, tmp_path):
    cfg["style"]["tokens"] = {"accent": SCRIPT_PAYLOAD}
    with pytest.raises(storyboard.StoryboardError):
        scenes.load_tokens({"scenes": []}, cfg, tmp_path)
    cfg["style"]["tokens"] = {}
    (tmp_path / "ref.json").write_text(json.dumps({"tokens": {"easing": "</script><script>1</script>"}}))
    sb = {"style": {"from_reference": "ref.json"}}
    with pytest.raises(storyboard.StoryboardError):
        scenes.load_tokens(sb, cfg, tmp_path)


def test_valid_tokens_still_work(cfg, tmp_path):
    page = _page(cfg, tmp_path, {"style": {"tokens": {
        "accent": "#112233", "easing": "snappy", "intensity": 1.3,
        "font_head": "\"Segoe UI\", Arial, sans-serif"}},
        "scenes": [{"title": "hi", "narration": "hi there"}]})
    assert "--accent:#112233" in page
    assert '"easing": "snappy"' in page
    assert "PWN" not in page


def test_script_payload_is_escaped():
    out = tokens.sanitize({"easing": "linear", "intensity": 1.0})
    assert out == {"easing": "linear", "intensity": 1.0}


def test_text_is_still_escaped(cfg, tmp_path):
    page = _page(cfg, tmp_path, {"title": "<img src=x onerror=alert(1)>",
                                 "scenes": [{"title": "<script>x</script>", "narration": "a b"}]})
    assert "<script>x</script>" not in page
    assert "&lt;script&gt;x&lt;/script&gt;" in page


def test_font_stem_is_escaped(tmp_path):
    (tmp_path / "ev;}il{x.ttf").write_bytes(b"")
    css = scenes._font_faces(str(tmp_path))
    assert "ev;}il" not in css and "ev__il_x" in css


# ---------------------------------------------------------------- M2 paths
def test_resolve_inside_rules(tmp_path):
    (tmp_path / "ok.html").write_text("<p>x</p>")
    outside = tmp_path.parent / "secret.txt"
    outside.write_text("TOPSECRET")
    assert paths.resolve_inside(tmp_path, "ok.html", (".html",), "x") == (tmp_path / "ok.html").resolve()
    for bad in ("../secret.txt", str(outside), "../ok.html", "missing.html", "ok.txt"):
        with pytest.raises(paths.PathError):
            paths.resolve_inside(tmp_path, bad, (".html",), "x")
    # absolute paths are an explicit opt-in
    other = tmp_path.parent / "other.html"
    other.write_text("<p>y</p>")
    assert paths.resolve_inside(tmp_path, str(other), (".html",), "x", allow_absolute=True) == other.resolve()


@pytest.mark.parametrize("html", ["../secret.html", "C:/Windows/win.html", "/etc/x.html", "sub/../../x.html"])
def test_custom_template_traversal_rejected(tmp_path, html):
    (tmp_path.parent / "secret.html").write_text("TOPSECRET")
    with pytest.raises(storyboard.StoryboardError) as e:
        storyboard.validate({"scenes": [{"template": "custom", "data": {"html": html}}]}, tmp_path)
    assert "custom" in str(e.value) or "html" in str(e.value)


def test_custom_template_wrong_type_and_non_string(tmp_path):
    (tmp_path / "a.txt").write_text("x")
    with pytest.raises(storyboard.StoryboardError):
        storyboard.validate({"scenes": [{"template": "custom", "data": {"html": "a.txt"}}]}, tmp_path)
    with pytest.raises(storyboard.StoryboardError):
        storyboard.validate({"scenes": [{"template": "custom", "data": {"html": 5}}]}, tmp_path)


def test_custom_template_inside_folder_works_and_render_time_check(cfg, tmp_path):
    (tmp_path / "frag.html").write_text("<p id=frag>hello</p>")
    page = _page(cfg, tmp_path, {"scenes": [{"template": "custom", "narration": "a b", "data": {"html": "frag.html"}}]},
                 tmp_path)
    assert 'id=frag' in page


def test_custom_template_symlink_escape(tmp_path):
    sub = tmp_path / "sb"
    sub.mkdir()
    target = tmp_path / "secret.html"
    target.write_text("TOPSECRET")
    try:
        (sub / "link.html").symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("symlinks not permitted here")
    with pytest.raises(storyboard.StoryboardError):
        storyboard.validate({"scenes": [{"template": "custom", "data": {"html": "link.html"}}]}, sub)


def test_absolute_paths_opt_in_via_load(tmp_path):
    sbdir = tmp_path / "sb"
    sbdir.mkdir()
    ext = tmp_path / "ext.html"
    ext.write_text("<p>x</p>")
    raw = {"scenes": [{"template": "custom", "data": {"html": str(ext)}}]}
    p = sbdir / "s.json"
    p.write_text(json.dumps(raw))
    with pytest.raises(storyboard.StoryboardError):
        storyboard.load(p)
    assert storyboard.load(p, allow_absolute=True)["scenes"][0]["template"] == "custom"


def test_from_reference_and_music_confined(tmp_path):
    (tmp_path.parent / "s.json").write_text("{}")
    with pytest.raises(storyboard.StoryboardError):
        storyboard.validate({"style": {"from_reference": "../s.json"}, "scenes": [{"title": "t"}]}, tmp_path)
    (tmp_path / "notes.txt").write_text("x")
    for music in ("../m.mp3", "notes.txt", "C:/x/y.mp3"):
        with pytest.raises(storyboard.StoryboardError):
            storyboard.validate({"music": music, "scenes": [{"title": "t"}]}, tmp_path)


def test_renderer_blocks_network_and_foreign_files(tmp_path):
    roots = [tmp_path]
    inside = (tmp_path / "index.html").as_uri()
    assert request_allowed(inside, roots)
    assert request_allowed("data:text/plain,hi", roots)
    assert not request_allowed("http://example.com/x.js", roots)
    assert not request_allowed("https://example.com/", roots)
    assert not request_allowed("ftp://example.com/", roots)
    assert not request_allowed((tmp_path.parent / "secret.txt").as_uri(), roots)
    assert not request_allowed("file:///etc/passwd", roots)


# ---------------------------------------------------------------- M3 / M9 models
@pytest.mark.parametrize("bad", ["../../evil-x-y", "en_GB-alan", "en_GB-alan-medium/../../x", "EN_gb-a-medium",
                                 "en_GB-a b-medium", "", "en_GB-alan-huge", "..\\..\\x"])
def test_piper_voice_name_whitelist(bad):
    with pytest.raises(ProviderUnavailable):
        models.piper_urls(bad)


def test_piper_urls_pinned_to_commit_and_digests():
    urls = models.piper_urls("en_US-ryan-medium")
    for name, (url, digest) in urls.items():
        assert models.PIPER_REV in url and "/main/" not in url
        assert digest and len(digest) == 64
    for v in ("en_GB-alan-medium", "en_US-ryan-medium", "en_US-amy-medium", "en_GB-jenny_dioco-medium"):
        for k in (f"{v}.onnx", f"{v}.onnx.json"):
            assert models.MODELS[k][1], k
    assert len(models.PIPER_REV) == 40


def test_registry_voices_all_pinned():
    from hermes_motion.providers.tts import voices
    for v in voices.PIPER.values():
        assert models.MODELS[f"{v}.onnx"][1] and models.MODELS[f"{v}.onnx.json"][1]


def _fake_fetch(content: bytes):
    def fetch(url, tmp, name):
        tmp.write_bytes(content)
    return fetch


def test_ensure_checksum_mismatch_removes_partial(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "_fetch", _fake_fetch(b"wrong bytes"))
    table = {"m.bin": ("https://example.invalid/m.bin", hashlib.sha256(b"right").hexdigest())}
    with pytest.raises(ProviderUnavailable) as e:
        models.ensure("m.bin", tmp_path, table)
    assert "checksum mismatch" in str(e.value)
    mdir = tmp_path / "models"
    assert not (mdir / "m.bin").exists() and not (mdir / "m.bin.part").exists()


def test_ensure_ok_and_cache_hit_and_corrupt_cache_redownloaded(tmp_path, monkeypatch):
    good = b"good bytes"
    table = {"m.bin": ("https://example.invalid/m.bin", hashlib.sha256(good).hexdigest())}
    calls = []

    def fetch(url, tmp, name):
        calls.append(name)
        tmp.write_bytes(good)

    monkeypatch.setattr(models, "_fetch", fetch)
    p = models.ensure("m.bin", tmp_path, table)
    assert p.read_bytes() == good and calls == ["m.bin"]
    models.ensure("m.bin", tmp_path, table)
    assert calls == ["m.bin"]  # cache hit, digest verified
    p.write_bytes(b"corrupt")
    models.ensure("m.bin", tmp_path, table)
    assert calls == ["m.bin", "m.bin"] and p.read_bytes() == good


def test_ensure_download_failure_cleans_part(tmp_path, monkeypatch):
    def boom(url, tmp, name):
        tmp.write_bytes(b"half")
        raise OSError("network down")

    monkeypatch.setattr(models, "_fetch", boom)
    table = {"m.bin": ("https://example.invalid/m.bin", "0" * 64)}
    with pytest.raises(ProviderUnavailable) as e:
        models.ensure("m.bin", tmp_path, table)
    assert "could not download" in str(e.value) and "network down" in str(e.value)
    assert not list((tmp_path / "models").glob("*.part"))


def test_ensure_refuses_digestless_unless_opted_in(tmp_path, monkeypatch):
    monkeypatch.setattr(models, "_fetch", _fake_fetch(b"anything"))
    table = {"v.onnx": ("https://example.invalid/v.onnx", None)}
    with pytest.raises(ProviderUnavailable) as e:
        models.ensure("v.onnx", tmp_path, table)
    assert "allow_unpinned" in str(e.value)
    assert not (tmp_path / "models" / "v.onnx").exists()
    assert models.ensure("v.onnx", tmp_path, table, allow_unpinned=True).read_bytes() == b"anything"


def test_ensure_rejects_traversal_names(tmp_path):
    for name in ("../evil.onnx", "sub/x.onnx", ".."):
        with pytest.raises(ProviderUnavailable):
            models.ensure(name, tmp_path, {name: ("https://example.invalid/x", "0" * 64)})


def test_unpinned_piper_voice_refused_by_default(tmp_path):
    urls = models.piper_urls("en_GB-northern_english_male-medium")  # valid shape, not in the pinned table
    assert all(d is None for _, d in urls.values())
    with pytest.raises(ProviderUnavailable):
        models.ensure("en_GB-northern_english_male-medium.onnx", tmp_path, urls)


# ---------------------------------------------------------------- M2 real browser
from conftest import needs_chromium, needs_ffmpeg  # noqa: E402


@needs_ffmpeg
@needs_chromium
def test_custom_scene_cannot_reach_network(cfg, tmp_path):
    import http.server
    import threading

    from hermes_motion import pipeline

    hits = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(200)
            self.end_headers()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    (tmp_path / "evil.html").write_text(
        f'<img src="http://127.0.0.1:{port}/pixel.png"><script>fetch("http://127.0.0.1:{port}/f")</script>'
        f'<iframe src="file:///{(tmp_path.parent / "x").as_posix().lstrip("/")}"></iframe>')
    sb = tmp_path / "s.json"
    sb.write_text(json.dumps({"fps": 24, "scenes": [{"template": "custom", "narration": "hi there",
                                                     "data": {"html": "evil.html"}}]}))
    try:
        pipeline.render(sb, tmp_path / "o.mp4", cfg, quiet=True)
    finally:
        srv.shutdown()
    assert hits == []
