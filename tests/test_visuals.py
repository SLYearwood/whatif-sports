import pytest

from whatif_sports import config
from whatif_sports.script import load_script
from whatif_sports.visuals import Ctx, render_frame
from whatif_sports.visuals.common import count_up, fit_text, slow_zoom

SCRIPT = load_script("seahawks-xlix-run")


@pytest.mark.parametrize("index", range(len(SCRIPT.segments)))
@pytest.mark.parametrize("t", [0.0, 0.5, 2.0, 5.9])
def test_every_template_renders_full_frame(index, t):
    img = render_frame(SCRIPT.segments[index], Ctx(), t, 6.0, caption="and they throw it")
    assert img.size == (config.WIDTH, config.HEIGHT)
    assert img.mode == "RGB"


def test_frames_change_over_time():
    seg = SCRIPT.segments[0]
    a = render_frame(seg, Ctx(), 0.2, 5.0).tobytes()
    b = render_frame(seg, Ctx(), 3.0, 5.0).tobytes()
    assert a != b, "every segment needs motion"


def test_bottom_safe_zone_stays_clear_of_captions():
    seg = SCRIPT.segments[0]
    without = render_frame(seg, Ctx(), 2.0, 5.0, caption="")
    with_cap = render_frame(seg, Ctx(), 2.0, 5.0, caption="a very long caption line here")
    box = (0, config.SAFE_BOTTOM, config.WIDTH, config.HEIGHT)
    assert without.crop(box).tobytes() == with_cap.crop(box).tobytes()


def test_count_up():
    assert count_up("102 yds", 0) == "0 yds"
    assert count_up("102 yds", 1) == "102 yds"
    assert count_up("1,306 YDS", 1) == "1,306 YDS"
    assert count_up("$4.5M", 1) == "$4.5M"
    assert count_up("28-3", 1) == "28-3"
    assert count_up("No number", 0.5) == "No number"


def test_fit_text_shrinks_to_fit():
    f, lines = fit_text("What if the Seahawks just ran it from the one yard line?", 900, 3, 160)
    assert len(lines) <= 3


def test_slow_zoom_keeps_size():
    img = render_frame(SCRIPT.segments[1], Ctx(), 1.0, 4.0)
    assert slow_zoom(img, 3.0, 4.0).size == (config.WIDTH, config.HEIGHT)
