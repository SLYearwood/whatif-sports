"""Thin wrappers around ffmpeg/ffprobe (argument lists only, never shell strings)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from whatif_sports import config


class MediaError(RuntimeError):
    pass


def run_ffmpeg(args: list[str], cwd: Path | None = None) -> None:
    cmd = [config.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise MediaError(f"ffmpeg failed ({proc.returncode}): {proc.stderr.strip()[-2000:]}")


def duration(path: Path) -> float:
    proc = subprocess.run(
        [
            config.ffprobe(),
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise MediaError(f"ffprobe failed on {path}: {proc.stderr.strip()}")
    return float(json.loads(proc.stdout)["format"]["duration"])
