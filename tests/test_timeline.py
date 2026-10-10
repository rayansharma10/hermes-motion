import numpy as np
import soundfile as sf

from hermes_motion import timeline as tl
from hermes_motion.providers.base import TTSResult, Word
from hermes_motion.providers.tts import align


def _res(tmp_path, name, nwords, per=0.4):
    sr = 24000
    p = tmp_path / f"{name}.wav"
    sf.write(str(p), np.full(int(sr * per * nwords), 0.2, dtype=np.float32), sr)
    ws = [Word(f"w{i}", i * per, (i + 1) * per) for i in range(nwords)]
    return TTSResult(p, per * nwords, ws, "fake", "v", sr)


def _sb(*ids, **extra):
    return {"scenes": [{"id": i, "template": "title", "transition": "fade", "narration": "x",
                        "data": {}, **extra.get(i, {})} for i in ids]}


def test_scene_boundaries_are_frame_aligned_and_follow_narration(tmp_path):
    sb = _sb("a", "b", "c", b={"min_seconds": 6}, c={"narration": "", "min_seconds": 2})
    res = {"a": _res(tmp_path, "a", 5), "b": _res(tmp_path, "b", 2), "c": None}
    t = tl.build(sb, res, 30, 0.2, 0.3)
    s = t["scenes"]
    assert abs(s[0]["length"] - (0.2 + 2.0 + 0.3)) < 1 / 30 + 1e-6
    assert s[1]["length"] >= 6          # min_seconds wins when longer
    assert s[1]["start"] == s[0]["end"]  # contiguous
    for sc in s:                         # every boundary on a frame
        assert abs(sc["start"] * 30 - round(sc["start"] * 30)) < 1e-3
    assert abs(s[0]["narration_start"] - s[0]["start"] - 0.2) < 1e-3
    assert s[2]["words"] == [] and s[2]["audio_offset"] is None
    assert t["total_frames"] == round(t["total_seconds"] * 30)


def test_mix_audio_places_at_offset(tmp_path):
    sb = _sb("a", "b")
    res = {"a": _res(tmp_path, "a", 2), "b": _res(tmp_path, "b", 2)}
    t = tl.build(sb, res, 30, 0.2, 0.3)
    out = tmp_path / "mix.wav"
    total = tl.mix_audio(t, res, out)
    audio, sr = sf.read(str(out))
    assert abs(total - t["total_seconds"]) < 0.01
    off = int(t["scenes"][1]["audio_offset"] * sr)
    assert audio[off + 100] > 0.1 and abs(audio[off - 200]) < 1e-6


def test_cue_times_match_keywords_in_order():
    words = [{"word": w, "start": 1 + i * 0.5, "end": 1.4 + i * 0.5}
             for i, w in enumerate("first we need dogs then cats finally birds".split())]
    cues = tl.cue_times(["dogs", "cats", "birds"], words, scene_start=0, scene_len=6)
    assert cues == sorted(cues)
    assert abs(cues[0] - (1 + 3 * 0.5 - 0.1)) < 1e-6
    assert abs(cues[2] - (1 + 7 * 0.5 - 0.1)) < 1e-6


def test_cue_times_interpolate_unmatched_monotonic():
    words = [{"word": "alpha", "start": 1.0, "end": 1.4}, {"word": "omega", "start": 5.0, "end": 5.4}]
    cues = tl.cue_times(["alpha", "mystery one", "mystery two", "omega"], words, 0, 6)
    assert len(cues) == 4
    assert cues[0] < cues[1] < cues[2] < cues[3]


def test_cue_times_no_words():
    cues = tl.cue_times(["a1", "b2", "c3"], [], 0, 5)
    assert len(cues) == 3 and cues == sorted(cues)


def test_caption_chunks_cover_all_words():
    words = [{"word": f"w{i}" + ("." if i == 6 else ""), "start": i * 0.3, "end": i * 0.3 + 0.25}
             for i in range(14)]
    chunks = tl.caption_chunks(words)
    assert sum(len(c["words"]) for c in chunks) == 14
    for a, b in zip(chunks, chunks[1:]):
        assert a["end"] <= b["start"] + 1e-9


def test_estimate_words_spans_voiced_audio():
    sr = 24000
    audio = np.concatenate([np.zeros(sr // 2), np.full(sr * 2, 0.3), np.zeros(sr // 2)]).astype(np.float32)
    ws = align.estimate_words("one two three, four", audio, sr, offset=10.0)
    assert abs(ws[0].start - 10.5) < 0.01 and abs(ws[-1].end - 12.5) < 0.01
    assert all(a.end <= b.start + 1e-9 for a, b in zip(ws, ws[1:]))
    assert all(type(w.start) is float for w in ws)


def test_split_clauses():
    assert align.split_clauses("One. Two, three! Four") == ["One.", "Two, three!", "Four"]
