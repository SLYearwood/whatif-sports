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


def timed(narration: str, audio_seconds: float, alignment: dict | None = None) -> list[Caption]:
    """Caption chunks with start/end times. Uses TTS character timings when available."""
    if alignment:
        aligned = _from_alignment(narration, audio_seconds, alignment)
        if aligned:
            return aligned
    parts = chunk(narration)
    total = sum(_weight(p) for p in parts) or 1.0
    out, t = [], 0.0
    for p in parts:
        d = audio_seconds * _weight(p) / total
        out.append(Caption(display_text(p), t, t + d))
        t += d
    return out


def _from_alignment(narration: str, audio_seconds: float, alignment: dict) -> list[Caption] | None:
    """Time chunks from per-character timings (ElevenLabs `alignment`).

    Each chunk appears when its first character is spoken and stays up until the next
    chunk starts, so there is never a blank gap mid-sentence. Returns None if the
    alignment doesn't match the narration text, so the caller can fall back.
    """
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    if "".join(chars) != narration or not (len(chars) == len(starts) == len(ends)):
        return None
    parts = chunk(narration)
    begin, cursor = [], 0
    for p in parts:
        idx = narration.find(p.split()[0], cursor)
        if idx < 0:
            return None
        begin.append(starts[idx])
        cursor = idx + len(p.split()[0])
    begin[0] = 0.0
    out = []
    for i, p in enumerate(parts):
        end = begin[i + 1] if i + 1 < len(parts) else max(ends[-1], audio_seconds)
        if end <= begin[i]:
            return None
        out.append(Caption(display_text(p), begin[i], end))
    return out


def at(captions: list[Caption], t: float) -> Caption | None:
    for c in captions:
        if c.start <= t < c.end:
            return c
    return None
