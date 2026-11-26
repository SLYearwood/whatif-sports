"""Render a full Short: per-segment TTS -> timed frames + captions -> one H.264/AAC MP4."""

from __future__ import annotations

import json
import math
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path

from whatif_sports import config, media
from whatif_sports.assemble import captions as cap
from whatif_sports.script.schema import Script, hex_to_rgb
from whatif_sports.visuals import Ctx, render_frame
from whatif_sports.visuals.common import progress
from whatif_sports.voice import Voice, cache_path, is_cached, load_alignment, synthesize


class RenderError(RuntimeError):
    pass


@dataclass
class SegmentPlan:
    index: int
    type: str
    audio: str
    audio_seconds: float
    seconds: float  # audio + pad, snapped to whole frames
    frames: int


def _context(script: Script, i: int) -> tuple[str, str]:
    """Neighbouring narration, so ElevenLabs keeps intonation flowing across cuts."""
    segs = script.segments
    prev = segs[i - 1].narration if i > 0 else ""
    nxt = segs[i + 1].narration if i + 1 < len(segs) else ""
    return prev, nxt


def billable_characters(script: Script, voice: Voice, audio_dir: Path) -> int:
    """Characters that would be sent to a paid TTS API (0 when everything is cached)."""
    if voice.backend != "elevenlabs":
        return 0
    return sum(
        len(seg.narration)
        for i, seg in enumerate(script.segments)
        if not is_cached(cache_path(seg.narration, voice, audio_dir, *_context(script, i)))
    )


def plan_segments(script: Script, voice: Voice, audio_dir: Path) -> list[SegmentPlan]:
    plans = []
    for i, seg in enumerate(script.segments):
        wav = synthesize(seg.narration, voice, audio_dir, *_context(script, i))
        a = media.duration(wav)
        frames = math.ceil((a + config.SEGMENT_PAD) * config.FPS)
        plans.append(SegmentPlan(i, seg.type, str(wav), a, frames / config.FPS, frames))
    return plans


def build_narration(plans: list[SegmentPlan], out: Path) -> None:
    """Pad each clip to its segment length, concatenate, and loudness-normalize."""
    args: list[str] = []
    for p in plans:
        args += ["-i", p.audio]
    chains = [
        f"[{i}:a]apad=whole_dur={p.seconds:.4f},atrim=0:{p.seconds:.4f}[a{i}]"
        for i, p in enumerate(plans)
    ]
    joined = "".join(f"[a{i}]" for i in range(len(plans)))
    chains.append(
        f"{joined}concat=n={len(plans)}:v=0:a=1,loudnorm=I=-14:TP=-1.5:LRA=11,aresample=44100[out]"
    )
    media.run_ffmpeg(
        [
            *args,
            "-filter_complex",
            ";".join(chains),
            "-map",
            "[out]",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(out),
        ]
    )


def render(script: Script, voice: Voice | None = None, log=print) -> Path:
    voice = voice or Voice.from_env()
    root = config.item_dir(script.id)
    audio_dir, render_dir = root / "audio", root / "render"
    render_dir.mkdir(parents=True, exist_ok=True)

    billable = billable_characters(script, voice, audio_dir)
    log(
        f"[voice] {voice.label} for {len(script.segments)} segments"
        + (f" ({billable} characters to synthesize, rest cached)" if billable else "")
    )
    limit = int(os.environ.get("WHATIF_MAX_TTS_CHARS", "3000"))
    if billable > limit:
        raise RenderError(
            f"{billable} characters would be sent to ElevenLabs (limit {limit}). "
            "Shorten the script or raise WHATIF_MAX_TTS_CHARS."
        )
    plans = plan_segments(script, voice, audio_dir)
    total = sum(p.seconds for p in plans)
    log(f"[plan]  {total:.1f}s total: " + ", ".join(f"{p.type} {p.seconds:.1f}s" for p in plans))
    if total > config.MAX_SECONDS:
        raise RenderError(
            f"Video would be {total:.1f}s; Shorts must stay under 60s. Trim the narration."
        )

    narration = render_dir / "narration.wav"
    build_narration(plans, narration)

    out = render_dir / f"{script.id}.mp4"
    tmp = render_dir / f"{script.id}.partial.mp4"
    ctx = Ctx(accent=hex_to_rgb(script.accent) if script.accent else config.BRAND_YELLOW)
    cmd = [
        config.ffmpeg(),
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "-s",
        f"{config.WIDTH}x{config.HEIGHT}",
        "-r",
        str(config.FPS),
        "-i",
        "-",
        "-i",
        str(narration),
        "-map",
        "0:v",
        "-map",
        "1:a",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-profile:v",
        "high",
        "-r",
        str(config.FPS),
        "-c:a",
        "aac",
        "-b:a",
        "192k",
        "-ar",
        "44100",
        "-shortest",
        "-movflags",
        "+faststart",
        str(tmp),
    ]
    started = time.time()
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdin is not None
    try:
        for p in plans:
            seg = script.segments[p.index]
            caps = cap.timed(seg.narration, p.audio_seconds, load_alignment(Path(p.audio)))
            for f in range(p.frames):
                t = f / config.FPS
                c = cap.at(caps, t)
                img = render_frame(
                    seg,
                    ctx,
                    t,
                    p.seconds,
                    caption=c.text if c else "",
                    caption_k=progress(t, c.start, 0.12) if c else 1.0,
                )
                proc.stdin.write(img.tobytes())
            log(f"[frames] {p.index + 1}/{len(plans)} {p.type} ({p.frames} frames)")
        proc.stdin.close()
    except BrokenPipeError:
        pass
    err = proc.stderr.read().decode(errors="replace") if proc.stderr else ""
    if proc.wait() != 0:
        raise RenderError(f"ffmpeg encode failed: {err.strip()[-2000:]}")
    tmp.replace(out)

    manifest = {
        "id": script.id,
        "title": script.title,
        "voice": asdict(voice),
        "seconds": round(media.duration(out), 3),
        "render_seconds": round(time.time() - started, 1),
        "segments": [asdict(p) for p in plans],
        "sources": script.sources,
    }
    (render_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    log(f"[done]  {out} ({manifest['seconds']}s, rendered in {manifest['render_seconds']}s)")
    return out
