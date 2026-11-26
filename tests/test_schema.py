import copy

import pytest
import yaml
from pydantic import ValidationError

from whatif_sports import config
from whatif_sports.script import load_script
from whatif_sports.script.schema import Script, hex_to_rgb
from whatif_sports.visuals.plays import PLAYS

SAMPLE = config.EXAMPLES_DIR / "seahawks-xlix-run.yaml"


@pytest.fixture
def raw():
    return yaml.safe_load(SAMPLE.read_text(encoding="utf-8"))


def test_sample_script_is_valid_and_complete():
    s = load_script("seahawks-xlix-run")
    assert s.id == "seahawks-xlix-run"
    assert s.segments[0].type == "title"
    assert s.sources, "every script must carry its stat sources"
    for seg in s.segments:
        if seg.type == "play_diagram":
            assert seg.play in PLAYS


def test_load_by_path_and_id_match():
    assert load_script(str(SAMPLE)) == load_script("seahawks-xlix-run")


def test_rejects_missing_sources(raw):
    raw["sources"] = []
    with pytest.raises(ValidationError):
        Script.model_validate(raw)


def test_rejects_unknown_segment_type(raw):
    bad = copy.deepcopy(raw)
    bad["segments"][1] = {"type": "game_clip", "narration": "x"}
    with pytest.raises(ValidationError):
        Script.model_validate(bad)


def test_rejects_extra_fields_and_bad_colors(raw):
    bad = copy.deepcopy(raw)
    bad["logo"] = "team.png"
    with pytest.raises(ValidationError):
        Script.model_validate(bad)
    bad = copy.deepcopy(raw)
    bad["accent"] = "green"
    with pytest.raises(ValidationError):
        Script.model_validate(bad)


def test_first_segment_must_be_title(raw):
    raw["segments"] = raw["segments"][1:]
    with pytest.raises(ValidationError):
        Script.model_validate(raw)


def test_hex_to_rgb():
    assert hex_to_rgb("#69BE28") == (0x69, 0xBE, 0x28)
