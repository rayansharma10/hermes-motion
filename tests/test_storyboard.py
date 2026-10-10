import json
from pathlib import Path

import pytest

from hermes_motion import storyboard as sbm

EXAMPLE = Path(__file__).resolve().parent.parent / "examples" / "agent-team.json"


def test_example_validates():
    sb = sbm.load(EXAMPLE)
    assert len(sb["scenes"]) == 5


def test_forgiving_shapes():
    sb = sbm.validate({"scenes": [
        {"narration": "hi", "nodes": ["A", "B"], "edges": ["A -> B"]},
        {"type": "bullets", "items": "- one\n- two"},
        {"title": "Hello"},
    ]})
    s1, s2, s3 = sb["scenes"]
    assert s1["template"] == "diagram" and s1["data"]["edges"][0] == {"from": "a", "to": "b"}
    assert s2["data"]["items"] == ["one", "two"]
    assert s3["template"] == "title" and s3["min_seconds"] == 3.0
    assert [s["id"] for s in sb["scenes"]] == ["s1", "s2", "s3"]


def test_errors_are_actionable():
    with pytest.raises(sbm.StoryboardError) as e:
        sbm.validate({"scenes": [{"template": "diagram", "data": {
            "nodes": [{"id": "a", "label": "A"}], "edges": [{"from": "a", "to": "zzz"}]}}]})
    msg = str(e.value)
    assert "edges[0].to" in msg and "zzz" in msg and "['a']" in msg


def test_unknown_template_lists_choices():
    with pytest.raises(sbm.StoryboardError) as e:
        sbm.validate({"scenes": [{"template": "spinning-cube", "data": {}}]})
    assert "spinning-cube" in str(e.value) and "diagram" in str(e.value)


def test_empty_scenes_and_bad_json(tmp_path):
    with pytest.raises(sbm.StoryboardError):
        sbm.validate({"scenes": []})
    p = tmp_path / "x.json"
    p.write_text("{nope")
    with pytest.raises(sbm.StoryboardError) as e:
        sbm.load(p)
    assert "not valid JSON" in str(e.value)


def test_chart_length_mismatch():
    with pytest.raises(sbm.StoryboardError):
        sbm.validate({"scenes": [{"template": "chart", "data": {"labels": ["a"], "values": [1, 2]}}]})


def test_duplicate_ids_and_bad_fps():
    with pytest.raises(sbm.StoryboardError) as e:
        sbm.validate({"fps": 60, "scenes": [{"id": "x", "title": "a"}, {"id": "x", "title": "b"}]})
    assert "duplicated" in str(e.value) and "fps" in str(e.value)


def test_schema_is_valid_json_schema():
    import jsonschema
    jsonschema.Draft7Validator.check_schema(sbm.STORYBOARD_SCHEMA)
    json.dumps(sbm.STORYBOARD_SCHEMA)
