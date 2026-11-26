"""ElevenLabs backend tests. The HTTP layer is mocked: no network, no credits spent."""

import base64
import io
import json
import urllib.error
import wave

import pytest

from whatif_sports import config, media
from whatif_sports.assemble import build
from whatif_sports.assemble import captions as cap
from whatif_sports.script import load_script
from whatif_sports.voice import Voice, elevenlabs, load_alignment, synthesize


def _has_ffmpeg() -> bool:
    try:
        config.ffmpeg()
        return True
    except FileNotFoundError:
        return False


needs_ffmpeg = pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not installed")


def _wav_bytes(seconds: float = 1.0, rate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(b"\x00\x10" * int(seconds * rate))
    return buf.getvalue()


def _alignment(text: str, per_char: float = 0.05) -> dict:
    return {
        "characters": list(text),
        "character_start_times_seconds": [i * per_char for i in range(len(text))],
        "character_end_times_seconds": [(i + 1) * per_char for i in range(len(text))],
    }


@pytest.fixture
def el_env(monkeypatch):
    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-key-not-real")
    monkeypatch.setenv("ELEVENLABS_VOICE_ID", "voice123")
    monkeypatch.delenv("WHATIF_TTS", raising=False)


@pytest.fixture
def fake_api(monkeypatch):
    calls = []

    def fake_post(url, payload, key, timeout=120):
        calls.append({"url": url, "payload": payload, "key": key})
        return json.dumps(
            {
                "audio_base64": base64.b64encode(_wav_bytes()).decode(),
                "alignment": _alignment(payload["text"]),
            }
        ).encode()

    monkeypatch.setattr(elevenlabs, "_post", fake_post)
    return calls


def test_backend_auto_selects_elevenlabs_when_configured(el_env):
    v = Voice.from_env()
    assert v.backend == "elevenlabs"
    assert v.name == "voice123"
    assert v.model == elevenlabs.DEFAULT_MODEL


def test_backend_falls_back_to_flite_without_key(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    monkeypatch.delenv("WHATIF_TTS", raising=False)
    assert Voice.from_env().backend == "flite"


def test_cache_key_covers_everything_that_changes_audio(el_env):
    v = Voice.from_env()
    base = v.cache_key("hello")
    assert v.cache_key("hello", previous_text="before") != base
    assert v.cache_key("hello", next_text="after") != base
    other_model = Voice("elevenlabs", v.name, model="eleven_flash_v2_5", settings=v.settings)
    assert other_model.cache_key("hello") != base
    slower = Voice("elevenlabs", v.name, model=v.model, settings=elevenlabs.Settings(speed=0.9))
    assert slower.cache_key("hello") != base


def test_missing_key_raises_clear_error(monkeypatch):
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    with pytest.raises(elevenlabs.ElevenLabsError, match="ELEVENLABS_API_KEY"):
        elevenlabs.tts("hi", "voice123")


@needs_ffmpeg
def test_synthesize_calls_api_once_then_uses_cache(el_env, fake_api, tmp_path):
    v = Voice.from_env()
    wav = synthesize("One yard to go.", v, tmp_path, "Super Bowl 49.", "Seattle has Lynch.")
    assert media.duration(wav) == pytest.approx(1.0, abs=0.05)
    assert len(fake_api) == 1
    call = fake_api[0]
    assert "/text-to-speech/voice123/with-timestamps" in call["url"]
    assert call["payload"]["previous_text"] == "Super Bowl 49."
    assert call["payload"]["next_text"] == "Seattle has Lynch."
    assert call["payload"]["model_id"] == elevenlabs.DEFAULT_MODEL
    assert load_alignment(wav)["characters"][0] == "O"

    again = synthesize("One yard to go.", v, tmp_path, "Super Bowl 49.", "Seattle has Lynch.")
    assert again == wav
    assert len(fake_api) == 1, "cached audio must not be re-billed"
    assert not list(tmp_path.glob("*.src.mp3")), "temporary download should be cleaned up"


def test_billable_characters_drops_to_zero_once_cached(el_env, fake_api, tmp_path):
    script = load_script("seahawks-xlix-run")
    v = Voice.from_env()
    total = sum(len(s.narration) for s in script.segments)
    assert build.billable_characters(script, v, tmp_path) == total
    if _has_ffmpeg():
        build.plan_segments(script, v, tmp_path)
        assert build.billable_characters(script, v, tmp_path) == 0
    assert build.billable_characters(script, Voice("flite", "rms"), tmp_path) == 0


def test_post_retries_on_rate_limit(monkeypatch):
    attempts = []

    class Resp(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        attempts.append(req)
        if len(attempts) == 1:
            raise urllib.error.HTTPError(
                req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b'{"detail": "slow down"}')
            )
        return Resp(b"ok")

    monkeypatch.setattr(elevenlabs.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(elevenlabs.time, "sleep", lambda s: None)
    assert elevenlabs._post("https://example.invalid/x", {"a": 1}, "k") == b"ok"
    assert len(attempts) == 2
    assert attempts[0].get_header("Xi-api-key") == "k"


def test_post_reports_bad_key_without_leaking_it(monkeypatch):
    def fake_urlopen(req, timeout=0):
        raise urllib.error.HTTPError(
            req.full_url,
            401,
            "Unauthorized",
            {},
            io.BytesIO(b'{"detail": {"message": "Invalid API key"}}'),
        )

    monkeypatch.setattr(elevenlabs.urllib.request, "urlopen", fake_urlopen)
    with pytest.raises(elevenlabs.ElevenLabsError) as e:
        elevenlabs._post("https://example.invalid/x", {}, "secret-key-123")
    assert "401" in str(e.value)
    assert "secret-key-123" not in str(e.value)


# --- caption timing from alignment ----------------------------------------------------
def test_captions_follow_character_timings():
    text = "Super Bowl 49. One yard to go."
    caps = cap.timed(text, 2.0, _alignment(text, per_char=0.05))
    assert [c.text for c in caps] == ["Super Bowl 49", "One yard to go"]
    assert caps[0].start == 0.0
    # "One" starts at character index 15 -> 0.75s
    assert caps[1].start == pytest.approx(15 * 0.05)
    assert caps[0].end == caps[1].start
    assert caps[-1].end == pytest.approx(2.0)


def test_captions_fall_back_when_alignment_does_not_match():
    text = "Super Bowl 49. One yard to go."
    caps = cap.timed(text, 2.0, _alignment("Something else entirely."))
    assert caps == cap.timed(text, 2.0)
