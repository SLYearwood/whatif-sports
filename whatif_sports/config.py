"""Project-wide settings: paths, video format, brand style, tool lookup."""

from __future__ import annotations

import glob
import os
import shutil
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT / "data"
EXAMPLES_DIR = ROOT / "examples"
FONTS_DIR = ROOT / "assets" / "fonts"

# --- video format -----------------------------------------------------------
WIDTH = 1080
HEIGHT = 1920
FPS = 30
MAX_SECONDS = 59.0
SEGMENT_PAD = 0.35  # seconds of silence after each segment's narration

# Platform UI covers the bottom ~20%; nothing important goes below this line.
SAFE_BOTTOM = int(HEIGHT * 0.80)
# Captions sit just above the unsafe zone; templates keep content above CONTENT_BOTTOM.
CAPTION_CENTER_Y = 1390
CONTENT_TOP = 170
CONTENT_BOTTOM = 1200

# --- brand ------------------------------------------------------------------
BG_TOP = (10, 14, 26)
BG_BOTTOM = (22, 30, 52)
BRAND_YELLOW = (255, 210, 63)
BRAND_WHITE = (245, 247, 250)
BRAND_RED = (255, 77, 77)
MUTED = (140, 152, 178)

# Bold display fonts, best first. Drop Inter-Black.ttf into assets/fonts/ to use it.
_FONT_CANDIDATES = [
    FONTS_DIR / "Inter-Black.ttf",
    FONTS_DIR / "Inter-ExtraBold.ttf",
    Path("C:/Windows/Fonts/ariblk.ttf"),
    Path("/Library/Fonts/Arial Black.ttf"),
    Path("/usr/share/fonts/truetype/msttcorefonts/Arial_Black.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
]


def load_dotenv(path: Path = ROOT / ".env") -> None:
    """Minimal .env reader (KEY=VALUE lines). Never prints values."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


@lru_cache(maxsize=1)
def font_path() -> str | None:
    for candidate in _FONT_CANDIDATES:
        if candidate.exists():
            return str(candidate)
    return None


def _find_tool(name: str, env_var: str | None = None) -> str:
    if env_var and (p := os.environ.get(env_var)):
        tool = Path(p)
        if tool.name.lower().startswith("ffmpeg") and name != "ffmpeg":
            tool = tool.with_name(tool.name.replace("ffmpeg", name))
        if tool.exists():
            return str(tool)
    if found := shutil.which(name):
        return found
    # winget installs (Gyan.FFmpeg) only reach PATH in new shells; look there directly.
    local = os.environ.get("LOCALAPPDATA")
    if local:
        pattern = os.path.join(local, "Microsoft", "WinGet", "Packages", "*FFmpeg*", "*", "bin")
        for bin_dir in sorted(glob.glob(pattern), reverse=True):
            exe = Path(bin_dir) / f"{name}.exe"
            if exe.exists():
                return str(exe)
    raise FileNotFoundError(
        f"{name} not found. Install ffmpeg (e.g. `winget install Gyan.FFmpeg`) "
        f"or set FFMPEG_PATH in .env."
    )


@lru_cache(maxsize=1)
def ffmpeg() -> str:
    return _find_tool("ffmpeg", "FFMPEG_PATH")


@lru_cache(maxsize=1)
def ffprobe() -> str:
    return _find_tool("ffprobe", "FFMPEG_PATH")


def item_dir(item_id: str) -> Path:
    d = DATA_DIR / item_id
    d.mkdir(parents=True, exist_ok=True)
    return d
