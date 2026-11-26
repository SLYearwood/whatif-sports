import pytest

from whatif_sports import config, media
from whatif_sports.voice import Voice, synthesize


def _has_ffmpeg() -> bool:
    try:
        config.ffmpeg()
        return True
    except FileNotFoundError:
        return False


def test_cache_key_depends_on_voice_and_text():
    a, b = Voice("flite", "rms"), Voice("flite", "slt")
    assert a.cache_key("hi") != b.cache_key("hi")
    assert a.cache_key("hi") != a.cache_key("hi!")
    assert a.cache_key("hi") == Voice("flite", "rms").cache_key("hi")


def test_from_env_rejects_unknown(monkeypatch):
    monkeypatch.setenv("WHATIF_TTS", "robot")
    with pytest.raises(ValueError):
        Voice.from_env()


@pytest.mark.ffmpeg
@pytest.mark.skipif(not _has_ffmpeg(), reason="ffmpeg not installed")
def test_flite_synthesizes_and_caches(tmp_path):
    v = Voice("flite", "kal")
    wav = synthesize("One yard to go.", v, tmp_path)
    assert media.duration(wav) > 0.3
    mtime = wav.stat().st_mtime_ns
    assert synthesize("One yard to go.", v, tmp_path) == wav
    assert wav.stat().st_mtime_ns == mtime, "second call must hit the cache"
