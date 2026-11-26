"""Stream frames of a video clip as 1080x1920 RGB images (cover-scaled, 30 fps)."""

from __future__ import annotations

import subprocess
from pathlib import Path

from PIL import Image

from whatif_sports import config


class ClipReader:
    """Sequential frame source. Past the clip's end it holds the last frame."""

    def __init__(self, path: Path):
        w, h = config.WIDTH, config.HEIGHT
        self.size = (w, h)
        self.frame_bytes = w * h * 3
        vf = (
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
