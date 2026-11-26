# whatif-sports

Automated pipeline for a faceless sports "What If" Shorts channel: idea → script → voice → visuals → captions → 9:16 MP4. Every idea and script gets a human review before publishing. See [CLAUDE.md](CLAUDE.md) for the full plan and content rules.

## Status

Milestone 1 is done: render a Short from a hand-written script YAML, fully offline.

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
.\.venv\Scripts\whatif render seahawks-xlix-run            # flite voice
.\.venv\Scripts\whatif render seahawks-xlix-run --voice sapi  # Windows voice, more natural
```

The output goes to `data/<id>/render/<id>.mp4`, next to a `manifest.json` that records segment timings, the voice used, and the sources. Audio is cached in `data/<id>/audio/`, keyed by a hash of the text.

A script can be an id (resolved from `data/<id>/script.yaml`, then `examples/<id>.yaml`) or a path to a YAML file.

## Layout

```
whatif_sports/
  script/    pydantic schema for the script YAML + loader
  voice/     TTS (flite via ffmpeg, Windows SAPI), cached by text hash
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
