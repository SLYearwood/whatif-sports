"""Narration audio."""

from whatif_sports.voice.elevenlabs import ElevenLabsError
from whatif_sports.voice.tts import (
    Voice,
    cache_path,
    is_cached,
    load_alignment,
    synthesize,
)

__all__ = ["ElevenLabsError", "Voice", "cache_path", "is_cached", "load_alignment", "synthesize"]
