"""Split narration into short caption chunks and time them across the audio.

Timing is proportional to characters, with extra weight for punctuation pauses.
Swap in Whisper word timestamps later if sync needs to be tighter.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

MAX_WORDS = 4
_BREAK = re.compile(r"[.,!?;:—]+[\"')\]]*$|\.\.\.$")
_PAUSE = re.compile(r"[.!?;:—]|\.\.\.")


@dataclass(frozen=True)
class Caption:
    text: str
    start: float
    end: float


def chunk(narration: str, max_words: int = MAX_WORDS) -> list[str]:
    chunks: list[str] = []
    cur: list[str] = []
    for word in narration.split():
        cur.append(word)
        if len(cur) >= max_words or _BREAK.search(word):
            chunks.append(" ".join(cur))
            cur = []
    if cur:
        chunks.append(" ".join(cur))
    # A lone word on screen reads badly. If the chunk before it was cut only by the word
    # limit (not a pause), move that chunk's last word forward: "tell me in the / comments."
    # becomes "tell me in / the comments."
    for i in range(1, len(chunks)):
        words, prev = chunks[i].split(), chunks[i - 1].split()
        if len(words) == 1 and len(prev) >= 3 and not _PAUSE.search(prev[-1][-1]):
            chunks[i - 1] = " ".join(prev[:-1])
            chunks[i] = f"{prev[-1]} {words[0]}"
    return chunks


def _weight(text: str) -> float:
    return len(text.replace(" ", "")) + 3.0 * len(_PAUSE.findall(text)) + 2.0


def display_text(text: str) -> str:
    """What goes on screen: drop trailing commas/ellipses, keep ? and !."""
    return re.sub(r"(\.\.\.|[,;:.—])+$", "", text.strip())


def timed(narration: str, audio_seconds: float) -> list[Caption]:
    parts = chunk(narration)
    total = sum(_weight(p) for p in parts) or 1.0
    out, t = [], 0.0
    for p in parts:
        d = audio_seconds * _weight(p) / total
        out.append(Caption(display_text(p), t, t + d))
        t += d
    return out


def at(captions: list[Caption], t: float) -> Caption | None:
    for c in captions:
        if c.start <= t < c.end:
            return c
    return None
