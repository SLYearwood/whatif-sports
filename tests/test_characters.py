"""Stylized players and broadcast play scenes."""

import pytest
from pydantic import ValidationError

from whatif_sports import config
from whatif_sports.script.schema import MomentSegment, PlaySceneSegment
from whatif_sports.visuals import Ctx, render_frame, scene
from whatif_sports.visuals import figures as fg
from whatif_sports.visuals.plays import PLAYS

SEA = {"jersey": "#002244", "pants": "#A5ACAF", "helmet": "#002244", "trim": "#69BE28"}
NE = {"jersey": "#F2F2F2", "pants": "#B0B7BC", "helmet": "#002244", "trim": "#C60C30"}
KIT = fg.Kit(jersey=(0, 34, 68))


@pytest.mark.parametrize("name", sorted(fg.POSES))
@pytest.mark.parametrize("facing", [1, -1])
def test_every_pose_draws_a_grounded_sprite(name, facing):
    f = fg.draw_figure(fg.POSES[name], 200, KIT, facing, ball=True)
    assert f.image.mode == "RGBA"
    assert f.image.getbbox() is not None, "sprite must not be empty"
    x, y = f.anchor
    assert 0 <= x <= f.image.width and 0 <= y <= f.image.height


def test_run_cycle_moves_legs():
    a, b = fg.run_pose(0.5), fg.run_pose(0.5 + 3.14159)
    assert a.near_thigh == pytest.approx(-b.near_thigh, abs=1e-3)


def test_pose_blend_endpoints():
    assert fg.STAND.blend(fg.DIVE, 0) == fg.STAND
    assert fg.STAND.blend(fg.DIVE, 1) == fg.DIVE


@pytest.mark.parametrize("play", sorted(PLAYS))
@pytest.mark.parametrize("t", [0.0, 0.7, 2.5, 4.5, 6.9])
def test_play_scene_renders(play, t):
    seg = PlaySceneSegment(
        type="play_scene", play=play, label="What if", offense=SEA, defense=NE, narration="x"
    )
    img = render_frame(seg, Ctx(), t, 7.0, caption="hand it off")
    assert img.size == (config.WIDTH, config.HEIGHT)


def test_play_scene_animates():
    seg = PlaySceneSegment(
        type="play_scene", play="inside_zone", offense=SEA, defense=NE, narration="x"
    )
    a = render_frame(seg, Ctx(), 0.2, 6.0).tobytes()
    b = render_frame(seg, Ctx(), 3.5, 6.0).tobytes()
    assert a != b


def test_every_route_belongs_to_a_player():
    for play in PLAYS.values():
        actors = scene._cast(play)
        for r in play.routes:
            if r.kind == "pass":
                continue
            assert any(a.route is r for a in actors), f"{play.name}: orphan route {r.points[0]}"


def test_interception_ball_ends_with_defender():
    play = PLAYS["slant_stack"]
    actors = scene._cast(play)
    tm = scene.Timing(7.0)
    *_, holder, _ = scene.ball_state(play, actors, tm, 6.9)
    assert holder is not None and not holder.offense


def test_touchdown_ball_ends_with_runner():
    play = PLAYS["inside_zone"]
    actors = scene._cast(play)
    tm = scene.Timing(7.0)
    *_, holder, _ = scene.ball_state(play, actors, tm, 6.9)
    assert holder is not None and holder.offense and holder.route.tag == "TD"


@pytest.mark.parametrize("pose", ["celebrate", "dejected", "dive", "run"])
def test_moment_renders(pose):
    seg = MomentSegment(
        type="moment", pose=pose, kit=SEA, text="Back to back", year=2015, narration="x"
    )
    assert render_frame(seg, Ctx(), 1.0, 4.0).size == (config.WIDTH, config.HEIGHT)


def test_kit_colors_validated():
    with pytest.raises(ValidationError):
        PlaySceneSegment(
            type="play_scene",
            play="inside_zone",
            offense={"jersey": "navy"},
            defense=NE,
            narration="x",
        )
