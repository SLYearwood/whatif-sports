"""Stylized football players: faceless, helmeted mannequins built from joint angles.

They are deliberately generic (no faces, no numbers, no logos) so they never depict a
real athlete. Team identity comes only from jersey and helmet colors.

Conventions (screen space, y down, figure facing +x):
- limb angles: 0 = hanging straight down, positive rotates forward (toward +x)
- torso lean: 0 = upright, positive leans forward
- knee bend folds the shin backward; elbow bend folds the forearm forward/up
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields

from PIL import Image, ImageDraw

from whatif_sports.visuals.common import RGB, mix

SS = 2  # supersampling factor for smooth edges

# segment lengths as fractions of standing height
THIGH, SHIN, TORSO = 0.245, 0.245, 0.30
UPPER_ARM, FOREARM, NECK, HEAD_R = 0.16, 0.15, 0.03, 0.085
SHOE = (18, 20, 28)


@dataclass(frozen=True)
class Pose:
    lean: float = 8.0
    head: float = 0.0
    near_thigh: float = 0.0
    near_knee: float = 5.0
    far_thigh: float = 0.0
    far_knee: float = 5.0
    near_arm: float = 10.0
    near_elbow: float = 20.0
    far_arm: float = -10.0
    far_elbow: float = 20.0
    lift: float = 0.0  # extra pelvis height (jumps, dives), in body heights

    def blend(self, other: Pose, k: float) -> Pose:
        k = max(0.0, min(1.0, k))
        return Pose(
            **{
                f.name: getattr(self, f.name) + (getattr(other, f.name) - getattr(self, f.name)) * k
                for f in fields(Pose)
            }
        )


STAND = Pose()
READY = Pose(
    lean=18,
    near_thigh=22,
    near_knee=40,
    far_thigh=10,
    far_knee=30,
    near_arm=35,
    near_elbow=70,
    far_arm=25,
    far_elbow=70,
)
STANCE = Pose(
    lean=62,
    head=-25,
    near_thigh=75,
    near_knee=115,
    far_thigh=40,
    far_knee=95,
    near_arm=28,
    near_elbow=0,
    far_arm=-5,
    far_elbow=40,
)
BLOCK = Pose(
    lean=38,
    head=-10,
    near_thigh=35,
    near_knee=55,
    far_thigh=-25,
    far_knee=15,
    near_arm=80,
    near_elbow=25,
    far_arm=70,
    far_elbow=30,
)
DIVE = Pose(
    lean=84,
    head=-55,
    near_thigh=-92,
    near_knee=12,
    far_thigh=-80,
    far_knee=30,
    near_arm=100,
    near_elbow=5,
    far_arm=88,
    far_elbow=10,
    lift=0.30,
)
CELEBRATE = Pose(
    lean=-6,
    head=15,
    near_thigh=12,
    near_knee=20,
    far_thigh=-8,
    far_knee=25,
    near_arm=170,
    near_elbow=10,
    far_arm=155,
    far_elbow=15,
)
DEJECTED = Pose(
    lean=40,
    head=-35,
    near_thigh=28,
    near_knee=50,
    far_thigh=18,
    far_knee=45,
    near_arm=40,
    near_elbow=10,
    far_arm=30,
    far_elbow=10,
)
CATCH = Pose(
    lean=5,
    head=20,
    near_thigh=20,
    near_knee=35,
    far_thigh=-15,
    far_knee=40,
    near_arm=150,
    near_elbow=25,
    far_arm=140,
    far_elbow=30,
    lift=0.06,
)
THROW = Pose(
    lean=-4,
    near_thigh=18,
    near_knee=20,
    far_thigh=-18,
    far_knee=15,
    near_arm=150,
    near_elbow=60,
    far_arm=70,
    far_elbow=20,
)

POSES = {
    "stand": STAND,
    "ready": READY,
    "stance": STANCE,
    "block": BLOCK,
    "dive": DIVE,
    "celebrate": CELEBRATE,
    "dejected": DEJECTED,
    "catch": CATCH,
    "throw": THROW,
}


def run_pose(phase: float, intensity: float = 1.0) -> Pose:
    """Run cycle; phase in radians (one stride per 2*pi)."""
    s = math.sin(phase)
    c = math.cos(phase)
    a = 42 * intensity
    return Pose(
        lean=20 * intensity + 4,
        head=-6,
        near_thigh=a * s,
        near_knee=20 + 70 * intensity * max(0.0, -c) ** 0.8,
        far_thigh=-a * s,
        far_knee=20 + 70 * intensity * max(0.0, c) ** 0.8,
        near_arm=-40 * intensity * s + 15,
        near_elbow=85,
        far_arm=40 * intensity * s + 15,
        far_elbow=85,
        lift=0.025 * intensity * abs(c),
    )


def celebrate_pose(t: float) -> Pose:
    """Arms-up celebration that bounces."""
    bounce = abs(math.sin(t * 6.0))
    p = CELEBRATE
    return Pose(
        **{
            **{f.name: getattr(p, f.name) for f in fields(Pose)},
            "lift": 0.12 * bounce,
            "near_arm": 170 - 18 * bounce,
            "far_arm": 150 + 15 * bounce,
        }
    )


@dataclass(frozen=True)
class Kit:
    """Uniform colors. Only colors: no numbers, logos, or names."""

    jersey: RGB
    pants: RGB = (225, 228, 236)
    helmet: RGB | None = None
    trim: RGB = (245, 247, 250)

    @property
    def helmet_color(self) -> RGB:
        return self.helmet or self.jersey


def _vec(angle_deg: float, length: float) -> tuple[float, float]:
    a = math.radians(angle_deg)
    return math.sin(a) * length, math.cos(a) * length


def _joints(p: Pose) -> dict[str, tuple[float, float]]:
    """Joint positions in body-height units, pelvis at origin, y down."""
    j: dict[str, tuple[float, float]] = {"pelvis": (0.0, 0.0)}
    lean = math.radians(p.lean)
    j["shoulder"] = (math.sin(lean) * TORSO, -math.cos(lean) * TORSO)
    neck = (j["shoulder"][0] + math.sin(lean) * NECK, j["shoulder"][1] - math.cos(lean) * NECK)
    hl = math.radians(p.lean * 0.6 + p.head)
    j["head"] = (neck[0] + math.sin(hl) * HEAD_R, neck[1] - math.cos(hl) * HEAD_R)
    for side in ("near", "far"):
        t, k = getattr(p, f"{side}_thigh"), getattr(p, f"{side}_knee")
        dx, dy = _vec(t, THIGH)
        knee = (dx, dy)
        sx, sy = _vec(t - k, SHIN)
        ankle = (knee[0] + sx, knee[1] + sy)
        j[f"{side}_knee"], j[f"{side}_ankle"] = knee, ankle
        fx, fy = _vec(t - k + 90, 0.07)
        j[f"{side}_toe"] = (ankle[0] + fx, ankle[1] + fy)
        a, e = getattr(p, f"{side}_arm"), getattr(p, f"{side}_elbow")
        ux, uy = _vec(a, UPPER_ARM)
        elbow = (j["shoulder"][0] + ux, j["shoulder"][1] + uy)
        fx2, fy2 = _vec(a + e, FOREARM)
        j[f"{side}_elbow"], j[f"{side}_hand"] = elbow, (elbow[0] + fx2, elbow[1] + fy2)
    # stand the figure on the ground: lowest foot point at y=0, then lift
    ground = max(j["near_ankle"][1], j["far_ankle"][1], j["near_toe"][1], j["far_toe"][1])
    off = -ground - p.lift
    return {k: (x, y + off) for k, (x, y) in j.items()}


# --- low-poly drawing -----------------------------------------------------------------
# Faceted, flat-shaded blocks (the channel's low-poly look). Light comes from the
# upper left, so faces turned toward it are lighter and the others darker.
LIGHT = (-0.55, -0.83)
SKIN_TONES = [(204, 150, 104), (168, 112, 74), (124, 82, 54), (226, 184, 146)]
EDGE = (10, 12, 20, 160)


def tint(c, k: float):
    """Lighten (k > 0) or darken (k < 0) an RGB color."""
    return mix(c, (255, 255, 255), k) if k > 0 else mix(c, (0, 0, 0), -k)


def _facet(normal: tuple[float, float]) -> float:
    """Shade amount for a face with this outward normal (-0.3 .. +0.22)."""
    nx, ny = normal
    n = math.hypot(nx, ny) or 1.0
    dot = (nx * LIGHT[0] + ny * LIGHT[1]) / n
    return 0.22 * dot if dot > 0 else 0.3 * dot


def _block(d: ImageDraw.ImageDraw, a, b, w_a: float, w_b: float, color, edge: float) -> None:
    """A faceted limb from a to b: two flat-shaded faces split along its length."""
    ax, ay = a
    bx, by = b
    dx, dy = bx - ax, by - ay
    length = math.hypot(dx, dy) or 1e-6
    nx, ny = -dy / length, dx / length
    ha, hb = w_a / 2, w_b / 2
    # extend slightly past both joints so neighbouring blocks overlap without gaps
    ex, ey = dx / length * ha * 0.5, dy / length * ha * 0.5
    a2, b2 = (ax - ex, ay - ey), (bx + ex, by + ey)
    left = [(a2[0] + nx * ha, a2[1] + ny * ha), (b2[0] + nx * hb, b2[1] + ny * hb), b2, a2]
    right = [a2, b2, (b2[0] - nx * hb, b2[1] - ny * hb), (a2[0] - nx * ha, a2[1] - ny * ha)]
    d.polygon(left, fill=tint(color, _facet((nx, ny))))
    d.polygon(right, fill=tint(color, _facet((-nx, -ny))))
    d.polygon([left[0], left[1], right[2], right[3]], outline=EDGE, width=max(1, int(edge)))


def _gem(
    d: ImageDraw.ImageDraw,
    c,
    r: float,
    color,
    sides: int = 8,
    squash: float = 1.0,
    rot: float = 0.0,
    edge: float = 1.0,
) -> list[tuple[float, float]]:
    """A faceted polygon: one flat-shaded triangle per side, like a low-poly sphere."""
    cx, cy = c
    pts = [
        (
            cx + math.cos(rot + i * 2 * math.pi / sides) * r,
            cy + math.sin(rot + i * 2 * math.pi / sides) * r * squash,
        )
        for i in range(sides)
    ]
    for i in range(sides):
        p1, p2 = pts[i], pts[(i + 1) % sides]
        mxp, myp = (p1[0] + p2[0]) / 2 - cx, (p1[1] + p2[1]) / 2 - cy
        d.polygon([c, p1, p2], fill=tint(color, _facet((mxp, myp)) * 1.3))
    d.polygon(pts, outline=EDGE, width=max(1, int(edge)))
    return pts


@dataclass(frozen=True)
class Figure:
    image: Image.Image  # RGBA
    anchor: tuple[float, float]  # ground point under the pelvis, in image pixels
    hand: tuple[float, float]  # near hand, relative to anchor (pixels)


def draw_figure(
    pose: Pose,
    height_px: float,
    kit: Kit,
    facing: int = 1,
    ball: bool = False,
    shadow: bool = True,
    skin: RGB | None = None,
) -> Figure:
    """Render one player as a supersampled, low-poly RGBA sprite."""
    h = height_px * SS
    j = _joints(pose)
    # size the canvas to this pose (plus room for helmet, pads, limb thickness and shadow)
    xs = [p[0] * facing for p in j.values()] + [-0.4, 0.4]
    ys = [p[1] for p in j.values()] + [0.05]
    pad = 0.2
    left, right = min(xs) - pad, max(xs) + pad
    top, bottom = min(ys) - pad, max(ys) + pad
    w_img, h_img = int((right - left) * h) + 2, int((bottom - top) * h) + 2
    ox, oy = -left * h, -top * h
    img = Image.new("RGBA", (w_img, h_img), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def P(name: str) -> tuple[float, float]:
        x, y = j[name]
        return ox + x * h * facing, oy + y * h

    edge = h * 0.008
    far = -0.28  # far-side limbs sit in shadow
    jersey, pants, helmet, trim = kit.jersey, kit.pants, kit.helmet_color, kit.trim
    skin = skin or SKIN_TONES[0]

    if shadow:
        sw = h * (0.32 + 0.25 * min(1.0, pose.lift * 3))
        d.ellipse((ox - sw, oy - h * 0.035, ox + sw, oy + h * 0.035), fill=(0, 0, 0, 90))

    def leg(side: str, shade: float) -> None:
        _block(d, P("pelvis"), P(f"{side}_knee"), h * 0.145, h * 0.115, tint(pants, shade), edge)
        _gem(d, P(f"{side}_knee"), h * 0.052, tint(pants, shade - 0.06), 6, edge=edge)
        _block(
            d,
            P(f"{side}_knee"),
            P(f"{side}_ankle"),
            h * 0.095,
            h * 0.075,
            tint(jersey, shade - 0.08),
            edge,
        )
        _block(
            d, P(f"{side}_ankle"), P(f"{side}_toe"), h * 0.075, h * 0.06, tint(SHOE, shade), edge
        )

    def arm(side: str, shade: float) -> None:
        _block(d, P("shoulder"), P(f"{side}_elbow"), h * 0.1, h * 0.085, tint(jersey, shade), edge)
        _block(
            d, P(f"{side}_elbow"), P(f"{side}_hand"), h * 0.08, h * 0.07, tint(skin, shade), edge
        )
        _gem(d, P(f"{side}_hand"), h * 0.045, tint(skin, shade), 4, rot=math.pi / 4, edge=edge)

    arm("far", far)
    leg("far", far)

    # torso: a boxy chest split into a lit front face and a shaded back face
    px, py = P("pelvis")
    sx, sy = P("shoulder")
    ux, uy = sx - px, sy - py
    ul = math.hypot(ux, uy) or 1.0
    nx, ny = -uy / ul * facing, ux / ul * facing  # toward the chest's front
    wb, wt = h * 0.125, h * 0.175
    back = [(px - nx * wb, py - ny * wb), (sx - nx * wt, sy - ny * wt), (sx, sy), (px, py)]
    front = [(px, py), (sx, sy), (sx + nx * wt, sy + ny * wt), (px + nx * wb, py + ny * wb)]
    d.polygon(back, fill=tint(jersey, -0.22))
    d.polygon(front, fill=tint(jersey, 0.06))
    d.polygon([back[0], back[1], front[2], front[3]], outline=EDGE, width=max(1, int(edge)))
    # waist band in the trim color
    _block(
        d,
        (px - nx * wb, py - ny * wb),
        (px + nx * wb, py + ny * wb),
        h * 0.045,
        h * 0.045,
        tint(trim, -0.05),
        edge,
    )
    # shoulder pads: a wide, squashed gem sitting across the shoulders
    _gem(d, (sx, sy), h * 0.185, jersey, 6, squash=0.7, rot=math.atan2(ny, nx), edge=edge)

    leg("near", 0.0)

    # helmet: faceted shell, face block, and a face mask in the trim color
    hx, hy = P("head")
    r = HEAD_R * h * 1.3
    tilt = math.radians(pose.lean * 0.6 + pose.head)
    fx, fy = math.cos(tilt) * facing, math.sin(tilt)  # forward, along the gaze
    gx, gy = -fy * facing, fx * facing  # "down" relative to the head (gaze turned 90°)
    _gem(d, (hx, hy), r, helmet, 8, rot=tilt, edge=edge)
    c = (hx + fx * r * 0.5 + gx * r * 0.2, hy + fy * r * 0.5 + gy * r * 0.2)
    face = [
        (c[0] - fx * r * 0.25 - gx * r * 0.38, c[1] - fy * r * 0.25 - gy * r * 0.38),
        (c[0] + fx * r * 0.32 - gx * r * 0.38, c[1] + fy * r * 0.32 - gy * r * 0.38),
        (c[0] + fx * r * 0.32 + gx * r * 0.45, c[1] + fy * r * 0.32 + gy * r * 0.45),
        (c[0] - fx * r * 0.25 + gx * r * 0.45, c[1] - fy * r * 0.25 + gy * r * 0.45),
    ]
    d.polygon(face, fill=tint(skin, -0.12))
    bar = max(1, int(h * 0.016))
    for k in (-0.08, 0.2):  # horizontal bars of the face mask
        a0 = (c[0] - fx * r * 0.05 + gx * r * k, c[1] - fy * r * 0.05 + gy * r * k)
        a1 = (c[0] + fx * r * 0.52 + gx * r * k, c[1] + fy * r * 0.52 + gy * r * k)
        d.line([a0, a1], fill=trim, width=bar)
    m0 = (c[0] + fx * r * 0.45 - gx * r * 0.35, c[1] + fy * r * 0.45 - gy * r * 0.35)
    m1 = (c[0] + fx * r * 0.45 + gx * r * 0.45, c[1] + fy * r * 0.45 + gy * r * 0.45)
    d.line([m0, m1], fill=trim, width=bar)
    # stripe over the crown
    s0 = (hx - fx * r * 0.65 - gx * r * 0.6, hy - fy * r * 0.65 - gy * r * 0.6)
    s1 = (hx + fx * r * 0.3 - gx * r * 0.92, hy + fy * r * 0.3 - gy * r * 0.92)
    d.line([s0, s1], fill=trim, width=max(1, int(h * 0.02)))

    hand = P("near_hand")
    if ball:
        _draw_ball(d, hand, h * 0.075, facing)

    arm("near", 0.0)

    out = img.resize((w_img // SS, h_img // SS), Image.LANCZOS)
    return Figure(out, (ox / SS, oy / SS), ((hand[0] - ox) / SS, (hand[1] - oy) / SS))


BALL = (128, 70, 36)


def _draw_ball(d: ImageDraw.ImageDraw, c, size: float, facing: int = 1) -> None:
    """Low-poly football: a faceted, elongated gem with white laces."""
    _gem(d, c, size * 1.3, BALL, 8, squash=0.6, edge=max(1.0, size * 0.06))
    x, y = c
    d.line(
        [(x - size * 0.45, y - size * 0.12), (x + size * 0.45, y - size * 0.12)],
        fill=(245, 245, 245),
        width=max(1, int(size * 0.13)),
    )


def ball_sprite(size_px: float, spin: float = 0.0) -> Image.Image:
    s = size_px * SS
    img = Image.new("RGBA", (int(s * 3), int(s * 3)), (0, 0, 0, 0))
    _draw_ball(ImageDraw.Draw(img), (s * 1.5, s * 1.5), s)
    img = img.rotate(spin, resample=Image.BICUBIC)
    return img.resize((int(s * 3 / SS), int(s * 3 / SS)), Image.LANCZOS)
