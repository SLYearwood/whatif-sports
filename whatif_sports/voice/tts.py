"""Text-to-speech per segment, cached by a hash of (backend, voice, text).

Backends (choose with WHATIF_TTS):
  flite  ffmpeg's built-in libflite voice. Works anywhere ffmpeg has --enable-libflite.
  sapi   Windows built-in voices via System.Speech. Offline, sounds more natural.
ElevenLabs arrives in Milestone 2 behind the same `synthesize()` interface.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from whatif_sports import media

FLITE_VOICES = {"kal", "kal16", "awb", "rms", "slt"}


@dataclass(frozen=True)
class Voice:
    backend: str = "flite"
    name: str = "rms"
    rate: int = 1  # sapi only: -10..10

    @classmethod
    def from_env(cls) -> Voice:
        backend = os.environ.get("WHATIF_TTS", "flite").lower()
        if backend == "flite":
            name = os.environ.get("WHATIF_FLITE_VOICE", "rms")
            if name not in FLITE_VOICES:
                raise ValueError(
                    f"Unknown flite voice {name!r}; pick one of {sorted(FLITE_VOICES)}"
                )
            return cls("flite", name)
        if backend == "sapi":
            return cls(
                "sapi",
                os.environ.get("WHATIF_SAPI_VOICE", ""),
                int(os.environ.get("WHATIF_SAPI_RATE", "1")),
            )
        raise ValueError(f"Unknown WHATIF_TTS backend {backend!r} (use flite or sapi)")

    def cache_key(self, text: str) -> str:
        raw = f"{self.backend}|{self.name}|{self.rate}|{text}".encode()
        return hashlib.sha256(raw).hexdigest()[:16]


def synthesize(text: str, voice: Voice, cache_dir: Path) -> Path:
    """Return a 44.1 kHz mono WAV of `text`, reusing the cached file if it exists."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = voice.cache_key(text)
    out = cache_dir / f"{key}.wav"
    if out.exists() and out.stat().st_size > 0:
        return out
    txt = cache_dir / f"{key}.txt"
    txt.write_text(text, encoding="utf-8")
    raw = cache_dir / f"{key}.raw.wav"
    if voice.backend == "flite":
        # Run inside cache_dir so the filter argument is a bare filename (no drive-colon escaping).
        media.run_ffmpeg(
            ["-f", "lavfi", "-i", f"flite=textfile={txt.name}:voice={voice.name}", raw.name],
            cwd=cache_dir,
        )
    elif voice.backend == "sapi":
        _sapi(txt, raw, voice)
    else:  # pragma: no cover - guarded by Voice.from_env
        raise ValueError(voice.backend)
    # Normalize format; trim leading silence so the hook starts immediately.
    media.run_ffmpeg(
        [
            "-i",
            str(raw),
            "-af",
            "silenceremove=start_periods=1:start_threshold=-50dB,aresample=44100",
            "-ac",
            "1",
            "-c:a",
            "pcm_s16le",
            str(out),
        ]
    )
    raw.unlink(missing_ok=True)
    return out


def _sapi(txt: Path, out: Path, voice: Voice) -> None:
    ps = shutil.which("powershell") or shutil.which("pwsh")
    if not ps:
        raise RuntimeError("WHATIF_TTS=sapi needs Windows PowerShell")
    script = Path(__file__).with_name("sapi.ps1")
    args = [
        ps,
        "-NoProfile",
        "-NonInteractive",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(script),
        "-TextFile",
        str(txt),
        "-OutFile",
        str(out),
        "-Rate",
        str(voice.rate),
    ]
    if voice.name:
        args += ["-Voice", voice.name]
    proc = subprocess.run(args, capture_output=True, text=True)
    if proc.returncode != 0 or not out.exists():
        raise RuntimeError(f"SAPI TTS failed: {proc.stderr.strip()[-1000:]}")
