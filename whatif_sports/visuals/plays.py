"""Named X/O play diagrams, drawn as stylized graphics (no logos, no likenesses).

Field coordinates are in yards: x runs across the field (0 to 53.3, ball at 26.65),
y is distance from the goal line (0 = goal line, negative = inside the end zone).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from functools import lru_cache

from PIL import Image, ImageDraw

from whatif_sports import config
from whatif_sports.visuals.common import (
    RGB,
    arrow_head,
    ease_out,
    ease_out_back,
    font,
    paste,
    pill,
    progress,
)

Pt = tuple[float, float]


@dataclass(frozen=True)
class Player:
    x: float
    y: float
    label: str = ""
    key: bool = False


@dataclass(frozen=True)
class Route:
    points: tuple[Pt, ...]
    kind: str = "route"  # route | run | pass | block | defense
    start: float = 0.0  # fraction of the animation window when drawing starts
    end: float = 1.0  # fraction when drawing finishes
    tag: str = ""  # pill shown at the end once complete, e.g. "INT", "TD"


@dataclass(frozen=True)
class Play:
    name: str
    title: str
    offense: tuple[Player, ...]
    defense: tuple[Player, ...]
    routes: tuple[Route, ...] = field(default_factory=tuple)


# Spacing is stylized (wider than real splits) so 22 players stay readable on a phone.
_LINE = (
    Player(22.6, 1.8),
    Player(24.6, 1.8),
    Player(26.65, 1.8),
    Player(28.7, 1.8),
    Player(30.7, 1.8),
)
_GOAL_LINE_D = (
    Player(21.6, -0.3),
    Player(24.6, -0.3),
    Player(28.7, -0.3),
    Player(31.7, -0.3),
    Player(19.5, -2.8),
    Player(26.65, -3.4),
    Player(33.8, -2.8),
    Player(16.5, -6.5),
    Player(37.0, -6.5),
)

PLAYS: dict[str, Play] = {
    "slant_stack": Play(
        name="slant_stack",
        title="Shotgun, stacked receivers: quick slant",
        offense=(
            *_LINE,
            Player(26.65, 6.5, "QB"),
            Player(23.8, 6.5, "RB"),
            Player(10.0, 1.8),
            Player(39.0, 1.9),
            Player(41.4, 4.4, "WR", key=True),
        ),
        defense=(
            *_GOAL_LINE_D[:7],
            Player(10.0, -1.2),
            Player(39.0, -0.8),
            Player(43.0, -3.2, "CB", key=True),
        ),
        routes=(
            Route(((39.0, 1.9), (37.8, 0.0)), "block", 0.0, 0.25),
            Route(((41.4, 4.4), (40.4, 1.8), (35.0, -2.0)), "route", 0.05, 0.45),
            Route(((26.65, 6.5), (35.3, -1.9)), "pass", 0.45, 0.7),
            Route(((43.0, -3.2), (39.4, -2.6), (35.4, -1.9)), "defense", 0.42, 0.72, tag="INT"),
        ),
    ),
    "inside_zone": Play(
        name="inside_zone",
        title="Goal line: inside zone to the running back",
        offense=(
            *_LINE,
            Player(20.5, 2.0),
            Player(32.8, 2.0),
            Player(26.65, 3.2, "QB"),
            Player(26.65, 8.0, "RB", key=True),
            Player(10.0, 1.8),
        ),
        defense=(*_GOAL_LINE_D, Player(10.0, -1.2)),
        routes=(
            Route(((22.6, 1.8), (23.2, 0.6)), "block", 0.0, 0.25),
            Route(((24.6, 1.8), (25.2, 0.6)), "block", 0.0, 0.25),
            Route(((26.65, 1.8), (27.25, 0.6)), "block", 0.0, 0.25),
            Route(((28.7, 1.8), (29.3, 0.6)), "block", 0.0, 0.25),
            Route(((30.7, 1.8), (31.3, 0.6)), "block", 0.0, 0.25),
            Route(((32.8, 2.0), (33.3, 0.8)), "block", 0.0, 0.25),
            Route(
                ((26.65, 8.0), (27.3, 5.0), (27.7, 1.2), (27.8, -4.5)), "run", 0.25, 0.75, tag="TD"
            ),
        ),
    ),
}

# --- field geometry -------------------------------------------------------------
X_MIN, X_MAX = 6.0, 47.3
Y_MIN, Y_MAX = -9.0, 12.0
BOX = (50, 300, config.WIDTH - 50, 1010)
SX = (BOX[2] - BOX[0]) / (X_MAX - X_MIN)
SY = (BOX[3] - BOX[1]) / (Y_MAX - Y_MIN)
BOX_BOTTOM = BOX[3]


def to_px(p: Pt) -> tuple[float, float]:
    return BOX[0] + (p[0] - X_MIN) * SX, BOX[1] + (p[1] - Y_MIN) * SY


@lru_cache(maxsize=8)
def _field(accent: RGB) -> Image.Image:
    w, h = config.WIDTH, config.HEIGHT
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    x0, y0, x1, y1 = BOX[0], BOX[1], BOX[2], BOX_BOTTOM
    d.rounded_rectangle((x0, y0, x1, y1), radius=28, fill=(16, 42, 32, 235))
    gy = to_px((0, 0))[1]
    d.rounded_rectangle((x0, y0, x1, gy), radius=28, fill=(*accent, 70))
    d.rectangle((x0, gy - 30, x1, gy), fill=(*accent, 70))
    ez = font(40)
    label = "END ZONE"
    tw = d.textlength(label, font=ez)
    d.text(((x0 + x1 - tw) / 2, y0 + 18), label, font=ez, fill=(255, 255, 255, 70))
    for yd in range(0, int(Y_MAX) + 1, 5):
        y = to_px((0, yd))[1]
        d.line(
            (x0, y, x1, y), fill=(255, 255, 255, 200 if yd == 0 else 70), width=8 if yd == 0 else 3
        )
    for yd in range(1, int(Y_MAX)):
        y = to_px((0, yd))[1]
        for hx in (23.6, 29.7):
            px = to_px((hx, 0))[0]
            d.line((px - 10, y, px + 10, y), fill=(255, 255, 255, 60), width=3)
    # line of scrimmage (ball on the 1)
    los = to_px((0, 1.0))[1]
    for xx in range(int(x0) + 10, int(x1) - 10, 36):
        d.line((xx, los, xx + 18, los), fill=(*config.BRAND_YELLOW, 160), width=4)
    return layer


def _partial(points: list[tuple[float, float]], k: float) -> list[tuple[float, float]]:
    """Leading fraction k of a polyline, by length."""
    if k >= 1:
        return points
    segs = [math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)]
    target, out = sum(segs) * k, [points[0]]
    for i, s in enumerate(segs):
        if target <= s:
            f = target / s if s else 0
            a, b = points[i], points[i + 1]
            out.append((a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f))
            return out
        target -= s
        out.append(points[i + 1])
    return out


def _dashed(d: ImageDraw.ImageDraw, pts: list, color, width: int, dash: int = 26) -> None:
    for i in range(len(pts) - 1):
        (ax, ay), (bx, by) = pts[i], pts[i + 1]
        n = max(1, int(math.dist((ax, ay), (bx, by)) // dash))
        for j in range(0, n, 2):
            f0, f1 = j / n, min(1, (j + 1) / n)
            d.line(
                (
                    ax + (bx - ax) * f0,
                    ay + (by - ay) * f0,
                    ax + (bx - ax) * f1,
                    ay + (by - ay) * f1,
                ),
                fill=color,
                width=width,
            )


def draw_play(base: Image.Image, play_name: str, t: float, dur: float, accent: RGB) -> None:
    play = PLAYS[play_name]
    base.alpha_composite(_field(accent))
    layer = Image.new("RGBA", base.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    window_start, window = 0.7, max(1.2, dur - 1.6)
    route_col = {
        "route": (*config.BRAND_WHITE, 235),
        "block": (255, 255, 255, 150),
        "run": (*accent, 255),
        "pass": (*config.BRAND_YELLOW, 255),
        "defense": (*config.BRAND_RED, 255),
    }
    tags: list[tuple[str, tuple[float, float], float, RGB]] = []
    for r in play.routes:
        k = ease_out(progress(t, window_start + r.start * window, (r.end - r.start) * window))
        if k <= 0:
            continue
        pts = _partial([to_px(p) for p in r.points], k)
        col = route_col[r.kind]
        width = 12 if r.kind in ("run", "defense") else 9
        if r.kind == "pass":
            _dashed(d, pts, col, 8)
        else:
            d.line(pts, fill=col, width=width, joint="curve")
        if len(pts) >= 2 and r.kind != "pass":
            if r.kind == "block":
                (ax, ay), (bx, by) = pts[-2], pts[-1]
                ang = math.atan2(by - ay, bx - ax) + math.pi / 2
                dx, dy = 18 * math.cos(ang), 18 * math.sin(ang)
                d.line((bx - dx, by - dy, bx + dx, by + dy), fill=col, width=8)
            else:
                arrow_head(d, pts[-2], pts[-1], col[:3], 40)
        if r.tag and k >= 1:
            tag_k = progress(t, window_start + r.end * window, 0.35)
            tag_col = config.BRAND_RED if r.kind == "defense" else accent
            tags.append((r.tag, to_px(r.points[-1]), tag_k, tag_col))

    base.alpha_composite(layer)

    radius = 22
    every = (*play.offense, *play.defense)
    for i, p in enumerate(every):
        is_off = i < len(play.offense)
        k = ease_out_back(progress(t, 0.04 * i, 0.3))
        if k <= 0:
            continue
        cx, cy = to_px((p.x, p.y))
        r = radius * k
        pd = ImageDraw.Draw(base)
        if is_off:
            fill = (*accent, 255) if p.key else (15, 20, 34, 255)
            pd.ellipse(
                (cx - r, cy - r, cx + r, cy + r),
                fill=fill,
                outline=config.BRAND_WHITE,
                width=max(1, int(7 * k)),
            )
        else:
            col = config.BRAND_RED if p.key else (200, 208, 224)
            w = max(1, int(10 * k))
            pd.line((cx - r, cy - r, cx + r, cy + r), fill=col, width=w)
            pd.line((cx - r, cy + r, cx + r, cy - r), fill=col, width=w)
        if p.label and k >= 0.9:
            lf = font(30)
            tw = pd.textlength(p.label, font=lf)
            ly = cy + radius + 8 if is_off else cy - radius - 42
            pd.text(
                (cx - tw / 2, ly),
                p.label,
                font=lf,
                fill=config.BRAND_WHITE,
                stroke_width=4,
                stroke_fill=(0, 0, 0),
            )

    for text, (x, y), k, col in tags:
        paste(
            base,
            pill(text, 64, config.BRAND_WHITE, col),
            x,
            y - 90,
            scale=ease_out_back(k),
            alpha=k,
        )
