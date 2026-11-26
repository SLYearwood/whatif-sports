"""Text-to-speech per segment, cached by a hash of everything that affects the audio.

Backends (WHATIF_TTS; when unset, `elevenlabs` if its key + voice id are configured, else `flite`):
  elevenlabs  ElevenLabs API (Shawn's cloned voice). Returns character timings for captions.
  flite       ffmpeg's built-in libflite voice. Offline dev fallback.
  sapi        Windows built-in voices via System.Speech. Offline, more natural than flite.

Cached files live in the given cache dir as <key>.wav (+ <key>.align.json for ElevenLabs).
Re-rendering never re-bills: a cached key is reused as-is.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from whatif_sports import media
from whatif_sports.voice import elevenlabs

FLITE_VOICES = {"kal", "kal16", "awb", "rms", "slt"}
BACKENDS = ("elevenlabs", "flite", "sapi")


@dataclass(frozen=True)
class Voice:
    backend: str = "flite"
    name: str = "rms"  # flite voice, SAPI voice name, or ElevenLabs voice id
    rate: int = 1  # sapi only: -10..10
    model: str = ""  # elevenlabs only
    settings: elevenlabs.Settings | None = None  # elevenlabs only

    @classmethod
    def from_env(cls, backend: str | None = None) -> Voice:
        backend = (backend or os.environ.get("WHATIF_TTS") or _default_backend()).lower()
        if backend == "elevenlabs":
            return cls(
                "elevenlabs",
                os.environ.get("ELEVENLABS_VOICE_ID", "").strip(),
                model=os.environ.get("ELEVENLABS_MODEL", elevenlabs.DEFAULT_MODEL),
                settings=elevenlabs.Settings.from_env(),
            )
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
        raise ValueError(f"Unknown TTS backend {backend!r} (use one of {', '.join(BACKENDS)})")

    @property
    def label(self) -> str:
        if self.backend == "elevenlabs":
            return f"elevenlabs:{self.model}"
        return f"{self.backend}:{self.name or 'default'}"

    def cache_key(self, text: str, previous_text: str = "", next_text: str = "") -> str:
        parts = [self.backend, self.name, str(self.rate), text]
        if self.backend == "elevenlabs":
            settings = asdict(self.settings) if self.settings else {}
            parts += [self.model, json.dumps(settings, sort_keys=True), previous_text, next_text]
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _default_backend() -> str:
    if os.environ.get("ELEVENLABS_API_KEY") and os.environ.get("ELEVENLABS_VOICE_ID"):
        return "elevenlabs"
    return "flite"


def cache_path(
    text: str, voice: Voice, cache_dir: Path, previous_text: str = "", next_text: str = ""
) -> Path:
    return cache_dir / f"{voice.cache_key(text, previous_text, next_text)}.wav"


def is_cached(path: Path) -> bool:
    return path.exists() and path.stat().st_size > 0


def synthesize(
    text: str,
    voice: Voice,
    cache_dir: Path,
    previous_text: str = "",
    next_text: str = "",
) -> Path:
    """Return a 44.1 kHz mono WAV of `text`, reusing the cached file if it exists.

    previous_text/next_text are only used by ElevenLabs (for natural flow between segments).
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    out = cache_path(text, voice, cache_dir, previous_text, next_text)
    if is_cached(out):
        return out
    key = out.stem
    if voice.backend == "elevenlabs":
        result = elevenlabs.tts(
            text, voice.name, voice.model, voice.settings, previous_text, next_text
        )
        src = cache_dir / f"{key}.src.mp3"
        src.write_bytes(result.audio)
        if result.alignment:
            out.with_suffix(".align.json").write_text(
                json.dumps(result.alignment), encoding="utf-8"
            )
        # No silence trimming here: it would shift the character timings.
        _to_wav(src, out, trim_start=False)
        src.unlink(missing_ok=True)
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
    else:
        raise ValueError(voice.backend)
    # Trim leading silence so the hook starts immediately.
    _to_wav(raw, out, trim_start=True)
    raw.unlink(missing_ok=True)
    return out


def load_alignment(wav: Path) -> dict | None:
    """Character timings saved next to an ElevenLabs clip, if any."""
    p = Path(wav).with_suffix(".align.json")
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _to_wav(src: Path, out: Path, trim_start: bool) -> None:
    filters = "aresample=44100"
    if trim_start:
        filters = "silenceremove=start_periods=1:start_threshold=-50dB," + filters
    tmp = out.with_suffix(".tmp.wav")
    media.run_ffmpeg(["-i", str(src), "-af", filters, "-ac", "1", "-c:a", "pcm_s16le", str(tmp)])
    tmp.replace(out)  # atomic: a half-written file never looks cached


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
