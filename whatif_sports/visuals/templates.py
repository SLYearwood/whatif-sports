"""Segment templates. Each one draws a full 1080x1920 frame for time t within the segment."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass

from PIL import Image, ImageDraw

from whatif_sports import config
from whatif_sports.script.schema import (
    MomentSegment,
    OutroSegment,
    PlayDiagramSegment,
    PlaySceneSegment,
    ScoreboardSegment,
    StatSegment,
    TeamKit,
    TimelineSegment,
    TitleSegment,
    hex_to_rgb,
)
from whatif_sports.visuals import figures as fg
from whatif_sports.visuals import plays, scene
from whatif_sports.visuals.common import (
    RGB,
    TextStyle,
    W,
    background,
    count_up,
    ease_in_out,
    ease_out,
    ease_out_back,
    fit_text,
    font,
    paste,
    pill,
    progress,
    slow_zoom,
    text_layer,
)

CONTENT_W = W - 140


@dataclass(frozen=True)
class Ctx:
    accent: RGB = config.BRAND_YELLOW


Template = Callable[..., Image.Image]


def _accent_bar(img: Image.Image, cy: float, k: float, color: RGB, width: int = 360) -> None:
    w = int(width * ease_out(k))
    if w <= 2:
        return
    ImageDraw.Draw(img).rounded_rectangle(
        (W // 2 - w // 2, cy - 8, W // 2 + w // 2, cy + 8), radius=8, fill=color
    )


# --- title ------------------------------------------------------------------------
_WHAT_IF = re.compile(r"^\s*what\s+if\s+", re.IGNORECASE)


def render_title(seg: TitleSegment, ctx: Ctx, t: float, dur: float) -> Image.Image:
    img = background(t, ctx.accent)
    k_badge = progress(t, 0.0, 0.35)
    paste(
        img,
        pill("WHAT IF?", 84, (12, 14, 22), config.BRAND_YELLOW, 44, 22),
        W / 2,
        360 - 60 * (1 - ease_out(k_badge)),
        alpha=k_badge,
    )

    body = _WHAT_IF.sub("", seg.text).upper() or seg.text.upper()
    f, lines = fit_text(body, CONTENT_W, 3, 140, 80)
    layer = text_layer(lines, f, TextStyle(line_gap=0.02))
    k = progress(t, 0.1, 0.45)
    cy = 470 + layer.height / 2
    paste(img, layer, W / 2, cy, scale=0.8 + 0.2 * ease_out_back(k), alpha=k)
    _accent_bar(img, cy + layer.height / 2 + 20, progress(t, 0.45, 0.5), ctx.accent)
    return img


# --- stat -----------------------------------------------------------------------
def render_stat(seg: StatSegment, ctx: Ctx, t: float, dur: float) -> Image.Image:
    img = background(t, ctx.accent)
    final = seg.big.upper()
    f, _ = fit_text(final, CONTENT_W, 1, 300, 120)
    shown = count_up(final, ease_out(progress(t, 0.15, 0.9)))
    layer = text_layer([shown], f, TextStyle(fill=config.BRAND_YELLOW))
    k = progress(t, 0.0, 0.3)
    paste(img, layer, W / 2, 640, scale=0.9 + 0.1 * ease_out(k), alpha=k)
    _accent_bar(img, 820, progress(t, 0.5, 0.5), ctx.accent, 480)

    lf, lines = fit_text(seg.label, CONTENT_W - 40, 3, 64, 40)
    lk = progress(t, 0.55, 0.45)
    paste(
        img,
        text_layer(lines, lf, TextStyle(fill=config.BRAND_WHITE)),
        W / 2,
        960 + 30 * (1 - ease_out(lk)),
        alpha=lk,
    )
    return img


# --- scoreboard -------------------------------------------------------------------
def render_scoreboard(seg: ScoreboardSegment, ctx: Ctx, t: float, dur: float) -> Image.Image:
    img = background(t, ctx.accent)
    x0, x1 = 80, W - 80

    # header: period + clock
    k0 = progress(t, 0.0, 0.3)
    if seg.period or seg.clock:
        head = "   ".join(p for p in (seg.period, seg.clock) if p)
        paste(
            img,
            pill(head, 72, config.BRAND_WHITE, (34, 44, 72), 40, 20),
            W / 2,
            400 - 40 * (1 - ease_out(k0)),
            alpha=k0,
        )

    row_h, top = 190, 500
    for i, team in enumerate(seg.teams):
        k = ease_out(progress(t, 0.15 + 0.15 * i, 0.4))
        if k <= 0:
            continue
        off = (1 - k) * (W if i == 0 else -W) * 0.6
        y = top + i * (row_h + 24)
        row = Image.new("RGBA", (x1 - x0, row_h), (0, 0, 0, 0))
        rd = ImageDraw.Draw(row)
        rd.rounded_rectangle((0, 0, row.width - 1, row_h - 1), radius=26, fill=(20, 27, 46, 240))
        rd.rounded_rectangle((0, 0, 30, row_h - 1), radius=14, fill=hex_to_rgb(team.color))
        nf, nl = fit_text(team.name.upper(), 560, 1, 84, 44)
        rd.text((70, row_h / 2), nl[0], font=nf, fill=config.BRAND_WHITE, anchor="lm")
        sf = font(130)
        rd.text(
            (row.width - 50, row_h / 2),
            str(team.score),
            font=sf,
            fill=config.BRAND_YELLOW,
            anchor="rm",
        )
        paste(img, row, W / 2 + off, y + row_h / 2, alpha=k)

    if seg.situation:
        ks = progress(t, 0.7, 0.35)
        pulse = 1 + 0.035 * math.sin(max(0.0, t - 1.05) * 5.0)
        paste(
            img,
            pill(seg.situation.upper(), 64, (12, 14, 22), config.BRAND_YELLOW, 40, 22),
            W / 2,
            top + 2 * (row_h + 24) + 90,
            scale=ease_out_back(ks) * pulse,
            alpha=ks,
        )
    return img


# --- play diagram -----------------------------------------------------------------
def render_play(seg: PlayDiagramSegment, ctx: Ctx, t: float, dur: float) -> Image.Image:
    img = background(t, ctx.accent)
    play = plays.PLAYS[seg.play]
    if seg.label:
        lab = seg.label.upper()
        col = config.BRAND_RED if "HAPPEN" in lab else ctx.accent
        k = progress(t, 0.0, 0.3)
        paste(
            img,
            pill(lab, 60, config.BRAND_WHITE, col, 36, 18),
            W / 2,
            220,
            alpha=k,
            scale=0.85 + 0.15 * ease_out_back(k),
        )
    plays.draw_play(img, seg.play, t, dur, ctx.accent)
    tf, tl = fit_text(play.title, CONTENT_W, 2, 42, 30)
    tlayer = text_layer(tl, tf, TextStyle(fill=config.MUTED, shadow=False, line_gap=0.0))
    paste(
        img,
        tlayer,
        W / 2 - tlayer.width / 2,
        plays.BOX_BOTTOM + 6,
        alpha=progress(t, 0.3, 0.4),
        anchor="topleft",
    )
    return img


# --- play scene (stylized players) ---------------------------------------------------
def to_kit(k: TeamKit) -> fg.Kit:
    return fg.Kit(
        jersey=hex_to_rgb(k.jersey),
        pants=hex_to_rgb(k.pants),
        helmet=hex_to_rgb(k.helmet) if k.helmet else None,
        trim=hex_to_rgb(k.trim),
    )


def render_play_scene(seg: PlaySceneSegment, ctx: Ctx, t: float, dur: float) -> Image.Image:
    img = Image.new("RGBA", (W, config.HEIGHT), (*config.BG_TOP, 255))
    kits = scene.Kits(to_kit(seg.offense), to_kit(seg.defense))
    scene.draw_scene(img, seg.play, t, dur, kits, ctx.accent)
    if seg.label:
        lab = seg.label.upper()
        col = config.BRAND_RED if "HAPPEN" in lab else ctx.accent
        k = progress(t, 0.0, 0.3)
        paste(
            img,
            pill(lab, 60, config.BRAND_WHITE, col, 36, 18),
            W / 2,
            230,
            alpha=k,
            scale=0.85 + 0.15 * ease_out_back(k),
        )
    return img


# --- moment (one big player) -----------------------------------------------------------
def _confetti(img: Image.Image, t: float, colors: list[RGB]) -> None:
    d = ImageDraw.Draw(img)
    for i in range(90):
        seed = i * 9301 + 49297
        x0 = seed % 1080
        speed = 260 + (seed % 7) * 60
        y = (-100 + (seed % 1900) * 0.6 + t * speed) % 1500 - 100
        x = x0 + 40 * math.sin(t * 2 + i)
        c = colors[i % len(colors)]
        a = t * 4 + i
        w, h = 18, 9
        pts = [
            (x + math.cos(a) * w - math.sin(a) * h, y + math.sin(a) * w + math.cos(a) * h),
            (x - math.cos(a) * w - math.sin(a) * h, y - math.sin(a) * w + math.cos(a) * h),
            (x - math.cos(a) * w + math.sin(a) * h, y - math.sin(a) * w - math.cos(a) * h),
            (x + math.cos(a) * w + math.sin(a) * h, y + math.sin(a) * w - math.cos(a) * h),
        ]
        d.polygon(pts, fill=c)


def render_moment(seg: MomentSegment, ctx: Ctx, t: float, dur: float) -> Image.Image:
    kit = to_kit(seg.kit)
    img = background(t, kit.jersey if seg.pose != "dejected" else (70, 76, 96))
    d = ImageDraw.Draw(img)
    # spotlight cone + floor glow
    cone = Image.new("RGBA", img.size, (0, 0, 0, 0))
    cd = ImageDraw.Draw(cone)
    cd.polygon(
        [(W / 2 - 90, 0), (W / 2 + 90, 0), (W / 2 + 420, 1180), (W / 2 - 420, 1180)],
        fill=(255, 255, 240, 26),
    )
    cd.ellipse((W / 2 - 400, 1120, W / 2 + 400, 1230), fill=(255, 255, 240, 40))
    img.alpha_composite(cone)

    if seg.pose == "celebrate":
        _confetti(img, t, [kit.jersey, kit.trim, config.BRAND_YELLOW, config.BRAND_WHITE])
        pose, facing, dx = fg.celebrate_pose(t), 1, 0.0
    elif seg.pose == "dejected":
        breathe = 0.5 + 0.5 * math.sin(t * 1.6)
        pose = fg.DEJECTED.blend(fg.Pose(**{**fg.DEJECTED.__dict__, "head": -45}), breathe)
        facing, dx = -1, 0.0
        for i in range(40):  # cold rain streaks
            x = (i * 137 + t * 90) % W
            y = (i * 251 + t * 1400) % 1300 - 100
            d.line((x, y, x - 14, y + 60), fill=(150, 165, 200), width=3)
    elif seg.pose == "dive":
        k = ease_in_out(progress(t, 0.2, max(0.8, dur * 0.5)))
        pose, facing, dx = fg.run_pose(t * 12).blend(fg.DIVE, k), 1, -380 + 520 * k
    else:  # run: in place, with speed lines
        pose, facing, dx = fg.run_pose(t * 13), 1, 0.0
        for i in range(14):
            y = 300 + i * 60
            x = W - ((t * 2200 + i * 330) % (W + 400))
            d.line((x, y, x + 240, y), fill=(255, 255, 255, 60), width=6)

    fig = fg.draw_figure(pose, 600, kit, facing, ball=seg.pose in ("dive", "run"))
    k = progress(t, 0.0, 0.35)
    paste(
        img, fig.image, W / 2 + dx - fig.anchor[0], 1215 - fig.anchor[1], alpha=k, anchor="topleft"
    )

    top = 220
    if seg.year is not None:
        kp = progress(t, 0.1, 0.3)
        paste(
            img,
            pill(str(seg.year), 64, (12, 14, 22), config.BRAND_YELLOW, 36, 16),
            W / 2,
            top,
            alpha=kp,
            scale=0.85 + 0.15 * ease_out_back(kp),
        )
        top += 110
    if seg.text:
        f, lines = fit_text(seg.text.upper(), CONTENT_W, 2, 92, 56)
        tl = text_layer(lines, f)
        kt = progress(t, 0.2, 0.4)
        paste(
            img, tl, W / 2, top + tl.height / 2 - 20, alpha=kt, scale=0.9 + 0.1 * ease_out_back(kt)
        )
    return img


# --- AI clip ----------------------------------------------------------------------------
def render_ai_clip(seg, ctx: Ctx, t: float, dur: float, source: Image.Image | None) -> Image.Image:
    """The generated clip full-bleed, or a clearly marked placeholder until it exists."""
    if source is not None:
        img = source.convert("RGBA")
        # darken the top a touch so an overlay headline stays readable
        shade = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(shade).rectangle((0, 0, W, 520), fill=(0, 0, 0, 70))
        img.alpha_composite(shade)
    else:
        img = background(t, ctx.accent)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((90, 330, W - 90, 1150), radius=36, outline=config.MUTED, width=6)
        paste(
            img, pill("AI CLIP PENDING", 56, (12, 14, 22), config.BRAND_YELLOW, 36, 18), W / 2, 480
        )
        f, lines = fit_text(seg.prompt, W - 260, 7, 40, 30)
        paste(img, text_layer(lines, f, TextStyle(fill=config.MUTED, shadow=False)), W / 2, 780)
        paste(
            img,
            text_layer(
                ["run: whatif clips <id> --yes"],
                font(34),
                TextStyle(fill=config.MUTED, shadow=False),
            ),
            W / 2,
            1080,
        )
    if seg.text:
        f, lines = fit_text(seg.text.upper(), CONTENT_W, 2, 92, 56)
        k = progress(t, 0.15, 0.4)
        paste(img, text_layer(lines, f), W / 2, 300, alpha=k, scale=0.9 + 0.1 * ease_out_back(k))
    return img


# --- timeline ------------------------------------------------------------------------
def render_timeline(seg: TimelineSegment, ctx: Ctx, t: float, dur: float) -> Image.Image:
    img = background(t, ctx.accent)
    if seg.title:
        k = progress(t, 0.0, 0.35)
        paste(
            img,
            pill(seg.title.upper(), 56, (12, 14, 22), config.BRAND_YELLOW, 36, 18),
            W / 2,
            250,
            alpha=k,
        )
    n = len(seg.events)
    y_top, y_bot = 370, config.CONTENT_BOTTOM - 50
    line_x = 130
    d = ImageDraw.Draw(img)
    kl = ease_out(progress(t, 0.1, 0.6))
    d.line((line_x, y_top, line_x, y_top + (y_bot - y_top) * kl), fill=(*ctx.accent, 255), width=8)

    step = (y_bot - y_top) / n
    span = max(0.8, dur * 0.65)
    text_x = line_x + 26  # layers carry ~24px of padding on the left
    year_style = TextStyle(fill=ctx.accent, align="left")
    body_style = TextStyle(fill=config.BRAND_WHITE, align="left", line_gap=0.0)
    for i, ev in enumerate(seg.events):
        k = progress(t, 0.35 + i * span / n, 0.45)
        if k <= 0:
            continue
        cy = y_top + step * (i + 0.5)
        r = 22 * ease_out_back(k)
        d.ellipse((line_x - r, cy - r, line_x + r, cy + r), fill=config.BRAND_YELLOW)
        slide = (1 - ease_out(k)) * 260
        yl = text_layer([str(ev.year)], font(76), year_style)
        tf, tl = fit_text(ev.text, W - text_x - 110, 2, 56, 40)
        tlayer = text_layer(tl, tf, body_style)
        gap = -38  # tighten padding between the year and its text
        top = cy - (yl.height + gap + tlayer.height) / 2
        paste(img, yl, text_x + slide, top, alpha=k, anchor="topleft")
        paste(img, tlayer, text_x + slide, top + yl.height + gap, alpha=k, anchor="topleft")
    return img


# --- outro ----------------------------------------------------------------------------
def render_outro(seg: OutroSegment, ctx: Ctx, t: float, dur: float) -> Image.Image:
    img = background(t, ctx.accent)
    f, lines = fit_text(seg.text.upper(), CONTENT_W, 3, 120, 70)
    layer = text_layer(lines, f)
    k = progress(t, 0.0, 0.4)
    cy = 400 + layer.height / 2
    paste(img, layer, W / 2, cy, scale=0.85 + 0.15 * ease_out_back(k), alpha=k)
    kf = progress(t, 0.6, 0.4)
    pulse = 1 + 0.04 * math.sin(max(0.0, t - 1.0) * 4.0)
    paste(
        img,
        pill("FOLLOW FOR MORE WHAT IFS", 52, (12, 14, 22), config.BRAND_YELLOW, 40, 22),
        W / 2,
        max(cy + layer.height / 2 + 90, 1000),
        scale=ease_out_back(kf) * pulse,
        alpha=kf,
    )
    return img


TEMPLATES: dict[str, Template] = {
    "title": render_title,
    "stat": render_stat,
    "scoreboard": render_scoreboard,
    "play_diagram": render_play,
    "play_scene": render_play_scene,
    "moment": render_moment,
    "timeline": render_timeline,
    "outro": render_outro,
}


# --- captions + final frame -----------------------------------------------------------
def draw_caption(img: Image.Image, text: str, k: float) -> None:
    """Big centered caption above the platform-UI zone, with a quick pop-in (k: 0..1)."""
    if not text:
        return
    f, lines = fit_text(text.upper(), W - 120, 2, 96, 60, stroke=10)
    layer = text_layer(lines, f, TextStyle(stroke=10, stroke_fill=(0, 0, 0), line_gap=0.0))
    cy = config.CAPTION_CENTER_Y
    # never let captions reach the bottom 20%
    max_cy = config.SAFE_BOTTOM - layer.height / 2 - 10
    paste(img, layer, W / 2, min(cy, max_cy), scale=0.88 + 0.12 * ease_out_back(k))


def render_frame(
    seg,
    ctx: Ctx,
    t: float,
    dur: float,
    caption: str = "",
    caption_k: float = 1.0,
    source: Image.Image | None = None,
) -> Image.Image:
    """source: the current frame of an AI clip (ai_clip segments only)."""
    if seg.type == "ai_clip":
        img = render_ai_clip(seg, ctx, t, dur, source)
    else:
        img = TEMPLATES[seg.type](seg, ctx, t, dur)
    img = slow_zoom(img, t, dur)
    draw_caption(img, caption, caption_k)
    return img.convert("RGB")
