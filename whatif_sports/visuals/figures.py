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
MANNEQUIN = (46, 52, 72)  # neutral tone for arms/legs; not a skin color
SHOE = (18, 20, 28)
MASK = (190, 196, 210)


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


def _capsule(d: ImageDraw.ImageDraw, a, b, width: float, fill, outline=None, ow: float = 0):
    if outline:
        _capsule(d, a, b, width + ow * 2, outline)
    d.line([a, b], fill=fill, width=max(1, int(width)))
    r = width / 2
    for x, y in (a, b):
        d.ellipse((x - r, y - r, x + r, y + r), fill=fill)


@dataclass(frozen=True)
class Figure:
    image: Image.Image  # RGBA
    anchor: tuple[float, float]  # ground point under the pelvis, in image pixels
    hand: tuple[float, float]  # near hand, relative to anchor (pixels)


def draw_figure(
    pose: Pose, height_px: float, kit: Kit, facing: int = 1, ball: bool = False, shadow: bool = True
) -> Figure:
    """Render one player as a supersampled RGBA sprite."""
    h = height_px * SS
    j = _joints(pose)
    # size the canvas to this pose (plus room for helmet, limbs' thickness and shadow)
    xs = [p[0] * facing for p in j.values()] + [-0.4, 0.4]
    ys = [p[1] for p in j.values()] + [0.05]
    pad = 0.16
    left, right = min(xs) - pad, max(xs) + pad
    top, bottom = min(ys) - pad, max(ys) + pad
    w_img, h_img = int((right - left) * h) + 2, int((bottom - top) * h) + 2
    ox, oy = -left * h, -top * h
    img = Image.new("RGBA", (w_img, h_img), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    def P(name: str) -> tuple[float, float]:
        x, y = j[name]
        return ox + x * h * facing, oy + y * h

    outline = (8, 10, 16, 255)
    ow = max(1.0, h * 0.012)
    dark = 0.35
    jersey, pants, helmet = kit.jersey, kit.pants, kit.helmet_color

    if shadow:
        sw = h * (0.32 + 0.25 * min(1.0, pose.lift * 3))
        d.ellipse((ox - sw, oy - h * 0.035, ox + sw, oy + h * 0.035), fill=(0, 0, 0, 90))

    def limb_set(side: str, shade: float) -> None:
        c_pants = mix(pants, (0, 0, 0), shade)
        c_sock = mix(jersey, (0, 0, 0), shade + 0.15)
        _capsule(d, P("pelvis"), P(f"{side}_knee"), h * 0.105, c_pants, outline, ow)
        _capsule(d, P(f"{side}_knee"), P(f"{side}_ankle"), h * 0.078, c_sock, outline, ow)
        _capsule(d, P(f"{side}_ankle"), P(f"{side}_toe"), h * 0.055, SHOE, outline, ow)

    def arm_set(side: str, shade: float) -> None:
        c_sleeve = mix(jersey, (0, 0, 0), shade)
        c_arm = mix(MANNEQUIN, (0, 0, 0), shade)
        _capsule(d, P("shoulder"), P(f"{side}_elbow"), h * 0.08, c_sleeve, outline, ow)
        _capsule(d, P(f"{side}_elbow"), P(f"{side}_hand"), h * 0.064, c_arm, outline, ow)
        hx, hy = P(f"{side}_hand")
        r = h * 0.036
        d.ellipse((hx - r, hy - r, hx + r, hy + r), fill=c_arm, outline=outline, width=int(ow))

    arm_set("far", dark)
    limb_set("far", dark)

    # torso: tapered jersey with shoulder pads
    px, py = P("pelvis")
    sx, sy = P("shoulder")
    ang = math.atan2(sy - py, sx - px) + math.pi / 2
    nx, ny = math.cos(ang), math.sin(ang)
    wb, wt = h * 0.09, h * 0.135
    torso = [
        (px + nx * wb, py + ny * wb),
        (sx + nx * wt, sy + ny * wt),
        (sx - nx * wt, sy - ny * wt),
        (px - nx * wb, py - ny * wb),
    ]
    d.polygon(torso, fill=jersey, outline=outline, width=int(ow * 2))
    pad = h * 0.1
    d.ellipse(
        (sx - pad, sy - pad, sx + pad, sy + pad), fill=jersey, outline=outline, width=int(ow * 2)
    )
    # sleeve stripe on the torso for a bit of uniform detail
    mx, my = (px + sx) / 2, (py + sy) / 2
    d.line(
        [(mx + nx * wb * 1.1, my + ny * wb * 1.1), (mx - nx * wb * 1.1, my - ny * wb * 1.1)],
        fill=kit.trim,
        width=max(1, int(h * 0.018)),
    )
    _capsule(
        d,
        (px - nx * wb * 0.9, py - ny * wb * 0.9),
        (px + nx * wb * 0.9, py + ny * wb * 0.9),
        h * 0.05,
        mix(pants, (0, 0, 0), 0.1),
    )

    limb_set("near", 0.0)

    # helmet: faceless dome, visor, facemask, center stripe
    hx, hy = P("head")
    r = HEAD_R * h * 1.18
    d.ellipse((hx - r, hy - r, hx + r, hy + r), fill=helmet, outline=outline, width=int(ow * 2))
    tilt = math.radians(pose.lean * 0.6 + pose.head)
    fx, fy = math.cos(tilt) * facing, math.sin(tilt)
    vx, vy = hx + fx * r * 0.55, hy + fy * r * 0.55
    d.ellipse((vx - r * 0.42, vy - r * 0.32, vx + r * 0.42, vy + r * 0.32), fill=(14, 16, 24))
    for k in (-0.25, 0.15):
        a0 = (hx + fx * r * 0.7 - fy * r * k * facing, hy + fy * r * 0.7 + fx * r * k * facing)
        a1 = (a0[0] + fx * r * 0.45, a0[1] + fy * r * 0.45)
        d.line([a0, a1], fill=MASK, width=max(1, int(h * 0.014)))
    d.arc(
        (hx - r * 0.98, hy - r * 0.98, hx + r * 0.98, hy + r * 0.98),
        start=200 if facing > 0 else 250,
        end=290 if facing > 0 else 340,
        fill=kit.trim,
        width=max(1, int(h * 0.02)),
    )

    hand = P("near_hand")
    if ball:
        _draw_ball(d, hand, h * 0.075, facing)

    arm_set("near", 0.0)

    out = img.resize((w_img // SS, h_img // SS), Image.LANCZOS)
    return Figure(out, (ox / SS, oy / SS), ((hand[0] - ox) / SS, (hand[1] - oy) / SS))


def _draw_ball(d: ImageDraw.ImageDraw, c, size: float, facing: int = 1) -> None:
    x, y = c
    d.ellipse(
        (x - size * 1.25, y - size * 0.75, x + size * 1.25, y + size * 0.75),
        fill=(122, 66, 34),
        outline=(40, 20, 10),
        width=max(1, int(size * 0.12)),
    )
    d.line(
        [(x - size * 0.5, y), (x + size * 0.5, y)],
        fill=(245, 245, 245),
        width=max(1, int(size * 0.14)),
    )


def ball_sprite(size_px: float, spin: float = 0.0) -> Image.Image:
    s = size_px * SS
    img = Image.new("RGBA", (int(s * 3), int(s * 3)), (0, 0, 0, 0))
    _draw_ball(ImageDraw.Draw(img), (s * 1.5, s * 1.5), s)
    img = img.rotate(spin, resample=Image.BICUBIC)
    return img.resize((int(s * 3 / SS), int(s * 3 / SS)), Image.LANCZOS)
