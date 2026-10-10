"""Encoder (m9) and timeline boundary (m6) tests."""
import json
import subprocess

import pytest

from conftest import needs_ffmpeg
from hermes_motion import timeline
from hermes_motion.providers import base
from hermes_motion.providers.base import ProviderUnavailable
from hermes_motion.providers.encode import ffmpeg as ff


def test_codec_args_table():
    e = {"crf": 18, "preset": "medium"}
    assert ff.codec_args("libx264", e)[:2] == ["-c:v", "libx264"] and "-crf" in ff.codec_args("libx264", e)
    assert "-rc" in ff.codec_args("h264_amf", e) and "cqp" in ff.codec_args("h264_amf", e)
    # hardware encoders must not receive AMF-only flags
    for codec in ("h264_nvenc", "h264_qsv", "h264_videotoolbox", "libx265", "something_else"):
        args = ff.codec_args(codec, e)
        assert args[:2] == ["-c:v", codec]
        assert "-qp_i" not in args and "cqp" not in args and "-quality" not in args
    assert "-tag:v" in ff.codec_args("libx265", e)


def _enc(cfg):
    return base.create("encoder", "ffmpeg", cfg)


def test_music_only_honours_volume(cfg, tmp_path):
    frames = tmp_path / "f"
    frames.mkdir()
    (frames / "000000.png").write_bytes(b"x")
    cfg["music"]["volume"] = 0.25
    cmd = _enc(cfg)._cmd(frames, 30, None, tmp_path / "o.mp4", "libx264", tmp_path / "m.wav", 2.0)
    joined = " ".join(cmd)
    assert "[1:a]volume=0.25[a]" in joined and "-map [a]" in joined


def test_narration_plus_music_mixes(cfg, tmp_path):
    frames = tmp_path / "f"
    frames.mkdir()
    (frames / "000000.png").write_bytes(b"x")
    cmd = " ".join(_enc(cfg)._cmd(frames, 30, tmp_path / "n.wav", tmp_path / "o.mp4", "libx264", tmp_path / "m.wav", 2.0))
    assert "amix=inputs=2" in cmd and "[2:a]volume" in cmd


def _make_frames(tmp_path, kind):
    d = tmp_path / kind
    d.mkdir()
    ext = "png" if kind == "png" else "jpg"
    args = ["-q:v", "1"] if kind == "jpg" else []
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", "color=c=0x336699:s=320x240:r=10",
                    "-frames:v", "10", *args, str(d / f"%06d.{ext}")], check=True)
    return d


def _probe(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=color_space,color_primaries,color_transfer,color_range,pix_fmt",
                          "-of", "json", str(path)], capture_output=True, text=True).stdout
    return json.loads(out)["streams"][0]


def _pixel(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vf", "select=eq(n\\,3),scale=in_range=limited:"
                          "in_color_matrix=bt709:out_range=full,format=rgb24", "-frames:v", "1", "-f", "rawvideo", "-"],
                         capture_output=True).stdout
    mid = (240 // 2) * 320 * 3 + (320 // 2) * 3
    return tuple(raw[mid:mid + 3])


@needs_ffmpeg
def test_png_and_jpeg_frames_get_same_tags_and_colour(cfg, tmp_path):
    outs = {}
    for kind in ("png", "jpg"):
        frames = _make_frames(tmp_path, kind)
        out = tmp_path / f"{kind}.mp4"
        _enc(cfg).encode(frames, 10, None, out)
        outs[kind] = out
    tp, tj = _probe(outs["png"]), _probe(outs["jpg"])
    assert tp == tj
    assert tp["color_space"] == "bt709" and tp["color_primaries"] == "bt709" and tp["color_range"] == "tv"
    px_png, px_jpg = _pixel(outs["png"]), _pixel(outs["jpg"])
    assert all(abs(a - b) <= 8 for a, b in zip(px_png, px_jpg)), (px_png, px_jpg)
    # decoded with the tagged matrix, the colour should be close to the source 0x336699
    assert all(abs(a - b) <= 12 for a, b in zip(px_png, (0x33, 0x66, 0x99))), px_png


def _tone(path, seconds=3):
    subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
                    str(path)], check=True)


def _mean_volume(path):
    err = subprocess.run(["ffmpeg", "-i", str(path), "-af", "volumedetect", "-vn", "-f", "null", "-"],
                         capture_output=True, text=True).stderr
    line = next(x for x in err.splitlines() if "mean_volume" in x)
    return float(line.split("mean_volume:")[1].split("dB")[0])


@needs_ffmpeg
def test_music_only_and_mixed_encode(cfg, tmp_path):
    frames = _make_frames(tmp_path, "png")
    music = tmp_path / "m.wav"
    narr = tmp_path / "n.wav"
    _tone(music)
    _tone(narr, 1)
    cfg["music"]["volume"] = 0.5
    loud = tmp_path / "loud.mp4"
    cfg["music"]["volume"] = 1.0
    _enc(cfg).encode(frames, 10, None, loud, music=music, duration=1.0)
    quiet = tmp_path / "quiet.mp4"
    cfg["music"]["volume"] = 0.1
    _enc(cfg).encode(frames, 10, None, quiet, music=music, duration=1.0)
    assert _mean_volume(quiet) < _mean_volume(loud) - 10  # volume applies to music-only (was ignored)
    both = tmp_path / "both.mp4"
    _enc(cfg).encode(frames, 10, narr, both, music=music, duration=1.0)
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=codec_name",
                          "-of", "csv=p=0", str(both)], capture_output=True, text=True).stdout
    assert out.strip() == "aac"


@needs_ffmpeg
def test_encode_timeout_is_reported(cfg, tmp_path):
    frames = _make_frames(tmp_path, "png")
    cfg["encoder"]["timeout_seconds"] = 0.001
    with pytest.raises(ProviderUnavailable) as e:
        _enc(cfg).encode(frames, 10, None, tmp_path / "t.mp4")
    assert "timed out" in str(e.value)


# ---------------------------------------------------------------- m6
class _R:
    def __init__(self, dur):
        self.duration = dur
        self.words = []


@pytest.mark.parametrize("fps", [24, 30])
def test_scene_boundaries_align_with_seek_times(fps):
    sb = {"scenes": [{"id": f"s{i}", "template": "title", "transition": "fade", "narration": "x",
                      "min_seconds": 0} for i in range(40)]}
    durs = [0.37 + 0.113 * i for i in range(40)]
    results = {f"s{i}": _R(d) for i, d in enumerate(durs)}
    tl = timeline.build(sb, results, fps, 0.15, 0.25)
    for sc in tl["scenes"]:
        k = round(sc["start"] * fps)
        assert abs(sc["start"] - k / fps) < 5e-7
        # the frame seeked at k/fps must already show this scene (motion.js tolerance is 1e-6)
        assert k / fps >= sc["start"] - 1e-6
