"""Broadcast-angle play scenes: stylized players act out a named play from plays.py.

Camera sits high on the near sideline looking across the field, like a TV broadcast.
The offense attacks to the right; the camera pans to follow the ball.

World coordinates (yards): x across the field (0 near sideline .. 53.3 far sideline),
y = distance from the goal line (negative = in the end zone), z = height.
Depth is compressed (stylized) so the whole formation fits a 9:16 frame.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter

from whatif_sports import config
from whatif_sports.visuals import figures as fg
from whatif_sports.visuals.common import (
    RGB,
    clamp,
    ease_in_out,
    ease_out_back,
    mix,
    paste,
    pill,
    progress,
)
from whatif_sports.visuals.plays import PLAYS, Play, Player, Route

W, H = config.WIDTH, config.HEIGHT

# --- camera -------------------------------------------------------------------------
HORIZON = 430
FOCAL = 1480.0
CAM_H = 4.4  # yards above the turf
X_NEAR, D_NEAR, DEPTH_K = 8.0, 7.6, 0.36
PLAYER_H = 2.15  # yards (stylized, a bit heroic)
FIELD_W = 53.3

SNAP_AT = 0.6  # seconds before the snap (pre-snap stance)


def depth(x: float) -> float:
    return D_NEAR + (x - X_NEAR) * DEPTH_K


def project(x: float, y: float, z: float, cam_y: float) -> tuple[float, float, float]:
    """World -> (screen x, screen y, pixels per yard at that depth)."""
    d = max(1.0, depth(x))
    s = FOCAL / d
    return W / 2 + (cam_y - y) * s, HORIZON + (CAM_H - z) * s, s


# --- timing ---------------------------------------------------------------------------
@dataclass(frozen=True)
class Timing:
    dur: float

    @property
    def window(self) -> float:
        return max(1.6, self.dur - SNAP_AT - 1.5)

    def route_k(self, r: Route, t: float) -> float:
        start = SNAP_AT + r.start * self.window
        return progress(t, start, (r.end - r.start) * self.window)

    def route_end(self, r: Route) -> float:
        return SNAP_AT + r.end * self.window

    def route_start(self, r: Route) -> float:
        return SNAP_AT + r.start * self.window


def _along(points: tuple, k: float) -> tuple[float, float]:
    if k <= 0:
        return points[0]
    if k >= 1:
        return points[-1]
    segs = [math.dist(points[i], points[i + 1]) for i in range(len(points) - 1)]
    target = sum(segs) * k
    for i, s in enumerate(segs):
        if target <= s:
            f = target / s if s else 0
            a, b = points[i], points[i + 1]
            return a[0] + (b[0] - a[0]) * f, a[1] + (b[1] - a[1]) * f
        target -= s
    return points[-1]


def _near(a, b, tol: float = 0.15) -> bool:
    return abs(a[0] - b[0]) < tol and abs(a[1] - b[1]) < tol


@dataclass
class Actor:
    player: Player
    offense: bool
    route: Route | None
    lineman: bool


def _cast(play: Play) -> list[Actor]:
    actors = []
    for side, group in ((True, play.offense), (False, play.defense)):
        for p in group:
            route = next(
                (r for r in play.routes if r.kind != "pass" and _near(r.points[0], (p.x, p.y))),
                None,
            )
            lineman = abs(p.y - (1.8 if side else -0.3)) < 0.35 and 20 < p.x < 34
            actors.append(Actor(p, side, route, lineman))
    return actors


def _pass(play: Play) -> Route | None:
    return next((r for r in play.routes if r.kind == "pass"), None)


def _run(play: Play) -> Route | None:
    return next((r for r in play.routes if r.kind == "run"), None)


def _qb(actors: list[Actor]) -> Actor | None:
    return next((a for a in actors if a.player.label == "QB"), None)


# --- positions & ball -----------------------------------------------------------------
def actor_pos(a: Actor, play: Play, tm: Timing, t: float, ball_xy) -> tuple[float, float]:
    p = (a.player.x, a.player.y)
    if a.route:
        k = tm.route_k(a.route, t)
        ease = ease_in_out(k) if a.route.kind == "block" else k
        return _along(a.route.points, ease)
    if t <= SNAP_AT or a.player.label == "QB":
        return p
    # everyone else reacts: drift toward the ball, a couple of yards at most
    k = clamp((t - SNAP_AT) / max(0.5, tm.window)) ** 0.8
    reach = 2.2 if not a.offense else 1.4
    bx, by = ball_xy
    dx, dy = bx - p[0], by - p[1]
    dist = math.hypot(dx, dy) or 1.0
    step = min(dist * 0.5, reach) * k
    return p[0] + dx / dist * step, p[1] + dy / dist * step


def ball_state(play: Play, actors: list[Actor], tm: Timing, t: float):
    """Returns (x, y, z, holder actor or None, spin degrees)."""
    qb = _qb(actors)
    qb_xy = (qb.player.x, qb.player.y) if qb else (26.65, 4.0)
    center = (26.65, 1.0)
    if t < SNAP_AT:
        return center[0], center[1], 0.15, None, 0.0
    snap_k = progress(t, SNAP_AT, 0.22)
    if snap_k < 1:
        x = center[0] + (qb_xy[0] - center[0]) * snap_k
        y = center[1] + (qb_xy[1] - center[1]) * snap_k
        return x, y, 0.3 + 0.6 * snap_k, None, snap_k * 720
    pr = _pass(play)
    if pr:
        k = tm.route_k(pr, t)
        if k <= 0:
            return qb_xy[0], qb_xy[1], 1.0, qb, 0.0
        if k < 1:
            x, y = _along(pr.points, k)
            return x, y, 1.1 + 2.0 * math.sin(math.pi * k), None, k * 1440
        catcher = next(
            (
                a
                for a in actors
                if a.route and _near(a.route.points[-1], pr.points[-1], 0.8) and a.route.tag
            ),
            None,
        )
        catcher = catcher or next((a for a in actors if a.route and a.route.kind == "route"), None)
        return pr.points[-1][0], pr.points[-1][1], 1.0, catcher, 0.0
    rr = _run(play)
    if rr:
        runner = next((a for a in actors if a.route is rr), None)
        if tm.route_k(rr, t) > 0.3:
            return 0, 0, 1.0, runner, 0.0
    return qb_xy[0], qb_xy[1], 1.0, qb, 0.0


# --- poses -------------------------------------------------------------------------------
def actor_pose(
    a: Actor, play: Play, tm: Timing, t: float, moving: float, stride: float, intercepted: bool
) -> tuple[fg.Pose, int | None]:
    """Pose plus forced facing (None = face direction of travel / default)."""
    pre = t < SNAP_AT
    r = a.route
    if pre:
        if a.lineman:
            return fg.STANCE, None
        return fg.READY, None
    if a.player.label == "QB":
        pr = _pass(play)
        if pr:
            k = progress(t, tm.route_start(pr) - 0.25, 0.35)
            if 0 < k < 1:
                return fg.READY.blend(fg.THROW, math.sin(math.pi * k)), None
        return fg.READY, None
    if r and r.kind == "block" or (not a.offense and a.lineman):
        return fg.BLOCK, None
    if r and r.tag:
        end = tm.route_end(r)
        if r.tag == "TD":
            dive_k = progress(t, end - 0.35, 0.3)
            if t > end + 0.45:
                return fg.celebrate_pose(t - end), 1
            if dive_k > 0:
                return fg.run_pose(stride).blend(fg.DIVE, dive_k), None
        if r.tag == "INT" and t > end - 0.15:
            if t < end + 0.5:
                return fg.CATCH, None
            return fg.celebrate_pose(t - end), None
    if intercepted and r and r.kind == "route" and t > tm.route_end(r):
        return fg.DEJECTED, None
    if moving > 0.15:
        return fg.run_pose(stride, clamp(moving / 1.2, 0.4, 1.0)), None
    return fg.READY, None


# --- backdrop -----------------------------------------------------------------------------
@lru_cache(maxsize=4)
def _crowd(accent: RGB) -> Image.Image:
    """Wide crowd strip (parallax-scrolled), generated once per accent color."""
    rnd = random.Random(7)
    w, h = W * 3, 420
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for row in range(26):
        y = h - 20 - row * 15
        size = 9 - row * 0.2
        shade = 0.65 + row * 0.012
        for x in range(0, w, 12):
            c = rnd.choice([accent, (200, 205, 215), (60, 70, 95), (120, 30, 40), (30, 40, 70)])
            c = mix(c, (10, 14, 26), shade)
            jx = rnd.uniform(-4, 4)
            d.ellipse((x + jx - size / 2, y - size, x + jx + size / 2, y), fill=(*c, 255))
            d.rectangle(
                (x + jx - size / 1.6, y - size * 0.25, x + jx + size / 1.6, y + 6),
                fill=(*mix(c, (0, 0, 0), 0.3), 255),
            )
    return img


@lru_cache(maxsize=4)
def _sky(accent: RGB) -> Image.Image:
    img = Image.new("RGBA", (W, H), (*config.BG_TOP, 255))
    d = ImageDraw.Draw(img)
    for y in range(0, 700, 4):
        d.rectangle((0, y, W, y + 4), fill=(*mix(config.BG_TOP, (30, 40, 70), y / 700), 255))
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    for lx in (120, 540, 960):
        gd.ellipse((lx - 160, 40, lx + 160, 260), fill=(255, 250, 220, 70))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(60)))
    for lx in (120, 540, 960):  # light banks
        for i in range(5):
            for j in range(2):
                gd2 = ImageDraw.Draw(img)
                cx, cy = lx - 48 + i * 24, 140 + j * 22
                gd2.ellipse((cx - 8, cy - 8, cx + 8, cy + 8), fill=(255, 252, 235, 255))
    return img


def _poly(cam_y: float, pts) -> list[tuple[float, float]]:
    return [project(x, y, 0, cam_y)[:2] for x, y in pts]


def draw_field(img: Image.Image, cam_y: float, accent: RGB, t: float) -> None:
    img.alpha_composite(_sky(accent))
    crowd = _crowd(accent)
    off = int((cam_y * 9 + t * 4) % (crowd.width - W))
    far_line_y = project(FIELD_W, 0, 0, cam_y)[1]
    img.alpha_composite(
        crowd.crop((off, 0, off + W, crowd.height)), (0, int(far_line_y - crowd.height - 34))
    )
    d = ImageDraw.Draw(img)
    # sideline wall with a team-color band
    d.rectangle((0, far_line_y - 40, W, far_line_y - 6), fill=(18, 24, 40))
    d.rectangle((0, far_line_y - 30, W, far_line_y - 22), fill=accent)

    grass_a, grass_b = (34, 92, 52), (30, 84, 47)
    y_lo, y_hi = cam_y - 45, cam_y + 45
    # near sideline / bench area fills everything below the field
    near = project(0, cam_y, 0, cam_y)[1]
    d.rectangle((0, near, W, H), fill=(24, 58, 36))
    # out of bounds behind the end line
    d.polygon(
        _poly(cam_y, [(0, -10), (0, y_lo - 30), (FIELD_W, y_lo - 30), (FIELD_W, -10)]),
        fill=(26, 70, 40),
    )
    start = math.floor(max(-10, y_lo) / 5) * 5
    yy = start
    while yy < y_hi:
        y0, y1 = max(yy, -10), yy + 5
        c = grass_a if int(math.floor(yy / 5)) % 2 == 0 else grass_b
        if y1 <= 0:
            c = mix(accent, (20, 40, 30), 0.45)
        d.polygon(_poly(cam_y, [(0, y0), (0, y1), (FIELD_W, y1), (FIELD_W, y0)]), fill=c)
        yy += 5
    # sideline paint
    d.line(_poly(cam_y, [(0.2, y_lo), (0.2, y_hi)]), fill=(240, 240, 240), width=6)
    d.line(
        _poly(cam_y, [(FIELD_W - 0.2, y_lo), (FIELD_W - 0.2, y_hi)]), fill=(230, 230, 230), width=3
    )
    # yard lines, goal line, end line, hash marks
    for yd in range(int(max(-10, y_lo)), int(y_hi) + 1):
        if yd % 5 == 0 or yd == -10:
            w = 7 if yd in (0, -10) else 4
            d.line(_poly(cam_y, [(0, yd), (FIELD_W, yd)]), fill=(245, 245, 245), width=w)
        elif yd > 0:
            for hx in (23.6, 29.7):
                d.line(
                    _poly(cam_y, [(hx - 0.4, yd), (hx + 0.4, yd)]), fill=(235, 235, 235), width=3
                )
    # broadcast-style line of scrimmage
    d.line(_poly(cam_y, [(0, 1.0), (FIELD_W, 1.0)]), fill=(80, 140, 255), width=6)
    _goal_post(d, cam_y)


def _goal_post(d: ImageDraw.ImageDraw, cam_y: float) -> None:
    yellow = (250, 214, 40)
    base = project(26.65, -11.0, 0, cam_y)
    bar_l = project(23.6, -11.0, 3.3, cam_y)
    bar_r = project(29.7, -11.0, 3.3, cam_y)
    mid = project(26.65, -11.0, 3.3, cam_y)
    w = max(3, int(base[2] * 0.18))
    d.line([base[:2], mid[:2]], fill=yellow, width=w)
    d.line([bar_l[:2], bar_r[:2]], fill=yellow, width=w)
    for x in (23.6, 29.7):
        lo = project(x, -11.0, 3.3, cam_y)
        hi = project(x, -11.0, 10.0, cam_y)
        d.line([lo[:2], hi[:2]], fill=yellow, width=w)


# --- main --------------------------------------------------------------------------------
@dataclass(frozen=True)
class Kits:
    offense: fg.Kit
    defense: fg.Kit


def _camera_y(play: Play, actors, tm: Timing, t: float) -> float:
    samples = []
    for i in range(6):
        ts = max(0.0, t - i * 0.12)
        bx, by, *_ = ball_state(play, actors, tm, ts)
        holder = ball_state(play, actors, tm, ts)[3]
        if holder is not None:
            bx, by = actor_pos(holder, play, tm, ts, (bx, by))
        samples.append(by)
    ball_y = sum(samples) / len(samples)
    # Anchor on the whole play (every route plus the key players), lean partly toward the
    # ball. Following the ball alone pans to the QB and loses the receiver and defender.
    ys = [p[1] for r in play.routes for p in r.points]
    ys += [p.y for p in (*play.offense, *play.defense) if p.key or p.label]
    center = (min(ys) + max(ys)) / 2
    return center * 0.55 + ball_y * 0.45


def _mirror(play: Play) -> Play:
    """Reflect a play across the field's long axis (x -> 53.3 - x)."""

    def mp(p: Player) -> Player:
        return Player(FIELD_W - p.x, p.y, p.label, p.key)

    def mr(r: Route) -> Route:
        return Route(tuple((FIELD_W - x, y) for x, y in r.points), r.kind, r.start, r.end, r.tag)

    return Play(
        play.name,
        play.title,
        tuple(mp(p) for p in play.offense),
        tuple(mp(p) for p in play.defense),
        tuple(mr(r) for r in play.routes),
    )


@lru_cache(maxsize=32)
def framed(play_name: str) -> Play:
    """The play as filmed: shot from whichever sideline is nearer its key players."""
    play = PLAYS[play_name]
    keys = [p.x for p in (*play.offense, *play.defense) if p.key]
    if keys and sum(keys) / len(keys) > FIELD_W / 2 + 1:
        return _mirror(play)
    return play


def draw_scene(
    img: Image.Image, play_name: str, t: float, dur: float, kits: Kits, accent: RGB
) -> None:
    play = framed(play_name)
    tm = Timing(dur)
    actors = _cast(play)
    cam_y = _camera_y(play, actors, tm, t)
    draw_field(img, cam_y, accent, t)

    bx, by, bz, holder, spin = ball_state(play, actors, tm, t)
    ball_xy = (bx, by)
    pr = _pass(play)
    intercepted = bool(
        pr and any(a.route and a.route.tag == "INT" for a in actors) and tm.route_k(pr, t) >= 1
    )

    sprites = []
    for a in actors:
        x, y = actor_pos(a, play, tm, t, ball_xy)
        x0, y0 = actor_pos(a, play, tm, max(0.0, t - 1 / 15), ball_xy)
        speed = math.hypot(x - x0, y - y0) * 15  # yards per second
        travelled = _travelled(a, play, tm, t, ball_xy)
        stride = travelled / 1.9 * 2 * math.pi
        pose, forced = actor_pose(a, play, tm, t, speed, stride, intercepted)
        if forced is not None:
            facing = forced
        elif speed > 0.3 and abs(y - y0) > 0.002:
            facing = 1 if y < y0 else -1  # toward the end zone = screen right
        else:
            facing = 1 if a.offense else -1
        if not a.offense and pose is fg.CATCH:
            facing = -1
        sx, sy, s = project(x, y, 0, cam_y)
        if sx < -200 or sx > W + 200:
            continue
        kit = kits.offense if a.offense else kits.defense
        carrying = holder is a
        sprites.append((depth(x), a, pose, facing, sx, sy, s, kit, carrying))

    # far to near so nearer players overlap farther ones
    for _depth, a, pose, facing, sx, sy, s, kit, carrying in sorted(sprites, key=lambda r: -r[0]):
        f = fg.draw_figure(pose, PLAYER_H * s, kit, facing, ball=carrying)
        img.alpha_composite(f.image, (int(sx - f.anchor[0]), int(sy - f.anchor[1])))
        if a.player.label and a.player.key:
            tag = pill(a.player.label, 34, (12, 14, 22), config.BRAND_WHITE, 16, 8)
            paste(img, tag, sx, sy - PLAYER_H * s - 46, alpha=0.92)
        r = a.route
        if r and r.tag:
            k = progress(t, tm.route_end(r) + 0.1, 0.35)
            if k > 0:
                col = config.BRAND_RED if r.tag == "INT" else accent
                paste(
                    img,
                    pill(r.tag, 84, config.BRAND_WHITE, col, 40, 16),
                    sx,
                    sy - PLAYER_H * s - 130,
                    scale=ease_out_back(k),
                    alpha=k,
                )

    if holder is None:  # loose ball: snap or pass in flight
        sx, sy, s = project(bx, by, bz, cam_y)
        sh = project(bx, by, 0, cam_y)
        d = ImageDraw.Draw(img)
        d.ellipse(
            (sh[0] - s * 0.3, sh[1] - s * 0.08, sh[0] + s * 0.3, sh[1] + s * 0.08),
            fill=(0, 0, 0, 90),
        )
        bs = fg.ball_sprite(max(10, s * 0.22), spin)
        img.alpha_composite(bs, (int(sx - bs.width / 2), int(sy - bs.height / 2)))


def _travelled(a: Actor, play: Play, tm: Timing, t: float, ball_xy) -> float:
    """Approximate distance covered so far (drives the stride phase)."""
    total, prev = 0.0, actor_pos(a, play, tm, 0.0, ball_xy)
    steps = max(1, int(t * 10))
    for i in range(1, steps + 1):
        cur = actor_pos(a, play, tm, t * i / steps, ball_xy)
        total += math.dist(cur, prev)
        prev = cur
    return total
