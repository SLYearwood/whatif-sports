"""Stream frames of a video clip as 1080x1920 RGB images (cover-scaled, 30 fps)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from whatif_sports import config, media

MAX_SPEEDUP = 1.6  # beyond this, motion looks rushed; trim the rest instead


def speed_factor(clip_seconds: float, segment_seconds: float | None) -> float:
    """How much to speed the clip up so its ending (usually the payoff) lands in the segment."""
    if not segment_seconds or clip_seconds <= segment_seconds:
        return 1.0
    return min(MAX_SPEEDUP, clip_seconds / segment_seconds)


class ClipReader:
    """Sequential frame source. Past the clip's end it holds the last frame.

    With fit_seconds, a longer clip is sped up (up to MAX_SPEEDUP) to fit the segment.
    """

    def __init__(self, path: Path, fit_seconds: float | None = None):
        w, h = config.WIDTH, config.HEIGHT
        self.size = (w, h)
        self.frame_bytes = w * h * 3
        self.speed = speed_factor(media.duration(path), fit_seconds) if fit_seconds else 1.0
        vf = (
            f"setpts=PTS/{self.speed:.4f},"
            f"scale={w}:{h}:force_original_aspect_ratio=increase,crop={w}:{h},"
            f"fps={config.FPS},format=rgb24"
        )
        self.proc = subprocess.Popen(
            [
                config.ffmpeg(),
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                str(path),
                "-an",
                "-vf",
                vf,
                "-f",
                "rawvideo",
                "-",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self.last: Image.Image | None = None
        self.ended = False

    def next(self) -> Image.Image:
        if not self.ended and self.proc.stdout is not None:
            data = self.proc.stdout.read(self.frame_bytes)
            if len(data) == self.frame_bytes:
                self.last = Image.frombytes("RGB", self.size, data)
            else:
                self.ended = True
        if self.last is None:
            raise RuntimeError("clip produced no frames")
        return self.last

    def close(self) -> None:
        if self.proc.stdout:
            self.proc.stdout.close()
        self.proc.wait()
