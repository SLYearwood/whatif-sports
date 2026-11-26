"""ElevenLabs text-to-speech (stdlib HTTP, no SDK).

Uses the `with-timestamps` endpoint, which returns the audio plus per-character start/end
times. Those timings drive caption sync. `previous_text` / `next_text` give the model the
neighbouring segments so the delivery flows across segment cuts.

The API key is read from the environment and is never logged or written to disk.
"""

from __future__ import annotations

import base64
import json
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass

API_ROOT = "https://api.elevenlabs.io/v1"
DEFAULT_MODEL = "eleven_multilingual_v2"
OUTPUT_FORMAT = "mp3_44100_128"  # available on every plan
MAX_RETRIES = 4


class ElevenLabsError(RuntimeError):
    pass


@dataclass(frozen=True)
class Settings:
    stability: float = 0.45
    similarity_boost: float = 0.8
    style: float = 0.15
    use_speaker_boost: bool = True
    speed: float = 1.05  # Shorts pacing; 0.7..1.2

    @classmethod
    def from_env(cls) -> Settings:
        def f(name: str, default: float) -> float:
            return float(os.environ.get(name, default))

        return cls(
            stability=f("ELEVENLABS_STABILITY", cls.stability),
            similarity_boost=f("ELEVENLABS_SIMILARITY", cls.similarity_boost),
            style=f("ELEVENLABS_STYLE", cls.style),
            speed=f("ELEVENLABS_SPEED", cls.speed),
        )

    def as_payload(self) -> dict:
        return {
            "stability": self.stability,
            "similarity_boost": self.similarity_boost,
            "style": self.style,
            "use_speaker_boost": self.use_speaker_boost,
            "speed": self.speed,
        }


@dataclass(frozen=True)
class Result:
    audio: bytes
    alignment: dict | None  # {"characters": [...], "character_start_times_seconds": [...], ...}


def _api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not key:
        raise ElevenLabsError("ELEVENLABS_API_KEY is not set. Add it to .env.")
    return key


def _post(url: str, payload: dict | None, key: str, timeout: float = 120) -> bytes:
    """POST JSON (GET when payload is None); retried on 429/5xx with backoff.

    Kept as one small function so tests can replace it.
    """
    body = json.dumps(payload).encode() if payload is not None else None
    for attempt in range(MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            data=body,
            method="POST" if body is not None else "GET",
            headers={
                "xi-api-key": key,
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            detail = _error_detail(e)
            if e.code in (429, 500, 502, 503, 504) and attempt < MAX_RETRIES:
                time.sleep(min(30, 2**attempt * 1.5))
                continue
            if e.code == 401:
                raise ElevenLabsError(f"ElevenLabs rejected the API key (401). {detail}") from None
            raise ElevenLabsError(f"ElevenLabs HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            if attempt < MAX_RETRIES:
                time.sleep(2**attempt)
                continue
            raise ElevenLabsError(f"Could not reach ElevenLabs: {e.reason}") from None
    raise ElevenLabsError("unreachable")  # pragma: no cover


def _error_detail(e: urllib.error.HTTPError) -> str:
    try:
        data = json.loads(e.read().decode(errors="replace"))
        detail = data.get("detail", data)
        if isinstance(detail, dict):
            return str(detail.get("message") or detail.get("status") or detail)
        return str(detail)
    except Exception:
        return e.reason or ""


def list_voices() -> list[dict]:
    data = json.loads(_post(f"{API_ROOT}/voices", None, _api_key()))
    return sorted(
        data.get("voices", []), key=lambda v: (v.get("category") != "cloned", v.get("name", ""))
    )


def tts(
    text: str,
    voice_id: str,
    model: str = DEFAULT_MODEL,
    settings: Settings | None = None,
    previous_text: str = "",
    next_text: str = "",
) -> Result:
    if not voice_id:
        raise ElevenLabsError("ELEVENLABS_VOICE_ID is not set. Add it to .env.")
    payload: dict = {
        "text": text,
        "model_id": model,
        "voice_settings": (settings or Settings()).as_payload(),
    }
    if previous_text:
        payload["previous_text"] = previous_text
    if next_text:
        payload["next_text"] = next_text
    url = f"{API_ROOT}/text-to-speech/{voice_id}/with-timestamps?output_format={OUTPUT_FORMAT}"
    raw = _post(url, payload, _api_key())
    try:
        data = json.loads(raw)
        audio = base64.b64decode(data["audio_base64"])
    except (ValueError, KeyError) as e:
        raise ElevenLabsError(f"Unexpected ElevenLabs response: {e}") from None
    return Result(audio=audio, alignment=data.get("alignment"))
