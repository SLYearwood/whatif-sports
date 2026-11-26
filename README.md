# whatif-sports

Automated pipeline for a faceless sports "What If" Shorts channel: idea → script → voice → visuals → captions → 9:16 MP4. Every idea and script gets a human review before publishing. See [CLAUDE.md](CLAUDE.md) for the full plan and content rules.

## Status

- Milestone 1 is done: render a Short from a hand-written script YAML, fully offline.
- Milestone 2 is done: ElevenLabs narration with a cache, so re-renders aren't billed again, and captions synced to the actual speech.

## Setup

Requires Python 3.11+ and an ffmpeg build with `libflite` (on Windows: `winget install Gyan.FFmpeg`).

```powershell
python -m venv .venv
.\.venv\Scripts\python -m pip install -e ".[dev]"
copy .env.example .env
```

## Usage

```powershell
.\.venv\Scripts\whatif validate seahawks-xlix-run
.\.venv\Scripts\whatif render seahawks-xlix-run                    # ElevenLabs if configured, else flite
.\.venv\Scripts\whatif render seahawks-xlix-run --voice flite      # force the offline voice
.\.venv\Scripts\whatif render seahawks-xlix-run --voice sapi       # Windows voice, offline
.\.venv\Scripts\whatif voices                                      # list ElevenLabs voice ids
```

The output goes to `data/<id>/render/<id>.mp4`, next to a `manifest.json` that records segment timings, the voice used, and the sources. Audio is cached in `data/<id>/audio/`, keyed by a hash of everything that affects the sound: text, voice, model, settings, and the neighbouring segments' text.

### ElevenLabs voice

1. In ElevenLabs, create a voice clone. Instant Voice Clone needs about 1–2 minutes of clean speech.
2. Put `ELEVENLABS_API_KEY` in `.env`, then run `whatif voices` and copy your clone's id into `ELEVENLABS_VOICE_ID`.
3. Run `whatif render <id>`. The log shows how many characters will be billed. Segments that are already cached cost nothing, and a render that would send more than `WHATIF_MAX_TTS_CHARS` (default 3000) is refused.

Each segment is sent along with the segments before and after it (`previous_text` / `next_text`), so the delivery flows across cuts. ElevenLabs returns per-character timings, and captions use them, so each caption appears exactly when its words are spoken.

A script can be an id (resolved from `data/<id>/script.yaml`, then `examples/<id>.yaml`) or a path to a YAML file.

## Layout

```
whatif_sports/
  script/    pydantic schema for the script YAML + loader
  voice/     TTS: ElevenLabs (with timestamps), flite via ffmpeg, Windows SAPI; hash-keyed cache
  visuals/   Pillow templates: title, stat, scoreboard, play_diagram, timeline, outro; plays.py
  assemble/  caption chunking/timing, narration mix, frame piping into ffmpeg
  cli.py     `whatif validate|render`
examples/    hand-written scripts
tests/
```

## Dev

```powershell
.\.venv\Scripts\python -m pytest
.\.venv\Scripts\ruff check .
.\.venv\Scripts\ruff format .
```
