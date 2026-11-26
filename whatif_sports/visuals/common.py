"""Shared drawing helpers: fonts, easing, background, text layout, motion."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from whatif_sports import config

W, H = config.WIDTH, config.HEIGHT
RGB = tuple[int, int, int]


# --- easing -------------------------------------------------------------------
def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


def progress(t: float, start: float, length: float) -> float:
    """0..1 progress of an animation that starts at `start` and lasts `length` seconds."""
    if length <= 0:
        return 1.0 if t >= start else 0.0
    return clamp((t - start) / length)


def ease_out(x: float) -> float:
    return 1 - (1 - clamp(x)) ** 3


def ease_in_out(x: float) -> float:
    x = clamp(x)
    return 4 * x**3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_out_back(x: float, s: float = 1.6) -> float:
    x = clamp(x) - 1
    return x * x * ((s + 1) * x + s) + 1


def mix(a: RGB, b: RGB, k: float) -> RGB:
    return tuple(int(a[i] + (b[i] - a[i]) * k) for i in range(3))  # type: ignore[return-value]


# --- fonts ----------------------------------------------------------------------
@lru_cache(maxsize=64)
def font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    path = config.font_path()
    if path:
        return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def text_width(text: str, f: ImageFont.ImageFont, stroke: int = 0) -> int:
    left, _, right, _ = f.getbbox(text, stroke_width=stroke)
    return int(right - left)


def wrap(text: str, f: ImageFont.ImageFont, max_width: int, stroke: int = 0) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if cur and text_width(trial, f, stroke) > max_width:
            lines.append(cur)
            cur = w
        else:
            cur = trial
    if cur:
        lines.append(cur)
    return lines


@lru_cache(maxsize=512)
def fit_text(
    text: str, max_width: int, max_lines: int, start: int, minimum: int = 40, stroke: int = 0
) -> tuple[ImageFont.ImageFont, list[str]]:
    """Largest font size (stepping down) at which `text` wraps into <= max_lines lines."""
    size = start
    while True:
        f = font(size)
        lines = wrap(text, f, max_width, stroke)
        too_wide = any(text_width(ln, f, stroke) > max_width for ln in lines)
        if (len(lines) <= max_lines and not too_wide) or size <= minimum:
            return f, lines
        size -= 6


@dataclass(frozen=True)
class TextStyle:
    fill: RGB | tuple[int, int, int, int] = config.BRAND_WHITE
    stroke: int = 0
    stroke_fill: RGB = (0, 0, 0)
    line_gap: float = 0.08  # extra space between lines, as a fraction of font size
    shadow: bool = True
    align: str = "center"  # center | left


def text_layer(
    lines: list[str], f: ImageFont.ImageFont, style: TextStyle | None = None
) -> Image.Image:
    """Render lines onto a tight transparent RGBA layer (cached; treat the result as read-only)."""
    return _text_layer(tuple(lines), f, style or TextStyle())


@lru_cache(maxsize=256)
def _text_layer(lines: tuple[str, ...], f: ImageFont.ImageFont, style: TextStyle) -> Image.Image:
    size = getattr(f, "size", 40)
    ascent, descent = f.getmetrics() if hasattr(f, "getmetrics") else (size, size // 4)
    line_h = ascent + descent + int(size * style.line_gap)
    pad = style.stroke + 24
    widths = [text_width(ln, f, style.stroke) for ln in lines]
    lw = max(widths, default=1) + pad * 2
    lh = line_h * len(lines) + pad * 2
    layer = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
    if style.shadow:
        shadow = Image.new("RGBA", (lw, lh), (0, 0, 0, 0))
        sd = ImageDraw.Draw(shadow)
        for i, ln in enumerate(lines):
            x = pad if style.align == "left" else (lw - widths[i]) // 2
            sd.text(
                (x, pad + i * line_h + 10),
                ln,
                font=f,
                fill=(0, 0, 0, 150),
                stroke_width=style.stroke,
                stroke_fill=(0, 0, 0, 150),
            )
        layer = Image.alpha_composite(layer, shadow.filter(ImageFilter.GaussianBlur(10)))
    d = ImageDraw.Draw(layer)
    for i, ln in enumerate(lines):
        x = pad if style.align == "left" else (lw - widths[i]) // 2
        d.text(
            (x, pad + i * line_h),
            ln,
            font=f,
            fill=style.fill,
            stroke_width=style.stroke,
            stroke_fill=style.stroke_fill,
        )
    return layer


def with_alpha(layer: Image.Image, alpha: float) -> Image.Image:
    if alpha >= 0.999:
        return layer
    a = layer.getchannel("A").point(lambda v: int(v * clamp(alpha)))
    out = layer.copy()
    out.putalpha(a)
    return out


def paste(
    base: Image.Image,
    layer: Image.Image,
    cx: float,
    cy: float,
    scale: float = 1.0,
    alpha: float = 1.0,
    anchor: str = "center",
) -> None:
    """Alpha-composite `layer` onto `base`.

    anchor: "center" puts the layer's center at (cx, cy); "left" puts its left edge at cx,
    vertically centered on cy; "topleft" puts its top-left corner at (cx, cy).
    """
    if alpha <= 0.001 or scale <= 0.01:
        return
    if abs(scale - 1.0) > 0.002:
        w = max(1, int(layer.width * scale))
        h = max(1, int(layer.height * scale))
        layer = layer.resize((w, h), Image.BILINEAR)
    layer = with_alpha(layer, alpha)
    x = int(cx - layer.width / 2) if anchor == "center" else int(cx)
    y = int(cy) if anchor == "topleft" else int(cy - layer.height / 2)
    # clip to the canvas (alpha_composite needs a non-negative, in-bounds destination)
    x0, y0 = max(0, -x), max(0, -y)
    x1, y1 = min(layer.width, base.width - x), min(layer.height, base.height - y)
    if x1 <= x0 or y1 <= y0:
        return
    if (x0, y0, x1, y1) != (0, 0, layer.width, layer.height):
        layer = layer.crop((x0, y0, x1, y1))
    base.alpha_composite(layer, (x + x0, y + y0))


# --- background -------------------------------------------------------------------
STRIPE_PERIOD = 220


@lru_cache(maxsize=8)
def _gradient(accent: RGB) -> Image.Image:
    top = Image.new("RGB", (1, H))
    for y in range(H):
        top.putpixel((0, y), mix(config.BG_TOP, config.BG_BOTTOM, y / H))
    img = top.resize((W, H)).convert("RGBA")
    # soft accent glow, upper area
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((-200, -300, W + 200, 900), fill=(*accent, 60))
    img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(180)))
    return img


@lru_cache(maxsize=8)
def _stripes(accent: RGB) -> Image.Image:
    h = H + STRIPE_PERIOD
    layer = Image.new("RGBA", (W, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    for c in range(-W, h + W, STRIPE_PERIOD):
        d.line([(0, c), (W, c - W)], fill=(*accent, 16), width=34)
    return layer


def background(t: float, accent: RGB) -> Image.Image:
    """Dark gradient with slowly drifting diagonal accent stripes."""
    img = _gradient(accent).copy()
    off = int((t * 40) % STRIPE_PERIOD)
    img.alpha_composite(_stripes(accent).crop((0, off, W, off + H)))
    return img


def slow_zoom(img: Image.Image, t: float, dur: float, amount: float = 0.04) -> Image.Image:
    """Ken Burns push-in over the segment so no frame is static."""
    s = 1 + amount * ease_in_out(t / max(dur, 0.01))
    if s <= 1.001:
        return img
    w, h = int(W * s), int(H * s)
    big = img.resize((w, h), Image.BILINEAR)
    x, y = (w - W) // 2, int((h - H) * 0.45)
    return big.crop((x, y, x + W, y + H))


# --- small shapes -------------------------------------------------------------------
@lru_cache(maxsize=128)
def pill(text: str, size: int, fg: RGB, bg: RGB, pad_x: int = 34, pad_y: int = 16) -> Image.Image:
    f = font(size)
    left, top, right, bottom = f.getbbox(text)
    w, h = right - left + pad_x * 2, bottom - top + pad_y * 2
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((0, 0, w - 1, h - 1), radius=h // 2 if h < 120 else 24, fill=bg)
    d.text((pad_x - left, pad_y - top), text, font=f, fill=fg)
    return layer


def arrow_head(d: ImageDraw.ImageDraw, p0: tuple, p1: tuple, color: RGB, size: int = 34) -> None:
    ang = math.atan2(p1[1] - p0[1], p1[0] - p0[0])
    a1, a2 = ang + math.radians(150), ang - math.radians(150)
    pts = [
        p1,
        (p1[0] + size * math.cos(a1), p1[1] + size * math.sin(a1)),
        (p1[0] + size * math.cos(a2), p1[1] + size * math.sin(a2)),
    ]
    d.polygon(pts, fill=color)


# --- number counters ------------------------------------------------------------------
_NUM = re.compile(r"^(\D*?)(\d[\d,]*(?:\.\d+)?)(.*)$")


def count_up(big: str, k: float) -> str:
    """Render `big` with its leading number at fraction k (0..1) of its final value."""
    m = _NUM.match(big)
    if not m:
        return big
    prefix, num, suffix = m.groups()
    decimals = len(num.split(".")[1]) if "." in num else 0
    value = float(num.replace(",", "")) * clamp(k)
    text = f"{value:,.{decimals}f}" if "," in num else f"{value:.{decimals}f}"
    return f"{prefix}{text}{suffix}"
